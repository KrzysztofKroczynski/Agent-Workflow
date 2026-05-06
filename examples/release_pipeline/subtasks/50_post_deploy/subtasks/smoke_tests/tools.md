## run_smoke_checks
> type: python

Read a production manifest and run basic smoke checks to confirm the deployment is live.

```python
def run_smoke_checks(ctx, production_manifest_path: str) -> dict:
    import json
    from pathlib import Path

    manifest = json.loads(Path(production_manifest_path).read_text(encoding="utf-8"))

    checks = [
        ("app_is_live", manifest.get("status") == "live"),
        ("environment_is_production", manifest.get("environment") == "production"),
        ("version_present", bool(manifest.get("version"))),
    ]

    passed = [name for name, result in checks if result]
    failed = [name for name, result in checks if not result]

    return {
        "passed": passed,
        "failed": failed,
        "all_passed": len(failed) == 0,
    }
```
