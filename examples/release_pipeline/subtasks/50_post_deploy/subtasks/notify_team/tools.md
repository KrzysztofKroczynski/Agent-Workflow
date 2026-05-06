## write_notification
> type: python

Write a deployment notification message to a file (simulates sending a team alert).

```python
def write_notification(ctx, output_dir: str, message: str) -> dict:
    from datetime import datetime
    from pathlib import Path

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    notification_file = Path(output_dir) / "deployment_notification.txt"
    notification_file.write_text(
        f"[{datetime.now().isoformat()}] {message}\n",
        encoding="utf-8",
    )
    return {"written_to": str(notification_file)}
```
