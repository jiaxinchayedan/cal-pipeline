"""`cal verify`：重算清单与全部登记文件的 SHA-256，能发现任何静默篡改。"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "cal", *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=900,
    )


def test_verify_passes_on_clean_run_and_detects_tampering(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    result = _run(
        "run", "--config", "cal.yaml", "--runs-dir", str(runs), "--run-id", "verify-1"
    )
    assert result.returncode == 0, result.stderr + result.stdout

    run_dir = runs / "verify-1"
    assert (run_dir / "manifest.sha256").is_file()

    clean = _run("verify", "--run-dir", str(run_dir))
    assert clean.returncode == 0, clean.stderr
    assert "校验通过" in clean.stdout

    # 篡改一个产物 → 必须报不一致
    target = run_dir / "eval" / "eval.json"
    target.write_text(target.read_text(encoding="utf-8").replace('"f1"', '"f1x"'), encoding="utf-8")
    tampered = _run("verify", "--run-dir", str(run_dir))
    assert tampered.returncode == 1
    assert "不匹配" in tampered.stderr

    # 篡改清单本身 → 自校验必须发现
    manifest = run_dir / "manifest.json"
    manifest.write_text(manifest.read_text(encoding="utf-8") + " ", encoding="utf-8")
    manifest_tampered = _run("verify", "--run-dir", str(run_dir))
    assert manifest_tampered.returncode == 1
    assert "清单自身被改动" in manifest_tampered.stderr


def test_verify_reports_missing_run_dir(tmp_path: Path) -> None:
    result = _run("verify", "--run-dir", str(tmp_path / "nope"))
    assert result.returncode == 2
