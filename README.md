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
python -m cal run --config cal.yaml --fail-step eval   # 故障注入（验证失败语义）
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
3. **配置哈希跨平台一致**：`config_sha256` 按规范化文本（CRLF/CR → LF）计算，避免 Windows 检出（CRLF）与 Linux CI（LF）算出不同哈希。
4. **产物不含易变信息**：`metrics.json` 不写时间戳、不写 run_id，所以两次运行能逐字节一致。
5. **依赖锁版本**：`requirements.lock` 固定 PyYAML 6.0.2 / pytest 8.3.4 等版本，CI 与本机一致（Python 3.11）。
6. **运行目录隔离**：默认 `run_id` 带 UTC 时间戳；同一 run_id 目录已存在时拒绝运行，避免复用半成品目录。
7. **清单不含绝对路径**：`manifest.json` 只记录配置文件名与哈希，换目录运行清单结构不变。
8. **哈希清单**：`manifest.json` 记录每步输入/输出的 SHA-256 与字节数，任何一步产物变化都能定位。

## 5. 验收标准对照

| # | 验收标准原文 | 对应实现 | 证据位置 |
|---|---|---|---|
| 1 | 同一配置运行两次，指标 JSON 的 SHA-256 相同（CI 日志截图） | CI 中 `ci-run-1`、`ci-run-2` 两次运行后 `sha256sum` 比对 | CI 步骤「验收标准 1」+ `docs/ci-run4-search-pass.png` |
| 2 | CI 中完整流水线 ≤15 分钟，关键指标与黄金值一致（CI 日志截图） | `scripts/check_golden.py` 逐数值叶子比对，容差 1e-9；单次流水线约 10 秒 | CI 步骤「验收标准 2」+ `docs/ci-run4-offline.png` |
| 3 | 断网环境下容器内运行成功（运行日志截图） | `docker run --network none` 跑完整八步 | CI 步骤「验收标准 3」+ `docs/ci-run4-offline.png` |
| 4 | 人为让 eval 步骤失败时不生成报告文件（测试通过） | `--fail-step eval` 故障注入；`tests/test_failure_semantics.py` | CI 步骤「验收标准 4」+ pytest |

## 6. CI 证据（GitHub Actions 真实运行）

- 仓库：<https://github.com/jiaxinchayedan/cal-pipeline>
- 验收运行：**run #4**（commit `d08f30d`）→ <https://github.com/jiaxinchayedan/cal-pipeline/actions/runs/45616297448>
- 执行环境：`ubuntu-latest` / Python 3.11.18 / 作业总耗时 **38 秒**（上限 15 分钟）

| 步骤 | 结论 | 耗时 |
|---|---|---|
| 检出代码 | ✅ | 1s |
| 安装 Python 3.11 | ✅ | 0s |
| 安装依赖（锁文件固定版本） | ✅ | 2s |
| 运行 1（基线） | ✅ | 4s |
| 运行 2（同配置复跑） | ✅ | 4s |
| 验收标准 1 — 两次运行 metrics.json 的 SHA-256 相同 | ✅ | 0s |
| 验收标准 2 — 关键指标与黄金值一致（差值 <1e-9） | ✅ | 0s |
| 单元测试 | ✅ | 14s |
| 验收标准 4 — eval 失败不生成报告 | ✅ | 0s |
| 验收标准 3 — 断网容器内运行（`docker run --network none`） | ✅ | 10s |
| 汇总 | ✅ | 0s |

CI 日志原文摘录：

```text
b2f36fb4aeb3ea00d08a25869e0d98f7608d54c91fdc5193034d2d026c0a4a03  runs/ci-run-1/report/metrics.json
b2f36fb4aeb3ea00d08a25869e0d98f7608d54c91fdc5193034d2d026c0a4a03  runs/ci-run-2/report/metrics.json
PASS 两次运行 metrics.json SHA-256 完全一致：b2f36fb4aeb3ea00d08a25869e0d98f7608d54c91fdc5193034d2d026c0a4a03
比对数值叶子 39 个，最大差值 0.000e+00（容差 1e-09）
PASS 关键指标与黄金值完全一致
run1_seconds=4
run2_seconds=4
14 passed in 13.21s
PASS eval 失败后 report/ 目录不存在，失败步骤与日志路径已输出
[cal] 流水线完成 | run_id=offline | metrics=runs/offline/report/metrics.json | sha256=b2f36fb4aeb3ea00d08a25869e0d98f7608d54c91fdc5193034d2d026c0a4a03
PASS 容器在 --network none 下完成八步流水线（上方日志可见 [cal] 流水线完成）
```

运行页面截图（真实页面，可直接对照上面的链接）：

| 截图 | 内容 |
|---|---|
| `docs/ci-run4-steps.png` | 11 个步骤全部绿色通过 + 各步耗时 + 作业总时长 38s |
| `docs/ci-run4-search-pass.png` | 日志搜索 `PASS`：两次运行 SHA-256 完全相同 |
| `docs/ci-run4-offline.png` | 黄金值比对 39 个数值叶子差值 0 + `docker run --network none` 断网运行 |

## 7. 测试结果（本机真实输出）

环境：Windows 11 / Python 3.13.14 / PyYAML 6.0.3 / pytest 8.4.2。

```
$ python -m pytest -q
..............                                                           [100%]
20 passed in 30.22s
```

两次完整运行、哈希一致：

```
$ python -m cal run --config cal.yaml --run-id r1
[cal] 流水线完成 | run_id=r1 | metrics=runs/r1/report/metrics.json | sha256=b2f36fb4aeb3ea00d08a25869e0d98f7608d54c91fdc5193034d2d026c0a4a03 | 总耗时=10.15s
$ python -m cal run --config cal.yaml --run-id r2
[cal] 流水线完成 | run_id=r2 | metrics=runs/r2/report/metrics.json | sha256=b2f36fb4aeb3ea00d08a25869e0d98f7608d54c91fdc5193034d2d026c0a4a03 | 总耗时=11.02s
$ sha256sum runs/r1/report/metrics.json runs/r2/report/metrics.json
b2f36fb4aeb3ea00d08a25869e0d98f7608d54c91fdc5193034d2d026c0a4a03 *runs/r1/report/metrics.json
b2f36fb4aeb3ea00d08a25869e0d98f7608d54c91fdc5193034d2d026c0a4a03 *runs/r2/report/metrics.json
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

读取 `data/raw/` 下 `companies.jsonl`、`demand_cards.jsonl`、`outcomes.jsonl`，对手机号、邮箱、18 位身份证号做正则掩码（`1**********`、`***@masked.invalid`）后再进入后续步骤。仓库自带 3 家企业 / 2 张需求卡的样例原始表，`tests/test_extract.py` 断言产物中不出现任何原始联系方式。

## 10. 边界与已知限制

- **不是算法调优**：流水线封装的是"可复现地跑一遍校准流程"，各步骤内部的模型逻辑保持确定性最小实现，不追求 SOTA 指标。
- **跨机器浮点**：本流水线只承诺同一环境（同一 Python 小版本、同一依赖版本）下逐字节一致；跨架构（如 x86 / ARM）不保证最后一位浮点一致，CI 与本机均为 CPython 3.11/3.13 的 x86_64 环境。
- **`extract` 模式**需自备 `data/raw` 三家原始表，脱敏仅覆盖手机号、邮箱、身份证号三类模式，真实业务字段脱敏策略需按客户规范扩展。
- **数据为虚构**：行业、区域、企业、需求卡均由种子生成，不对应任何真实主体。
