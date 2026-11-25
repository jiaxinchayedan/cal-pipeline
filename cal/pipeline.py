"""流水线编排：顺序执行八步、运行目录隔离、每步 SHA-256 清单、失败即停。

失败语义（验收标准 4）：任一步抛错 → 立即停止、清理已生成的报告产物、
把失败步骤名与日志路径写到 stderr、进程退出码 2。
"""
from __future__ import annotations

import datetime as _dt
import importlib
import logging
import shutil
import sys
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from . import hashing
from .config import load_config

STEP_ORDER: tuple = (
    "prepare",
    "profile",
    "replay",
    "eval",
    "scan-thresholds",
    "search",
    "ablation",
    "report",
)

MODULES: Dict[str, str] = {
    "prepare": "cal.steps.prepare",
    "profile": "cal.steps.profile",
    "replay": "cal.steps.replay",
    "eval": "cal.steps.eval",
    "scan-thresholds": "cal.steps.scan_thresholds",
    "search": "cal.steps.search",
    "ablation": "cal.steps.ablation",
    "report": "cal.steps.report",
}

LOG_FORMAT = "%(asctime)s %(levelname)-5s %(message)s"


@dataclass
class Context:
    cfg: dict
    run_dir: Path
    seed: int
    logger: logging.Logger
    config_path: Path
    config_sha256: str


class StepFailure(RuntimeError):
    """步骤内部失败（携带步骤名，便于上层统一输出）。"""


def _make_logger(step: str, log_path: Path) -> logging.Logger:
    logger = logging.getLogger(f"cal.{step}.{id(log_path)}")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    for handler in list(logger.handlers):
        logger.removeHandler(handler)

    formatter = logging.Formatter(LOG_FORMAT)
    stream = logging.StreamHandler(stream=sys.stdout)
    stream.setFormatter(formatter)
    logger.addHandler(stream)

    file_handler = logging.FileHandler(log_path, mode="w", encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    return logger


def _hash_entries(run_dir: Path, rel_paths: List[str], step: str) -> List[dict]:
    entries = []
    for rel in rel_paths:
        path = run_dir / rel
        if not path.is_file():
            raise StepFailure(f"步骤 {step} 声明的文件不存在：{rel}")
        entries.append(
            {
                "path": rel,
                "sha256": hashing.sha256_file(path),
                "bytes": path.stat().st_size,
            }
        )
    return entries


def _purge_partial_report(run_dir: Path) -> None:
    """保证失败时不留半成品报告（验收标准 4 的硬断言）。"""
    report_dir = run_dir / "report"
    if report_dir.exists():
        shutil.rmtree(report_dir)


def default_run_id(config_sha256: str) -> str:
    stamp = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{config_sha256[:12]}"


def run_pipeline(
    config_path: str | Path,
    run_id: Optional[str] = None,
    runs_dir: str | Path = "runs",
    fail_step: Optional[str] = None,
) -> int:
    config_path = Path(config_path)
    cfg = load_config(config_path)
    config_sha = hashing.sha256_text_normalized(config_path)

    rid = run_id or default_run_id(config_sha)
    run_dir = Path(runs_dir) / rid
    if run_dir.exists():
        print(f"[cal] 运行目录已存在，拒绝复用半成品目录：{run_dir}", file=sys.stderr)
        return 3

    run_dir.mkdir(parents=True)
    (run_dir / "logs").mkdir()
    pipeline_started = time.perf_counter()
    print(f"[cal] 开始运行 run_id={rid} 目录={run_dir}")

    manifest = {
        "schema_version": "1.0",
        "run_id": rid,
        "config_path": str(config_path).replace("\\", "/"),
        "config_sha256": config_sha,
        "steps": [],
    }

    for step in STEP_ORDER:
        (run_dir / step).mkdir(exist_ok=True)
        log_path = run_dir / "logs" / f"{step}.log"
        logger = _make_logger(step, log_path)
        context = Context(
            cfg=cfg,
            run_dir=run_dir,
            seed=int(cfg["seed"]),
            logger=logger,
            config_path=config_path,
            config_sha256=config_sha,
        )
        started = time.perf_counter()
        try:
            if fail_step == step:
                raise StepFailure(f"故障注入：强制步骤 {step} 失败（--fail-step {step}）")
            module = importlib.import_module(MODULES[step])
            meta = module.run(context) or {}
        except BaseException:
            _purge_partial_report(run_dir)
            logger.error("步骤 %s 失败，流水线中止：\n%s", step, traceback.format_exc())
            for handler in list(logger.handlers):
                handler.flush()
                handler.close()
                logger.removeHandler(handler)
            print(
                f"[cal] 流水线中止 | 失败步骤={step} | 日志={log_path.as_posix()} | 未生成报告",
                file=sys.stderr,
            )
            return 2

        duration_ms = int((time.perf_counter() - started) * 1000)
        entry = {
            "step": step,
            "duration_ms": duration_ms,
            "inputs": _hash_entries(run_dir, meta.get("inputs", []), step),
            "outputs": _hash_entries(run_dir, meta.get("outputs", []), step),
        }
        manifest["steps"].append(entry)
        logger.info("步骤 %s 完成，耗时 %d ms", step, duration_ms)
        for handler in list(logger.handlers):
            handler.flush()
            handler.close()
            logger.removeHandler(handler)

    hashing.write_canonical_json(run_dir / "manifest.json", manifest)
    metrics_path = run_dir / "report" / "metrics.json"
    total_seconds = time.perf_counter() - pipeline_started
    print(
        f"[cal] 流水线完成 | run_id={rid} | metrics={metrics_path.as_posix()} "
        f"| sha256={hashing.sha256_file(metrics_path)} | 总耗时={total_seconds:.2f}s"
    )
    return 0
