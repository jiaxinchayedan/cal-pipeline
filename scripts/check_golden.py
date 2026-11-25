#!/usr/bin/env python3
"""黄金值比对：逐个数值叶子比较，差值必须 < 容差（默认 1e-9）。

用法：python scripts/check_golden.py <actual.json> <golden.json> [--tol 1e-9]
退出码：0 = 一致；1 = 有差异或结构不同。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

NUMERIC = (int, float)


def compare(golden, actual, tol: float, path: str, diffs: list, stats: dict) -> None:
    if isinstance(golden, dict) and isinstance(actual, dict):
        missing = sorted(set(golden) - set(actual))
        extra = sorted(set(actual) - set(golden))
        for key in missing:
            diffs.append(f"{path}.{key}: 黄金值缺少于实际结果")
        for key in extra:
            diffs.append(f"{path}.{key}: 实际结果多出该键")
        for key in sorted(set(golden) & set(actual)):
            compare(golden[key], actual[key], tol, f"{path}.{key}", diffs, stats)
        return
    if isinstance(golden, list) and isinstance(actual, list):
        if len(golden) != len(actual):
            diffs.append(f"{path}: 列表长度不同 {len(golden)} != {len(actual)}")
        for index, (g_item, a_item) in enumerate(zip(golden, actual)):
            compare(g_item, a_item, tol, f"{path}[{index}]", diffs, stats)
        return
    if isinstance(golden, bool) or isinstance(actual, bool):
        if golden != actual:
            diffs.append(f"{path}: {golden!r} != {actual!r}")
        return
    if isinstance(golden, NUMERIC) and isinstance(actual, NUMERIC):
        diff = abs(float(golden) - float(actual))
        stats["compared"] += 1
        stats["max_diff"] = max(stats["max_diff"], diff)
        if diff > tol:
            diffs.append(f"{path}: 黄金值 {golden} vs 实际 {actual}，差值 {diff:.3e} ≥ {tol:.0e}")
        return
    if golden != actual:
        diffs.append(f"{path}: {golden!r} != {actual!r}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="metrics.json 黄金值比对")
    parser.add_argument("actual", help="实际产出的 metrics.json")
    parser.add_argument("golden", help="仓库中的黄金值文件")
    parser.add_argument("--tol", type=float, default=1e-9, help="允许的最大差值（默认 1e-9）")
    args = parser.parse_args(argv)

    actual = json.loads(Path(args.actual).read_text(encoding="utf-8"))
    golden = json.loads(Path(args.golden).read_text(encoding="utf-8"))

    diffs: list = []
    stats = {"compared": 0, "max_diff": 0.0}
    compare(golden, actual, args.tol, "$", diffs, stats)

    print(f"比对数值叶子 {stats['compared']} 个，最大差值 {stats['max_diff']:.3e}（容差 {args.tol:.0e}）")
    if diffs:
        print(f"FAIL 发现 {len(diffs)} 处不一致：")
        for line in diffs[:50]:
            print("  - " + line)
        return 1
    print("PASS 关键指标与黄金值完全一致")
    return 0


if __name__ == "__main__":
    sys.exit(main())
