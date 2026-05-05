import json
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel


class _Encoder(json.JSONEncoder):
    def default(self, obj: Any) -> Any:
        if isinstance(obj, BaseModel):
            return obj.model_dump()
        if isinstance(obj, Path):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


def dumps(obj: Any) -> str:
    return json.dumps(obj, cls=_Encoder, default=str)
