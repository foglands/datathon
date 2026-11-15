# AlphaForge AI 风险模型可靠性修改对照说明

对照依据是 2026 年 11 月 15 日版《风险模型可靠性修改说明》。以 [`c8a90d4`][base] 为原始核查基线，以 [`98661fe`][app-rev] 为实际完成并通过验收的应用版本。[`afe2036`][first-change] 完成第一轮发布保护，[验证记录][verification] 保存本地及比赛 AWS 的实测依据。

| 状态 | 含义 |
| --- | --- |
| 已修改 | 在当前产品范围内已接入执行或发布流程 |
| 已有并复核 | 基线已有实现，本轮沿用并核对，必要时补充验收 |
| 部分修改 | 已实现可用部分，原说明中更广的覆盖仍有缺口 |
| 另行设计 | 这次未启用的能力或原说明单独划出的后续工作 |

## 1. 数值权限和计算方法

| 原说明条目 | 状态 | 实际实现与修改 |
| --- | --- | --- |
| §1、§3 LLM 决策和数字来源分离 | 已修改 | Profile 解析并澄清输入。Evidence、Scenario、Exposure、Alternatives 和 Review 在各自阶段调用允许的工具。LLM 可以选择受支持的复查项目。Python 根据冻结数据和已确认条件计算派生值、判定约束和生成公开说明。原来的可选模型说明路径已移除。[角色定义][agents] · [执行链][workflow] · [发布层][publication] |
| §3 价格、汇率、持仓和行业分类的来源 | 已修改 | 冻结官方价格与汇率 CSV，记录文件指纹和来源元数据。持仓按披露的观察日期、可用日期和时效筛选。行业证据保持分类体系、版本、分母和原文定位。证据缺失保留为未知，证据充分性和计算核验分别记录。[市场来源][data] · [发行人证据][issuer-evidence] · [行业证据][sector-evidence] |
| §3 用户数值和假设 | 已修改 | 自由文本路径检查金额、单位及对应约束。明确且唯一的受支持数值可以从原文补回。无法绑定的字段必须澄清或手填，不能通过限定范围入口静默跳过。报告记录已确认的值、来源类型和引文指纹，原文片段在输入界面核对。买入后持有等模型假设和费用、税费、日内波动的范围单列。[数字核验][profile-numbers] · [规则验证][workflow] · [范围说明][publication] |
| §4.1 币种转换 | 已修改 | 使用同日 CAD/USD 汇率将 USD 调整收盘价换算为 CAD，CAD 报价直接采用原价。Review 独立从冻结原始字段用 Decimal 重建序列并对账，拦截反向、错日或重复转换。供应商上游复权质量仍取决于原始数据提供者。[数据加载与复核][data] |
| §4.2 买入并持有路径 | 已有并复核 | 用起始权重与各资产相对起点的 CAD 价格计算组合净值，权重随价格漂移。以调整收盘价回放，增加独立已知路径、换汇和缩放测试。费用、税费和日内变化列为计算范围外。[公式][finance] · [独立复算][governance] · [公式测试][formula-tests] |
| §4.3 期末收益与损失 | 已有并复核 | 同时保留有符号期末收益和非负损失。盈利路径验收保留 20% 收益、0% 损失和期内回撤。[公式测试][formula-tests] |
| §4.4 最大回撤与峰谷 | 已有并复核 | 从组合净值和历史峰值计算最大回撤，保存该组合的峰值日和谷值日。移除官方窗口真实谷值日的行情或汇率会使该窗口证据不足。[公式测试][formula-tests] · [交易日测试][calendar-tests] |
| §4.5、§4.6 收益与回撤贡献 | 已有并复核 | 保留每项贡献的符号，独立复算收益贡献和各组合自身峰谷内的回撤贡献。测试两类贡献守恒、资产负贡献以及前后组合峰谷不同的情形。结果保留各自峰谷供解释。[独立复算][governance] · [公式测试][formula-tests] |
| §4.7 发行人与行业敞口 | 已修改 | 以持仓权重和合格证据计算区间。若行业比例基于基金股票部分，先换算为净资产口径。前后比较共享同一套未知系数，未变动持仓的未知贡献抵消。逐行业上下界表示各自的范围。[行业公式][sector] · [独立敞口复核][exposure-review] · [敞口测试][exposure-tests] |
| §4.8 可行域、精度与容差 | 部分修改 | 复用两资金来源求解器和独立可行边界复算。判定使用原始精度，界面显示时再圆整。新增两种显示均为 14.00% 的临界测试，验证实际越界仍失败。已有筛选与完整约束集的对照测试。当前各程序保留自己的数值容差，统一逐指标容差登记和公开导出尚未加入。[求解器][finance] · [复核规则][governance] · [边界测试][boundary-tests] |
| §4.8 描述性行业分析与行业上限 | 已有并复核 | 行业分析发布上下界、变化和覆盖。绑定的行业上限进入未评估要求路径，用户只能明确确认有限审计。现有求解器可执行的敞口上限是有适用政策和证据的发行人上限。[要求状态][requirements] · [行业范围][sector-evidence] |
| §1、§6 新估计方法 | 另行设计 | VaR、Expected Shortfall、市场状态模型和训练 ML 需要单独定义估计对象、数据窗口和验证方法。现有结果限定在指定历史路径。[适用范围][readme] |

