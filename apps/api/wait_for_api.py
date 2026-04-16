#!/usr/bin/env python3
"""Wait for API server to be ready"""
import sys
import time
import urllib.request
import urllib.error

url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000/version"
max_attempts = int(sys.argv[2]) if len(sys.argv) > 2 else 30

for i in range(max_attempts):
    try:
        urllib.request.urlopen(url, timeout=2)
        print(f"API ready after {i+1} attempts!")
        sys.exit(0)
    except Exception:
        print(f"  wait {i+1}/{max_attempts}...")
        time.sleep(2)

print("ERROR: API not ready after timeout", file=sys.stderr)
sys.exit(1)
