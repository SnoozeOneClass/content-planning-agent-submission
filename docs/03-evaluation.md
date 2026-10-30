# 测试与评估

## 执行命令

```sh
python -m unittest discover -s tests -v
python -m src.evaluate --mode mock
python -m src.evaluate --mode real
```

单元与集成测试检查业务约束、存储和模型接口协议；协议测试使用进程内 HTTP 传输替身，模型决策效果由真实运行评估。`evaluate` 为每个用例使用独立数据库，保存实际输出、逐步 Trace 和断言结果。

当前 **56/56 项自动化测试通过**。执行 `python scripts/verify.py` 可同时重现测试与离线验收，并更新[实际测试结果](../examples/test-results.txt)。

部分用例可通过 `--case` 指定，默认写入独立的 `runtime/evaluations/` 子目录。已有完整验收索引受到保护；需要固定目录时，使用 `--out runtime/real-smoke` 等独立位置。

## 离线实际结果

离线流程回归 **12/12 通过**，结果见 [results.json](../examples/mock/results.json)。这些用例检查工具执行、费用与时间、保存及恢复状态。

预算不足、资料不足或工具故障时，程序通过 `needs_input` 或 `incomplete` 返回原因并保留已有成果。这些状态是异常场景的预期结果，对应的处理功能已经实现并通过验收。

| 场景 | 预期 | 实际状态 | 累计费用 / 耗时 | 材料 |
| --- | --- | --- | --- | --- |
| 正常 | 生成并保存 | completed | 12 / 38 | [输入](../examples/inputs/normal.json)、[输出](../examples/mock/normal.output.json)、[Trace](../examples/mock/normal.trace.md) |
| 超限后调整 | 调整选材并重新估算 | completed | 8 / 29 | [输入](../examples/inputs/replan.json)、[输出](../examples/mock/replan.output.json)、[Trace](../examples/mock/replan.trace.md) |
| 缺预算 | 明确缺失字段，无工具调用 | needs_input | 0 / 0 | [输入](../examples/inputs/missing-budget.json)、[输出](../examples/mock/missing-budget.output.json)、[Trace](../examples/mock/missing-budget.trace.md) |
| 缺时间 | 明确缺失字段，无工具调用 | needs_input | 0 / 0 | [输入](../examples/inputs/missing-time.json)、[输出](../examples/mock/missing-time.output.json)、[Trace](../examples/mock/missing-time.trace.md) |
| 生成暂时失败 | 保留检索结果，失败如实记账 | completed | 22 / 69 | [输入](../examples/inputs/tool-failure.json)、[输出](../examples/mock/tool-failure.output.json)、[Trace](../examples/mock/tool-failure.trace.md) |
| 保存失败 | 返回保存失败原因并保留脚本 | incomplete | 12 / 38 | [输入](../examples/inputs/save-failure.json)、[输出](../examples/mock/save-failure.output.json)、[Trace](../examples/mock/save-failure.trace.md) |
| 无预算可行解 | 未完成并报告缺口 | incomplete | 2 / 8 | [输入](../examples/inputs/over-budget.json)、[输出](../examples/mock/over-budget.output.json)、[Trace](../examples/mock/over-budget.trace.md) |
| 无时间可行解 | 未完成并报告缺口 | incomplete | 2 / 8 | [输入](../examples/inputs/out-of-time.json)、[输出](../examples/mock/out-of-time.output.json)、[Trace](../examples/mock/out-of-time.trace.md) |
| 无资料 | 说明资料缺口并停止生成 | incomplete | 4 / 10 | [输入](../examples/inputs/no-materials.json)、[输出](../examples/mock/no-materials.output.json)、[Trace](../examples/mock/no-materials.trace.md) |
| 重复执行 | 两次输出对应同一份保存结果 | completed | 12 / 38，无新增 | [输入](../examples/inputs/repeat.json)、[两次输出](../examples/mock/repeat.output.json)、[Trace](../examples/mock/repeat.trace.md) |
| 部分成功后续跑 | 保留第一条脚本，只补第二条 | completed | 32 / 99，含失败消耗 | [输入](../examples/inputs/partial-resume.json)、[两次输出](../examples/mock/partial-resume.output.json)、[Trace](../examples/mock/partial-resume.trace.md) |
| 执行上限 | 明确 STEP_LIMIT | incomplete | 2 / 5 | [输入](../examples/inputs/step-limit.json)、[输出](../examples/mock/step-limit.output.json)、[Trace](../examples/mock/step-limit.trace.md) |

故障配置位于 [examples/faults](../examples/faults)。评估逐项核对：累计消耗与 Trace 相等、预算/时间非负、保存输出与数据库一致、失败后保留成功成果、重复执行不新增步骤，以及续跑不重做成功脚本。

## 真实模型验证

使用 `deepseek-flash` 原生工具调用完成真实验收。四项 P2 修复后完整重跑，**12/12 组程序化验收通过**，最新记录见 [真实 results.json](../examples/real/results.json)。动作由模型响应产生，Trace 保留 response ID、tool call ID 和工具执行结果。缺输入的两组由输入校验直接返回。

