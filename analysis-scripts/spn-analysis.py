#!/usr/bin/env python3
import argparse
import csv
import json
import re
from pathlib import Path
from collections import Counter, defaultdict

# --- Regex patterns (tune as needed for your log format) ---

RE_LOG_SCENARIO = re.compile(r"@@@\s*\d+\s+LOG\s+scenario\s+(\w+)")
RE_STATE_SCENARIO = re.compile(r"\bscenario\s*=\s*(\w+)\b")

# SPIN trace replay errors often look like: "37: error: invalid statement"
RE_TRACE_ERROR_LINE = re.compile(r"^\s*\d+:\s*error:\s*(.*)$", re.IGNORECASE | re.MULTILINE)

# Coverage flags appear in state dump as e.g. "cov_send_inv_id = 0"
RE_COV_ASSIGN = re.compile(r"\b(cov_[A-Za-z0-9_]+)\s*=\s*([01])\b")

# Other useful indicators
RE_ASSERT = re.compile(r"\bassert\(", re.IGNORECASE)
RE_CANNOT_FIND_TRAIL = re.compile(r"cannot\s+find\s+trail\s+file", re.IGNORECASE)
RE_VALID_END = re.compile(r"<valid end state>", re.IGNORECASE)

def read_text(p: Path) -> str:
    # spn files can be large; but typically still OK to read whole file.
    return p.read_text(errors="replace")

def detect_scenario(text: str) -> str:
    # Prefer explicit LOG scenario lines (your model prints these)
    m = RE_LOG_SCENARIO.search(text)
    if m:
        return m.group(1)

    # Fallback: scenario in state dump
    # Using last occurrence often matches final state snapshot
    all_m = list(RE_STATE_SCENARIO.finditer(text))
    if all_m:
        return all_m[-1].group(1)

    return "UNKNOWN"

def extract_coverage(text: str) -> dict:
    cov = {}
    # last assignment wins (final state dump is usually what you care about)
    for m in RE_COV_ASSIGN.finditer(text):
        cov[m.group(1)] = int(m.group(2))
    return cov

def extract_errors(text: str) -> list[str]:
    # Collect trace replay errors
    errs = [m.group(1).strip() for m in RE_TRACE_ERROR_LINE.finditer(text)]
    return errs

def file_line_count(p: Path) -> int:
    # fast-ish line count
    with p.open("rb") as f:
        return sum(1 for _ in f)

def analyze_file(p: Path) -> dict:
    text = read_text(p)
    scenario = detect_scenario(text)
    cov = extract_coverage(text)
    errors = extract_errors(text)

    return {
        "file": p.name,
        "path": str(p),
        "lines": file_line_count(p),
        "scenario": scenario,
        "has_valid_end_state": bool(RE_VALID_END.search(text)),
        "mentions_assert": bool(RE_ASSERT.search(text)),
        "cannot_find_trail": bool(RE_CANNOT_FIND_TRAIL.search(text)),
        "error_count": len(errors),
        "errors_sample": "; ".join(errors[:5]),
        "coverage": cov,
    }

def aggregate(results: list[dict]) -> dict:
    by_scenario = Counter(r["scenario"] for r in results)
    error_files = sum(1 for r in results if r["error_count"] > 0)
    cannot_find_trail_files = sum(1 for r in results if r["cannot_find_trail"])
    assert_mentions = sum(1 for r in results if r["mentions_assert"])

    # Coverage aggregates: how many files have each cov_* = 1
    cov_hits = Counter()
    for r in results:
        for k, v in r["coverage"].items():
            if v == 1:
                cov_hits[k] += 1

    # Coverage profile counts per scenario (useful for thesis tables)
    # profile key: scenario + sorted list of cov flags that are 1 (truncated to keep keys manageable)
    profile_counts = Counter()
    for r in results:
        ones = sorted([k for k, v in r["coverage"].items() if v == 1])
        # keep profile key short-ish
        key = (r["scenario"], tuple(ones))
        profile_counts[key] += 1

    top_profiles = [
        {"scenario": s, "cov_ones": list(c), "count": n}
        for (s, c), n in profile_counts.most_common(25)
    ]

    return {
        "total_files": len(results),
        "by_scenario": dict(by_scenario),
        "files_with_errors": error_files,
        "files_with_cannot_find_trail": cannot_find_trail_files,
        "files_mentioning_assert": assert_mentions,
        "coverage_hits": dict(cov_hits),
        "top_coverage_profiles": top_profiles,
    }

def write_csv(results: list[dict], out_csv: Path):
    # Collect superset of all coverage keys for stable columns
    cov_keys = sorted({k for r in results for k in r["coverage"].keys()})

    fieldnames = [
        "file", "lines", "scenario",
        "has_valid_end_state", "mentions_assert", "cannot_find_trail",
        "error_count", "errors_sample",
    ] + cov_keys

    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in results:
            row = {k: r.get(k) for k in fieldnames}
            for ck in cov_keys:
                row[ck] = r["coverage"].get(ck, 0)
            w.writerow(row)

def main():
    ap = argparse.ArgumentParser(description="Analyze SPIN -T .spn files for scenario/coverage/errors.")
    ap.add_argument("spn_dir", help="Directory containing .spn files (e.g., event-mgr/gen)")
    ap.add_argument("--glob", default="*.spn", help="Glob for spn files (default: *.spn)")
    ap.add_argument("--outdir", default="spn_analysis", help="Output directory (default: spn_analysis)")
    args = ap.parse_args()

    spn_dir = Path(args.spn_dir)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    files = sorted(spn_dir.glob(args.glob))
    if not files:
        raise SystemExit(f"No files matched {args.glob} in {spn_dir}")

    results = [analyze_file(p) for p in files]
    summ = aggregate(results)

    # outputs
    (outdir / "summary.json").write_text(json.dumps(summ, indent=2), encoding="utf-8")
    write_csv(results, outdir / "traces.csv")

    print(f"Wrote: {outdir/'summary.json'}")
    print(f"Wrote: {outdir/'traces.csv'}")
    print("Scenario counts:", summ["by_scenario"])
    print("Files with errors:", summ["files_with_errors"])

if __name__ == "__main__":
    main()