# 测试与评估

## 执行命令

```sh
python -m unittest discover -s tests -v
python -m src.evaluate --mode mock
python -m src.evaluate --mode real
```

单元与集成测试验证业务边界、存储和模型协议；模型协议测试使用进程内 HTTP 传输替身，不计入真实模型效果证据。`evaluate` 对每个用例使用独立数据库，输出实际结果、逐步 Trace 和断言结果。

当前 **34/34 项自动化测试通过**。执行 `python scripts/verify.py` 可同时重现测试与离线验收，并更新[实际测试结果](../examples/test-results.txt)。

## 离线实际结果

当前离线验收为 **12/12 通过**，全部结果来源于真实执行的 Mock 模式程序，见 [results.json](../examples/mock/results.json)。Mock 不证明真实模型会作出这些决策。

| 场景 | 预期 | 实际状态 | 累计费用 / 耗时 | 材料 |
| --- | --- | --- | --- | --- |
| 正常 | 生成并保存 | completed | 12 / 38 | [输入](../examples/inputs/normal.json)、[输出](../examples/mock/normal.output.json)、[Trace](../examples/mock/normal.trace.md) |
| 超限后调整 | 调整选材并重新估算 | completed | 8 / 29 | [输入](../examples/inputs/replan.json)、[输出](../examples/mock/replan.output.json)、[Trace](../examples/mock/replan.trace.md) |
| 缺预算 | 明确缺失字段，无工具调用 | needs_input | 0 / 0 | [输入](../examples/inputs/missing-budget.json)、[输出](../examples/mock/missing-budget.output.json)、[Trace](../examples/mock/missing-budget.trace.md) |
| 缺时间 | 明确缺失字段，无工具调用 | needs_input | 0 / 0 | [输入](../examples/inputs/missing-time.json)、[输出](../examples/mock/missing-time.output.json)、[Trace](../examples/mock/missing-time.trace.md) |
| 生成暂时失败 | 保留检索结果，失败如实记账 | completed | 22 / 69 | [输入](../examples/inputs/tool-failure.json)、[输出](../examples/mock/tool-failure.output.json)、[Trace](../examples/mock/tool-failure.trace.md) |
| 保存失败 | 不虚报保存成功，保留脚本 | incomplete | 12 / 38 | [输入](../examples/inputs/save-failure.json)、[输出](../examples/mock/save-failure.output.json)、[Trace](../examples/mock/save-failure.trace.md) |
| 无预算可行解 | 未完成并报告缺口 | incomplete | 2 / 8 | [输入](../examples/inputs/over-budget.json)、[输出](../examples/mock/over-budget.output.json)、[Trace](../examples/mock/over-budget.trace.md) |
| 无时间可行解 | 未完成并报告缺口 | incomplete | 2 / 8 | [输入](../examples/inputs/out-of-time.json)、[输出](../examples/mock/out-of-time.output.json)、[Trace](../examples/mock/out-of-time.trace.md) |
| 无资料 | 不凭空生成 | incomplete | 4 / 10 | [输入](../examples/inputs/no-materials.json)、[输出](../examples/mock/no-materials.output.json)、[Trace](../examples/mock/no-materials.trace.md) |
| 重复执行 | 两次输出对应同一份保存结果 | completed | 12 / 38，无新增 | [输入](../examples/inputs/repeat.json)、[两次输出](../examples/mock/repeat.output.json)、[Trace](../examples/mock/repeat.trace.md) |
| 部分成功后续跑 | 保留第一条脚本，只补第二条 | completed | 32 / 99，含失败消耗 | [输入](../examples/inputs/partial-resume.json)、[两次输出](../examples/mock/partial-resume.output.json)、[Trace](../examples/mock/partial-resume.trace.md) |
| 执行上限 | 明确 STEP_LIMIT | incomplete | 2 / 5 | [输入](../examples/inputs/step-limit.json)、[输出](../examples/mock/step-limit.output.json)、[Trace](../examples/mock/step-limit.trace.md) |

故障配置位于 [examples/faults](../examples/faults)。评估逐项核对：累计消耗与 Trace 相等、预算/时间非负、保存输出与数据库一致、失败后保留成功成果、重复执行不新增步骤，以及续跑不重做成功脚本。

## 真实模型验证

使用 `deepseek-flash` 原生工具调用完成两轮真实验收。第二轮在收紧生成提示词后完整重跑，**12/12 组程序化验收通过**，最终记录见 [真实 results.json](../examples/real/results.json)。本轮并非固定脚本回放，动作来自模型响应，记录包含 response ID 与 tool call ID。缺输入的两组在调用模型之前返回。

