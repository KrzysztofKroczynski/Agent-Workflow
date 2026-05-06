## run_lint
> type: python

Scan Python source files for style and quality issues. Returns a list of issues found and a count of files checked.

```python
def run_lint(ctx, src_dir: str) -> dict:
    import ast
    import re
    from pathlib import Path

    issues = []
    py_files = list(Path(src_dir).rglob("*.py"))

    for pyfile in py_files:
        source = pyfile.read_text(encoding="utf-8")
        name = pyfile.name

        # Check for hardcoded secrets
        if re.search(r'(SECRET|PASSWORD|API_KEY|TOKEN)\s*=\s*["\'][^"\']{4,}["\']', source):
            issues.append(f"{name}: possible hardcoded secret")

        # Check syntax
        try:
            ast.parse(source)
        except SyntaxError as e:
            issues.append(f"{name}: syntax error — {e}")

        # Check style: missing space after comma in function signatures
        for i, line in enumerate(source.splitlines(), 1):
            if re.search(r"def \w+\([^)]*,[^ )]", line):
                issues.append(f"{name}:{i}: missing space after comma in function signature")

        # Check for bare except
        for i, line in enumerate(source.splitlines(), 1):
            if line.strip() == "except:":
                issues.append(f"{name}:{i}: bare except clause")

    return {"files_checked": len(py_files), "issues": issues}
```
