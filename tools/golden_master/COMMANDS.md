# Golden-Master Safety Harness COMMANDS

This directory contains the golden-master safety validation harness for strategy_cpm.
It ensures that any optimization, refactoring, or performance speedup changes do not alter any math, records, or outputs.

---

## 1. Quick Verification (Two Commands)

To verify your performance changes or refactors:

### Command 1: Generate candidate artifacts from your branch
```bash
PYTHONPATH=. .venv/bin/python3 tools/golden_master/capture_all.py --out /tmp/gm/verify
```

### Command 2: Validate candidates against committed baseline hashes
```bash
PYTHONPATH=. .venv/bin/python3 tools/golden_master/validate.py --cand /tmp/gm/verify
```

---

## 2. Validation Options

### A. Compare against committed lightweight reference hashes (Default)
This compares all deterministic CSV, JSON, TXT, and masked HTML artifacts against the lightweight, version-controlled `baseline_hashes.json`:
```bash
PYTHONPATH=. .venv/bin/python3 tools/golden_master/validate.py --cand /tmp/gm/verify
```

### B. Deep Directory-to-Directory Comparison (Optional)
If you have a local copy of the raw baseline files, you can perform a deep file-to-file comparison (which also checks parquet binaries via pandas):
```bash
PYTHONPATH=. .venv/bin/python3 tools/golden_master/validate.py --cand /tmp/gm/verify --base /tmp/gm/baseline
```

---

## 3. Expected Successful Outputs

When all artifacts match identically, the validation script output looks like this:

```
Performing validation against hashes: tools/golden_master/baseline_hashes.json vs cand=/tmp/gm/verify

--- Validation Report ---
MATCH: allocate.txt
MATCH: blend.csv
MATCH: blend_uncapped.csv
MATCH: bull_cc.csv
MATCH: cpm_cc.csv
MATCH: cpm_dashboard.html
MATCH: cpm_mooex.csv
MATCH: cpm_records.json
MATCH: format_message.txt
MATCH: mooex_coverage.json
MATCH: ndx_cc.csv
MATCH: ndx_mooex.csv
MATCH: ndx_records.json
MATCH: rpv_cc.csv
MATCH: rpv_mooex.csv
MATCH: rpv_records.json
MATCH: val_mooex.csv
MATCH: val_records.json

VALIDATION PASSED: All artifact classes are 100% identical!
```
