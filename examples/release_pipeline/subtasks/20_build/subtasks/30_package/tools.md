## create_zip
> type: python

Package all Python source files into a versioned zip archive.

```python
def create_zip(ctx, src_dir: str, output_dir: str, version: str) -> dict:
    import zipfile
    from pathlib import Path

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    artifact = output / f"release-{version}.zip"

    with zipfile.ZipFile(artifact, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(Path(src_dir).rglob("*.py")):
            zf.write(f, f.relative_to(Path(src_dir).parent))

    return {
        "artifact_path": str(artifact),
        "size_bytes": artifact.stat().st_size,
    }
```
