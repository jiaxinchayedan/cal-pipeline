# cal-pipeline — 会员空间平台 · 健康分与匹配校准流水线

把健康分与匹配校准的各个环节串成一条**一条命令跑完、结果可逐字节复现**的流水线。全部数据为虚构数据，不含任何真实个人信息或企业信息。

```bash
cal run --config cal.yaml
```

---

## 1. 流水线做了什么

`cal run` 按固定顺序执行八步，每步产物写入 `runs/<run_id>/<step>/`，并把每步输入/输出文件的 SHA-256 记进 `runs/<run_id>/manifest.json`：

| 序号 | 步骤 | 作用 | 产物 |
|---|---|---|---|
| 1 | `prepare` | 生成虚构数据（300 家企业 / 24 个月快照 / 200 张需求卡）或从 `data/raw` 脱敏抽取 | `companies.jsonl`、`demand_cards.jsonl`、`outcomes.jsonl`、`stats.json` |
| 2 | `profile` | 数据画像：字段缺失率、行业/区域分布、活跃度均值与方差 | `profile.json` |
| 3 | `replay` | 用当前权重给每张需求卡回放排序，取前 5 名候选 | `replay.json` |
| 4 | `eval` | 在指定阈值下计算混淆矩阵、precision/recall/F1/AUC | `eval.json` |
| 5 | `scan-thresholds` | 在 19 个阈值点上扫描，按 F1 选最优阈值 | `thresholds.json` |
| 6 | `search` | 27 组权重组合网格搜索，按 AUC 选优 | `search.json` |
| 7 | `ablation` | 逐个特征归零，量化各特征对 AUC 的贡献 | `ablation.json` |
| 8 | `report` | 汇总 Markdown 报告 + **唯一**的指标文件 `metrics.json` | `report.md`、`metrics.json` |

任一步失败 → 立即停止、删除 `report/` 目录（不留半成品报告）、stderr 输出失败步骤名与日志路径、退出码 2。

## 2. 目录结构

```
cal-pipeline/
├── cal/
│   ├── cli.py            # 命令行入口（run / steps）
│   ├── config.py         # cal.yaml 加载、默认值合并、合法性校验
│   ├── dataset.py        # 虚构数据生成 + 正则脱敏抽取
│   ├── model.py          # 五维特征、打分、AUC/混淆矩阵、阈值网格
│   ├── hashing.py        # SHA-256 + 确定性 JSON 序列化
│   ├── pipeline.py       # 八步编排、日志、清单、失败语义
│   └── steps/            # 八个独立步骤模块
├── bin/cal               # 容器内 cal 命令入口
├── cal.yaml              # 配置样例（seed / 数据规模 / 权重 / 阈值 / 搜索网格）
├── data/raw/             # extract 模式样例原始表（3 家企业 / 2 张需求卡，含虚构联系方式用于验证脱敏）
├── Dockerfile            # 两阶段构建，运行期离线
├── .dockerignore         # 构建上下文瘦身（排除 .git / runs / docs / tests）
├── requirements.txt      # 运行期依赖（PyYAML）
├── requirements.lock     # 完整锁文件（含 pytest 等测试依赖）
├── golden/metrics.json   # 黄金值
├── scripts/check_golden.py  # 黄金值比对（容差 1e-9）
├── tests/                # 14 个测试
└── .github/workflows/ci.yml
```

## 3. 运行方法

### 本机

```bash
python -m pip install -r requirements.lock
python -m cal run --config cal.yaml            # 默认 run_id = UTC 时间戳 + 配置哈希
python -m cal run --config cal.yaml --run-id demo-1
python -m cal steps                            # 查看八步顺序
# 让 `cal run --config cal.yaml` 与本机命令行完全一致：
export PATH="$PWD/bin:$PATH" && cal run --config cal.yaml
python -m cal run --config cal.yaml --fail-step eval   # 故障注入（验证失败语义）
python -m cal verify --run-dir runs/<run_id>           # 回验：重算清单与全部文件 SHA-256
```

### Docker（运行期不需要外网）

```bash
docker build -t cal-pipeline:latest .
docker run --rm --network none cal-pipeline:latest run --config cal.yaml --run-id offline
```

`--network none` 下仍能跑完八步，因为依赖全部在构建阶段装进镜像，运行期不访问任何网络。

