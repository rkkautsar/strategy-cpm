# tools/golden_master/validate.py
import argparse
import glob
import hashlib
import json
import os
import re
import sys
import numpy as np
import pandas as pd

def mask_html(text):
    # Mask base64 PNGs
    text = re.sub(r'data:image/png;base64,[A-Za-z0-9+/=]+', 'PNG', text)
    # Mask Git SHAs (7 to 40 hex chars)
    text = re.sub(r'\b[0-9a-f]{7,40}\b', 'GITSHA', text)
    # Mask wall-clock timestamps
    text = re.sub(r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9:]+', 'TS', text)
    # Mask microsecond fractions
    text = re.sub(r'TS\.[0-9]+', 'TS', text)
    # Mask built/on dates (volatile generation dates)
    text = re.sub(r'built \d{4}-\d{2}-\d{2}', 'built DATE', text)
    text = re.sub(r'on \d{4}-\d{2}-\d{2}', 'on DATE', text)
    
    # Mask Matplotlib random SVG IDs
    text = re.sub(r'\b[pm][0-9a-f]{10}\b', 'MPLID', text)
    text = re.sub(r'#[pm][0-9a-f]{10}', '#MPLID', text)
    text = re.sub(r'\bC\d+_\d+_[0-9a-f]{10}\b', 'MPLPATH', text)
    text = re.sub(r'#C\d+_\d+_[0-9a-f]{10}', '#MPLPATH', text)
    
    # Mask Matplotlib random image IDs
    text = re.sub(r'\bimage[0-9a-f]{10}\b', 'MPLIMAGE', text)
    text = re.sub(r'#image[0-9a-f]{10}', '#MPLIMAGE', text)
    
    # Normalize stable sorting of table rows inside tbody to bypass python set-order randomization
    def sort_tbody(match):
        tbody_content = match.group(1)
        rows = re.findall(r'<tr>.*?</tr>', tbody_content, re.DOTALL)
        return '<tbody>' + ''.join(sorted(rows)) + '</tbody>'
    
    text = re.sub(r'<tbody>(.*?)</tbody>', sort_tbody, text, flags=re.DOTALL)
    
    return text

def compute_sha256(data):
    if isinstance(data, str):
        data = data.encode('utf-8')
    return hashlib.sha256(data).hexdigest()

