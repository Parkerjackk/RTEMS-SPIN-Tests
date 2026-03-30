#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause

from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set


SPN_NAME_RE = re.compile(r"^(?P<root>.+)-(?P<idx>\d+)\.spn$")
TRAIL_NAME_RE = re.compile(r"^(?P<root>.+)\.pml(?P<trailno>\d+)\.trail$")

# Common patterns seen in SPIN replay outputs that can reveal the trail number
# We’ll search the spn text for these and fall back if not found.
TRAILNO_PATTERNS = [
    re.compile(r"\bspin\s+-t(\d+)\b"),             # "spin -t518"
    re.compile(r"\.pml(\d+)\.trail\b"),            # "event-mgr.pml518.trail"
    re.compile(r"\btrail\s*file\s*:\s*\S*?(\d+)\.trail\b", re.IGNORECASE),
]


@dataclass(frozen=True)
class TraceRow:
    index: int
    spn_file: str
    scenario: str
    line_count: int
    errors: str
    cov_flags: Dict[str, int]


def parse_cov_flags_from_row(row: Dict[str, str]) -> Dict[str, int]:
    cov: Dict[str, int] = {}
    if "cov_flags" in row and row["cov_flags"].strip():
        try:
            obj = json.loads(row["cov_flags"])
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if k.startswith("cov_"):
                        cov[k] = 1 if str(v) in ("1", "true", "True") else 0
        except Exception:
            pass
    for k, v in row.items():
        if k.startswith("cov_"):
            cov[k] = 1 if str(v).strip() in ("1", "true", "True") else 0
    return cov


