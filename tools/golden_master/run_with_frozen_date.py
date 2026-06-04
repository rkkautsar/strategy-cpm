import sys
import runpy
import pandas as pd
import socket

# Block network at socket level (force offline execution)
_orig_connect = socket.socket.connect
_orig_connect_ex = socket.socket.connect_ex

def patched_connect(self, address):
    host = address[0]
    if host not in ("127.0.0.1", "localhost"):
        raise OSError("Network access blocked by safety harness")
    return _orig_connect(self, address)

def patched_connect_ex(self, address):
    host = address[0]
    if host not in ("127.0.0.1", "localhost"):
        return 111  # ECONNREFUSED
    return _orig_connect_ex(self, address)

socket.socket.connect = patched_connect
socket.socket.connect_ex = patched_connect_ex

FROZEN_DATE = "2026-05-01"

# Freeze pandas today and now
pd.Timestamp.today = lambda *args, **kwargs: pd.Timestamp(FROZEN_DATE)
pd.Timestamp.now = lambda *args, **kwargs: pd.Timestamp(FROZEN_DATE)

if len(sys.argv) < 2:
    print("Usage: run_with_frozen_date.py <script.py> [args...]")
    sys.exit(1)

script_path = sys.argv[1]
# Adjust sys.argv for the target script
sys.argv = sys.argv[1:]

runpy.run_path(script_path, run_name='__main__')
