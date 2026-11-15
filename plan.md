# Contents

- [Contents](#contents)
- [AWS service use cases](#aws-service-use-cases)
  - [Tools and their roles](#tools-and-their-roles)
    - [1. Foundation models and orchestration](#1-foundation-models-and-orchestration)
    - [2. Enterprise capabilities and safeguards](#2-enterprise-capabilities-and-safeguards)
    - [3. Production infrastructure and agent execution](#3-production-infrastructure-and-agent-execution)
- [Initial plan](#initial-plan)
  - [Finance and business @Shaoze](#finance-and-business-shaoze)
  - [Engineering and development @Pengpeng @Liu](#engineering-and-development-pengpeng-liu)
    - [Local development and rapid prototyping with Kiro (kiro.dev)](#local-development-and-rapid-prototyping-with-kiro-kirodev)
    - [Cloud development and tuning with Amazon SageMaker AI Studio (JupyterLab)](#cloud-development-and-tuning-with-amazon-sagemaker-ai-studio-jupyterlab)
  - [Practice case study — Smart Quantitative & Fundamental Analyzer](#practice-case-study--smart-quantitative--fundamental-analyzer)
    - [I. Business context and objectives](#i-business-context-and-objectives)
    - [II. Dataset schema](#ii-dataset-schema)
    - [III. Practice tasks](#iii-practice-tasks)
      - [Task 1. Data preprocessing and validation](#task-1-data-preprocessing-and-validation)
      - [Task 2. Quantitative calculation tools](#task-2-quantitative-calculation-tools)
- [Schedule](#schedule)
  - [Saturday, November 14 — Challenge presentation](#saturday-november-14--challenge-presentation)
    - [1. Prepare queries](#1-prepare-queries)
    - [2. Prepare reusable tools](#2-prepare-reusable-tools)
  - [Monday, November 16 at 13:00 — Wrap-up](#monday-november-16-at-1300--wrap-up)
  - [Monday, November 16 at 14:00 — Submission deadline](#monday-november-16-at-1400--submission-deadline)

# AWS service use cases

- Market surveillance, anti-money-laundering controls, and fraud detection
- Financial crime and compliance investigations
- AI investment associate and portfolio management
- AI investment research assistant

## Tools and their roles

### 1. Foundation models and orchestration

**Amazon Bedrock**

Bedrock provides a unified API for foundation models such as Nova, Claude, Llama, and Mistral. Kiro or code running in SageMaker can use Bedrock to access those models.

**Strands Agents**

Strands Agents is a lightweight, open-source SDK for Python and TypeScript. It handles interactions between a foundation model and local functions registered as tools, including functions decorated with `@tool`.

### 2. Enterprise capabilities and safeguards

**Knowledge Bases**

Knowledge Bases supports retrieval-augmented generation (RAG). If the challenge requires the agent to consult company financial statements, PDF reports, or internal documents, the service can retrieve relevant passages and help ground answers in those sources.

**Guardrails**

Guardrails supports content moderation and compliance controls. It can filter sensitive terms, restrict specified topics, mask personally identifiable information (PII) in user input, and check whether responses are grounded in the provided sources.

### 3. Production infrastructure and agent execution

**Bedrock AgentCore**

AgentCore provides infrastructure for agents running at production scale. Its capabilities include runtime session management, short- and long-term memory, gateway communication between agents, and observability.

**AgentCore Code Interpreter**

The Code Interpreter provides an isolated environment for executing code. When an agent needs an on-demand calculation, the model can write Python code, run it in the sandbox, and receive the result.

# Initial plan

## Finance and business @Shaoze

- Define the business logic, oversee the financial metrics, design the strategy framework, and deliver the final pitch.
- Prepare a report template.
  - Consider an introduction, a details section, and a conclusion.
  - Diagrams
  - Tables

## Engineering and development @Pengpeng @Liu

Set up the AWS environment and clean the data.

- Kiro for the agent workflow
- SageMaker for Jupyter notebooks and Python libraries

Prepare technical documentation.

- Describe the agent workflow in detail.
- Document other implementation details.

### Local development and rapid prototyping with Kiro (kiro.dev)

Kiro fits the early stages of the project, when the team is getting started with the code or wants to scaffold the project using natural language.

- **Model selection** through integrated APIs for foundation models such as Nova and Claude on Amazon Bedrock.
- **Rapid development** using natural-language requests to generate preprocessing and cleaning scripts, including pandas code for CSV files.

### Cloud development and tuning with Amazon SageMaker AI Studio (JupyterLab)

Use JupyterLab for detailed quantitative modeling, backtesting, and algorithm iteration.

- **Data cleaning and feature engineering** using Python in notebook cells. Use pandas and NumPy to work with data frames, handle missing values, and normalize date formats.
- **Model selection and tuning** using machine learning libraries such as scikit-learn to train models and adjust hyperparameters.
- **Agent tools** using functions registered with `@tool`, such as functions that calculate volatility or the Sharpe ratio.

## Practice case study — Smart Quantitative & Fundamental Analyzer

### I. Business context and objectives

As a junior quantitative analyst at an asset management firm, you need to assess the market risk and financial health of a group of technology stocks over a weekend. Use Canadian equities such as TECH.TO as examples.

With limited time, use Python scripts and an AI agent to automate data cleaning, calculate volatility and the Sharpe ratio, extract key financial statement figures, and produce a structured analysis report.

### II. Dataset schema

The project uses two CSV datasets. You can create synthetic data for the exercise locally or in SageMaker.

1. Daily trading data in `prices_daily.csv`

   - `date` — trading date in YYYY-MM-DD format
   - `symbol` — ticker, such as TECH.TO
   - `close` — unadjusted closing price
   - `adj_close` — adjusted closing price, which avoids distortions due to stock splits
   - `volume` — trading volume

2. Quarterly company fundamentals in `company_financials.csv`

   - `date` — publication date, used to guard against look-ahead bias
   - `symbol` — ticker
   - `quarter` — fiscal quarter, such as Q1 or Q2
   - `revenue` — revenue
   - `net_income` — net income
   - `free_cash_flow` — free cash flow

### III. Practice tasks

Complete the tasks using Python scripts.

#### Task 1. Data preprocessing and validation

- Read `prices_daily.csv`.
- Calculate returns from `adj_close`. Do not use the unadjusted `close`.
- Validate and sort the observations by `date` so the time series stays aligned.

#### Task 2. Quantitative calculation tools

Write two independent Python functions. You can register them with `@tool`.

1. **Volatility** (`volatility`)
   - Compute daily log or percentage returns. For percentage returns, use $r_t = \frac{P_t}{P_{t-1}} - 1$.
   - Compute annualized volatility using the standard deviation of returns, $\text{Vol} = \text{stdev}(r) \times \sqrt{252} \times 100$.

2. **Sharpe ratio** (`sharpe_ratio`)
   - Assume a risk-free rate of 2% (0.02).
   - Use $\text{Sharpe} = \frac{\text{Annualized Return} - \text{Rf}}{\text{Annualized Volatility}}$.

3. **Fundamental data and date alignment**
   - Read `company_financials.csv`.
   - Use a quarterly financial statement only when the strategy's evaluation date follows its publication date. Using an unpublished statement just after the fiscal quarter ends would introduce look-ahead bias.

4. **Agent orchestration and reporting**
   - Register the calculation functions as agent tools, following the Strands Agents pattern.
   - Submit a natural-language request such as “Calculate the annualized volatility of TECH.TO from `prices_daily.csv` and use the financial data to assess its free cash flow.”
   - Produce a structured text report with specific figures, calculation methods, and cited sources.

# Schedule

## Saturday, November 14 — Challenge presentation

Note the important time windows and key terms during the presentation.

### 1. Prepare queries

### 2. Prepare reusable tools

## Monday, November 16 at 13:00 — Wrap-up

## Monday, November 16 at 14:00 — Submission deadline

Submit the video, one-pager, and technical documentation.