## 4. 可复现性怎么保证

1. **单一熵源**：所有随机过程（数据生成、标签噪声、候选排序）都从 `cal.yaml` 的 `seed` 派生，代码里不存在 `random.random()` 这类无种子调用。
2. **确定性序列化**：JSON 统一 `sort_keys=True`、固定缩进、UTF-8 + LF；所有浮点统一 `round(x, 10)`，消除末位噪声。
3. **配置哈希是语义哈希**：`config_sha256` 由解析后的配置对象做规范化 JSON 哈希得到，与文件行尾（CRLF/LF）、缩进、注释都无关，只随真实参数变化；改注释不会再误伤黄金值比对。
4. **产物不含易变信息**：`metrics.json` 不写时间戳、不写 run_id，所以两次运行能逐字节一致。
5. **依赖锁版本**：`requirements.lock` 固定 PyYAML 6.0.2 / pytest 8.3.4 等版本，CI 与本机一致（Python 3.11）。
6. **运行目录隔离**：默认 `run_id` 带 UTC 时间戳；同一 run_id 目录已存在时拒绝运行，避免复用半成品目录。
7. **清单可自证**：`runs/<run_id>/manifest.sha256` 记录清单自身的哈希，`cal verify` 会先校验清单本身、再逐个重算所有输入/输出文件的 SHA-256，任何静默篡改都会被发现。`extract` 模式会把三张原始表快照到 `prepare/raw/`，运行目录自包含，换机器/换目录回验都成立；`manifest.sha256` 缺失时直接判失败，删掉自校验文件无法绕过。
8. **清单不含绝对路径**：配置项只记文件名与语义哈希，`extract` 的原始表以快照形式登记在运行目录内，清单整体可随运行目录搬迁。
9. **哈希清单覆盖每步输入与输出**：`extract` 模式会把 `data/raw` 三张原始表的 SHA-256 一并登记，能回答「这次跑的是哪一版原始数据」。

## 5. 验收标准对照

| # | 验收标准原文 | 对应实现 | 证据位置 |
|---|---|---|---|
| 1 | 同一配置运行两次，指标 JSON 的 SHA-256 相同（CI 日志截图） | CI 中 `ci-run-1`、`ci-run-2` 两次运行后 `sha256sum` 比对 | CI 步骤「验收标准 1」+ `docs/ci-summary.png` |
| 2 | CI 中完整流水线 ≤15 分钟，关键指标与黄金值一致（CI 日志截图） | `scripts/check_golden.py` 逐数值叶子比对（容差 1e-9）+ 单次耗时断言（≤900s）+ 作业级 `timeout-minutes: 15` + 整作业耗时断言 | CI 步骤「验收标准 2」「整作业耗时断言」+ `docs/ci-summary.png` |
| 3 | 断网环境下容器内运行成功（运行日志截图） | `docker run --network none` 跑完整八步 | CI 步骤「验收标准 3」+ `docs/ci-summary.png` |
| 4 | 人为让 eval 步骤失败时不生成报告文件（测试通过） | `--fail-step eval` 故障注入；CI 显式断言 退出码=2 + stderr 含「失败步骤=eval」「未生成报告」+ `report/` 不存在；`tests/test_failure_semantics.py` | CI 步骤「验收标准 4」+ pytest |

## 6. CI 证据（GitHub Actions 真实运行）

- 仓库：<https://github.com/jiaxinchayedan/cal-pipeline>
- 代码提交 `ce715ca` 的验证运行：**run #16** → <https://github.com/jiaxinchayedan/cal-pipeline/actions/runs/45625116056>
- 执行环境：`ubuntu-latest` / Python 3.11.18 / 作业总耗时 **79 秒**（作业级硬上限 `timeout-minutes: 15`）