## 2. P0 及 P1 修改对照

| 原优化项 | 状态 | 做了什么 | 核查依据 |
| --- | --- | --- | --- |
| **P0-1 附加数字进入独立复核** | 已修改 | 行业和发行人变化在 Review 内独立重算。核对分类及分母、合格日期、上下界、未知比例、共享变化和来源。发布分别取两个章节的核验结果。某附加章节缺证或被篡改，隐藏该章节的数字并保留核验通过的主报告。 | [执行链][workflow] · [敞口复核][exposure-review] · [发布隔离测试][publication-tests] |
| **P0-2 公开数字和说明引用核验结果** | 已修改 | 为公开衍生值生成稳定指标标识和 `value_ref`，指向公开报告中同一个经过核验的值。输入区分原文证据和用户手填。公开解释和比较方向由程序模板生成，违规幅度和剩余空间由程序按规则生成。缺失或无效的指标引用无法解析成可发布数字。若未来启用自由生成说明，还需另建生成后核验流程。 | [指标索引][metric-records] · [界面证据][audit-view] · [指标测试][metric-tests] |
| **P0-3 原始记录到 CAD 估值独立核对** | 已修改 | 原始价格、报价币种、汇率、日期和来源文件保留到复核环节。常规计算完成后，Review 独立重建所用 CAD 价格并比较实际使用值。检测重复、非正或非有限价格以及错日、反向和重复换汇。重要日期缺失时报告只保留诊断。 | [换汇复核][data] · [市场来源测试][provenance-tests] · [流程拦截测试][financial-tests] |
| **P0-4 冻结结果及输入版本绑定** | 已修改 | 使用不可变复核快照，关联输入指纹、确认规则、公式版本、复核 ID 和附加章节。报告或对照复查的数字、规则、复核记录错配时失去发布资格。Streamlit 检测行情源变化后清除旧结果及相关授权。更换外部持仓或行业证据应开启新一轮审计，已有记录保留当时快照。 | [快照与版本][snapshot] · [应用缓存边界][app] · [篡改测试][publication-tests] |
| **P1-1 统一到每项公开指标的记录** | 已修改 | 主风险、贡献、敞口、资金边界、规则差值和反事实结果建立指标索引。记录方法与版本、单位、分母、历史窗口或观察日期、来源、输入指纹、假设、核验状态及复核 ID。界面可选择指标查看，JSON 使用同一索引。披露原始金额和运行遥测按各自来源类型保留。 | [记录契约][metric-records] · [覆盖测试][metric-tests] |
| **P1-2 交易日及样本覆盖** | 部分修改 | 三个官方窗口用独立归档日历检查。报告记录预期和实际观测数、休市与已知汇率排除日、意外缺日分类和连续缺口。官方窗口缺少关键日期时拦截回撤与求解结果。未登记窗口输出 `coverage_not_verified`，扩展市场和任意日期区间的独立日历尚未接入。 | [日历][calendar] · [市场来源][data] · [交易日测试][calendar-tests] |
| **P1-3 可重算的保守下界** | 已修改 | ZST.TO 改用 BMO 2026 年 6 月 30 日的公允价值与净资产披露。原始报告以千加元列示非股票投资公允价值 4,144,027 和净资产 4,158,550。按每侧留一个披露单位计算 `(4,144,027 − 1) / (4,158,550 + 1)`，下界约 99.65%。同一笔 10 个百分点的 ZST.TO 转 NVDA 交易，信息技术敞口变化区间由约 8.37～10.00 个百分点收窄到 9.97～10.00 个百分点。导出保留金额、单位、币种和公式。旧目录只有人工下界而缺少依据时，该部分计入未映射。[财报与原文定位][sector-evidence] | [主计算][sector] · [独立复算][exposure-review] · [行业测试][sector-tests] |
| **P1-4 计算有效性与未来问题** | 已修改 | `scope_notes` 分列计算核验状态、CAD 买入持有的历史适用范围，以及未来问题。会明确列出未来亏损概率、潜在损失幅度和未测价格路径在本次评估中没有得到回答。 | [范围与发布字段][publication] · [计算方法界面][audit-view] |

