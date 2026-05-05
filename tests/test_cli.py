from click.testing import CliRunner

from agentflow.cli.main import cli


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
