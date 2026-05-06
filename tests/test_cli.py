import sys
from unittest.mock import patch

from click.testing import CliRunner

from agentflow.cli.main import cli, _collect_and_install_dependencies
from agentflow.core.loader import TaskLoader


def test_collect_dependencies_none(tmp_workflow):
    root_path = tmp_workflow({"instructions.md": "go"})
    root = TaskLoader().load(root_path)
    _collect_and_install_dependencies(root)  # no dependencies — no error


def test_collect_dependencies_installs(tmp_workflow):
    root_path = tmp_workflow(
        {
            "task.yaml": "name: root\ndependencies:\n  - some-pkg>=1.0\n",
            "subtasks": {
                "a": {
                    "task.yaml": "dependencies:\n  - other-pkg\n",
                    "instructions.md": "go",
                }
            },
        }
    )
    root = TaskLoader().load(root_path)
    with patch("agentflow.cli.main.subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        _collect_and_install_dependencies(root)
        mock_run.assert_called_once()
        called_args = mock_run.call_args[0][0]
        assert sys.executable in called_args
        assert "some-pkg>=1.0" in called_args
        assert "other-pkg" in called_args


def test_collect_dependencies_deduplicates(tmp_workflow):
    root_path = tmp_workflow(
        {
            "task.yaml": "name: root\ndependencies:\n  - requests>=2\n",
            "subtasks": {
                "a": {
                    "task.yaml": "dependencies:\n  - requests>=2\n",
                    "instructions.md": "go",
                }
            },
        }
    )
    root = TaskLoader().load(root_path)
    with patch("agentflow.cli.main.subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        _collect_and_install_dependencies(root)
        called_args = mock_run.call_args[0][0]
        assert called_args.count("requests>=2") == 1


def test_tree_command(tmp_workflow):
    root = tmp_workflow(
        {
            "task.yaml": "name: root\n",
            "subtasks": {
                "a": {"instructions.md": "a"},
                "b": {"instructions.md": "b"},
            },
        }
    )
    runner = CliRunner()
    result = runner.invoke(cli, ["tree", str(root)])
    assert result.exit_code == 0, result.output
    assert "root" in result.output
    assert "a" in result.output
    assert "b" in result.output


def test_validate_clean_workflow(tmp_workflow):
    root = tmp_workflow(
        {
            "task.yaml": (
                "name: root\n"
                "providers:\n"
                "  default: fake\n"
                "  fake:\n"
                "    module: agentflow.providers.fake\n"
            ),
            "instructions.md": "go",
        }
    )
    runner = CliRunner()
    result = runner.invoke(cli, ["validate", str(root)])
    assert result.exit_code == 0, result.output
    assert "valid" in result.output.lower()


def test_validate_unknown_shared_tool(tmp_workflow):
    root = tmp_workflow(
        {
            "task.yaml": "name: root\n",
            "subtasks": {
                "child": {
                    "task.yaml": "tools:\n  use_shared: [missing]\n",
                    "instructions.md": "go",
                }
            },
        }
    )
    runner = CliRunner()
    result = runner.invoke(cli, ["validate", str(root)])
    assert result.exit_code == 1
    assert "missing" in result.output
