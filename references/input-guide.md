# 报价输入约定

schema_version固定为1.0，rule_version记录所用规则版本。project包含id、name、revision、currency=CNY、price_basis=inclusive或exclusive；tax_rate为小数字符串或null。inclusive且税率未知时保留含税报价，不计算拆税。exclusive缺少税率则完整含税价待核定。

sources每条有唯一id，可记录path、sha256、state及页码等定位。用户口头估算也可作为来源，但注明说话人、日期及“未核定”，不得虚构已批准。历史资料应固定版本，不靠文件修改日期自动选新。

items每条含唯一id、name、scope、method、pricing、source_refs。bucket默认“软件”，frequency默认once，可选year。scope为base/optional/excluded；optional使用selected布尔值，默认false。description和conditions会进入客户稿，不能写内部成本、利润或个人信息。feature_ids保留需求对应。estimate_basis只在内部使用。

pricing按method填写：

|method|pricing字段|解释|
|---|---|---|
|service_days|days、rate、rate_kind=service_price|综合服务工日×单价，不再加成|
|cost_plus|components数组、markup、rate_kind=cost|成本明细amount之和×(1+加成率)|
|module_price|quantity、unit_price、rate_kind=module_price|数量×已核定模块售价|
|included|空对象|必须给included_in数组，指向收费项|

数值采用十进制字符串；缺失用null。零值需要zero_reason，已含项除外。components每条包括唯一id、name、amount；岗位人工、预备费等可在上游明细中计算后引用，但必须保留计算依据，不把未确认数值直接标成真实成本。本版计算器只汇总已给出的成本明细，不自动推导人员排期或管理费比例。

relations三种关系：

- exclusive：id、kind、items。最多选中一项。
- requires_any：items包含一个依赖发起项；any_of为`{"item":"计价项编号"}`或`{"condition":"条件编号"}`的列表，至少满足一个。
- overlap_credit：items为需要同时选中的项目；condition指向conditions中的true/false/null；amount为扣减金额，description描述具体共用范围。同一项目参与多个扣减关系时先拆工作包核定，避免重复扣减。

conditions保存布尔或null；condition_evidence另存依据。true也可以是有明确标识的回放假设，不代表现场已验证。

requirements每条含id、item_ids、required。明确排除的需求填写disposition=excluded及reason。open_questions每条包含question、blocks_price、resolved；重要价格缺口blocks_price=true。未选中的选配项缺价不影响已选部分。

overrides可按bucket和frequency设置amount与reason。此数值按project.price_basis计价。保存估算价及商务调整，不修改原工作量以凑总价。

reviews仅记录实际核定：stage为scope/technical/commercial，reviewer、date、input_hash缺一不可。计算器比较当前输入指纹；修改范围、参数、来源或规则版本会使旧核定失效。指纹不是身份认证，不证明签名或公司审批。

输出internal.json包含计算量、计价因子、来源与问题；customer.json只含允许的客户字段。input-snapshot.json保存本轮输入。输出status只有“待补充”和“可审阅草稿”，不会自动宣称已审批或可签合同。

当前能力限制：人民币、一次性/年度分列、非负费用，减价用明确扣减或执行价；跨币种、复杂分期、混合税率、人员排期和自动成本分摊需先扩展规则，不能静默近似。语义重复、实际能力和报价合理性由AI梳理加人工复核，计算器只验证显式结构。
