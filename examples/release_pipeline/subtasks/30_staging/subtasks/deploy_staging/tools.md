## write_staging_manifest
> type: python

Simulate a staging deployment by writing a manifest file describing the deployed build.

```python
def write_staging_manifest(ctx, artifact_path: str, version: str, staging_dir: str) -> dict:
    import json
    from datetime import datetime
    from pathlib import Path

    Path(staging_dir).mkdir(parents=True, exist_ok=True)
    manifest = {
        "version": version,
        "artifact": artifact_path,
        "deployed_at": datetime.now().isoformat(),
        "environment": "staging",
        "status": "deployed",
    }
    manifest_path = Path(staging_dir) / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))

    return {
        "staging_url": f"http://staging.example.com/{version}",
        "staging_manifest_path": str(manifest_path),
    }
```
