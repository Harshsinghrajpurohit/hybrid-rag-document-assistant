#!/usr/bin/env python
"""
Run Phase 3 tests and capture results
"""
import subprocess
import sys

print("=" * 80)
print("PHASE 3: RUNNING FULL TEST SUITE")
print("=" * 80)

result = subprocess.run(
    [sys.executable, "-m", "pytest", "tests/test_retriever.py", "-v", "--tb=line"],
    capture_output=True,
    text=True,
    timeout=600
)

# Get last 80 lines of output
lines = result.stdout.split('\n')
for line in lines[-80:]:
    print(line)

print(f"\nExit code: {result.returncode}")

# Count results
if "passed" in result.stdout:
    import re
    match = re.search(r'(\d+) passed', result.stdout)
    if match:
        print(f"Tests passed: {match.group(1)}")

sys.exit(result.returncode)
