from types import SimpleNamespace

from agentflow.core.context import ContextManager
from agentflow.schemas.task_schema import IOBlock, TaskConfig


def _task(name: str, **kw):
    cfg = TaskConfig(**kw)
    return SimpleNamespace(name=name, config=cfg, parent=None)


def test_default_output_under_task_name():
    cm = ContextManager()
    cm.capture_output(_task("greet"), "hello there")
    assert cm.data["greet"] == "hello there"


def test_declared_output_extracts_json_block():
    cm = ContextManager()
    response = """Sure, here you go:

```json
{"raw_data": [1, 2, 3], "fetch_metadata": {"count": 3}}
```
"""
    cm.capture_output(_task("fetch", output=["raw_data", "fetch_metadata"]), response)
    assert cm.data["raw_data"] == [1, 2, 3]
    assert cm.data["fetch_metadata"] == {"count": 3}


def test_declared_output_falls_back_when_no_json():
    cm = ContextManager()
    cm.capture_output(_task("x", output=["raw_data"]), "no json here")
    assert cm.data["raw_data"] == "no json here"


def test_prepare_input_required_missing():
    cm = ContextManager({"a": 1})
    task = _task("t", input=IOBlock(required=["a", "b"]))
    try:
        cm.prepare_input(task)
    except KeyError as e:
        assert "b" in str(e)
    else:
        raise AssertionError("expected KeyError")


def test_prepare_input_required_and_optional():
    cm = ContextManager({"a": 1, "b": 2, "c": 3})
    task = _task("t", input=IOBlock(required=["a"], optional=["b"]))
    out = cm.prepare_input(task)
    assert out == {"a": 1, "b": 2}
