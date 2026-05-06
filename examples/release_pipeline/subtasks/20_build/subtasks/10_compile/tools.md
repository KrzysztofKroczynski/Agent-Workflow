## check_syntax
> type: python

Validate Python syntax of all .py files in a directory using the AST parser. Returns a list of files that passed and any syntax errors found.

```python
def check_syntax(ctx, src_dir: str) -> dict:
    import ast
    from pathlib import Path

    passed = []
    errors = []

    for pyfile in sorted(Path(src_dir).rglob("*.py")):
        try:
            ast.parse(pyfile.read_text(encoding="utf-8"))
            passed.append(str(pyfile))
        except SyntaxError as e:
            errors.append(f"{pyfile.name}: {e}")

    return {"files_ok": passed, "syntax_errors": errors}
```