| 步骤 | 结论 | 耗时 |
|---|---|---|
| 记录作业开始时间 | ✅ | 0s |
| 检出代码 | ✅ | 1s |
| 安装 Python 3.11 | ✅ | 4s |
| 安装依赖（锁文件固定版本） | ✅ | 4s |
| 运行 1（基线，记录耗时） | ✅ | 7s |
| 运行 2（同配置复跑，记录耗时） | ✅ | 7s |
| 验收标准 1 — 两次运行 metrics.json 的 SHA-256 相同 | ✅ | 0s |
| 验收标准 2 — 黄金值一致（差值 <1e-9）且单次流水线 ≤15 分钟 | ✅ | 0s |
| 单元测试（22 个） | ✅ | 32s |
| 清单回验 — `cal verify` 重算全部文件 SHA-256 | ✅ | 0s |
| 验收标准 4 — 人为让 eval 失败时不生成报告 | ✅ | 1s |
| 验收标准 3 — 断网容器内运行（`docker run --network none`） | ✅ | 19s |
| 整作业耗时断言（≤15 分钟） | ✅ | 0s |
| 汇总 | ✅ | 0s |

CI 日志原文摘录（可在上面的 run 链接里逐行核对）：

```text
0429639483244a88a465ee0b0fa9bb4ee397b97504df75d7201d18f1e0b3ddf0  runs/ci-run-1/report/metrics.json
0429639483244a88a465ee0b0fa9bb4ee397b97504df75d7201d18f1e0b3ddf0  runs/ci-run-2/report/metrics.json
PASS 两次运行 metrics.json SHA-256 完全一致：0429639483244a88a465ee0b0fa9bb4ee397b97504df75d7201d18f1e0b3ddf0
比对数值叶子 39 个，最大差值 0.000e+00（容差 1e-09）
PASS 完整流水线耗时均 ≤15 分钟，关键指标与黄金值一致
22 passed in 31.00s
[cal] 校验通过：35 个文件 SHA-256 全部一致（含清单自校验）
PASS 退出码=2、失败步骤与日志路径已输出、report/ 目录不存在
[cal] 流水线完成 | run_id=offline | metrics=runs/offline/report/metrics.json | sha256=0429639483244a88... | 总耗时=7.06s
PASS 容器在 --network none 下完成八步流水线
整作业耗时 75s（含检出、测试、镜像构建）
PASS 整作业耗时 75s ≤ 900s
```

截图（均取自 run #16，非拼接）：

| 截图 | 内容 |
|---|---|
| `docs/ci-steps.png` | 14 个步骤全部绿色通过，含各步耗时与作业总时长 |
| `docs/ci-summary.png` | 两次运行 SHA-256 相同、`cal verify` 35 个文件通过、断网容器 `run_id=offline` 完成日志 |

> 说明：本节的数字与截图绑定 run #16（代码提交 `ce715ca`）。之后若只改文档，会触发同一工作流的再验证（如 #17），
> 结果可在 Actions 页面按 run 编号逐条核对，不存在「截图取一次、数字取另一次」的拼接。

### 6.1 审查与修复记录（真实失败留痕）

| 现象 | 原因 | 处理 |
|---|---|---|
| run #1 红：黄金值比对失败 | 本地 cal.yaml 为 CRLF、CI 检出为 LF，配置哈希不同 | 改为语义哈希 + 回归测试 |
| run #2 红：容器内 `ModuleNotFoundError: cal` | 入口脚本在 `/usr/local/bin`，拿不到 `/app` 的包 | Dockerfile 增加 `PYTHONPATH=/app` |
| run #11 红：整作业耗时断言找不到开始时间 | `actions/checkout` 清理了工作区里的临时文件 | 开始时间改写 `RUNNER_TEMP` |

这些失败运行都保留在 Actions 历史里，可作为「断言确实会红」的旁证。

## 7. 测试结果（本机真实输出）

环境：Windows 11 / Python 3.13.14 / PyYAML 6.0.3 / pytest 8.4.2。

```
$ python -m pytest -q
..............                                                           [100%]
22 passed（耗时随机器负载波动）
```

两次完整运行、哈希一致：

```
$ python -m cal run --config cal.yaml --run-id r1
[cal] 流水线完成 | run_id=r1 | metrics=runs/r1/report/metrics.json | sha256=0429639483244a88a465ee0b0fa9bb4ee397b97504df75d7201d18f1e0b3ddf0 | 总耗时=10.15s
$ python -m cal run --config cal.yaml --run-id r2
[cal] 流水线完成 | run_id=r2 | metrics=runs/r2/report/metrics.json | sha256=0429639483244a88a465ee0b0fa9bb4ee397b97504df75d7201d18f1e0b3ddf0 | 总耗时=11.02s
$ sha256sum runs/r1/report/metrics.json runs/r2/report/metrics.json
0429639483244a88a465ee0b0fa9bb4ee397b97504df75d7201d18f1e0b3ddf0 *runs/r1/report/metrics.json
0429639483244a88a465ee0b0fa9bb4ee397b97504df75d7201d18f1e0b3ddf0 *runs/r2/report/metrics.json
```

