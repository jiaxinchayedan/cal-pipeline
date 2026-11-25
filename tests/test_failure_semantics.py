"""验收标准 4：人为让 eval 步骤失败时，不生成任何报告产物，且输出失败步骤与日志路径。"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_cal(*args: str, cwd: Path = ROOT) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "cal", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=600,
    )


def test_eval_failure_produces_no_report(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    result = run_cal(
        "run",
        "--config",
        "cal.yaml",
        "--runs-dir",
        str(runs_dir),
        "--run-id",
        "inject-eval",
        "--fail-step",
        "eval",
    )

    assert result.returncode == 2, f"退出码应为 2，实际 {result.returncode}\n{result.stdout}\n{result.stderr}"

    # stderr 必须给出失败步骤名与日志路径，不允许出现半成品提示
    assert "失败步骤=eval" in result.stderr
    assert "logs/eval.log" in result.stderr.replace("\\", "/")
    assert "未生成报告" in result.stderr

    run_dir = runs_dir / "inject-eval"
    assert not (run_dir / "report").exists(), "失败时不应存在 report 目录"
    assert not (run_dir / "report" / "metrics.json").exists()
    assert not (run_dir / "report" / "report.md").exists()

    # 前置步骤产物与失败日志应保留，便于定位
    assert (run_dir / "prepare" / "companies.jsonl").is_file()
    eval_log = run_dir / "logs" / "eval.log"
    assert eval_log.is_file()
    assert "故障注入" in eval_log.read_text(encoding="utf-8")


def test_unknown_step_is_rejected_by_cli() -> None:
    result = run_cal("run", "--config", "cal.yaml", "--fail-step", "not-a-step")
    assert result.returncode != 0
    assert "invalid choice" in result.stderr
