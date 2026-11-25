"""八步流水线模块。

每个模块暴露 `run(ctx) -> {"inputs": [...], "outputs": [...]}`，
路径均为相对 runs/<run_id>/ 的 POSIX 路径，由编排器统一计算 SHA-256。
"""
