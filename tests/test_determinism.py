"""验收标准 1/2：同配置重复运行指标逐字节一致，且 manifest 中每个文件名与 SHA-256 自洽。"""
from __future__ import annotations

import hashlib
import json
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
        timeout=900,
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def test_two_runs_are_byte_identical(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    for run_id in ("det-1", "det-2"):
        result = run_cal(
            "run",
            "--config",
            "cal.yaml",
            "--runs-dir",
            str(runs_dir),
            "--run-id",
            run_id,
        )
        assert result.returncode == 0, result.stderr + result.stdout

    first = runs_dir / "det-1" / "report" / "metrics.json"
    second = runs_dir / "det-2" / "report" / "metrics.json"
    assert _sha256(first) == _sha256(second), "两次运行 metrics.json 的 SHA-256 必须相同"

    # 黄金值文件同样必须一致（CI 中还会做 1e-9 容差比对）
    golden = ROOT / "golden" / "metrics.json"
    assert _sha256(first) == _sha256(golden), "实际产物与仓库黄金值不一致，请确认是否改了配置或算法"


def test_manifest_records_sha256_for_every_step(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    result = run_cal("run", "--config", "cal.yaml", "--runs-dir", str(runs_dir), "--run-id", "manifest-1")
    assert result.returncode == 0, result.stderr + result.stdout

    run_dir = runs_dir / "manifest-1"
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))

    steps = [entry["step"] for entry in manifest["steps"]]
    assert steps == [
        "prepare",
        "profile",
        "replay",
        "eval",
        "scan-thresholds",
        "search",
        "ablation",
        "report",
    ]

    checked = 0
    for entry in manifest["steps"]:
        assert entry["outputs"], f"步骤 {entry['step']} 必须声明至少一个输出文件"
        for item in entry["outputs"]:
            path = run_dir / item["path"]
            assert path.is_file(), f"缺失产物 {item['path']}"
            assert _sha256(path) == item["sha256"], f"SHA-256 不匹配：{item['path']}"
            assert item["bytes"] == path.stat().st_size
            checked += 1
        for item in entry["inputs"]:
            assert (run_dir / item["path"]).is_file()

    assert checked >= 10, f"清单覆盖的输出文件过少：{checked}"
