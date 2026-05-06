## deploy_to_production
> type: python

Simulate a production deployment by writing a production manifest file.

```python
def deploy_to_production(ctx, artifact_path: str, version: str, output_dir: str) -> dict:
    import json
    from datetime import datetime
    from pathlib import Path

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    manifest = {
        "version": version,
        "artifact": artifact_path,
        "deployed_at": datetime.now().isoformat(),
        "environment": "production",
        "status": "live",
    }
    manifest_path = Path(output_dir) / "production_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))

    return {
        "production_url": "https://app.example.com",
        "production_manifest_path": str(manifest_path),
    }
```
