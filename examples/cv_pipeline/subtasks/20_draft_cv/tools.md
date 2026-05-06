## read_file
> type: python

Read the full text contents of a file from the filesystem.

```python
def read_file(ctx, path: str) -> str:
    from pathlib import Path
    return Path(path).read_text(encoding="utf-8")
```