## 3. 修改后的智能体如何执行

| 环节 | 修改结果 |
| --- | --- |
| Profile → 用户确认 | 数值尽可能绑定到原文。歧义、冲突或缺少依据触发定向澄清或直接填写。用户确认的是可执行规则，用户填写的假设与观察数据分别记录。 |
| Evidence → Scenario／Exposure | 绑定受支持的原始数据、窗口和日期。流程允许 Scenario 与适用的 Exposure 并行。持仓或行业缺失显示为未知区间，来源和时效随结果保留。 |
| 原交易与 Alternatives | 首轮独立审计原交易。明确授权后才运行资金求解器并复核候选边界。支持先查原规模，若需缩量且用户未授权，则另行确认。复查沿用原先的搜索授权范围。 |
| Review → 发布 | Review 调用独立 Python 工具复算。有效违规结论可以发布，附加章节有各自的核验状态，未知或不支持的约束标明范围。报告不靠调整用户阈值或移除已确认的历史窗口来改变判定。Streamlit、CLI 和反事实导出共用发布边界。 |

相关入口见 [应用][app]、[CLI][cli]、[反事实流程][counterfactual] 和 [要求状态][requirements]。

## 4. 原验收矩阵逐项核查

| 原测试 | 覆盖情况 | 验证依据 |
| --- | --- | --- |
| 1 已知路径 | 100 → 120 → 90。期末损失 10%，最大回撤 25%。 | [公式测试][formula-tests] |
| 2 盈利路径 | 100 → 90 → 120。期末收益 20%，期末损失 0%，最大回撤 10%。 | [公式测试][formula-tests] |
| 3 不变路径 | 固定价格和汇率的收益、损失和最大回撤均为 0。 | [公式测试][formula-tests] |
| 4 单位缩放 | 所有资产价格同倍放大，风险比例和各项贡献保持一致，覆盖主计算及 Review。 | [公式测试][formula-tests] |
| 5 换汇 | 已分别验证 USD 同日乘汇率、CAD 原价保留，拒绝反向及重复换汇。现有夹具同时改变 USD 价格和汇率，原说明的固定 USD 价格单变化汇率未单设用例。 | [市场来源测试][provenance-tests] |
| 6 贡献守恒 | 收益贡献之和等于期末收益，回撤贡献之和等于该组合最大回撤。 | [公式测试][formula-tests] |
| 7 贡献符号 | 已验证上涨资产在峰谷段可以产生负回撤贡献，前后组合可有不同峰谷。 | [公式测试][formula-tests] |
| 8 日期缺失 | 从归档窗口移除真实谷值日行情或汇率，保留缺失原因并阻止完整结果发布。连续缺口跨已知休市日按预期交易日计数。 | [交易日测试][calendar-tests] |
| 9 异常输入 | 已验证重复记录、无效格式、非正价格、NaN 和无穷值被拒绝。 | [市场来源测试][provenance-tests] |
| 10 分母错误 | 基金持仓 20% × 基金股票比例 80% × 股类行业比例 40% 得 6.4%，错误口径在复核中判为无效。 | [敞口测试][exposure-tests] |
| 11 未知行业 | 保留未映射份额，旧下界证据不足时该部分同样保持未知。 | [行业测试][sector-tests] |
| 12 共享未知 | 未交易持仓的同一未知系数在前后区间差中抵消，覆盖行业和发行人变化。 | [行业测试][sector-tests] · [敞口测试][exposure-tests] |
| 13 行业篡改 | 本地把行业下界改为 99%，发布层只隐藏行业章节。AWS 的 Amira 另核对了更改 ZST.TO 行业证据下界后的同类行为。 | [发布测试][publication-tests] · [AWS 证明][verification] |
| 14 风险篡改 | 篡改期末损失、回撤或贡献会被复核或发布检查发现。求解边界与见证也有篡改测试。 | [复核测试][governance-tests] · [发布测试][publication-tests] |
| 15 模型编造 | CLI、JSON 和反事实报告的测试注入了「风险 0%」、保证安全及虚构收益的文字，发布层拦截这些声明。伪造指标引用无法获得发布值。 | [CLI 输出测试][numeric-tests] · [发布测试][publication-tests] · [指标测试][metric-tests] |
| 16 版本错配 | 已验证规则版本、证据、数值、范围和复查快照错配会使旧审核失效，行情源更新会撤销相关结果和授权。 | [发布测试][publication-tests] · [界面测试][app-tests] |
| 17 未请求替代 | 本地检查离线及代理执行下均跳过资金求解和候选边界复核。AWS Robert 原交易和委托 Review 也维持原搜索范围。 | [授权测试][intent-tests] · [AWS 证明][verification] |
| 18 通用性 | 在支持范围内验证 Robert、Amira、自定义权重、新增固定窗口、不同行业和未知证据。未支持的资产、规则或窗口会触发限制提示。主交易和融资仍使用产品支持的资产，任意新市场与资产的端到端模型尚未开放。 | [范围测试][scope-tests] · [行业测试][sector-tests] · [AWS 证明][verification] |

