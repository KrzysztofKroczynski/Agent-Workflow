## scan_for_secrets
> type: python

Scan Python source files for hardcoded secrets, dangerous patterns, and injection risks.

```python
def scan_for_secrets(ctx, src_dir: str) -> dict:
    import re
    from pathlib import Path

    patterns = [
        (r'[A-Z_]*(SECRET|PASSWORD|KEY|TOKEN)[A-Z_]*\s*=\s*["\'][^"\']{4,}["\']', "hardcoded secret"),
        (r'\beval\s*\(', "dangerous eval()"),
        (r'\bexec\s*\(', "dangerous exec()"),
        (r'subprocess\.[a-z_]+\([^)]*shell\s*=\s*True', "shell injection risk"),
        (r'pickle\.loads?\(', "unsafe pickle deserialisation"),
    ]

    findings = []
    for pyfile in Path(src_dir).rglob("*.py"):
        source = pyfile.read_text(encoding="utf-8")
        for pattern, description in patterns:
            if re.search(pattern, source):
                findings.append(f"{pyfile.name}: {description}")

    severity = "clean" if not findings else "high"
    return {"findings": findings, "severity": severity}
```
