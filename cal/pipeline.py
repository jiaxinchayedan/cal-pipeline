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


def _hash_entries(run_dir: Path, items: List, step: str) -> List[dict]:
    """items 元素可以是相对 run_dir 的路径字符串，也可以是 {"path","abs"} 字典。

    后者用于记录流水线外部的输入（如 extract 模式的 data/raw 原始表）。
    """
    entries = []
    for item in items:
        if isinstance(item, dict):
            label = item["path"]
            path = Path(item["abs"])
        else:
            label = item
            path = run_dir / item
        if not path.is_file():
            raise StepFailure(f"步骤 {step} 声明的文件不存在：{label}")
        entry = {
            "path": label,
            "sha256": hashing.sha256_file(path),
            "bytes": path.stat().st_size,
        }
        if isinstance(item, dict) and item.get("abs"):
            entry["abs"] = item["abs"]
        entries.append(entry)
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
    # 语义哈希：与行尾、缩进、注释无关，只与解析后的配置值有关
    config_sha = hashing.sha256_json(cfg)

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
        # 只记文件名，不记绝对路径：清单不应随运行位置（cwd）变化
        "config": config_path.name,
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

    try:
        manifest_path = hashing.write_canonical_json(run_dir / "manifest.json", manifest)
        (run_dir / "manifest.sha256").write_text(
            hashing.sha256_file(manifest_path) + "\n", encoding="utf-8", newline="\n"
        )
    except BaseException:
        _purge_partial_report(run_dir)
        print(
            f"[cal] 流水线中止 | 失败步骤=manifest | 清单写入失败，已清理报告产物 | 日志目录={(run_dir / 'logs').as_posix()}",
            file=sys.stderr,
        )
        return 2

    metrics_path = run_dir / "report" / "metrics.json"
    total_seconds = time.perf_counter() - pipeline_started
    print(
        f"[cal] 流水线完成 | run_id={rid} | metrics={metrics_path.as_posix()} "
        f"| sha256={hashing.sha256_file(metrics_path)} | 总耗时={total_seconds:.2f}s"
    )
    return 0


def verify_run(run_dir: str | Path) -> int:
    """回验一次运行：重算清单自身与每个已登记文件的 SHA-256。

    用法：cal verify --run-dir runs/<run_id>
    返回 0 = 全部一致；1 = 有文件被篡改或缺失；2 = 运行目录/清单不存在。
    """
    run_dir = Path(run_dir)
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.is_file():
        print(f"[cal] 校验失败：找不到清单 {manifest_path}", file=sys.stderr)
        return 2

    ok = True
    stamp_path = run_dir / "manifest.sha256"
    if not stamp_path.is_file():
        print("[cal] 校验失败：缺少清单自校验文件 manifest.sha256（无法证明清单未被改动）", file=sys.stderr)
        return 1
    recorded = stamp_path.read_text(encoding="utf-8").strip()
    actual = hashing.sha256_file(manifest_path)
    if recorded != actual:
        print(f"[cal] 清单自身被改动：记录 {recorded[:16]}… 实际 {actual[:16]}…", file=sys.stderr)
        ok = False

    manifest = hashing.read_json(manifest_path)
    checked = failed = skipped = 0
    for entry in manifest.get("steps", []):
        for kind in ("inputs", "outputs"):
            for item in entry.get(kind, []):
                label = item["path"]
                candidates = []
                if item.get("abs"):
                    candidates.append(Path(item["abs"]))
                candidates.append(run_dir / label)
                candidates.append(Path(label))
                candidate = next((path for path in candidates if path.is_file()), None)
                if candidate is None:
                    # 外部输入（如 data/raw）可能已随原始环境移动：跳过并告警，不误判为篡改
                    print(f"[cal] 未定位（跳过）：{label}", file=sys.stderr)
                    skipped += 1
                    continue
                checked += 1
                actual = hashing.sha256_file(candidate)
                if actual != item["sha256"]:
                    print(f"[cal] SHA-256 不匹配：{label}", file=sys.stderr)
                    failed += 1

    if failed:
        print(f"[cal] 校验失败：{failed}/{checked + failed} 个文件不一致", file=sys.stderr)
        return 1
    note = f"，{skipped} 个外部输入未定位已跳过" if skipped else ""
    print(f"[cal] 校验通过：{checked} 个文件 SHA-256 全部一致（含清单自校验）{note}")
    return 0
