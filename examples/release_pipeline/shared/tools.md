## read_file
> type: python

Read the full text contents of a file from the filesystem.

```python
def read_file(ctx, path: str) -> str:
    from pathlib import Path
    return Path(path).read_text(encoding="utf-8")
```

## list_files
> type: python

List all files in a directory recursively. Returns one path per line.

```python
def list_files(ctx, directory: str) -> str:
    from pathlib import Path
    p = Path(directory)
    if not p.exists():
        return ""
    return "\n".join(str(f) for f in sorted(p.rglob("*")) if f.is_file())
```
