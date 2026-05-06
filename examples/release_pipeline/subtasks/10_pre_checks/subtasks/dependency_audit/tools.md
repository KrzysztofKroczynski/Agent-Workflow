## audit_dependencies
> type: python

Check a requirements.txt file for packages with known CVEs. Returns a list of vulnerabilities and a count of packages checked.

```python
def audit_dependencies(ctx, requirements_file: str) -> dict:
    from pathlib import Path

    known_vulnerable = {
        "flask": ("2.3.0", "2.3.2", "CVE-2023-30861"),
        "requests": ("2.28.0", "2.31.0", "CVE-2023-32681"),
        "pydantic": ("1.10.0", "1.10.13", "CVE-2024-3772"),
    }

    lines = Path(requirements_file).read_text(encoding="utf-8").splitlines()
    packages = [l.strip() for l in lines if l.strip() and not l.startswith("#")]
    vulnerabilities = []

    for pkg in packages:
        if "==" in pkg:
            name, version = pkg.split("==", 1)
            name = name.strip().lower()
            version = version.strip()
            if name in known_vulnerable:
                vuln_ver, fix_ver, cve = known_vulnerable[name]
                if version == vuln_ver:
                    vulnerabilities.append(
                        f"{name}=={version}: {cve} — upgrade to >={fix_ver}"
                    )

    return {"packages_checked": len(packages), "vulnerabilities": vulnerabilities}
```
