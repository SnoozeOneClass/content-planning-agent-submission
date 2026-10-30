# tool-failure 执行记录

模式：mock

离线 Mock，仅验证流程，不证明真实模型决策效果

## 第 1 次执行

状态：completed；累计费用：22；累计耗时：69；复用：False

### 步骤 1 search_materials

依据：Mock：先获取可用参考资料。

参数：`{"query":"字幕功能推广"}`

返回：检索返回 5 份素材：M01,M02,M03,M04,M08

结果状态：succeeded；本次消耗：`{"cost":2,"duration":5}`

后续动作：estimate_plan；依据：Mock：先估算候选计划。

### 步骤 2 estimate_plan

依据：Mock：先估算候选计划。

参数：`{"scripts":[{"brief":"字幕功能推广介绍第1条","material_ids":["M01","M02","M03","M04"],"step_id":"script_1"}]}`

返回：预计总费用 12，总耗时 38，可行=True

结果状态：succeeded；本次消耗：`{"cost":0,"duration":1}`

后续动作：generate_script；依据：Mock：执行估算通过的未完成步骤。

### 步骤 3 generate_script

依据：Mock：执行估算通过的未完成步骤。

参数：`{"step_id":"script_1"}`

返回：INJECTED_TOOL_FAILURE: 生成服务暂时不可用，请根据剩余额度决定是否再次尝试

结果状态：failed；本次消耗：`{"cost":10,"duration":30}`

后续动作：estimate_plan；依据：Mock：根据实际消耗重新估算未完成步骤。

### 步骤 4 estimate_plan

依据：Mock：根据实际消耗重新估算未完成步骤。

参数：`{"scripts":[{"brief":"字幕功能推广介绍第1条","material_ids":["M01","M02","M03","M04"],"step_id":"script_1"}]}`

返回：预计总费用 22，总耗时 69，可行=True

结果状态：succeeded；本次消耗：`{"cost":0,"duration":1}`

后续动作：generate_script；依据：Mock：执行估算通过的未完成步骤。

### 步骤 5 generate_script

依据：Mock：执行估算通过的未完成步骤。

参数：`{"step_id":"script_1"}`

返回：生成步骤 script_1，素材=M01,M02,M03,M04

结果状态：succeeded；本次消耗：`{"cost":10,"duration":30}`

后续动作：save_plan；依据：Mock：所有脚本成功后保存。

### 步骤 6 save_plan

依据：Mock：所有脚本成功后保存。

参数：`{"summary":"围绕主题组织已生成脚本，按脚本顺序完成内容准备。","title":"字幕功能推广内容活动方案"}`

返回：方案已保存：P-297d2545b7f8be01

结果状态：succeeded；本次消耗：`{"cost":0,"duration":2}`

后续动作：end；依据：执行结束，最终状态以实际结果为准
