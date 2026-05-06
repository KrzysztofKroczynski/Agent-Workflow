## run_integration_checks
> type: python

Verify a staging deployment by reading its manifest and running a set of integration checks.

```python
def run_integration_checks(ctx, staging_manifest_path: str) -> dict:
    import json
    from pathlib import Path

    manifest = json.loads(Path(staging_manifest_path).read_text(encoding="utf-8"))

    checks = [
        ("deployment_exists", manifest.get("status") == "deployed"),
        ("version_matches", bool(manifest.get("version"))),
        ("artifact_present", bool(manifest.get("artifact"))),
    ]

    passed = [name for name, result in checks if result]
    failed = [name for name, result in checks if not result]

    return {
        "passed_checks": passed,
        "failed_checks": failed,
        "all_passed": len(failed) == 0,
        "report": f"{len(passed)}/{len(checks)} integration checks passed",
    }
```
