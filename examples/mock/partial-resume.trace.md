# partial-resume 执行记录

模式：mock

离线 Mock，仅验证流程，不证明真实模型决策效果

## 第 1 次执行

状态：incomplete；累计费用：22；累计耗时：66；复用：False

### 步骤 1 search_materials

依据：Mock：先获取可用参考资料。

参数：`{"query":"字幕功能推广"}`

返回：检索返回 5 份素材：M01,M02,M03,M04,M08

结果状态：succeeded；本次消耗：`{"cost":2,"duration":5}`

后续动作：estimate_plan；依据：Mock：先估算候选计划。

### 步骤 2 estimate_plan

依据：Mock：先估算候选计划。

参数：`{"scripts":[{"brief":"字幕功能推广介绍第1条","material_ids":["M01","M02","M03","M04"],"step_id":"script_1"},{"brief":"字幕功能推广介绍第2条","material_ids":["M01","M02","M03","M04"],"step_id":"script_2"}]}`

返回：预计总费用 22，总耗时 68，可行=True

结果状态：succeeded；本次消耗：`{"cost":0,"duration":1}`

后续动作：generate_script；依据：Mock：执行估算通过的未完成步骤。

### 步骤 3 generate_script

依据：Mock：执行估算通过的未完成步骤。

参数：`{"step_id":"script_1"}`

返回：生成步骤 script_1，素材=M01,M02,M03,M04

结果状态：succeeded；本次消耗：`{"cost":10,"duration":30}`

后续动作：generate_script；依据：Mock：执行估算通过的未完成步骤。

### 步骤 4 generate_script

依据：Mock：执行估算通过的未完成步骤。

参数：`{"step_id":"script_2"}`

返回：INJECTED_TOOL_FAILURE: 第二条脚本生成失败，本次运行停止；可在服务恢复后显式续跑

结果状态：failed；本次消耗：`{"cost":10,"duration":30}`

后续动作：finish；依据：Mock：不可恢复错误，保留成功结果并停止。

### 步骤 5 finish

依据：Mock：不可恢复错误，保留成功结果并停止。

参数：`{"message":"第二条脚本生成失败，本次运行停止；可在服务恢复后显式续跑"}`

返回：{'code': 'MODEL_STOPPED', 'message': '第二条脚本生成失败，本次运行停止；可在服务恢复后显式续跑'}

结果状态：stopped；本次消耗：`{"cost":0,"duration":0}`

后续动作：end；依据：执行结束，最终状态以实际结果为准

结束原因：{"code":"MODEL_STOPPED","message":"第二条脚本生成失败，本次运行停止；可在服务恢复后显式续跑"}

## 第 2 次执行

状态：completed；累计费用：32；累计耗时：99；复用：False

### 步骤 1 search_materials

依据：Mock：先获取可用参考资料。

参数：`{"query":"字幕功能推广"}`

返回：检索返回 5 份素材：M01,M02,M03,M04,M08

结果状态：succeeded；本次消耗：`{"cost":2,"duration":5}`

后续动作：estimate_plan；依据：Mock：先估算候选计划。

### 步骤 2 estimate_plan

依据：Mock：先估算候选计划。

参数：`{"scripts":[{"brief":"字幕功能推广介绍第1条","material_ids":["M01","M02","M03","M04"],"step_id":"script_1"},{"brief":"字幕功能推广介绍第2条","material_ids":["M01","M02","M03","M04"],"step_id":"script_2"}]}`

返回：预计总费用 22，总耗时 68，可行=True

结果状态：succeeded；本次消耗：`{"cost":0,"duration":1}`

后续动作：generate_script；依据：Mock：执行估算通过的未完成步骤。

### 步骤 3 generate_script

依据：Mock：执行估算通过的未完成步骤。

参数：`{"step_id":"script_1"}`

返回：生成步骤 script_1，素材=M01,M02,M03,M04

结果状态：succeeded；本次消耗：`{"cost":10,"duration":30}`

后续动作：generate_script；依据：Mock：执行估算通过的未完成步骤。

### 步骤 4 generate_script

依据：Mock：执行估算通过的未完成步骤。

参数：`{"step_id":"script_2"}`

返回：INJECTED_TOOL_FAILURE: 第二条脚本生成失败，本次运行停止；可在服务恢复后显式续跑

结果状态：failed；本次消耗：`{"cost":10,"duration":30}`

后续动作：finish；依据：Mock：不可恢复错误，保留成功结果并停止。

### 步骤 5 finish

依据：Mock：不可恢复错误，保留成功结果并停止。

参数：`{"message":"第二条脚本生成失败，本次运行停止；可在服务恢复后显式续跑"}`

返回：{'code': 'MODEL_STOPPED', 'message': '第二条脚本生成失败，本次运行停止；可在服务恢复后显式续跑'}

结果状态：stopped；本次消耗：`{"cost":0,"duration":0}`

后续动作：estimate_plan；依据：Mock：根据实际消耗重新估算未完成步骤。

### 步骤 6 estimate_plan

依据：Mock：根据实际消耗重新估算未完成步骤。

参数：`{"scripts":[{"brief":"字幕功能推广介绍第1条","material_ids":["M01","M02","M03","M04"],"step_id":"script_1"},{"brief":"字幕功能推广介绍第2条","material_ids":["M01","M02","M03","M04"],"step_id":"script_2"}]}`

返回：预计总费用 32，总耗时 99，可行=True

结果状态：succeeded；本次消耗：`{"cost":0,"duration":1}`

后续动作：generate_script；依据：Mock：执行估算通过的未完成步骤。

### 步骤 7 generate_script

依据：Mock：执行估算通过的未完成步骤。

参数：`{"step_id":"script_2"}`

返回：生成步骤 script_2，素材=M01,M02,M03,M04

结果状态：succeeded；本次消耗：`{"cost":10,"duration":30}`

后续动作：save_plan；依据：Mock：所有脚本成功后保存。

### 步骤 8 save_plan

依据：Mock：所有脚本成功后保存。

参数：`{"summary":"围绕主题组织已生成脚本，按脚本顺序完成内容准备。","title":"字幕功能推广内容活动方案"}`

返回：方案已保存：P-0f9bd9566105714d

结果状态：succeeded；本次消耗：`{"cost":0,"duration":2}`

后续动作：end；依据：执行结束，最终状态以实际结果为准