| 场景 | 实际状态 | 费用 / 耗时 | 实际材料 |
| --- | --- | --- | --- |
| 正常 | completed | 12 / 38 | [输出](../examples/real/normal.output.json)、[Trace](../examples/real/normal.trace.md) |
| 超限后调整 | completed | 8 / 29 | [输出](../examples/real/replan.output.json)、[Trace](../examples/real/replan.trace.md) |
| 缺预算 | needs_input | 0 / 0 | [输出](../examples/real/missing-budget.output.json)、[Trace](../examples/real/missing-budget.trace.md) |
| 缺时间 | needs_input | 0 / 0 | [输出](../examples/real/missing-time.output.json)、[Trace](../examples/real/missing-time.trace.md) |
| 生成暂时失败 | completed | 22 / 68 | [输出](../examples/real/tool-failure.output.json)、[Trace](../examples/real/tool-failure.trace.md) |
| 保存失败 | incomplete | 12 / 38 | [输出](../examples/real/save-failure.output.json)、[Trace](../examples/real/save-failure.trace.md) |
| 无预算可行解 | incomplete | 2 / 7 | [输出](../examples/real/over-budget.output.json)、[Trace](../examples/real/over-budget.trace.md) |
| 无时间可行解 | incomplete | 2 / 8 | [输出](../examples/real/out-of-time.output.json)、[Trace](../examples/real/out-of-time.trace.md) |
| 无资料 | incomplete | 8 / 20 | [输出](../examples/real/no-materials.output.json)、[Trace](../examples/real/no-materials.trace.md) |
| 重复执行 | completed | 12 / 38，无新增 | [两次输出](../examples/real/repeat.output.json)、[Trace](../examples/real/repeat.trace.md) |
| 部分成功后续跑 | completed | 20 / 68 | [两次输出](../examples/real/partial-resume.output.json)、[Trace](../examples/real/partial-resume.trace.md) |
| 执行上限 | incomplete | 2 / 5 | [输出](../examples/real/step-limit.output.json)、[Trace](../examples/real/step-limit.trace.md) |

其中三组可重点复核动态决策：

1. 正常请求选择 M01–M04，估算通过后生成并保存；受限请求先得到费用 12、耗时 38 的超限反馈，模型随后保留 M01 与 M04，重新估算为费用 8、耗时 29，再生成保存。第二轮选材并非简单取检索前两条。
2. 生成工具返回可重试错误后，模型依据剩余额度选择重试；保存工具返回不可恢复错误后，模型选择停止，保留脚本并说明未保存。
3. 两条脚本中 S1 成功、S2 失败时，首次运行停止在费用 14、耗时 46；显式续跑只生成 S2 并保存，最终费用 20、耗时 68。S1 的原内容和生成响应记录完全保留。

两轮输出的文字和部分动作存在差异，这是模型运行结果。评估判断约束、状态和真实执行，不要求逐字相同或固定走一条路径。

## 生成内容复核与改进

第一轮自动断言虽通过，AI 助手阅读实际脚本后发现“无需来回切换工具”“新手快速开始”等缺少资料支持的表述。原始输出和修正依据保留在 [writer-v1 复核记录](../examples/iterations/writer-v1/review.md)。

收紧生成提示词，要求标题和旁白仅陈述资料支持的事实，不把 brief 中的体验宣传自动写入脚本。随后完整重跑真实验收，并逐条对照最终七条不同脚本的旁白和引用素材，已去掉上述无依据的体验承诺。结构和引用范围由测试检查，语义阅读由本次 AI 助手完成；未声称具备通用自动事实验证能力。

## 开发中发现的问题与修正

- Windows 沙箱的系统临时目录无法供 SQLite 正常创建文件，初次测试在初始化阶段失败。测试和评估改为在仓库 `runtime/` 下创建隔离目录，清理前检查绝对路径仍在该目录内。
- 当前沙箱阻止本地回环 HTTP 测试连接。协议测试改为进程内传输替身，仍验证请求结构、工具调用解析、JSON 生成、错误脱敏和缺密钥行为；真实 HTTP 连通性由真实模型验收验证。

## 限制

检索是确定性的本地匹配，未建设向量库；不进行素材重复度分析。脚本内容只做结构和引用范围的自动检查，后续更换素材和模型后仍应复核生成文本。时间是题目内模拟时间，不代表真实 API 延迟。GitHub URL 按用户安排在本地验收后填写；题目名称为“内容任务规划 Agent”，若原题有编号则提交时同时填写该编号。
