# 内容任务规划 Agent 独立模拟验收报告

验收日期：2026-10-30，北京时间。

验收基线：`0aa2ca62bf5d277c2e2e54d986a1ab955ae5ef23`。本报告由独立子 Agent 依据题目要求、用户已确认的费率和数据范围完成；未修改产品代码、未覆盖原运行证据、未执行 Git 提交。

## 整体结论

**本地技术验收通过，可进入仓库提交环节；正式对外提交为有条件通过，条件是补齐 GitHub URL 并验证评审可读。**

在本次验收范围内，未发现可复现的阻断性代码缺陷。正常完成、缺预算/时间、工具失败、预算超限、重复执行均有可运行实现和证据；执行上限、时间约束及失败步骤续跑也通过检查。真实模式的动态决策不是由离线 Mock 或固定日志代替。

本结论不附精确分数，题面未提供评分权重。未要求额外实现素材重复度分析、向量库、界面、线上部署或生产级运行时。

## 本次验收范围与证据来源

| 验证方式 | 本次实际工作 | 能证明什么 |
| --- | --- | --- |
| 原自动化测试重跑 | 34 项测试通过，退出码 0 | 工具约束、记账、持久化、参数与模型接口协议 |
| CLI 独立实跑 | 新数据库中执行 12 类场景、14 次 CLI，均符合预期 | 命令可复制，程序的实际状态、费用和保存结果一致 |
| 额外边界验证 | 5 个独立边界用例通过 | 等额边界、差额阻断、ID 计数和保存失败时的时间约束 |
| 已有真实模型记录复核 | 逐步检查 12 类用例中的 14 份运行记录 | 费率、累计消耗、引用范围、动作调整与记录的一致性 |
| 真实文本阅读 | 对照资料阅读最终 7 条不同脚本的标题与旁白 | 当前合成资料上的内容依据与主题一致性 |

**本轮新跑的 CLI 使用 `mock` 模式；5 个边界用例使用明确标记的协议替身。没有新增模型 API 调用。** 真实模型部分复核的是原提交中已经保存的 DeepSeek 运行记录，不能将本轮离线结果描述为新一轮真实模型成功率。

真实模式的 12 类用例中，缺预算、缺时间的 2 类在输入校验阶段返回，没有调用模型。其余记录可去重得到 45 个模型决策 response ID 和 7 个脚本生成 response ID；重复执行和续跑输出里重复出现的历史记录未重复计数。

本次没有读取或打印 API Key。CLI 显式使用不存在的 `--env-file runtime/acceptance-no-env`，且子进程的模型密钥为空。真实模式原记录中的响应 ID 为可核对的记录标识，本轮未再次向模型服务请求验证。

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

CLI 的业务未完成状态按 README 约定返回退出码 `0`，判断是否完成必须读取 JSON 的 `status`。本次验收按预期业务状态检查，不把所有退出码 `0` 都解释为任务完成。

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
| AI 使用、实际用时与限制 | 通过 | `docs/04-ai-usage.md` 与 `docs/05-retrospective.md` 明确责任、改进、计时范围和剩余提交事项 |
| GitHub URL 与评审访问 | 尚待外部完成 | 基线 `git remote -v` 无输出，仓库尚未创建；这是已知提交条件，不是新增代码缺陷 |

## 真实动态决策证据复核

### 路径一 正常估算后完成

[真实 normal Trace](../examples/real/normal.trace.md) 中，步骤 1 检索、步骤 2 估算、步骤 3 生成、步骤 4 保存。四份资料的生成费用为 `2 + 2*4 = 10`，连同检索共 12；耗时为 `5 + 1 + 30 + 2 = 38`。

### 路径二 超限后重新选材

[真实 replan Trace](../examples/real/replan.trace.md) 中：

1. 步骤 2 选择 M01–M04，工具返回预计费用 12、耗时 38，不可行。
2. 步骤 3 模型根据超限结果改选 M01、M04，公开依据为保留添加编辑与时间同步能力；再次估算为费用 8、耗时 29。
3. 步骤 4、5 才执行生成与保存。

素材选择并非固定取排序前两条，实际参数和原因来自记录中的模型响应。复算同时包含两次估算耗时，未将初始报价 12 误计为已支出。

### 路径三 错误结果改变后续动作

[真实生成失败 Trace](../examples/real/tool-failure.trace.md) 中，步骤 3 返回可重试错误后，模型在步骤 4 根据剩余额度选择重试；失败调用费用仍保留，最终费用 22、耗时 68。

