# 内容任务规划 Agent 独立模拟验收报告

验收日期：2026-10-30，北京时间。

技术验收基线：`0aa2ca62bf5d277c2e2e54d986a1ab955ae5ef23`。独立子 Agent 依据题目要求、已确认费率和数据范围完成实跑与证据复核；发布状态根据后续仓库检查同步更新。

本报告保留基线版本的独立验收记录。后续四项 P2 修复及最新回归结果见[测试与评估](03-evaluation.md)。

## 整体结论

**技术验收通过，核心功能与验证材料符合本题要求。公开仓库已发布并确认可访问。**

正常完成、缺预算/时间、工具失败、预算超限和重复执行均通过核验；执行上限、时间约束及失败步骤续跑也符合预期。真实模式记录展示了模型依据工具返回选择后续动作的过程。本次验收未发现阻断性代码缺陷。

## 本次验收范围与证据来源

| 验证方式 | 本次实际工作 | 能证明什么 |
| --- | --- | --- |
| 原自动化测试重跑 | 34 项测试通过，退出码 0 | 工具约束、记账、持久化、参数与模型接口协议 |
| CLI 独立实跑 | 新数据库中执行 12 类场景、14 次 CLI，均符合预期 | 命令可复制，程序的实际状态、费用和保存结果一致 |
| 额外边界验证 | 5 个独立边界用例通过 | 等额边界、差额阻断、ID 计数和保存失败时的时间约束 |
| 已有真实模型记录复核 | 逐步检查 12 类用例中的 14 份运行记录 | 费率、累计消耗、引用范围、动作调整与记录的一致性 |
| 真实文本阅读 | 对照资料阅读最终 7 条不同脚本的标题与旁白 | 当前合成资料上的内容依据与主题一致性 |

本轮 CLI 实跑使用 `mock` 模式，5 个边界用例使用协议替身检查程序约束；真实模型部分通过复核已有 DeepSeek 运行记录，检查决策、结果与消耗的一致性。

真实模式的 12 类用例中，缺预算、缺时间的 2 类在输入校验阶段返回，没有调用模型。其余记录可去重得到 45 个模型决策 response ID 和 7 个脚本生成 response ID；重复执行和续跑输出里重复出现的历史记录未重复计数。

离线 CLI 使用 `--env-file runtime/acceptance-no-env` 并清空子进程的模型密钥，可直接复现本轮程序行为检查。

## 可复现命令与运行材料

从项目根目录执行：

```sh
python -X utf8 examples/acceptance/run_acceptance.py
```

本次退出码为 `0`，汇总为：

```json
{
  "all_checks_passed": true,
  "cli_runs": 14,
  "boundary_cases": 5,
  "real_records_checked": 14
}
```

- [验收执行脚本](../examples/acceptance/run_acceptance.py)：每次创建新的 `runtime/acceptance-<随机 ID>/` 数据库目录。
- [完整结果与逐条命令](../examples/acceptance/results.json)：记录命令、退出码、输出文件、数据库行数与断言结果。
- [自动化测试原始输出](../examples/acceptance/unit-tests.stderr.txt)：`python -X utf8 -m unittest discover -s tests -v`，34 项通过。
- [基线检查记录](../examples/acceptance/baseline-check.txt)：审计文件创建前工作区干净，原提交检查器返回通过。

CLI 对合法业务请求返回 JSON 和退出码 `0`，任务结果由 `status` 表达。本次验收分别检查命令是否正常执行，以及业务状态是否符合用例预期。

## 逐项验收矩阵