def load_traces_csv(csv_path: Path) -> List[TraceRow]:
    out: List[TraceRow] = []
    with csv_path.open("r", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            spn = r.get("spn_file") or r.get("file") or ""
            idx_s = r.get("index") or ""
            scenario = r.get("scenario") or "UNKNOWN"
            lc_s = r.get("line_count") or r.get("lines") or "0"
            errors = r.get("errors") or ""

            try:
                idx = int(idx_s)
            except Exception:
                m = SPN_NAME_RE.match(Path(spn).name)
                if not m:
                    continue
                idx = int(m.group("idx"))

            try:
                lc = int(lc_s)
            except Exception:
                lc = 0

            out.append(
                TraceRow(
                    index=idx,
                    spn_file=spn,
                    scenario=scenario,
                    line_count=lc,
                    errors=errors,
                    cov_flags=parse_cov_flags_from_row(r),
                )
            )
    return out


def pick_evenly_spaced(items: List[int], n: int) -> List[int]:
    items = sorted(items)
    if n <= 0 or not items:
        return []
    if len(items) <= n:
        return items
    if n == 1:
        return [items[len(items) // 2]]
    picked = [items[0]]
    for k in range(1, n - 1):
        pos = round(k * (len(items) - 1) / (n - 1))
        picked.append(items[pos])
    picked.append(items[-1])
    # de-dup
    out: List[int] = []
    seen: Set[int] = set()
    for x in picked:
        if x not in seen:
            out.append(x)
            seen.add(x)
    return out


def select_from_csv(rows: List[TraceRow], per_scenario: int, per_flag: int, skip_errors: bool) -> List[int]:
    filtered = [r for r in rows if not (skip_errors and r.errors.strip())]

    # 1) per scenario: evenly spaced by line_count
    by_scenario: Dict[str, List[TraceRow]] = {}
    for r in filtered:
        by_scenario.setdefault(r.scenario or "UNKNOWN", []).append(r)

    selected: Set[int] = set()
    for scen, scen_rows in by_scenario.items():
        scen_rows_sorted = sorted(scen_rows, key=lambda x: (x.line_count, x.index))
        idxs = [r.index for r in scen_rows_sorted]
        for picked in pick_evenly_spaced(idxs, per_scenario):
            selected.add(picked)

    # 2) per flag: rare-first
    freq: Dict[str, int] = {}
    for r in filtered:
        for k, v in r.cov_flags.items():
            if v == 1:
                freq[k] = freq.get(k, 0) + 1

    flags_by_rarity = sorted(freq.items(), key=lambda kv: (kv[1], kv[0]))
    for flag, _ in flags_by_rarity:
        hitters = [r for r in filtered if r.cov_flags.get(flag, 0) == 1]
        hitters_sorted = sorted(hitters, key=lambda x: (x.line_count, x.index))
        for r in hitters_sorted[: max(0, per_flag)]:
            selected.add(r.index)

    return sorted(selected)


def parse_indices_arg(s: str) -> List[int]:
    idxs = []
    for part in s.split(","):
        part = part.strip()
        if part:
            idxs.append(int(part))
    return sorted(set(idxs))


def extract_trailno_from_spn(spn_path: Path) -> Optional[int]:
    try:
        text = spn_path.read_text(errors="ignore")
    except Exception:
        return None

    for pat in TRAILNO_PATTERNS:
        m = pat.search(text)
        if m:
            try:
                return int(m.group(1))
            except Exception:
                pass
    return None


def copy_support_files(model_dir: Path, dest_root: Path, model_root: str) -> None:
    dest_root.mkdir(parents=True, exist_ok=True)
    candidates = [
        f"{model_root}.pml",
        f"{model_root}-pre.h",
        f"{model_root}-post.h",
        f"{model_root}-run.h",
        f"{model_root}-rfn.yml",
    ]
    for name in candidates:
        src = model_dir / name
        if src.exists():
            shutil.copy2(src, dest_root / name)


def stage_selected_copy_only(
    model_dir: Path,
    model_root: str,
    selected_indices: List[int],
    source_gen: Path,
    dest: Path,
    isolate: bool,
) -> None:
    """
    Backwards compatible:
      - NEVER modifies source_gen.
      - Copies selected spn into dest/gen (renumbered contiguously).
      - Copies only the matched trails (by parsing trail number from spn).
    """
    dest = dest.resolve()
    dest_gen = dest / "gen"

    if isolate and dest.exists():
        shutil.rmtree(dest)
    dest_gen.mkdir(parents=True, exist_ok=True)

    copy_support_files(model_dir, dest, model_root)

    manifest_rows: List[Dict[str, str]] = []
    selected_files_txt: List[str] = []

    for new_i, old_i in enumerate(selected_indices):
        spn_src = source_gen / f"{model_root}-{old_i}.spn"
        if not spn_src.exists():
            raise FileNotFoundError(f"Missing SPN: {spn_src}")

        spn_dst = dest_gen / f"{model_root}-{new_i}.spn"
        shutil.copy2(spn_src, spn_dst)
        selected_files_txt.append(spn_dst.name)

        trailno = extract_trailno_from_spn(spn_src)
        trail_src = None
        if trailno is not None:
            candidate = source_gen / f"{model_root}.pml{trailno}.trail"
            if candidate.exists():
                trail_src = candidate

        if trail_src is not None:
            shutil.copy2(trail_src, dest / trail_src.name)

        manifest_rows.append({
            "selected_index": str(new_i),
            "original_index": str(old_i),
            "spn_file": spn_dst.name,
            "trailno_from_spn": "" if trailno is None else str(trailno),
            "trail_copied": "" if trail_src is None else trail_src.name,
        })

    (dest / "selected_files.txt").write_text("\n".join(selected_files_txt) + "\n")

    with (dest / "manifest.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["selected_index", "original_index", "spn_file", "trailno_from_spn", "trail_copied"])
        w.writeheader()
        w.writerows(manifest_rows)

    report = {
        "model_root": model_root,
        "model_dir": str(model_dir),
        "source_gen": str(source_gen),
        "dest": str(dest),
        "isolate": bool(isolate),
        "selected_count": len(selected_indices),
        "selected_original_indices": selected_indices,
        "note": "Copy-only selection: source gen/ untouched. SPNs renumbered contiguously in selected_gen/gen; see manifest.csv. Trails copied only when mapping is found in SPN.",
    }
    (dest / "selected_report.json").write_text(json.dumps(report, indent=2) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model-dir", required=True, help="e.g. event-mgr")
    ap.add_argument("--model-root", required=True, help="e.g. event-mgr")
    ap.add_argument("--indices", help="Comma-separated spn indices, e.g. '0,5,10'")
    ap.add_argument("--from-csv", dest="from_csv", help="Path to traces.csv from spn-analysis.py")
    ap.add_argument("--per-scenario", type=int, default=3)
    ap.add_argument("--per-flag", type=int, default=1)
    ap.add_argument("--skip-errors", action="store_true")
    ap.add_argument("--source-gen", default="gen", help="Source gen directory relative to model-dir (default: gen)")
    ap.add_argument("--dest", default="selected_gen", help="Destination directory relative to model-dir (default: selected_gen)")
    ap.add_argument("--isolate", action="store_true", help="Delete and rebuild dest/ before copying (safe; does not touch gen/)")
    args = ap.parse_args()

    model_dir = Path(args.model_dir).resolve()
    model_root = args.model_root
    source_gen = (model_dir / args.source_gen).resolve()
    dest = (model_dir / args.dest).resolve()

    if not source_gen.exists():
        raise FileNotFoundError(f"Source gen directory does not exist: {source_gen}")

    if args.from_csv:
        rows = load_traces_csv(Path(args.from_csv))
        selected_indices = select_from_csv(rows, args.per_scenario, args.per_flag, args.skip_errors)
        if not selected_indices:
            raise SystemExit("No traces selected from CSV (check filters / CSV content).")
    else:
        if not args.indices:
            ap.error("one of --indices or --from-csv is required")
        selected_indices = parse_indices_arg(args.indices)

    stage_selected_copy_only(
        model_dir=model_dir,
        model_root=model_root,
        selected_indices=selected_indices,
        source_gen=source_gen,
        dest=dest,
        isolate=args.isolate,
    )

    print(f"Selected {len(selected_indices)} traces into: {dest}")
    print(f"SPNs in: {dest/'gen'}")
    print("Mapping in: manifest.csv")


if __name__ == "__main__":
    main()