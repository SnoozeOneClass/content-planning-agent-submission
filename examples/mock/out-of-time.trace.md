# out-of-time 执行记录

模式：mock

离线 Mock，仅验证流程，不证明真实模型决策效果

## 第 1 次执行

状态：incomplete；累计费用：2；累计耗时：8；复用：False

### 步骤 1 search_materials

依据：Mock：先获取可用参考资料。

参数：`{"query":"字幕功能推广"}`

返回：检索返回 5 份素材：M01,M02,M03,M04,M08

结果状态：succeeded；本次消耗：`{"cost":2,"duration":5}`

后续动作：estimate_plan；依据：Mock：先估算候选计划。

### 步骤 2 estimate_plan

依据：Mock：先估算候选计划。

参数：`{"scripts":[{"brief":"字幕功能推广介绍第1条","material_ids":["M01","M02","M03","M04"],"step_id":"script_1"}]}`

返回：预计总费用 12，总耗时 38，可行=False

结果状态：succeeded；本次消耗：`{"cost":0,"duration":1}`

后续动作：estimate_plan；依据：Mock：根据超限估算减少选用素材，再次估算。

### 步骤 3 estimate_plan

依据：Mock：根据超限估算减少选用素材，再次估算。

参数：`{"scripts":[{"brief":"字幕功能推广介绍第1条","material_ids":["M01","M02"],"step_id":"script_1"}]}`

返回：预计总费用 8，总耗时 29，可行=False

结果状态：succeeded；本次消耗：`{"cost":0,"duration":1}`

后续动作：estimate_plan；依据：Mock：根据超限估算减少选用素材，再次估算。

### 步骤 4 estimate_plan

依据：Mock：根据超限估算减少选用素材，再次估算。

参数：`{"scripts":[{"brief":"字幕功能推广介绍第1条","material_ids":["M01"],"step_id":"script_1"}]}`

返回：预计总费用 6，总耗时 25，可行=False

结果状态：succeeded；本次消耗：`{"cost":0,"duration":1}`

后续动作：finish；依据：Mock：无可行方案。

### 步骤 5 finish

依据：Mock：无可行方案。

参数：`{"message":"最小可执行计划仍不满足预算或时间，缺口见估算结果"}`

返回：{'code': 'MODEL_STOPPED', 'message': '最小可执行计划仍不满足预算或时间，缺口见估算结果', 'shortfall': {'budget': 0, 'time_budget': 5}}

结果状态：stopped；本次消耗：`{"cost":0,"duration":0}`

后续动作：end；依据：执行结束，最终状态以实际结果为准

结束原因：{"code":"MODEL_STOPPED","message":"最小可执行计划仍不满足预算或时间，缺口见估算结果","shortfall":{"budget":0,"time_budget":5}}