| 要求 | 验收结论 | 依据 |
| --- | --- | --- |
| 用户主题、预算、时间输入 | 通过 | `src/domain.py:35` 校验；缺字段不填默认预算或时间 |
| 合成素材和工具费率数据 | 通过 | `data/materials.json` 仅有三类约定字段；`data/tool_rates.json` 符合固定表 |
| 四个业务工具 | 通过 | `src/agent.py:153` 执行入口及四个分支；`finish` 仅是结束控制动作 |
| 任务计划、步骤状态、工具结果、费用合计 | 通过 | CLI 输出的 `task_plan`、`steps`、`spent`，已对照实际返回和独立费用重算 |
| 已保存方案或未完成原因 | 通过 | `src/agent.py:180` 阻止提前保存；实际数据库中仅完成场景有方案行 |
| 正常完成 | 通过 | [独立 CLI 输出](../examples/acceptance/cli/normal-1.json)：completed，费用 12，耗时 38，方案行数 1 |
| 缺预算或截止时间 | 通过 | [缺预算](../examples/acceptance/cli/missing-budget-1.json)、[缺时间](../examples/acceptance/cli/missing-time-1.json)：needs_input，0 费用、0 耗时，无工具执行 |
| 工具失败 | 通过 | [生成失败](../examples/acceptance/cli/tool-failure-1.json) 记录失败消耗；[保存失败](../examples/acceptance/cli/save-failure-1.json) 返回 incomplete 且方案行数 0，已生成脚本保留 |
| 预算超限 | 通过 | [调整后完成](../examples/acceptance/cli/replan-1.json) 为 8 / 29；[无可行解](../examples/acceptance/cli/over-budget-1.json) 返回缺口，未超支 |
| 时间约束 | 通过 | [无时间可行解](../examples/acceptance/cli/out-of-time-1.json) 未保存；额外边界证明保存耗时也计入约束 |
| 重复执行 | 通过 | [第一次](../examples/acceptance/cli/repeat-1.json)、[第二次](../examples/acceptance/cli/repeat-2.json)：相同方案、消耗和步骤，第二次 replayed=true，数据库仅 1 行 |
| 失败步骤续跑 | 通过，加分项已实现 | [首次失败](../examples/acceptance/cli/partial-resume-1.json) 保留一条脚本；[续跑](../examples/acceptance/cli/partial-resume-2.json) 保留该脚本并补齐结果，不重做成功步骤 |
| 模型决策循环 | 通过 | `src/model.py:86` 读取真实状态并请求工具选择，`src/agent.py:77` 执行模型动作；实际状态回传下一轮 |
| 至少两条不同动态路径 | 通过 | 正常与超限、可恢复与不可恢复错误、部分成功后续跑均有不同实际后续动作，见下一节 |
| 步数上限与明确未完成状态 | 通过 | `src/agent.py:71`；[独立上限输出](../examples/acceptance/cli/step-limit-1.json) 返回 STEP_LIMIT |
| 可复制运行方式与依赖 | 通过 | README CLI 命令可执行；Python 3.11 标准库，无额外框架依赖 |
| 规定文档与验证材料 | 通过 | README、src、tests、examples、data、五份规定文档、依赖文件和 .env.example 均存在 |
| AI 使用、实际用时与限制 | 通过 | `docs/04-ai-usage.md` 与 `docs/05-retrospective.md` 记录分工、改进、计时范围与后续优化 |
| GitHub URL 与评审访问 | 发布后核对通过 | [公开仓库](https://github.com/SnoozeOneClass/content-planning-agent-submission) 已确认可匿名读取 |

## 真实动态决策证据复核

### 路径一 正常估算后完成

[基线 normal Trace](https://github.com/SnoozeOneClass/content-planning-agent-submission/blob/0aa2ca62bf5d277c2e2e54d986a1ab955ae5ef23/examples/real/normal.trace.md) 中，步骤 1 检索、步骤 2 估算、步骤 3 生成、步骤 4 保存。四份资料的生成费用为 `2 + 2*4 = 10`，连同检索共 12；耗时为 `5 + 1 + 30 + 2 = 38`。

### 路径二 超限后重新选材

[基线 replan Trace](https://github.com/SnoozeOneClass/content-planning-agent-submission/blob/0aa2ca62bf5d277c2e2e54d986a1ab955ae5ef23/examples/real/replan.trace.md) 中：

1. 步骤 2 选择 M01–M04，工具返回预计费用 12、耗时 38，不可行。
2. 步骤 3 模型根据超限结果改选 M01、M04，公开依据为保留添加编辑与时间同步能力；再次估算为费用 8、耗时 29。
3. 步骤 4、5 才执行生成与保存。

模型保留了支持添加编辑和时间同步的 M01、M04，实际参数与依据均记录在 Trace 中。独立复算包含两次估算耗时，并分别核对候选报价与实际支出。

### 路径三 错误结果改变后续动作

[基线生成失败 Trace](https://github.com/SnoozeOneClass/content-planning-agent-submission/blob/0aa2ca62bf5d277c2e2e54d986a1ab955ae5ef23/examples/real/tool-failure.trace.md) 中，步骤 3 返回可重试错误后，模型在步骤 4 根据剩余额度选择重试；失败调用费用仍保留，最终费用 22、耗时 68。

[基线保存失败 Trace](https://github.com/SnoozeOneClass/content-planning-agent-submission/blob/0aa2ca62bf5d277c2e2e54d986a1ab955ae5ef23/examples/real/save-failure.trace.md) 中，步骤 4 返回不可恢复的存储错误，步骤 5 模型选择 `finish`；任务明确未完成，`saved_plan` 为 null，生成脚本保留。

[基线续跑 Trace](https://github.com/SnoozeOneClass/content-planning-agent-submission/blob/0aa2ca62bf5d277c2e2e54d986a1ab955ae5ef23/examples/real/partial-resume.trace.md) 的首次运行保留 S1，S2 失败后停止在费用 14、耗时 46；显式恢复后只重做 S2 并保存，最终费用 20、耗时 68。旧的成功结果及响应 ID 保持不变。

上述记录展示了模型在可行估算、超限反馈、可恢复错误和不可恢复错误下的不同动作；预算检查、防重和持久化状态由程序约束保障。

## 独立边界与反例检查

这五项使用固定动作序列主动请求工具，核验费用、时间、依赖和保存约束。

| 边界 | 预期 | 实际 | 材料 |
| --- | --- | --- | --- |
| 一份素材，预算 6、时间 23 | 恰好完成 | completed，6 / 23，保存 1 行 | [输出](../examples/acceptance/boundary/exact-boundary.json) |
| 一份素材，预算 6、时间 22 | 因缺保存所需总时间而阻断 | incomplete，只消耗检索与估算的 2 / 6，保存 0 行 | [输出](../examples/acceptance/boundary/time-one-short.json) |
| 一份素材，预算 5、时间 23 | 预算差 1 不执行生成 | incomplete，2 / 6，保存 0 行 | [输出](../examples/acceptance/boundary/budget-one-short.json) |
| 同一个素材 ID 在输入中出现两次 | 按唯一 ID 数量计费 | completed，6 / 23 | [输出](../examples/acceptance/boundary/duplicate-id.json) |
| 恰好到截止时间时保存失败，再请求保存 | 不超时重试、不虚报保存成功 | incomplete，6 / 23，脚本保留、保存 0 行 | [输出](../examples/acceptance/boundary/save-fails-at-deadline.json) |

费用复算直接按已确认的四条费率独立计算，与产品中的 `Rates.quote` 分开实现。

## 交付状态与复测建议

| 项目 | 当前状态 | 核对方式 |
| --- | --- | --- |
| 仓库与访问 | 已公开发布 | 通过 README 中的 GitHub URL 直接读取 |
| 验收报告与证据 | 已纳入仓库 | 本报告及 `examples/acceptance/` 保存完整命令与结果 |
| 提交版本 | 以最终 main 分支为准 | 使用 `git rev-parse HEAD` 核对 SHA，执行提交检查脚本 |
| 后续修改 | 按对应场景回归 | 更换素材、模型或提示词后，对比任务状态、执行消耗和生成内容 |

## 验收适用范围

本轮在 Windows、Python 3.11 环境下完成，使用项目内两个主题的合成资料和既定模拟费率。程序约束通过独立实跑检查，真实决策通过已有运行记录交叉复核，七条脚本的标题和旁白通过逐条对照素材检查。

后续扩展主题、素材规模或模型接入时，可沿用本报告的命令和核对方法补充回归材料。步骤级恢复的适用范围见[方案文档](02-solution.md)。

## 发布状态

[SnoozeOneClass/content-planning-agent-submission](https://github.com/SnoozeOneClass/content-planning-agent-submission) 已公开，匿名读取检查通过。本报告与独立验收证据已随项目发布。
