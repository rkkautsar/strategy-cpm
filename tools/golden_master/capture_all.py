# tools/golden_master/capture_all.py
import argparse
import os
import shutil
import subprocess
import sys
import tempfile

def main():
    parser = argparse.ArgumentParser(description="Generate a full set of candidate golden master artifacts.")
    parser.add_argument("--out", required=True, help="Output directory for candidate artifacts")
    args = parser.parse_args()

    out_dir = os.path.abspath(args.out)
    os.makedirs(out_dir, exist_ok=True)

    py_exe = sys.executable
    gm_dir = os.path.dirname(os.path.abspath(__file__))
    run_with_frozen = os.path.join(gm_dir, "run_with_frozen_date.py")

    run_tmpdir = tempfile.mkdtemp(prefix="gm_cap_")
    run_env = os.environ.copy()
    run_env["TMPDIR"] = run_tmpdir
    print(f"Using isolated TMPDIR for this capture run: {run_tmpdir}")

    # 1. Run dump_streams.py
    print("Generating numeric streams (dump_streams.py)... ")
    cmd_streams = [
        py_exe, run_with_frozen,
        os.path.join(gm_dir, "dump_streams.py"),
        "--end", "2026-04-30",
        "--out", out_dir
    ]
    res = subprocess.run(cmd_streams, capture_output=True, text=True, env=run_env)
    if res.returncode != 0:
        print("ERROR in dump_streams.py:")
        print(res.stdout)
        print(res.stderr)
        sys.exit(res.returncode)

    # 2. Run cpm_live.py allocate -> allocate.txt
    print("Generating allocate.txt... ")
    cmd_alloc = [
        py_exe, run_with_frozen,
        "cpm_live.py", "allocate"
    ]
    # monthly-signal.yml merges stderr with 2>&1
    res = subprocess.run(cmd_alloc, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=run_env)
    if res.returncode != 0:
        print("ERROR in cpm_live.py allocate:")
        print(res.stdout)
        sys.exit(res.returncode)
    with open(os.path.join(out_dir, "allocate.txt"), "w", encoding="utf-8") as f:
        f.write(res.stdout)

    # 3. Run format_message.py -> format_message.txt
    print("Generating format_message.txt... ")
    cmd_msg = [
        py_exe, run_with_frozen,
        "deploy/cf-pages/format_message.py"
    ]
    res = subprocess.run(cmd_msg, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=run_env)
    if res.returncode != 0:
        print("ERROR in format_message.py:")
        print(res.stdout)
        print(res.stderr)
        sys.exit(res.returncode)
    with open(os.path.join(out_dir, "format_message.txt"), "w", encoding="utf-8") as f:
        f.write(res.stdout)

    # 4. Run build_dashboard.py -> copy cpm_dashboard.html
    print("Generating cpm_dashboard.html... ")
    cmd_dash = [
        py_exe, run_with_frozen,
        "build_dashboard.py",
        "--end", "2026-04-30"
    ]
    res = subprocess.run(cmd_dash, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=run_env)
    if res.returncode != 0:
        print("ERROR in build_dashboard.py:")
        print(res.stdout)
        print(res.stderr)
        sys.exit(res.returncode)

    dash_src = "cpm_dashboard.html"
    if os.path.exists(dash_src):
        shutil.copy(dash_src, os.path.join(out_dir, "cpm_dashboard.html"))
        print(f"Copied {dash_src} to {out_dir}")
    else:
        print(f"WARNING: {dash_src} not found in CWD!")

    print(f"Successfully generated all golden-master candidate artifacts in {out_dir}")

if __name__ == '__main__':
    main()
