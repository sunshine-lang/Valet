<div align="center">

<img src="web/public/favicon.svg" alt="Valet" width="64" height="64" />

<h1>Valet</h1>

<p><strong>让智能体的每一步，都看得见。</strong></p>

<p>可复用的 AI Agent 工作台：从模型决策、工具执行，到权限确认与运行追踪。</p>

<p>
  <img src="https://img.shields.io/badge/Python-3.12%2B-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python 3.12+" />
  <img src="https://img.shields.io/badge/Vue-3-42B883?style=flat-square&logo=vuedotjs&logoColor=white" alt="Vue 3" />
  <img src="https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white" alt="FastAPI" />
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-Apache_2.0-18181B?style=flat-square" alt="Apache License 2.0" /></a>
</p>

<p>
  <a href="#快速开始">快速开始</a> ·
  <a href="#核心能力">核心能力</a> ·
  <a href="#工作原理">工作原理</a> ·
  <a href="#开发与验证">开发与验证</a> ·
  <a href="#当前边界">当前边界</a> ·
  <a href="#迭代计划">迭代计划</a>
</p>

</div>

![Valet 首次启动：模型配置引导](docs/assets/valet-first-run.png)

<p align="center"><sub>首次启动未配置模型时的真实界面。填写 .env 或在设置页保存模型配置后开始对话。</sub></p>

## 为什么做 Valet

开发 Agent 时，除了得到答案，还需要知道：模型调用了哪个工具、参数是什么、为什么暂停、失败后怎么处理，以及这次运行用了多少 Token。

Valet 把这些环节放进同一个工作台。你可以配置模型与提示词、开关工具、管理 Skills，在对话中查看执行结果，再展开追踪记录检查每一步。它适合学习 Agent 工程、验证工具与护栏，也适合作为业务助手的开发底座。

## 核心能力

| 能力 | 当前实现 |
| --- | --- |
| **Agent 主循环** | 模型原生函数调用、流式输出、上下文裁剪、运行中插话和取消；包含步数、超时与连续失败处理 |
| **工具与权限** | Pydantic 参数定义与校验；工具开关；按权限策略放行、拦截或暂停等待确认 |
| **项目文件** | `ls`、`read_file`、`write_file`、`str_replace`；支持上传资料与会话交付物，限制敏感路径访问 |
| **联网能力** | 天气查询；通过博查或 Tavily 搜索，搜索词要求使用用户当前的语言 |
| **Skills** | 内置、市场、用户导入三类技能；支持 ZIP 导入、按需读取全文，以及本轮指定技能 |
| **运行追踪** | 会话 → 运行 → 步骤；查看输入、输出、耗时、Token、费用估算与配置快照 |
| **定时任务** | 单次、固定间隔，以及每日、每周、隔周、每月、每年执行 |
| **网页工作台** | 对话、工具与确认卡片、追踪抽屉、模型设置、技能管理、运行记录和明暗主题 |
| **消息反馈** | 用户与 AI 消息复制；AI 回复点赞、点踩；多选反馈原因及 200 字补充说明，反馈随消息保存 |

运行追踪按会话、运行和步骤组织，提供输入、输出、错误、Token 与配置快照。当前工具耗时、取消步骤和下载入口仍有已记录缺口，详见 [Ego Lite 复测报告](docs/egolite-four-items-2026-10-12.md)。

## 快速开始

