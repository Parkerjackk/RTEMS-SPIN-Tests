# Trace Analysis Utilities (SPIN / Testbuilder)

This folder contains helper scripts to **analyze SPIN trace replays (`*.spn`)**, extract **scenario + coverage evidence**, and **select a subset of traces** for conversion into C tests using Testbuilder / `spin2test`.

These scripts are intentionally **test-engineering oriented**: they treat SPIN traces as execution artifacts that can be triaged, summarized, and sampled in a repeatable way.

---

## Folder / File Expectations

### Where traces come from

Typical workflow:

1. Generate trails + spn with:
   ```bash
   tb spin <model-name>
   ```

This produces (depending on your setup):
    - <model-name>/gen/<model-root>-<i>.spn
    - <model-name>/gen/<model-root>.pml<k>.trail

Supported Layouts:
    - model's main gen/ directory
    - a selection sandbox <model-name>/selected_gen/gen/

## Scripts
1. **spn-analysis.py**
    Parses *.spn fiels (SPIN -T replay output) and extracts:
      - Scenario classification: SndRcv, Send, Receive, etc.
      - Coverage flags: any cov_* variables discovered in state dumps
      - Error markers: e.g. error: invalid statement, cannot find trail file
      - Basic metadata: linecount, file name/index, presence/absence of round markers, etc.
    
    **Outputs**
      - traces.csv - one row per .spn file (primary input selection)
      - summary.json - aggregate counts (scenario, voverage hits, errors)
      - errors.csv - traces with detected error markers
    
    **Usage**
    From repo root:
   ```bash
   python3 analysis-scripts/spn-analysis.py <model-name>/gen --outdir <model-name>/analysis/output
   ```

    Functionality options: 
      -  Include only a subset:
   ```bash
   python3 analysis-scripts/spn-analysis.py <model-name>/gen --outdir <model-name>/analysis/output --limit 2000
   ```
      - Produce sparate errors-only export
   ```bash
   python3 analysis-scripts/spn-analysis.py <model-name>/gen --outdir <model-name>/analysis/output --write-errors
   ```

2. **select-traces**
    Two modes: 
      2.1 - Select by explicit indices (manual selection)
      Example:
      ```bash
      python3 analysis-scripts/select-traces.py \
      --model-dir <model-name> \
      --model-root <model-root> \
      --indices "2570,1285,0,3929,2571,4420,4469,491,516,542" \
      --clean
      ```
      Sample output:
      <model-name>/selected_gen/
        <model-root>.pml
        <model-root>-pre.h
        <model-root>-post.h
        <model-root>-run.h
        <model-root>-rfn.yml
        <model-root>.pml<k>.trail     (selected trails copied in)
        manifest.csv
        gen/
          <model-name>-0.spn
          <model-name>-1.spn
          ...

      ***Note: indices are renumbered contiguously in selected_gen/gen/ (manifest contains the mapping from origianl to new index)***

      2.2 - Select automatically from traces.csv (best for systematic sampling)
      Example:
      ```bash
      python3 analysis-scripts/select-traces.py \
        --from-csv <model-name>/analysis/output/traces.csv \
        --model-dir <model-name> \
        --model-root <model-root> \
        --per-scenario 3 \
        --per-flag 1 \
        --isolate

3. **Generating C tests**
    Testbuilder was extended in a backwards-compatible way to support generating tests only for selected traces (to avoid converting 1000s of traces).
      - Default behaviour
        ```bash 
        tb gentests <model-name>
        ```
      - Selected-only conversion:
        ```bash
        tb genselected <model-name>
        ```

  