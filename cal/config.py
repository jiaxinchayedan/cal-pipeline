"""配置加载与校验。

所有可变参数集中在 cal.yaml，代码内不出现魔法数字；配置只从文件与环境变量读取。
"""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Dict

import yaml

DEFAULTS: Dict[str, Any] = {
    "seed": 20261125,
    "data": {
        "source": "generate",          # generate | extract
        "companies": 300,
        "months": 24,
        "demand_cards": 200,
        "raw_dir": "data/raw",
    },
    "model": {
        "weights": {
            "industry_match": 0.90,
            "region_match": 0.50,
            "size_fit": 0.70,
            "activity": 1.10,
            "resource_overlap": 1.30,
        },
        "bias": -1.20,
    },
    "eval": {"threshold": 0.60},
    "scan_thresholds": {"min": 0.05, "max": 0.95, "step": 0.05, "metric": "f1"},
    "search": {
        "grid": {
            "industry_match": [0.70, 0.90, 1.10],
            "size_fit": [0.50, 0.70, 0.90],
            "resource_overlap": [1.10, 1.30, 1.50],
        }
    },
    "ablation": {
        "features": [
            "industry_match",
            "region_match",
            "size_fit",
            "activity",
            "resource_overlap",
        ]
    },
    "runtime": {"timezone": "UTC", "json_indent": 2},
}


class ConfigError(ValueError):
    """配置非法。"""


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    out = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _validate(cfg: Dict[str, Any]) -> None:
    if not isinstance(cfg.get("seed"), int):
        raise ConfigError("seed 必须是整数（所有随机过程的唯一熵源）")
    data = cfg["data"]
    if data["source"] not in ("generate", "extract"):
        raise ConfigError("data.source 只允许 generate 或 extract")
    for key in ("companies", "months", "demand_cards"):
        if not isinstance(data[key], int) or data[key] <= 0:
            raise ConfigError(f"data.{key} 必须是正整数")
    weights = cfg["model"]["weights"]
    if set(weights) != {
        "industry_match",
        "region_match",
        "size_fit",
        "activity",
        "resource_overlap",
    }:
        raise ConfigError("model.weights 必须且只能包含五个特征权重")
    thr = cfg["eval"]["threshold"]
    if not 0.0 < float(thr) < 1.0:
        raise ConfigError("eval.threshold 必须在 (0,1) 开区间内")
    scan = cfg["scan_thresholds"]
    if float(scan["step"]) <= 0:
        raise ConfigError("scan_thresholds.step 必须为正")


def load_config(path: str | Path) -> Dict[str, Any]:
    """加载 YAML 并与内置默认值深度合并（缺省项用默认值补齐）。"""
    p = Path(path)
    if not p.is_file():
        raise ConfigError(f"配置文件不存在：{p}")
    with p.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    if not isinstance(raw, dict):
        raise ConfigError("配置文件根部必须是映射（key: value）")
    cfg = _deep_merge(DEFAULTS, raw)
    _validate(cfg)
    return cfg
