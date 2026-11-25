"""命令行入口：cal run --config cal.yaml / cal steps / cal --version。"""
from __future__ import annotations

import argparse

from . import __version__
from .pipeline import STEP_ORDER, run_pipeline, verify_run


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cal",
        description="会员空间平台 · 健康分与匹配校准流水线（离线可复现）",
    )
    parser.add_argument("--version", action="version", version=f"cal {__version__}")

    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="按序执行八步流水线（任一步失败即停）")
    run.add_argument("--config", default="cal.yaml", help="配置文件路径（默认 cal.yaml）")
    run.add_argument("--run-id", default=None, help="运行 id（默认 UTC 时间戳 + 配置哈希）")
    run.add_argument("--runs-dir", default="runs", help="运行目录根（默认 runs）")
    run.add_argument(
        "--fail-step",
        choices=STEP_ORDER,
        default=None,
        help="故障注入：强制指定步骤失败，仅用于验证失败语义",
    )

    sub.add_parser("steps", help="列出八步执行顺序")

    verify = sub.add_parser("verify", help="回验一次运行：重算清单与全部文件 SHA-256")
    verify.add_argument("--run-dir", required=True, help="运行目录，例如 runs/20261125T…")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "steps":
        for index, name in enumerate(STEP_ORDER, start=1):
            print(f"{index}. {name}")
        return 0
    if args.command == "verify":
        return verify_run(args.run_dir)
    return run_pipeline(
        config_path=args.config,
        run_id=args.run_id,
        runs_dir=args.runs_dir,
        fail_step=args.fail_step,
    )