| 场景 | 实际状态 | 费用 / 耗时 | 实际材料 |
| --- | --- | --- | --- |
| 正常 | completed | 12 / 38 | [输出](../examples/real/normal.output.json)、[Trace](../examples/real/normal.trace.md) |
| 超限后调整 | completed | 8 / 30 | [输出](../examples/real/replan.output.json)、[Trace](../examples/real/replan.trace.md) |
| 缺预算 | needs_input | 0 / 0 | [输出](../examples/real/missing-budget.output.json)、[Trace](../examples/real/missing-budget.trace.md) |
| 缺时间 | needs_input | 0 / 0 | [输出](../examples/real/missing-time.output.json)、[Trace](../examples/real/missing-time.trace.md) |
| 生成暂时失败 | completed | 22 / 68 | [输出](../examples/real/tool-failure.output.json)、[Trace](../examples/real/tool-failure.trace.md) |
| 保存失败 | incomplete | 12 / 40 | [输出](../examples/real/save-failure.output.json)、[Trace](../examples/real/save-failure.trace.md) |
| 无预算可行解 | incomplete | 2 / 7 | [输出](../examples/real/over-budget.output.json)、[Trace](../examples/real/over-budget.trace.md) |
| 无时间可行解 | incomplete | 2 / 8 | [输出](../examples/real/out-of-time.output.json)、[Trace](../examples/real/out-of-time.trace.md) |
| 无资料 | incomplete | 8 / 20 | [输出](../examples/real/no-materials.output.json)、[Trace](../examples/real/no-materials.trace.md) |
| 重复执行 | completed | 12 / 38，无新增 | [两次输出](../examples/real/repeat.output.json)、[Trace](../examples/real/repeat.trace.md) |
| 部分成功后续跑 | completed | 20 / 69 | [两次输出](../examples/real/partial-resume.output.json)、[Trace](../examples/real/partial-resume.trace.md) |
| 执行上限 | incomplete | 2 / 5 | [输出](../examples/real/step-limit.output.json)、[Trace](../examples/real/step-limit.trace.md) |

其中三组可重点复核动态决策：

1. 正常请求选择 M01–M04，估算通过后生成并保存。受限请求先得到费用 12、耗时 38 的超限反馈，再缩减为三份素材，估算为费用 10、耗时 34；模型随后改为 M01、M02，估算为费用 8、耗时 30，完成生成与保存。
2. 生成工具返回可重试错误后，模型依据剩余额度选择重试。本轮保存失败场景中，模型额外尝试了一次保存，连续失败后停止；两次保存耗时均已计入，总耗时为 40，脚本保留且未报告保存成功。
3. 两条脚本中 S1 成功、S2 失败时，首次运行停止在费用 14、耗时 46；显式续跑重新估算剩余工作，只生成 S2 并保存，最终费用 20、耗时 69。S1 的原内容和生成响应记录完全保留。

评估以约束、任务状态和工具执行结果为判断标准。每次完整重跑更新当前运行材料，历史版本可通过 Git 提交记录追溯。

## 生成内容复核与改进

首轮内容复核发现“无需来回切换工具”“新手快速开始”等缺少资料支持的表述。原始输出和修正依据见 [writer-v1 复核记录](../examples/iterations/writer-v1/review.md)。

生成提示词增加了标题、旁白与素材事实一致的要求。完整重跑后，AI 助手逐条对照七条不同脚本的旁白与引用素材，确认上述体验承诺已去除。程序检查结构和引用范围，内容复核检查表达是否有资料依据。

## 开发中发现的问题与修正

- Windows 测试环境的临时目录访问限制导致 SQLite 初始化失败，调整为在仓库 `runtime/` 下创建隔离目录后通过测试。
- 模型接口协议采用进程内传输替身完成可重复测试；实际 HTTP 通信通过 DeepSeek 完整验收验证，覆盖调用、返回解析和生成结果保存。

## 四项 P2 修复与回归

后续 Review 的组合用例暴露了四项问题，已修复并增加回归测试。[修复前后核对结果](../examples/regressions/p2-fixes.json)记录了实际复测结果。

| 问题 | 修复后的行为 | 回归测试 |
| --- | --- | --- |
| 结束时沿用旧缺口 | 补查后停止时，缺口从旧值 `2 / 8` 正确更新为 `4 / 13`；历史报价保持原值 | [Agent 测试](../tests/test_agent.py)中的 `test_finish_recalculates_shortfall_after_another_search` |
| 仅有汇总也能通过提交检查 | 逐个读取用例输入、输出和 Trace；删除 24 个真实证据文件后检查返回失败 | [证据检查测试](../tests/test_submission.py)中的 `test_summary_without_real_outputs_is_rejected` |
| 部分运行覆盖完整报告 | 部分用例使用独立目录，向已有完整报告目录写入会在执行前拒绝，原 12 组索引保留 | [评估测试](../tests/test_evaluation.py)中的 `test_partial_cli_does_not_overwrite_existing_full_index` |
| 模型故障误判为无素材通过 | 必须观察到成功检索的空结果、保留空脚本状态，并由模型结束；`MODEL_ERROR` 不通过该场景 | [评估测试](../tests/test_evaluation.py)中的 `test_model_outage_is_not_a_passing_no_materials_case` |

提交检查器还会核对用例集合、输入一致性、运行模式、素材与费率摘要、实际动作记录及 Trace 内容。数据库一致性在执行评估时检查，提交阶段重新核对保存下来的业务结果与证据文件。

## 评估范围与已知限制

当前评估基于两个主题、八份合成参考资料和既定模拟费率，覆盖本题的功能及异常场景。检索采用字符二元组与主题匹配，同义表达和更广主题的匹配效果可通过扩展输入集继续优化。

脚本的自动检查覆盖结构与引用范围，内容依据通过样例复核确认。后续调整资料或提示词时，将沿用相同输入进行回归并复核生成文本。截止时间采用工具表中的模拟耗时计算；步骤级恢复的具体范围见[方案文档](02-solution.md)。