需要 **Python 3.12+、[uv](https://docs.astral.sh/uv/)、Node.js 22+ 和 pnpm**。先获取项目：

```bash
git clone https://github.com/sunshine-lang/Valet.git
cd Valet
```

### 配置模型并启动

默认使用本地 SQLite，无需 Docker。项目只运行真实模型，未配置密钥时可以启动服务，界面会引导完成模型配置。

在仓库根目录复制配置模板；已有 `.env` 时直接编辑：

```bash
cp -n .env.example .env
```

填写百炼配置：

```dotenv
DASHSCOPE_API_KEY=你的百炼密钥
DASHSCOPE_MODEL=deepseek-v4-flash-0731
DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
```

**终端一 · 后端**：

```bash
cd services/agent-api
uv sync --frozen
uv run uvicorn agent_api.main:app --host 127.0.0.1 --port 8000
```

**终端二 · 前端**（从仓库根目录开始）：

```bash
cd web
pnpm install --frozen-lockfile
pnpm dev --host 127.0.0.1 --strictPort
```

打开 **[http://localhost:5173](http://localhost:5173)**。后端接口文档位于 [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)。

首次启动还没有填写 `.env` 时，点击「去配置模型」，在「设置 → 模型」填写 API Key 并选择模型。保存后对话会立即可用，不必重启后端。修改 `.env` 后则需要重启后端，再刷新页面或点击「重新检查」。

没有配置密钥时，对话和新建定时任务会明确提示先配置模型，不会生成模拟回答；已到点的任务会等待配置，不因缺少密钥被消费。计算、时间、文件与联网工具执行真实操作；模拟通知、慢任务和随机失败工具仅用于自动化测试。

| 配置 | 用途 |
| --- | --- |
| `AGENT_NAME` | 界面名称、接口标题，以及未保存过的默认系统提示词 |
| `DASHSCOPE_API_KEY` | 百炼模型密钥；设置页已保存的密钥优先，前端只接收是否已保存的状态 |
| `DASHSCOPE_MODEL` | 未保存模型配置时的默认模型；当前已保存的选择优先 |
| `DASHSCOPE_BASE_URL` | 百炼接口地址；页面显式地址优先，其次为环境配置，再次为目录默认地址 |
| `BOCHA_API_KEY` / `TAVILY_API_KEY` | 联网搜索二选一；未配置时搜索工具会返回错误 |
| `DATABASE_URL` | 默认使用仓库 `.valet/valet.db`；也可配置 PostgreSQL |
| `WEB_ORIGIN` | 前端 CORS 来源，默认 `http://localhost:5173` |

需要 PostgreSQL 时，在 `.env` 中填写以下连接地址，并先运行 `docker compose up -d`：

```dotenv
DATABASE_URL=postgresql+asyncpg://valet:valet@localhost:5433/valet
```

当前已验证的接入范围是百炼的 12 个模型。页面保留其他供应商与自定义兼容接口目录，其可用性需要分别验证。

改名后，已保存的系统提示词不会自动改写；请在「设置 → 通用」中同步修改。

## 工作原理

```mermaid
flowchart LR
    UI[Vue 工作台] <-->|HTTP / SSE| API[FastAPI]
    API --> LOOP[Agent 主循环]
    LOOP <-->|流式响应 / 函数调用| LLM[真实兼容模型接口]
    LOOP --> GUARD[参数校验与护栏]
    GUARD --> TOOLS[天气 / 搜索 / 文件 / Skills]
    TOOLS -->|结果回填| LOOP
    LOOP --> TRACE[运行与步骤追踪]
    TRACE --> DB[(PostgreSQL / SQLite)]
    API <--> DB
```

模型提出工具调用，执行层校验参数并判断权限，再执行工具、回填结果。需要确认时，运行暂停等待用户选择；未启用的工具会被拦截。

### 运行怎样停止

| 条件 | 默认值 | 处理方式 |
| --- | --- | --- |
| 模型调用步数 | 8 步 | 停止调用工具，用已有信息再生成一次收尾回复 |
| 整次运行时间 | 900 秒 | 在轮次边界检查预算；到点后不再开新工具，用已有结果收尾 |
| 模型流空闲 | 90 秒 | 持续有新输出就继续；空闲超时则停止并保留已输出内容 |
| 工具连续失败 | 3 次 | 停止继续调用工具，说明失败情况 |

单个工具另有独立超时，错误会交回模型处理。用户也可以主动取消，或在运行中发送新消息，当前轮结束后继续处理插话。停止原因会保存在运行记录中。

### 工具与技能怎样扩展

- **工具**放在 [`tools/`](services/agent-api/src/agent_api/tools/)，继承 `Tool`，用 Pydantic 定义 `Args`，实现 `run()`，再加入注册表。同一份参数定义用于模型 JSON Schema 和服务端校验。
- **内置技能**放在 `skills/builtin/`，启动时可用。
- **市场技能**放在 `skills/market/`，安装后使用。
- **用户技能**写入 `data/skills/`，支持 ZIP 导入，也可通过 `create_skill` 创建。
- 系统提示中只列技能名和使用时机；模型通过 `read_skill` 按需读取全文。输入框选中的技能正文只注入当前一轮。

文件工具以仓库为工作区，上传和交付物保存在 `.valet/sessions/{会话}/`。上传目录只读；敏感文件和 Git 内部目录受路径限制，项目外访问与联网由权限策略控制。

## 项目结构

```text
Valet/
├── services/agent-api/
│   ├── src/agent_api/
│   │   ├── agent/          # 主循环、上下文、运行管理与护栏
│   │   ├── llm/            # 模型抽象与供应商目录
│   │   ├── tools/          # 工具定义与注册
│   │   ├── skills/         # 技能目录与导入
│   │   ├── tracing/        # 步骤记录与导出协议
│   │   └── schedules.py    # 定时任务与进程内调度
│   └── tests/              # 后端测试
├── web/                    # Vue 3 + TypeScript + Pinia + Tailwind CSS v4
├── skills/                 # 内置技能与市场技能
├── docs/                   # 设计文档、停止规则调研与界面截图
├── docker-compose.yml      # 本地 PostgreSQL
└── .env.example            # 环境配置示例
```

## 开发与验证

**后端**（从仓库根目录开始）：

```bash
cd services/agent-api
uv run pytest
uv run ruff check src tests
```

**前端**（从仓库根目录开始）：

```bash
cd web
pnpm test
pnpm build
```

后端测试使用脚本模型，覆盖成功、参数错误回填、工具超时、连续失败、最大步数、确认与拒绝、运行中插话、取消、禁用工具、文件、Skills 和定时任务等路径。真实供应商连通性、模型决策质量和线上稳定性需要单独验证。

<details>
<summary><strong>常见启动问题</strong></summary>

- **移动目录后提示 `No module named 'agent_api'`**：在 `services/agent-api` 中重新执行 `uv sync --frozen`，让本地包指向当前目录。
- **Docker 数据库连接失败**：确认 Docker 已启动，并在仓库根目录执行 `docker compose up -d`；也可使用 SQLite 模式。
- **5173 或 8000 已占用**：先检查占用进程。修改后端端口时，要同步调整 `web/vite.config.ts` 中的代理；修改前端来源时，同步调整 `WEB_ORIGIN`。
- **需要停止服务**：在对应终端按 `Ctrl+C`。Docker 数据库可用 `docker compose stop` 停止。

</details>

## 当前边界

- 当前交付的是通用 Agent 工作台。知识库页面仍为占位；电商客服中的订单、售后规则、RAG 和人工坐席记录在[业务设计文档](docs/design.md)中，属于后续业务设计。
- Word、PDF 技能支持读取抽出的正文并整理成文本；PPT 技能目前只整理演示大纲，不能直接解析二进制 `.pptx`。当前均不包含原生 `.docx`、`.pdf`、`.pptx` 成品生成能力。
- 追踪字段按 OpenTelemetry GenAI 约定命名，已预留[导出协议](services/agent-api/src/agent_api/tracing/exporter.py)；默认使用空导出器，外部追踪平台需要另外接入。费用是估算值，未配置价格的模型不能据此判断实际账单。
- 定时任务由后端进程内调度器执行；后端停止期间不会继续运行。

## 迭代计划

> 更新于 2026-10-12。以下均为待完成计划，按优先级推进；完成状态以对应提交、回归测试和实际运行验收为依据。

下一轮围绕数据保护、执行可靠性和能力展示展开，先把现有工作台的关键流程做扎实，再用真实任务验证模型表现。

### 第一阶段：保护数据与用户输入

| 计划 | 验收标准 |
| --- | --- |
| **技能安全导入与替换** | 安装前校验技能名称、目标路径和完整内容；无效导入不影响目录外文件，替换失败保留原技能 |
| **统一文件权限判断** | 按实际路径执行只读与授权规则；不同路径写法不能改写上传原件，`ls` 按传入的目标目录判断权限 |
| **插话消息先保存再处理** | 连续插话、达到运行预算、取消或重启后，已接收消息仍可查；未处理消息有明确状态和后续处理入口 |
| **准确记录工具执行** | 执行前产生开始事件，耗时覆盖实际执行区间；并发、超时和取消的步骤均能正确结束并追踪 |
| **会话与文件一致清理** | 使用统一的会话目录定义；删除会话时处理活动运行，并清理对应上传资料与交付物 |

本阶段为上述边界补回归测试，覆盖正常流程、拒绝操作和失败后保留原数据。

### 第二阶段：完善运行可靠性与使用体验

| 计划 | 验收标准 |
| --- | --- |
| **统一上下文预算** | 统计最终请求中的历史、思考、系统提示、工具定义与技能全文；应用输入上限并预留输出空间，前端展示与实际裁剪一致 |
| **刷新与断线恢复** | 重新打开会话可恢复活动运行状态，持续同步进度和最终结果；仍在运行的任务可停止，断线后的事件缓存受控 |
| **定时任务失败可见、可重试** | 区分“到点触发”和“成功创建运行”；启动失败保留错误与重试入口，单次任务不会因启动失败静默跳过 |
| **明确追踪价格状态** | 未知价格与零费用分别展示，避免把缺少价格目录误认为免费 |

### 第三阶段：建立自动验证与真实任务验收

| 计划 | 验收标准 |
| --- | --- |
| **接入 GitHub Actions** | Push 和 PR 自动执行后端测试、Ruff 与前端构建，依赖按锁文件安装；失败结果可直接定位 |
| **建立真实模型评测集** | 按需运行固定任务，检查工具选择、授权边界和交付物正确性，记录模型配置、耗时、Token 与费用；模拟测试和真实模型结果分别报告 |
| **打通资料整理流程** | 围绕“上传资料 → 按技能整理 → 输出文件 → 追踪复盘”提供可复现样例；交付物可下载，内容可对照输入核验 |

### 部署扩展：按使用规模推进

面向公网、多人或多后端进程部署时，再推进以下能力：

- 身份认证、会话与文件归属校验，以及模型凭据的访问控制。
- 跨进程运行状态协调、定时任务领取与防重复执行机制。
- 数据库迁移、备份与恢复验证，以及负载测试。

## 进一步阅读

- [业务与架构设计](docs/design.md)
- [Agent 停止规则调研](docs/agent-stop-rules.md)
- [模型与环境配置示例](.env.example)
- [Agent 主循环源码](services/agent-api/src/agent_api/agent/loop.py)

## License

[Apache License 2.0](LICENSE)
