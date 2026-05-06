## run_pytest
> type: python

Run pytest on a test directory. Returns exit code, output, and whether all tests passed.

```python
def run_pytest(ctx, test_dir: str) -> dict:
    import subprocess
    import sys
    from pathlib import Path

    test_path = Path(test_dir)
    project_root = str(test_path.parent)
    result = subprocess.run(
        [sys.executable, "-m", "pytest", test_path.name, "--tb=short", "-q"],
        capture_output=True,
        text=True,
        cwd=project_root,
    )
    output = (result.stdout + result.stderr).strip()
    return {
        "exit_code": result.returncode,
        "output": output[-2000:],
        "passed": result.returncode == 0,
    }
```