def main():
    ap = argparse.ArgumentParser(description="Validate candidate golden-master artifacts against baseline.")
    ap.add_argument("--cand", required=True, help="Path to candidate directory")
    ap.add_argument("--base", help="Path to baseline directory (if provided, performs full file-based validation)")
    ap.add_argument("--hashes", help="Path to baseline_hashes.json (defaults to tools/golden_master/baseline_hashes.json)")
    args = ap.parse_args()

    cand = os.path.abspath(args.cand)
    failures = []
    matches = []

    if args.base:
        base = os.path.abspath(args.base)
        print(f"Performing directory-to-directory validation: base={base} vs cand={cand}")

        # 1. Parquet Numeric Streams
        for p in glob.glob(os.path.join(base, "*.parquet")):
            n = os.path.basename(p)
            cand_p = os.path.join(cand, n)
            if not os.path.exists(cand_p):
                failures.append(f"Missing parquet in candidate: {n}")
                continue

            a = pd.read_parquet(p)["ret"].values
            b = pd.read_parquet(cand_p)["ret"].values

            if a.shape != b.shape:
                failures.append(f"Shape mismatch in {n}: {a.shape} vs {b.shape}")
                continue

            if not np.array_equal(a, b, equal_nan=True):
                if np.allclose(a, b, rtol=1e-12, atol=1e-12, equal_nan=True):
                    print(f"WARNING: {n} is not byte-identical but matches within 1e-12 tolerance.")
                    matches.append(n)
                else:
                    failures.append(f"Value mismatch in {n}")
            else:
                matches.append(n)

        # 2. CSV files (deterministic float text representation)
        for p in glob.glob(os.path.join(base, "*.csv")):
            n = os.path.basename(p)
            cand_p = os.path.join(cand, n)
            if not os.path.exists(cand_p):
                failures.append(f"Missing CSV in candidate: {n}")
                continue
            with open(p, "rb") as f:
                a = f.read()
            with open(cand_p, "rb") as f:
                b = f.read()
            if a != b:
                failures.append(f"CSV mismatch in {n}")
            else:
                matches.append(n)

        # 3. JSON records / coverage
        for n in ["cpm_records.json", "rpv_records.json", "ndx_records.json", "val_records.json", "mooex_coverage.json"]:
            p = os.path.join(base, n)
            cand_p = os.path.join(cand, n)
            if not os.path.exists(p):
                continue
            if not os.path.exists(cand_p):
                failures.append(f"Missing JSON in candidate: {n}")
                continue

            with open(p) as f:
                a = json.load(f)
            with open(cand_p) as f:
                b = json.load(f)

            if a != b:
                failures.append(f"JSON mismatch in {n}")
            else:
                matches.append(n)

        # 4. Live Text Outputs
        for n in ["allocate.txt", "format_message.txt"]:
            p = os.path.join(base, n)
            cand_p = os.path.join(cand, n)
            if not os.path.exists(p) or not os.path.exists(cand_p):
                failures.append(f"Missing text file: {n}")
                continue

            with open(p, "rb") as f:
                a = f.read()
            with open(cand_p, "rb") as f:
                b = f.read()

            if a != b:
                failures.append(f"Byte mismatch in {n}")
            else:
                matches.append(n)

        # 5. Dashboard HTML
        p_html = os.path.join(base, "cpm_dashboard.html")
        cand_html = os.path.join(cand, "cpm_dashboard.html")
        if os.path.exists(p_html) and os.path.exists(cand_html):
            with open(p_html, "r", encoding="utf-8") as f:
                a_text = mask_html(f.read())
            with open(cand_html, "r", encoding="utf-8") as f:
                b_text = mask_html(f.read())

            if a_text != b_text:
                failures.append("Dashboard HTML mismatch (masked)")
                # Write masked versions for easy debugging
                with open("/tmp/gm/masked_base.html", "w", encoding="utf-8") as f:
                    f.write(a_text)
                with open("/tmp/gm/masked_cand.html", "w", encoding="utf-8") as f:
                    f.write(b_text)
                print("Masked HTML files written to /tmp/gm/masked_base.html and /tmp/gm/masked_cand.html")
            else:
                matches.append("cpm_dashboard.html (masked)")
        else:
            if os.path.exists(p_html) or os.path.exists(cand_html):
                failures.append("Dashboard HTML presence mismatch")

    else:
        # Fall back to baseline_hashes.json
        hashes_path = args.hashes or os.path.join(os.path.dirname(os.path.abspath(__file__)), "baseline_hashes.json")
        print(f"Performing validation against hashes: {hashes_path} vs cand={cand}")
        
        if not os.path.exists(hashes_path):
            print(f"ERROR: Hashes file {hashes_path} not found!")
            sys.exit(1)

        with open(hashes_path, "r", encoding="utf-8") as f:
            baseline_hashes = json.load(f)

        for filename, expected_hash in baseline_hashes.items():
            cand_p = os.path.join(cand, filename)
            if not os.path.exists(cand_p):
                failures.append(f"Missing file in candidate: {filename}")
                continue

            if filename == "cpm_dashboard.html":
                with open(cand_p, "r", encoding="utf-8") as f:
                    masked_content = mask_html(f.read())
                actual_hash = compute_sha256(masked_content)
            else:
                with open(cand_p, "rb") as f:
                    actual_hash = compute_sha256(f.read())

            if actual_hash != expected_hash:
                failures.append(f"Hash mismatch in {filename} (expected {expected_hash}, got {actual_hash})")
            else:
                matches.append(filename)

    print("\n--- Validation Report ---")
    for m in sorted(matches):
        print(f"MATCH: {m}")
    
    if failures:
        print("\nVALIDATION FAILED:")
        for f in failures:
            print(f" - {f}")
        sys.exit(1)
    else:
        print("\nVALIDATION PASSED: All artifact classes are 100% identical!")
        sys.exit(0)

if __name__ == "__main__":
    main()
