# no-materials 执行记录

模式：mock

离线 Mock，仅验证流程，不证明真实模型决策效果

## 第 1 次执行

状态：incomplete；累计费用：4；累计耗时：10；复用：False

### 步骤 1 search_materials

依据：Mock：先获取可用参考资料。

参数：`{"query":"火星地质勘探"}`

返回：检索返回 0 份素材：

结果状态：succeeded；本次消耗：`{"cost":2,"duration":5}`

后续动作：search_materials；依据：Mock：先获取可用参考资料。

### 步骤 2 search_materials

依据：Mock：先获取可用参考资料。

参数：`{"query":"火星地质勘探"}`

返回：检索返回 0 份素材：

结果状态：succeeded；本次消耗：`{"cost":2,"duration":5}`

后续动作：finish；依据：Mock：两次检索无结果。

### 步骤 3 finish

依据：Mock：两次检索无结果。

参数：`{"message":"未检索到支持主题的资料，请补充素材"}`

返回：{'code': 'MODEL_STOPPED', 'message': '未检索到支持主题的资料，请补充素材'}

结果状态：stopped；本次消耗：`{"cost":0,"duration":0}`

后续动作：end；依据：执行结束，最终状态以实际结果为准

结束原因：{"code":"MODEL_STOPPED","message":"未检索到支持主题的资料，请补充素材"}
