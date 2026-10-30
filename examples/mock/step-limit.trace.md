# step-limit 执行记录

模式：mock

离线 Mock，仅验证流程，不证明真实模型决策效果

## 第 1 次执行

状态：incomplete；累计费用：2；累计耗时：5；复用：False

### 步骤 1 search_materials

依据：Mock：先获取可用参考资料。

参数：`{"query":"字幕功能推广"}`

返回：检索返回 5 份素材：M01,M02,M03,M04,M08

结果状态：succeeded；本次消耗：`{"cost":2,"duration":5}`

后续动作：end；依据：执行结束，最终状态以实际结果为准

结束原因：{"code":"STEP_LIMIT","message":"达到 1 次模型决策上限，任务未完成"}