[真实保存失败 Trace](../examples/real/save-failure.trace.md) 中，步骤 4 返回不可恢复的存储错误，步骤 5 模型选择 `finish`；任务明确未完成，`saved_plan` 为 null，生成脚本保留。

[真实续跑 Trace](../examples/real/partial-resume.trace.md) 的首次运行保留 S1，S2 失败后停止在费用 14、耗时 46；显式恢复后只重做 S2 并保存，最终费用 20、耗时 68。旧的成功结果及响应 ID 保持不变。

这些事实支持“模型根据工具返回调整下一步”的判断。程序的硬性预算检查、防重或自动结束本身不计作模型决策证据。

## 独立边界与反例检查

这五项使用固定动作序列主动请求工具，用来核验程序底线；不作为真实模型行为证据。

| 边界 | 预期 | 实际 | 材料 |
| --- | --- | --- | --- |
| 一份素材，预算 6、时间 23 | 恰好完成 | completed，6 / 23，保存 1 行 | [输出](../examples/acceptance/boundary/exact-boundary.json) |
| 一份素材，预算 6、时间 22 | 因缺保存所需总时间而阻断 | incomplete，只消耗检索与估算的 2 / 6，保存 0 行 | [输出](../examples/acceptance/boundary/time-one-short.json) |
| 一份素材，预算 5、时间 23 | 预算差 1 不执行生成 | incomplete，2 / 6，保存 0 行 | [输出](../examples/acceptance/boundary/budget-one-short.json) |
| 同一个素材 ID 在输入中出现两次 | 按唯一 ID 数量计费 | completed，6 / 23 | [输出](../examples/acceptance/boundary/duplicate-id.json) |
| 恰好到截止时间时保存失败，再请求保存 | 不超时重试、不虚报保存成功 | incomplete，6 / 23，脚本保留、保存 0 行 | [输出](../examples/acceptance/boundary/save-fails-at-deadline.json) |

费用复算函数没有调用产品的 `Rates.quote`，而是直接按已确认的四条费率独立计算，避免用同一计算函数同时产生结果和验证结果。

## 缺陷、提交条件与复测建议

**本次没有发现需要修复后才能提交的 P0/P1/P2 产品代码缺陷。** 此结论限于已说明的代码检查、实跑用例和现有真实记录范围，不代表穷尽所有输入。

| 项目 | 性质与影响 | 建议 |
| --- | --- | --- |
| GitHub URL / 评审可读权限尚未落地 | 正式交付前必须完成；本地通过不能替代仓库提交 | 按用户安排创建仓库、推送最终提交，核对公开可读或指定评审权限 |
| 本次报告与证据尚未提交 | 审计产物产生的工作区变化，不是原基线缺陷 | 如纳入交付，提交报告及 `examples/acceptance/` 后重新取得最终 SHA |
| 后续更换素材、模型或提示词 | 可能改变脚本内容和实际路径 | 重跑对应真实场景，并检查旁白与所引素材；不只看汇总通过数字 |

审计开始时原基线干净，`check_submission.py` 返回通过。新增本报告及证据之后，该脚本会因未提交文件返回未就绪，这是本轮新增材料的正常状态，不能倒推为原提交存在脏工作区。

## 未验证范围与已知边界

- 本轮没有重新调用 DeepSeek，也没有再次向服务商验证现有 response ID；真实决策结论基于原始运行文件与代码逻辑的交叉复核。
- 没有在其他操作系统、模型供应商或大规模资料库上复测。
- 没有测试任意自然语言输入的最优选材、通用事实正确性或生产级并发/崩溃恢复；这些不作为本题新增要求。
- 模拟时间遵循用户确认的相对时间额度，不表示真实 API 延迟；该边界已在项目说明中写明。
- 对当前七条脚本逐条阅读后，标题和旁白的功能描述能够对应给定素材；这不等于自动事实验证器已经实现。

最终建议：保留当前范围，把报告及复测证据按需要纳入最终提交，完成 GitHub 交付信息后即可提交评审。

## 发布准备补记

独立验收结束后，主 Agent 根据用户指令创建了仓库 [SnoozeOneClass/content-planning-agent-submission](https://github.com/SnoozeOneClass/content-planning-agent-submission)，并将本报告及本次验收证据纳入发布版本的提交材料。仓库随后按用户要求改为公开，已通过不携带凭据的请求确认可匿名读取。前述工作区状态和 GitHub 缺项描述是验收基线时的记录，独立验收结论未作修改；GitHub URL 和公开读取条件现已补齐。