## 5. 全量验证和复现

| 验证 | 实际结果 |
| --- | --- |
| 本地 macOS，Python 3.10，完整官方数据 | 219/219 全量回归，6/6 离线 CLI |
| 比赛 AWS CloudShell `us-east-1`，Python 3.13，完整官方数据 | 219/219 全量回归，6/6 离线 CLI |
| 同一代码版本的真实 Bedrock 执行 | 6 个 CLI 场景和 5 个追加检查，11/11。共 36 次带 AWS 请求 ID 的 Converse HTTP 200 |

追加检查覆盖英法文数值绑定、原交易与指标索引、行业证据改动的发布拦截、Review 委托的反事实复查。故意设置违规、证据不足或篡改的场景，以系统正确判断或拦截为通过条件。公开记录保存请求 ID 的脱敏指纹。[验证记录与复现命令][verification]

[base]: https://github.com/WindsTrace/datathon-prep/commit/c8a90d4e607c86ff60f36b86307ff92e6f85d232
[first-change]: https://github.com/WindsTrace/datathon-prep/commit/afe2036c79ed87865bac885c6f3024bb018a2ecb
[app-rev]: https://github.com/WindsTrace/datathon-prep/commit/98661fe71f880139d51d2361624193adc8db7c82
[verification]: https://github.com/WindsTrace/datathon-prep/blob/b19e00f706eacb16ea319e109286bf61ed94fe2c/submission/verification.md#risk-reliability-completion-on-local-and-competition-aws
[readme]: https://github.com/WindsTrace/datathon-prep/blob/98661fe/README.md#data-and-scope
[agents]: https://github.com/WindsTrace/datathon-prep/blob/98661fe/datathon/agents.py
[app]: https://github.com/WindsTrace/datathon-prep/blob/98661fe/app.py
[cli]: https://github.com/WindsTrace/datathon-prep/blob/98661fe/datathon/__main__.py
[workflow]: https://github.com/WindsTrace/datathon-prep/blob/98661fe/datathon/workflow.py
[profile-numbers]: https://github.com/WindsTrace/datathon-prep/blob/98661fe/datathon/profile_numbers.py
[finance]: https://github.com/WindsTrace/datathon-prep/blob/98661fe/datathon/finance.py
[governance]: https://github.com/WindsTrace/datathon-prep/blob/98661fe/datathon/governance.py
[data]: https://github.com/WindsTrace/datathon-prep/blob/98661fe/datathon/data.py
[calendar]: https://github.com/WindsTrace/datathon-prep/blob/98661fe/datathon/market_calendar.py
[issuer-evidence]: https://github.com/WindsTrace/datathon-prep/blob/98661fe/datathon/evidence.py
[sector-evidence]: https://github.com/WindsTrace/datathon-prep/blob/98661fe/SECTOR_EVIDENCE.md
[sector]: https://github.com/WindsTrace/datathon-prep/blob/98661fe/datathon/sector.py
[exposure-review]: https://github.com/WindsTrace/datathon-prep/blob/98661fe/datathon/exposure_review.py
[snapshot]: https://github.com/WindsTrace/datathon-prep/blob/98661fe/datathon/review_snapshot.py
[publication]: https://github.com/WindsTrace/datathon-prep/blob/98661fe/datathon/publication.py
[metric-records]: https://github.com/WindsTrace/datathon-prep/blob/98661fe/datathon/metric_records.py
[audit-view]: https://github.com/WindsTrace/datathon-prep/blob/98661fe/datathon/audit_view.py
[requirements]: https://github.com/WindsTrace/datathon-prep/blob/98661fe/datathon/requirement_status.py
[counterfactual]: https://github.com/WindsTrace/datathon-prep/blob/98661fe/datathon/counterfactual.py
[app-tests]: https://github.com/WindsTrace/datathon-prep/blob/98661fe/tests/test_app.py
[boundary-tests]: https://github.com/WindsTrace/datathon-prep/blob/98661fe/tests/test_drawdown_constraints.py
[calendar-tests]: https://github.com/WindsTrace/datathon-prep/blob/98661fe/tests/test_market_calendar.py
[exposure-tests]: https://github.com/WindsTrace/datathon-prep/blob/98661fe/tests/test_exposure_review.py
[financial-tests]: https://github.com/WindsTrace/datathon-prep/blob/98661fe/tests/test_financial_boundary.py
[formula-tests]: https://github.com/WindsTrace/datathon-prep/blob/98661fe/tests/test_formula_acceptance.py
[governance-tests]: https://github.com/WindsTrace/datathon-prep/blob/98661fe/tests/test_governance.py
[intent-tests]: https://github.com/WindsTrace/datathon-prep/blob/98661fe/tests/test_audit_intent.py
[metric-tests]: https://github.com/WindsTrace/datathon-prep/blob/98661fe/tests/test_metric_records.py
[numeric-tests]: https://github.com/WindsTrace/datathon-prep/blob/98661fe/tests/test_numeric_output.py
[provenance-tests]: https://github.com/WindsTrace/datathon-prep/blob/98661fe/tests/test_market_provenance.py
[publication-tests]: https://github.com/WindsTrace/datathon-prep/blob/98661fe/tests/test_publication.py
[scope-tests]: https://github.com/WindsTrace/datathon-prep/blob/98661fe/tests/test_scope.py
[sector-tests]: https://github.com/WindsTrace/datathon-prep/blob/98661fe/tests/test_sector.py
