# Valet

可复用的智能体调试台：主循环、工具、会话文件目录和全链路追踪。名字默认是 Valet，换项目时改 `.env` 里的 `AGENT_NAME`。业务设计见 [`docs/design.md`](docs/design.md)。

## 底座里有什么

- **主循环**（`services/agent-api/src/agent_api/agent/loop.py`）：原生函数调用。停的方式有四层：
  - 最大步数到了，去掉工具，用已有结果再答一次；
  - 单个工具超时，把错误交回模型，循环继续；
  - 模型流空闲超时：一直有新输出就不掐断，安静太久才停；
  - 运行时间上限只在两轮之间检查。正在输出的这一轮会跑完，到点后不再开新工具，用已有结果收尾。
  - 另外可以中途取消，工具连续失败会停下来说明原因。运行中再发一条消息会插进当前这轮，等这一轮结束再处理。
- **上下文**：历史太长时按轮次丢掉较早的工具结果，并在系统提示里注明。
- **护栏**（`agent/guardrails.py`）：位于「模型决定调用工具」与「工具执行」之间。未启用的工具会被拦截；需要确认的工具会暂停运行，等用户确认或拒绝后再继续。
- **工具**分两类，都注册在 `tools/`，在设置的工具页里开关：
  - 正式工具默认打开：天气、联网搜索、项目文件（`ls` / `read_file` / `write_file` / `str_replace`）。工作区是项目根目录。上传和交付物在项目内的 `.valet/sessions/{会话}/`。`.env`、密钥和 `.git` 不能读写。项目外路径和联网会先请求授权：本次允许、本对话允许或拒绝。
  - 示例工具默认关闭，用来试成功、参数错误、超时、连续失败和需确认这几条路径。
- **搜索**：`web_search` 要求用用户正在使用的语言搜一次。
- **技能**分三类。`skills/market/` 是平台收录的技能市场，浏览后点「使用」才安装。`skills/builtin/` 是注册就有的技能，包括 Word、PDF、PPT 和平台自带能力。`data/skills/` 是每个人另外导入的技能，显示在「已安装」，不包含内置技能。模型能用内置技能、已安装技能，以及自己从市场装上的技能。系统提示里只有名字和何时使用；`read_skill` 再读全文。输入框里点中的技能，只在这一轮把正文注进提示。
- **追踪**（`tracing/`）：数据层级是会话 → 运行 → 步骤。每一步都记录输入、输出、耗时、token 和费用估算；每次运行保存一份配置快照。字段按 OpenTelemetry GenAI 约定命名，预留了导出接口。
- **前端**（`web/`，Vue 3 + shadcn-vue + Tailwind v4）：对话页（流式输出、深度思考可折叠、工具卡片、确认卡片、停止按钮）、右侧追踪抽屉、模型配置、工具列表、运行记录。界面上的名字来自后端的 `AGENT_NAME`。

已经保存过的系统提示词不会跟着 `AGENT_NAME` 自动改，在设置的「通用」里改第一句即可。

## 本地运行

需要 Docker、Python 3.12+（用 [uv](https://docs.astral.sh/uv/) 管理）、Node 22+ 和 pnpm。

```bash
cp .env.example .env          # 填 DASHSCOPE_API_KEY；没有 Key 就把 LLM_PROVIDER 改成 mock
docker compose up -d          # Postgres（端口 5433）

cd services/agent-api
uv sync
uv run uvicorn agent_api.main:app --reload --reload-dir src --port 8000

cd web                        # 另开一个终端
pnpm install
pnpm dev                      # http://localhost:5173
```

**不装 Docker、不配 Key 也能体验**：后端用 SQLite 加本地模拟模型启动。模拟模型按关键词触发探针工具，不调外部接口，也不计费。

```bash
cd services/agent-api
LLM_PROVIDER=mock DATABASE_URL="sqlite+aiosqlite:///./dev.db" uv run uvicorn agent_api.main:app --reload --reload-dir src
```

## 测试

```bash
cd services/agent-api && uv run pytest && uv run ruff check src tests
cd web && pnpm build
```

后端测试用一个按脚本回复的假模型，覆盖以下路径：成功、参数校验错误回填、工具超时、连续失败熔断、最大步数、确认后执行、拒绝执行、新消息打断待确认操作、中途取消、未启用工具被拦截。

## License

Apache License 2.0 — see [`LICENSE`](LICENSE).