黄金值比对：

```
$ python scripts/check_golden.py runs/r1/report/metrics.json golden/metrics.json --tol 1e-9
比对数值叶子 39 个，最大差值 0.000e+00（容差 1e-09）
PASS 关键指标与黄金值完全一致
```

故障注入（验收标准 4）：

```
$ python -m cal run --config cal.yaml --runs-dir runs --run-id demo-fail --fail-step eval
[cal] 流水线中止 | 失败步骤=eval | 日志=runs/demo-fail/logs/eval.log | 未生成报告
$ echo $?
2
$ ls runs/demo-fail
ablation  eval  logs  prepare  profile  replay        # 无 report 目录
```

## 8. 关键指标（当前配置）

| 指标 | 值 |
|---|---|
| 数据规模 | 300 家企业 × 24 个月 / 200 张需求卡 / 60,000 个候选对 |
| 正样本率 | 0.3230 |
| 线上阈值 0.60 下 F1 / AUC | 0.5043 / 0.6676 |
| 扫描后最优阈值 | 0.50（F1 = 0.5241） |
| 权重搜索最优 AUC | 0.6681（27 组组合） |
| 最重要特征 | `resource_overlap`（去掉后 AUC −0.0621） |

## 9. 配置项

| 键 | 含义 |
|---|---|
| `seed` | 唯一熵源，改它则所有数据与指标全变 |
| `data.source` | `generate` 生成虚构数据；`extract` 从 `data/raw/*.jsonl` 脱敏抽取 |
| `data.companies / months / demand_cards` | 数据规模 |
| `model.weights / bias` | 当前线上权重与偏置 |
| `eval.threshold` | 线上在用的阈值（本次为 0.60） |
| `scan_thresholds` | 阈值扫描区间与步长、目标指标 |
| `search.grid` | 权重网格搜索范围 |
| `ablation.features` | 参与消融的特征 |

### 9.1 extract（脱敏抽取）模式

```bash
python -m cal run --config cal.yaml   # cal.yaml 中 data.source 改成 extract
```

读取 `data/raw/` 下 `companies.jsonl`、`demand_cards.jsonl`、`outcomes.jsonl`，对手机号、邮箱、18 位身份证号做正则掩码（`1**********`、`***@masked.invalid`），并把原始表快照到 `runs/<run_id>/prepare/raw/` 以便回验，之后进入后续步骤。仓库自带 3 家企业 / 2 张需求卡的样例原始表，`tests/test_extract.py` 断言产物中不出现任何原始联系方式。

## 10. 边界与已知限制

- **不是算法调优**：流水线封装的是"可复现地跑一遍校准流程"，各步骤内部的模型逻辑保持确定性最小实现，不追求 SOTA 指标。
- **跨机器浮点**：本流水线只承诺同一环境（同一 Python 小版本、同一依赖版本）下逐字节一致；跨架构（如 x86 / ARM）不保证最后一位浮点一致，CI 与本机均为 CPython 3.11/3.13 的 x86_64 环境。
- **`extract` 模式**需自备 `data/raw` 三家原始表，脱敏仅覆盖手机号、邮箱、身份证号三类模式，真实业务字段脱敏策略需按客户规范扩展。
- **数据为虚构**：行业、区域、企业、需求卡均由种子生成，不对应任何真实主体。
- **黄金值的来源**：`golden/metrics.json` 由基线版本首次运行产出，经人工核对后作为「合约」入库。它保证的是「算法与数据不再漂移」，不是「模型效果最优」。任何算法或种子变更都必须同步更新黄金值并在提交说明里写清原因，否则 CI 会红。
- **CI 证据的时效性**：本文所有 CI 数字与截图均绑定同一次运行（run #16 / 代码提交 `ce715ca`）；后续文档变更会触发同样的验证，可在 Actions 页面按 run 编号核对。
