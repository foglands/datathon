# 目录
- [目录](#目录)
- [AWS服务用处案例](#aws服务用处案例)
  - [工具用处与介绍](#工具用处与介绍)
    - [1. 核心大模型与调度层](#1-核心大模型与调度层)
    - [2. 企业级增强与安全防护层](#2-企业级增强与安全防护层)
    - [3. 大规模生产与代理执行层](#3-大规模生产与代理执行层)
- [初步规划](#初步规划)
  - [金融/业务 @Shaoze](#金融业务-shaoze)
  - [技术/开发 @Pengpeng @Liu](#技术开发-pengpeng-liu)
    - [本地/快速原型端：Kiro (kiro.dev)](#本地快速原型端kiro-kirodev)
    - [云端深度开发与调优端：Amazon SageMaker AI Studio (JupyterLab)](#云端深度开发与调优端amazon-sagemaker-ai-studio-jupyterlab)
  - [练手 Case Study：智能量化投资分析助手 (Smart Quantitative \& Fundamental Analyzer)](#练手-case-study智能量化投资分析助手-smart-quantitative--fundamental-analyzer)
    - [一、 项目背景与业务目标 (Business Context \& Objectives)](#一-项目背景与业务目标-business-context--objectives)
    - [二、 给定数据集结构 (Dataset Schema)](#二-给定数据集结构-dataset-schema)
    - [三、 练手任务清单 (Tasks for Practice)](#三-练手任务清单-tasks-for-practice)
      - [任务 1：数据预处理与验证 (Data Preprocessing)](#任务-1数据预处理与验证-data-preprocessing)
      - [任务 2：量化指标核心计算器 (Quant Calculation Tools)](#任务-2量化指标核心计算器-quant-calculation-tools)
- [实际步骤](#实际步骤)
  - [Samedi 14 novembre （Présentation du défi）](#samedi-14-novembre-présentation-du-défi)
    - [1. 准备queries](#1-准备queries)
    - [2. 准备通用工具集](#2-准备通用工具集)
  - [Lundi 16 novembre 13:00 （收尾）](#lundi-16-novembre-1300-收尾)
  - [Lundi 16 novembre 14:00 （Date limite de soumission ）](#lundi-16-novembre-1400-date-limite-de-soumission-)


# AWS服务用处案例 

- 市场监控与反洗钱/反欺诈 (Market Surveillance & Fraud Detection)
- 金融犯罪与合规调查 (Financial Crime Investigations)
- "人工智能投资副手"与资产管理 (Artificial Investment Associate / Portfolio Management)
- 智能投资研究助手 (Investment Research Assistant)


## 工具用处与介绍
### 1. 核心大模型与调度层
**Amazon Bedrock**:

作用：提供各种顶尖基础大模型（如 Nova、Claude、Llama、Mistral）的统一 API 接口。无论是 Kiro 还是你在 SageMaker 里写代码调用大模型，底层基本都通过 Bedrock 来访问这些模型。

**Strands Agents**:

作用：一个轻量级的开源 Python/TypeScript SDK。如果你想在代码里快速写一个具备工具调用能力的 AI 代理（Agent），只需要写几行代码导入它，它帮你处理好大模型与本地工具函数（如 @tool 装饰器）之间的交互逻辑。

### 2. 企业级增强与安全防护层
**Knowledge Bases (知识库)**:

作用：用于检索增强生成 (RAG)。如果比赛中需要让 AI 去查阅大量公司财报、PDF 报告或内部文档，并基于真实文档回答，Knowledge Bases 负责帮你的智能体快速检索并“锚定”相关内容，防止大模型胡说八道（幻觉）。

**Guardrails (安全护栏)**:

作用：用于内容审核与合规控制。它可以帮你过滤掉敏感词、禁止回答某些违规话题、自动对用户输入的个人隐私信息（PII）进行脱敏掩码处理，并检查 AI 的回答是否严格基于真实来源。

### 3. 大规模生产与代理执行层
**Bedrock AgentCore**:

作用：面向大规模生产环境的代理基础设施集。它提供代理运行时的会话管理、长期/短期内存保持（Memory）、多代理间的网关通信（Gateway）以及运行状态的可观测性（Observability）。

**AgentCore Code Interpreter** (代码解释器):

作用：一个沙箱隔离的代码执行环境。当你的 AI 代理需要动态计算数据时，它可以让大模型自己编写一段 Python 代码并在安全隔离的环境中运行，最后把计算结果返回给代理。


# 初步规划
## 金融/业务 @Shaoze

- 负责梳理业务逻辑、把控财务指标、设计策略框架及最后的简报汇报（Pitch）。
- 准备Report模板
  - Document structure (?Intro - Details - Conclusion?)
  - Diagrams
  - Tables


## 技术/开发 @Pengpeng @Liu

负责 AWS 环境配置、数据清洗
- Kiro (Agentic workflow)
- SageMaker (jupyter notebook & python lib)

负责 Technical Documentation
- 明细 Agent 工作流程
- 明细

### 本地/快速原型端：Kiro (kiro.dev)
适用场景：适合项目初期快速启动、代码编写刚起步时，或者需要通过自然语言快速生成基础架构。

可进行的微调/操作：

模型选择：通过底层对接的 API 选择不同的基础大模型（如 Amazon Bedrock 支持的 Nova、Claude 等）。

快速编写代码：用自然语言让 Kiro 自动生成数据预处理和清洗脚本（例如编写基于 pandas 处理 CSV 文件的逻辑）。

### 云端深度开发与调优端：Amazon SageMaker AI Studio (JupyterLab)
适用场景：适合进行深入、细颗粒度的量化建模、回测和算法迭代的主战场。

可进行的微调/操作：

数据清理与特征工程：在 Jupyter 单元格中逐行编写 Python 代码，利用 pandas 和 NumPy 处理数据框、处理缺失值、统一转换日期。

模型选择与参数微调：调用机器学习库（如 scikit-learn）进行算法模型的训练与超参数调整。

Agent 工具函数编写：编写并注册 @tool 装饰器函数（如自定义计算波动率、夏普比率的计算逻辑）。


## 练手 Case Study：智能量化投资分析助手 (Smart Quantitative & Fundamental Analyzer)

### 一、 项目背景与业务目标 (Business Context & Objectives)
作为资产管理公司的初级量化分析师，你需要在周末期间快速评估一组科技股（以加拿大股票为例，如 TECH.TO 等）的市场风险与基本面健康度。
由于时间有限，你需要借助 Python 脚本与 AI 代理（Agent）自动化完成数据清洗、核心量化指标计算（波动率、夏普比率）以及财报关键指标提取，最终输出一份结构化的分析报告。

### 二、 给定数据集结构 (Dataset Schema)
项目包含两个核心 CSV 数据文件，你可以直接在本地或 SageMaker 中创建模拟数据进行练习 

1. 价格数据集：prices_daily.csv
记录了资产每日的交易表现：
- date (日期): YYYY-MM-DD
- symbol (股票代码): 如 TECH.TO
- close (收盘价 - 毛价)
- adj_close (调整后收盘价 - 核心避坑字段：防股票分拆失真)
- volume (交易量)

2. 财务数据集：company_financials.csv

记录了公司的季度基本面数据：
- date (发布日期 - 核心避坑字段：防前视偏差)
- symbol (股票代码)
- quarter (财季): 如 Q1, Q2revenue (营业收入)
- net_income (净利润)
- free_cash_flow (自由现金流)

### 三、 练手任务清单 (Tasks for Practice)
请尝试通过编写 Python 脚本

#### 任务 1：数据预处理与验证 (Data Preprocessing)
- 要求： 读取 prices_daily.csv。
- 避坑点：必须使用 adj_close（调整后收盘价）计算收益率，严禁使用毛价 close。
- 检查并按 date 排序，确保时间序列无错位。

#### 任务 2：量化指标核心计算器 (Quant Calculation Tools)
编写两个独立的 Python 函数（可尝试封装为 @tool）：
1. 波动率计算 (volatility)：
  - 计算每日对数收益率或百分比收益率：$r_t = \frac{P_t}{P_{t-1}} - 1$
  - 利用统计标准差计算年化波动率：$\text{Vol} = \text{stdev}(r) \times \sqrt{252} \times 100$

2. 夏普比率计算 (sharpe_ratio)：
  - 假设无风险利率（Risk-free rate）为 2% (0.02)。
  - 计算公式：$\text{Sharpe} = \frac{\text{Annualized Return} - \text{Rf}}{\text{Annualized Volatility}}$。
  
3. 基本面与时间对齐验证 (Fundamental Alignment)
- 要求： 读取 company_financials.csv。
- 避坑点： 确保在分析某季度财报时，策略调用的时间必须在财报的发布日期（Publication Date）之后，严禁使用财季刚结束但未公开的数据（防范前视偏差）。

4. 代理工作流组装与报告生成 (Agent Orchestration & Synthesis)
- 要求：
  - 模仿 Strands Agents 的写法，将上述计算函数注册为代理的工具。   
  - 输入自然语言指令（例如：“请分析 TECH.TO 在 prices_daily.csv 中的年化波动率，并结合财务数据检查其自由现金流表现”）。
  - 输出一段包含具体数值、计算依据以及引用来源的结构化文本报告。

# 实际步骤

## Samedi 14 novembre （Présentation du défi）
过程中注意关键的时间段与关键词

### 1. 准备queries 

### 2. 准备通用工具集 

## Lundi 16 novembre 13:00 （收尾）

## Lundi 16 novembre 14:00 （Date limite de soumission ）
: vidéo, one-pager et documentation technique