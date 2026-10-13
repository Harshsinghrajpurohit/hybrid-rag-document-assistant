"""
Run Phase 3 tests and display results clearly
"""
import subprocess
import sys

print("=" * 80)
print("PHASE 3: HYBRID RETRIEVER - RUNNING FULL TEST SUITE")
print("=" * 80)

result = subprocess.run(
    [sys.executable, "-m", "pytest", "tests/test_retriever.py", "-v", "--tb=short"],
    capture_output=True,
    text=True,
    timeout=600
)

# Print output
print(result.stdout)
if result.stderr:
    print("STDERR:", result.stderr)

# Parse results
lines = result.stdout.split('\n')
for line in lines[-30:]:
    print(line)

# Exit code
print(f"\nExit code: {result.returncode}")
sys.exit(result.returncode)
