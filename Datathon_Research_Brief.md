# AlphaForge AI 研究简报

2026 年 11 月 14 日 · PolyFinances × Banque Nationale × AWS

## 正式赛题确认

正式题目要求以公开金融数据支持虚拟投资决策，并用来源、假设、局限及可观察的执行记录解释结果。两种对比情境是官方演示建议。AWS 对原型的运行必须有实际且可展示的贡献，同时占 15% 评分。原型与代码、约 5 分钟的视频、技术文档和最多一页的 one-pager 仍是四项交付。题目第 16 页把截止时间、入口和格式交由官方赛务通知。 [官方资料包，英文 Case 第 3–19 页及参赛演示第 4、7、9–11 页](https://chatgpt.com/library?file_id=libfile_9d3dbce691dc8191993a39be5f3b9381&account_id=personal)

## 最有竞争力的设计方向

**同一次调仓可以改善地域分散、加深底层持仓重叠，并在一组明确的冲击下放大损失。** 建议围绕一个问题做原型：给定现有组合、明确的资金来源和一笔假设调仓，这个改变改善了哪类风险，又放大了哪类风险？什么投资者约束或市场假设会改变结论？

主办方的金融工作坊以 Canadian equities、ZEQT 和 XSP 说明这一决策。已有持仓分析产品也提供资产穿透和重叠检查。参赛亮点可以落在**把同一笔调仓的不同风险后果、投资者约束、结论翻转点和可验证的证据放进一次交互**。案例、角色数量和指标是本简报提出的设计选项。 [官方金融工作坊，第 9–15 页](https://chatgpt.com/library?file_id=libfile_45683714475c8191b8fa95a48f9a0566&account_id=personal) · [Morningstar Stock Intersection](https://www.morningstar.com/help-center/portfolio/stock-intersection)

## 用发行人披露复算一笔调仓

采用 **2026-06-30** 的同日估值。BMO 披露 ZEQT 的基金地域分类为加拿大 24.7%、美国 49.3%、国际发达市场 16.6%、新兴市场 9.4%。其中 ZSP 公允价值 C$400.775M，ZEQT 净资产 C$880.582M，约占 **45.51%**。BlackRock 同日披露 XSP 持有的 IVV 约占 XSP 净资产 **99.9%**，汇率远期另列。以下将 XSP 的权益暴露近似为 100% 美国大盘和 S&P 500，将示例加拿大股票篮子设为 100% 加拿大。汇率对冲作用与底层权益地域分开处理。 [BMO ZEQT 半年报，Schedule of Investments](https://bmo.bynder.com/m/7617d719b2a3e5e7/original/SA_FS_ZEQT_E.pdf) · [BlackRock 半年财务报表，XSP Schedule of Investments](https://www.blackrock.com/ca/investors/en/literature/semi-annual-report/sar-fs-equity-en-ca.pdf) · [XSP 投资目标及底层披露](https://www.blackrock.com/ca/investors/en/literature/semi-annual-mrfp/sa-mrfp-xsp-en-ca.pdf)

| 指标 | A · 初始模拟组合 | B · 从加拿大股票转 10 个百分点至 XSP |
| --- | ---: | ---: |
| 配置：加拿大股票 / ZEQT / XSP | 40% / 50% / 10% | 30% / 50% / 20% |
| 加拿大权益暴露 | 52.35% | 42.35% |
| 美国权益暴露 | 34.65% | 44.65% |
| 国际发达 / 新兴市场 | 8.30% / 4.70% | 8.30% / 4.70% |
| 四地区集中度 HHI（地区权重平方和） | 0.4032 | 0.3878 |
| S&P 500 配置占比（XSP 权重 + ZEQT 权重 × 45.51%） | 32.76% | 42.76% |
| 假设情景损益（加拿大 −12%、美国 −20%、国际发达 −15%、新兴市场 −25%） | −15.63% | −16.43% |

地域暴露按「组合持仓权重 × 基金地域权重」累加。固定冲击下，用各地域权重乘对应冲击再求和。若只改变美国冲击且加拿大维持 −12%，B 与 A 的损益差是 `0.10 × (美国冲击 − 加拿大冲击)`。美国冲击恰为 −12% 时，**两种配置的情景损益相同**。美国跌幅小于 12% 时，B 的损失较小。跌幅大于 12% 时，B 的损失较大。四个地域冲击是分别设定的假设输入，未叠加单独的汇率、费用或流动性冲击。持仓日期用于说明暴露截面，历史回测须以实际公开时间限制可用信息。 [Bank of Canada 的情景分析示例](https://www.bankofcanada.ca/publications/financial-stability-report/financial-stability-report-2026/how-a-financial-market-correction-could-worsen-the-effects-of-an-oil-shock/)

### 底层持仓的直接证据

同日发行人表中，XSP 底层 IVV 与 ZEQT 持有的 ZSP 公布了相同的前 25 家发行人。逐项取显示权重的较小值后求和，得到 **51.7 个百分点的已披露重叠**。计算使用 IVV 和 ZSP 各自净资产权重，表格四舍五入至 0.1 个百分点。该数字仅反映这两只底层基金已核对的 25 家发行人。完整重叠和 XSP 与 ZEQT 整体重叠仍需同日完整持仓与统一标识。报表可在同一个界面提供「组合里的标普 500 配置占比」和「两只底层基金的已观察持仓重叠」，各自显示分母和覆盖范围。 [BlackRock XSP MRFP，Summary of Investment Portfolio](https://www.blackrock.com/ca/investors/en/literature/semi-annual-mrfp/sa-mrfp-xsp-en-ca.pdf) · [BMO ZSP MRFP，Summary of Investment Portfolio](https://bmo.bynder.com/m/44946315307b6828/original/SA_MRFP_ZSP_E.pdf) · [Artiga Gonzalez et al.，2024，公式 1](https://www.diw.de/documents/publikationen/73/diw_01.c.813391.de/dp1937.pdf)

## 让投资者画像改变输出

官方画像提供的是案例背景。下表的规则和缺失条件可作为原型测试输入，数值上限由团队在模拟中明示。对同一个组合改动，三个案例共用同一份行情、持仓和风险计算。 [官方人物场景](https://chatgpt.com/library?file_id=libfile_fd2be5295b3c81918f0baade28077865&account_id=personal) · [CSA／CIRO 31-368，风险意愿与承受能力](https://www.ciro.ca/newsroom/publications/joint-canadian-securities-administrators-canadian-investment-regulatory-organization-staff-notice-31-0)

| 画像 | 评委可以验证的行为 |
| --- | --- |
| Amira · 26 岁，15 年以上，高风险意愿 | 允许探索成长或高波动主题。若某方案触及本场景明示的单一发行人、行业或主题上限，指出是哪项暴露触发。风险意愿和实际亏损承受能力分别输入。 |
| Mateo · 41 岁，8–12 年，中等风险 | 明确其希望避开涉及重大环境或社会争议的企业。若有发行人或公开披露支持，展示所采用的筛选标准及覆盖。若资料不足，将是否涉及争议标为未知。行业排除和敞口限制可作为另行设定的模拟条件。 |
| Robert · 59 岁，3–5 年，低至中等风险 | 媒体热点触发一笔模拟增持请求。以明确的资金用途、提款时间、可承受损失与流动性检查决定是否标记冲突。示例可用 16% 假设冲击损失上限，让 A 与 B 分别落在阈值两边。该全权益组合用于演示一项规则，整体判断仍需其余约束。 |

**优先演示 Robert。** 同一屏展示地区集中度下降和冲击损失跨越假设上限。固定其他冲击及 16% 上限时，B 在美国跌幅约 **19.03%** 处触及上限。两方案相对优劣则在美国跌幅 **12%** 时翻转。这两个阈值回答不同问题。再用 Mateo 重跑相同调仓，展示 ESG 数据不足或偏好改变时的输出。Amira 用来证明较高风险意愿仍受底层集中度约束。Berg 等研究六家评级机构，发现分歧来自测量、范围和加权口径。用带来源的窄规则处理 Mateo 的输入更容易验证。 [Berg、Kölbel 与 Rigobon，2022](https://alexandria.unisg.ch/entities/publication/ed9c77e4-016b-498b-a6e6-b4c76d3a4f91) · [CSA ESG 基金披露指引，AMF](https://lautorite.qc.ca/fileadmin/lautorite/reglementation/valeurs-mobilieres/0-avis-acvm-staff/2024/2024mars07-81-334-avis-acvm-revise-en.pdf)

## 多智能体分工与 AWS

建议让 **证据 Agent** 和 **约束 Agent** 并行。**分析 Agent** 接收两路结构化结果，调用 Python 工具。确定性校验通过后，由 **解释 Agent** 将已验证的结果整理为用户可读的决策说明。每个模型 Agent 有独立任务、输入、输出及工具权限。编排层负责运行顺序、超时和分支，计算与校验留在确定性代码。 [AutoGen，COLM 2024](https://www.microsoft.com/en-us/research/publication/autogen-enabling-next-gen-llm-applications-via-multi-agent-conversation-framework/) · [Strands Graph](https://strandsagents.com/docs/user-guide/sdk/multi-agent/graph/)

| 角色 | 可展示的交接内容 |
| --- | --- |
| 证据 Agent | 从允许的公开出处选择持仓资料，返回证据 ID、观察日期、可用日期、分母、币种、粒度、覆盖率和缺失项。 |
| 投资者约束 Agent | 将模拟目标、期限、风险意愿、承受能力及 ESG 条件转为硬约束或偏好，显式标记未知项。 |
| 分析 Agent | 选择适用计算，调用 `compare_exposures` 和 `run_scenario` 等工具，返回数值、贡献项、条件变化和证据 ID。 |
| 解释 Agent | 用已通过校验的结果回答使用了什么数据、为何得出结论、有哪些局限、什么会改变结论。 |

**工程方案。** 用 Strands Graph 或小型 Python 编排器显式定义有向无环流程，通过 Bedrock Converse 执行模型及工具调用。Converse 由应用执行工具并用相同的 `toolUseId` 回传结果。赛事 Workshop 指定 `us-east-1`，建议先以 `global.amazon.nova-2-lite-v1:0` 验证一次文本响应及完整工具往返。所有 Agent 共用团队账号配额，超时、重试和工具轮数应有上限。Workshop 也提供 Codex on Bedrock 的开发配置。AWS 文档说明 **Bedrock Agents Classic 自 2026-07-30 起停止向新客户开放**。AWS 备选可以是在分析过程中从比赛账号的私有 S3 bucket 读取有版本的公开证据快照，前提是权限、数据授权与竞赛口径均允许。 [赛事 AWS 设置](https://catalog.us-east-1.prod.workshops.aws/event/dashboard/fr-FR/workshop/20-setup) · [赛事 Codex 指引](https://catalog.us-east-1.prod.workshops.aws/event/dashboard/fr-FR/workshop/40-quickstarts/60-ai-coding-assistant/30-codex) · [Bedrock 工具调用](https://docs.aws.amazon.com/bedrock/latest/userguide/tool-use-client-side.html) · [Classic 维护模式](https://docs.aws.amazon.com/us_en/bedrock/latest/userguide/agents-classic-maintenance-mode.html) · [S3 GetObject](https://docs.aws.amazon.com/AmazonS3/latest/API/API_GetObject.html)

**可解释性和失效处理。** 保存运行 ID、版本、工具入参、结果、规则及证据 ID。证据日期、币种、粒度或版本不兼容时，让校验明确标记，输出条件成立时的结果或请求必需信息。校验权重、单位、数据覆盖、数字与引用。MAST 从多智能体运行轨迹中识别系统设计、协作失配和验证不足三类共 14 种失效模式。Kim 等人的预印本发现架构收益明显取决于任务可分解性。两项研究支持明确交接与独立验证的设计。 [Cemri et al.，MAST，NeurIPS 2025](https://proceedings.neurips.cc/paper_files/paper/2025/hash/b1041e52d3be19f0a9bc491657488e4a-Abstract-Datasets_and_Benchmarks_Track.html) · [Kim et al.，arXiv v3，2026](https://arxiv.org/abs/2512.08296) · [NISTIR 8312](https://doi.org/10.6028/NIST.IR.8312) · [Turpin et al.，NeurIPS 2023](https://papers.neurips.cc/paper_files/paper/2023/hash/ed3fea9033a80fea1376299fa7863f4a-Abstract-Conference.html)

## 让评委在五分钟内看到证据

| 维度 | Demo 中可直接看到的证据 |
| --- | --- |
| Solution · 20% | 同一笔调仓改善一类风险并加大另一类风险。投资者约束改变最终判断。 |
| Agentique · 20% | 展开一次真实运行的交接记录，显示哪个 Agent 找到重叠证据、哪个 Agent 应用画像规则、哪个工具给出数值。 |
| Données · 20% | 一键展开发行人原文、观察日期、分母、计算式和覆盖范围。缺失证据在输出可见。 |
| UX · 10% | 同屏对照原组合与模拟调整，明示资金来源。单变量滑块能重现情景结果翻转。 |
| AWS · 15% | 展示关键路径中实际发生的 Bedrock 或其他赛事 AWS 服务调用，以及该操作得到的结果。 |
| Pitch · 15% | 原型、视频、技术文档和 one-pager 都讲同一笔调仓。用一句话说明差异，再给评委复算入口。 |

开场提出「增持 XSP 会不会更分散」，接着显示同日真实披露和假设调仓。用 Robert 展示两条指标给出不同信号，再只改一个冲击参数或切换到 Mateo。最后展开工具交接、AWS 执行、来源和局限。评分权重已由正式题目第 19 页及参赛演示第 10 页核对。最后一项还看商业价值与营销。 [官方资料包](https://chatgpt.com/library?file_id=libfile_9d3dbce691dc8191993a39be5f3b9381&account_id=personal)

## 文献与数据使用清单

正式发布的 starter 是可选的。实际文件含 31 个资产、40,049 条日价格、658 条公司行动、1,245 条汇率和 8,281 条宏观观察。价格覆盖 2021-11-12 至 2026-11-12，提取于 2026-11-13。XSP、ZEQT、底层持仓和争议信息不在包内，核心案例可继续用日期和口径一致的发行人披露。若展示 2022 年的市场背景，可使用包内资产作补充。先统一币种和交易日历，使用 `adj_close`，不要重复应用拆股。历史宏观模拟须区分数据所属月份、实际发布时间及后续修订。发布原始 CSV 前核对各来源的再分发条款。 [官方资料包，starter README 与 sources_metadata.csv](https://chatgpt.com/library?file_id=libfile_9d3dbce691dc8191993a39be5f3b9381&account_id=personal)

| 读什么 | 用在项目的哪里 |
| --- | --- |
| [Markowitz，Portfolio Selection，1952](https://doi.org/10.1111/j.1540-6261.1952.tb01525.x) | 协方差解释组合波动。地域 HHI、持仓重叠和基于收益序列的波动刻画不同问题。 |
| [DeMiguel、Garlappi 与 Uppal，2009](https://doi.org/10.1093/rfs/hhm075) | 在该研究的 7 组数据中，14 个模型均未在报告的样本外判据上持续胜过等权。若选做优化，以未调整组合为主基线，并用同一合格资产池的等权作额外比较。 |
| [Bailey et al.，The Probability of Backtest Overfitting](https://doi.org/10.21314/jcf.2016.322) · [作者存档](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf) | 避免通过反复选资产、窗口或冲击挑出最漂亮的图。若加历史回测，明确事前规则、可用时间和按时间切分的样本外评价。 |
| [Gao et al.，ALCE，EMNLP 2023](https://aclanthology.org/2023.emnlp-main.398/) · [Chen et al.，FinQA，EMNLP 2021](https://aclanthology.org/2021.emnlp-main.300/) · [Islam et al.，FinanceBench，arXiv](https://arxiv.org/abs/2311.11944) | 分开检验数字、单位、公式和证据。抽查关键事实是否有支持、链接是否真的支持该句。 |
| [Ribeiro et al.，CheckList，ACL 2020](https://aclanthology.org/2020.acl-main.442/) · [Yao et al.，τ-bench，ICLR 2025](https://proceedings.iclr.cc/paper_files/paper/2025/hash/1b126cc38b8638e07bef37e7b2bb72bf-Abstract-Conference.html) | 测已知答案、换序不变性、单变量方向及重复运行。记录每次成功率与同一用例多次全通过的比例，并说明样本量。 |
| [BlackRock XSP](https://www.blackrock.com/ca/investors/en/products/239727/ishares-sp-500-index-etf-cadhedged-fund) · [BMO ZEQT](https://www.bmoetfs.ca/etfs/zeqt-bmo-all-equity-etf) | 核对基金结构、指数、对冲和披露日期。完整穿透采集前先确认下载文件是否为直接持仓或底层持仓。仓库发布前核对再分发条款。 |
| [BoC Valet](https://www.bankofcanada.ca/valet-api-how-to/) · [美元兑加元 JSON](https://www.bankofcanada.ca/valet/observations/FXUSDCAD/json?recent=5) · [StatCan CPI](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1810000401) · [ALFRED 版本说明](https://fred.stlouisfed.org/docs/api/fred/realtime_period.html) | 可选宏观输入。FXUSDCAD 是每美元兑换加元的指示性汇率，CPI 表是月度未季调指数。历史决策按发布日期和已发布版本取值。 |
| [SEDAR+](https://systems.securities-administrators.ca/onlinehelp/general-help/getting-started/general-public-access/) · [SEC EDGAR API](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) · [ECCC 设施排放](https://www.canada.ca/en/environment-climate-change/services/climate-change/greenhouse-gas-emissions/facility-reporting/data.html) | 可选财报与 ESG 数据。记录报告期和公开时间。设施排放使用报告年份、覆盖和业主映射，无法直接代表母公司整体 Scope 1–3。 |

## 原型验收

1. 两个已知配置必须复现表格数字。各地域贡献加总等于情景损益，调仓前后权重合计为 100%。
2. 调换持仓输入顺序，风险判断保持一致。只改美国冲击，复现 −12% 的交叉点。只改 Robert 的场景损失上限，结果按边界改变。
3. 人为删掉一项关键持仓或更换快照日期，验证覆盖率、数据缺失与结论限制确实显示。
4. 逐个查看 Agent 的工具调用、输入、输出与交接。用固定测试样例记录至少三次独立运行中的计算、约束、引证与错误情况。
5. 团队 CloudShell 已验证 Nova 2 Lite 文本调用与客户端工具往返，并运行完官方入门 Notebook。交付前在参赛应用中展示一次实际 AWS 调用，验证真实输入、结果和失败路径。提交表仍需按主办方最新通知核实。 [实测 Notebook](https://chatgpt.com/library?file_id=libfile_ca31bd6cfc3481919f0e1ccd121f7bd7&account_id=personal)
