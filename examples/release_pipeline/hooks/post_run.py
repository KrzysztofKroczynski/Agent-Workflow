from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


def run(ctx: Any, task: Any) -> None:
    output_dir = Path(ctx.workflow_root) / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    s = ctx.state
    report = {
        "generated_at": datetime.now().isoformat(),
        "version": s.get("version"),
        "pre_checks": {
            "passed": s.get("pre_checks_passed"),
            "summary": s.get("pre_checks_summary"),
            "lint": s.get("lint_result"),
            "security": s.get("security_result"),
            "dependencies": s.get("dependency_result"),
        },
        "build": {
            "compile_passed": (s.get("compile_result") or {}).get("passed"),
            "tests_passed": s.get("tests_passed"),
            "test_result": s.get("test_result"),
            "artifact_path": s.get("artifact_path"),
        },
        "staging": {
            "url": s.get("staging_url"),
            "integration_tests_passed": s.get("integration_tests_passed"),
            "integration_report": s.get("integration_report"),
            "approved": s.get("approved"),
            "feedback": s.get("feedback"),
            "summary": s.get("staging_summary"),
        },
        "production": {
            "url": s.get("production_url"),
            "smoke_tests_passed": s.get("smoke_tests_passed"),
        },
        "errors": s.get("_errors", []),
    }

    report_path = output_dir / "release_report.json"
    report_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    ctx.logger.info("Release report saved -> %s", report_path)
