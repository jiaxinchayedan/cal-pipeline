"""extract（脱敏抽取）模式：样例数据 + 端到端可用性 + 脱敏断言。"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"


def _config(tmp_path: Path, raw_dir: str) -> Path:
    config = tmp_path / "extract.yaml"
    config.write_text(
        "seed: 42\n"
        "data:\n"
        "  source: extract\n"
        f"  raw_dir: {raw_dir}\n"
        "  companies: 3\n"
        "  months: 3\n"
        "  demand_cards: 2\n",
        encoding="utf-8",
    )
    return config


def _run(config: Path, runs_dir: Path, run_id: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "cal",
            "run",
            "--config",
            str(config),
            "--runs-dir",
            str(runs_dir),
            "--run-id",
            run_id,
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=600,
    )


def test_extract_mode_completes_and_masks_contacts(tmp_path: Path) -> None:
    assert RAW.is_dir(), "缺少 data/raw 样例数据"
    config = _config(tmp_path, RAW.as_posix())
    runs = tmp_path / "runs"

    result = _run(config, runs, "ex-1")
    assert result.returncode == 0, result.stderr + result.stdout

    companies = (runs / "ex-1" / "prepare" / "companies.jsonl").read_text(encoding="utf-8")
    cards = (runs / "ex-1" / "prepare" / "demand_cards.jsonl").read_text(encoding="utf-8")

    # 原始手机号 / 邮箱不得出现在产物中
    for raw_value in ("13800138001", "13800138002", "user1@example.com", "user2@example.com"):
        assert raw_value not in companies
    for raw_value in ("13900139000", "13900139001", "demand1@example.com"):
        assert raw_value not in cards

    # 掩码确实生效
    assert "1**********" in companies
    assert "***@masked.invalid" in companies

    # 流水线照常产出报告
    assert (runs / "ex-1" / "report" / "metrics.json").is_file()
    manifest_path = runs / "ex-1" / "manifest.json"
    assert manifest_path.is_file()

    # extract 模式下 prepare 必须记录三张原始表的真实输入 SHA-256
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    prepare = manifest["steps"][0]
    assert prepare["step"] == "prepare"
    assert [item["path"] for item in prepare["inputs"]] == [
        "prepare/raw/companies.jsonl",
        "prepare/raw/demand_cards.jsonl",
        "prepare/raw/outcomes.jsonl",
    ]
    for item in prepare["inputs"]:
        assert "abs" not in item
    for item in prepare["inputs"]:
        assert len(item["sha256"]) == 64
        assert item["bytes"] > 0

    # 清单可回验
    verified = subprocess.run(
        [sys.executable, "-m", "cal", "verify", "--run-dir", str(runs / "ex-1")],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=300,
    )
    assert verified.returncode == 0, verified.stderr

    # 换一个 cwd 回验（原始表路径已记绝对路径，不应误报"缺失文件"）
    env = dict(os.environ, PYTHONPATH=str(ROOT))
    verified_elsewhere = subprocess.run(
        [sys.executable, "-m", "cal", "verify", "--run-dir", str(runs / "ex-1")],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=300,
        env=env,
    )
    assert verified_elsewhere.returncode == 0, verified_elsewhere.stderr
    assert "未定位" not in verified_elsewhere.stderr
    # 原始表以快照形式留在运行目录，运行自包含
    assert (runs / "ex-1" / "prepare" / "raw" / "companies.jsonl").is_file()


def test_extract_mode_reports_missing_raw_tables(tmp_path: Path) -> None:
    config = _config(tmp_path, (tmp_path / "no_such_dir").as_posix())
    result = _run(config, tmp_path / "runs", "ex-2")

    assert result.returncode == 2
    combined = (result.stderr + result.stdout).replace("\\", "/")
    assert "缺少原始表" in combined
    assert not (tmp_path / "runs" / "ex-2" / "report").exists()
