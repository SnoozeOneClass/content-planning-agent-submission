# 内容任务规划 Agent

根据主题、预算和剩余时间检索合成参考资料，由模型选择工具、估算候选计划、调整选材、生成脚本并保存内容活动方案。工具结果决定后续动作；费用、耗时和保存状态由程序核验。

GitHub 仓库：[SnoozeOneClass/content-planning-agent-submission](https://github.com/SnoozeOneClass/content-planning-agent-submission)。仓库已公开，评审无需额外授权即可读取。

## 评审入口

- [需求与验收点](docs/01-requirements.md)
- [调用流程与技术取舍](docs/02-solution.md)
- [测试预期和实际结果](docs/03-evaluation.md)
- [AI 使用记录](docs/04-ai-usage.md)
- [复盘与实际用时](docs/05-retrospective.md)
- [独立模拟验收报告](docs/06-independent-acceptance.md)
- [已确认的工具费用与耗时规则](docs/tool-cost-and-time.md)
- [离线用例结果](examples/mock/results.json)
- [真实 DeepSeek 用例结果](examples/real/results.json)
- [真实超限重规划 Trace](examples/real/replan.trace.md)
- [真实部分成功后续跑 Trace](examples/real/partial-resume.trace.md)

当前验证结果：**34 项自动化测试通过，12/12 组离线验收通过，12/12 组真实 DeepSeek 验收通过**。已记录正常完成、超限后重新选材、工具失败后重试或停止、重复执行和部分成功后续跑等真实路径。离线与真实模型证据分别保存。

## 环境与安装

Python 3.11 或更新版本，无第三方运行依赖。已在 Windows / Python 3.11.15 验证离线测试。下列命令在项目根目录运行，Windows PowerShell 与常规终端均可使用：

```sh
python --version
python -m unittest discover -s tests -v
```

运行依赖为 Python 标准库，依赖说明见 `requirements.txt`；Agent 调用循环采用原生实现。

## 无密钥运行

```sh
python -m src.main --input examples/inputs/normal.json --mode mock
python -m src.main --input examples/inputs/replan.json --mode mock
python -m src.main --input examples/inputs/save-failure.json --mode mock --faults examples/faults/save-always.json
python -m src.evaluate --mode mock
```

一次性重跑测试和离线验收、更新 `examples/test-results.txt`：

```sh
python scripts/verify.py
```

`MockModel` 使用确定性策略验证工具、记账、状态和保存流程。Mock 仅验证流程，模型决策与生成效果通过真实模式的运行记录评估。

## DeepSeek 真实运行

将 `.env.example` 复制为 `.env`（已有 `.env` 时直接编辑），填写 `MODEL_API_KEY`：

```text
MODEL_BASE_URL=https://api.deepseek.com
MODEL_API_KEY=填写自己的密钥
MODEL_NAME=deepseek-flash
MODEL_TIMEOUT_SECONDS=90
```

`.env` 已被 Git 忽略，模型和接口地址通过 `MODEL_NAME`、`MODEL_BASE_URL` 配置。真实模式使用模型原生工具调用决定动作，脚本生成工具调用模型产出具体脚本。默认使用 DeepSeek 非思考模式，Trace 记录公开动作依据和工具结果。

```sh
python -m src.main --input examples/inputs/normal.json --mode real --db runtime/real.sqlite3 --output runtime/normal-real.json
python -m src.evaluate --mode real
```

完整评估会调用模型多次。先检查接入时，可以只执行指定场景：

```sh
python -m src.evaluate --mode real --case normal --case replan --case save-failure
```

接口依据：[DeepSeek 接入说明](https://api-docs.deepseek.com/en/)、[工具调用](https://api-docs.deepseek.com/guides/tool_calls/)。接口异常返回 `MODEL_ERROR`，修复配置后可使用 `--resume` 继续任务。

## 输入与输出

```json
{"request_id":"demo-001","topic":"字幕功能推广","budget":10,"time_budget":30}
```

- 必填：`topic`、`budget`、`time_budget`。预算和时间使用不带后缀的模拟数值。
- `time_budget` 表达任务开始后的相对截止时间，所有工具按费用与耗时表推进模拟时钟。
- `request_id` 可省略，默认根据规范化请求生成；同一请求重复运行返回原结果。
- `script_count` 可选，默认 `1`，指定需要生成的脚本数量。执行计划始终保留用户要求的数量。

输出 JSON 包含 `status`、`task_plan`、`plan_revisions`、`steps`、`scripts`、`spent`、`remaining`、`saved_plan` 和 `reason`。`steps` 包含模型动作依据、工具参数、返回结果、消耗、下一步动作和模型响应标识。

任务状态为 `completed`、`needs_input` 或 `incomplete`。只有数据库实际保存成功才返回 `completed`。输入格式/调用环境错误退出码为 `2`；合法业务请求无论完成与否均返回 JSON，退出码为 `0`，应读取 `status` 判断结果。评估命令存在失败断言时退出码为 `1`。

## 费用与时间

| 工具 | cost | duration |
| --- | --- | --- |
| 素材检索 | `2` | `5` |
| 脚本生成 | `2 + 2*n` | `10 + 5*n` |
| 成本估算 | `0` | `1` |
| 方案保存 | `0` | `2` |

`n` 为本次生成实际处理的去重素材数量。一旦工具启动，即便失败也记入该次消耗；执行前被参数、依赖或额度检查拦截的动作不扣费。估算只产生报价，不扣除未执行的生成费用。

## 保存、防重复与续跑

方案保存在本地 SQLite 的 `plans` 表中，`request_id` 为唯一键；完整成果也包含在 CLI 输出中。输出文件可用 `--output` 导出。重复请求不再次调用模型、不重复计费或保存。相同 ID 对应的输入、素材、费率或运行模式发生变化时返回 `REQUEST_CONFLICT`，请使用新 ID 或独立数据库。

```sh
python -m src.main --input examples/inputs/partial-resume.json --mode mock --db runtime/resume.sqlite3 --faults examples/faults/second-script.json
python -m src.main --input examples/inputs/partial-resume.json --mode mock --db runtime/resume.sqlite3 --faults examples/faults/second-script.json --resume
```

第一条命令保留已成功的脚本，第二条只处理未完成步骤。累计费用、时间和决策次数继续保留。默认最多 `16` 次模型决策，含被拒绝的动作；`--max-steps` 可调整到 `1–100`，达到上限明确返回 `STEP_LIMIT`，续跑不重置计数。

评估命令为每个用例创建独立临时数据库，因此可以重复执行而不会把上次缓存误当成本次运行。实际输出、Trace 和检查结果保存到 `examples/mock/` 或 `examples/real/`。

## 提交

所有代码、合成资料、文档、测试和运行材料放在同一仓库。正式题号以公司原题编号为准；选题名称为“内容任务规划 Agent”。提交时使用本页仓库 URL，并执行以下命令取得最终 SHA：

```sh
git rev-parse HEAD
python scripts/check_submission.py
```

`.env`、运行数据库和临时文件由 `.gitignore` 排除。提交检查脚本核对材料完整性、运行证据和 Git 提交状态。
