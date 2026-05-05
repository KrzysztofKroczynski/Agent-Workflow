import pytest

from agentflow.core.templating import render_instructions
from agentflow.exceptions import ConfigError


def test_simple_include(tmp_path):
    shared = tmp_path / "shared" / "instructions"
    shared.mkdir(parents=True)
    (shared / "fmt.md").write_text("be brief")
    rendered = render_instructions(
        'do the thing\n{% include "fmt" %}', tmp_path / "shared"
    )
    assert "be brief" in rendered
    assert "do the thing" in rendered


def test_nested_include(tmp_path):
    shared = tmp_path / "shared" / "instructions"
    shared.mkdir(parents=True)
    (shared / "outer.md").write_text('{% include "inner" %}')
    (shared / "inner.md").write_text("INNER")
    rendered = render_instructions('{% include "outer" %}', tmp_path / "shared")
    assert "INNER" in rendered


def test_cycle_detection(tmp_path):
    shared = tmp_path / "shared" / "instructions"
    shared.mkdir(parents=True)
    (shared / "a.md").write_text('{% include "b" %}')
    (shared / "b.md").write_text('{% include "a" %}')
    with pytest.raises(ConfigError):
        render_instructions('{% include "a" %}', tmp_path / "shared")


def test_missing_snippet(tmp_path):
    shared = tmp_path / "shared" / "instructions"
    shared.mkdir(parents=True)
    with pytest.raises(ConfigError):
        render_instructions('{% include "nope" %}', tmp_path / "shared")


def test_no_shared_dir():
    with pytest.raises(ConfigError):
        render_instructions('{% include "x" %}', None)
