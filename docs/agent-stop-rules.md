# 运行停止规则调研

> 2026-10-10。对照问题：整次运行超过 120 秒就记为失败（`run_timeout`，文案「运行超过 N 秒未完成」）。
> 只记一手来源：各框架官方文档或仓库源码。

## 我们现在怎么停

按上面的结论改过了，主预算仍是步数。

- 最大步数、连续失败：到顶后去掉工具再要一次回复。
- 运行上限默认 900 秒，只在两轮之间检查。正在输出的这一轮会跑完；到点后不再调用工具，用已有结果收尾。有回复记 `completed` / `run_timeout`，没有回复才记失败。
- 模型流空闲默认 90 秒。中间一直有新内容就不会触发。已经写出的正文会留下，记 `stream_idle`。
- 单个工具超时仍把错误交回模型。用户取消是独立路径。

## 其他框架

| 框架 | 主停止条件 | 时间怎么用 | 到顶之后 |
| --- | --- | --- | --- |
| pi-agent-core | 模型自己停；`abort()` 硬停；`shouldStopAfterTurn` 在本轮工具跑完后退出 | 循环里没有整次运行墙钟。卡住不返回是已知问题 | 优雅停不取消正在跑的工具，也不改 stop reason |
| DeerFlow | 主代理 `recursion_limit` 默认 100，服务端天花板 1000。子代理另有 `max_turns`（通用 150，bash 60） | 子代理墙钟默认 1800 秒，bash 300 秒。主代理没有 120 秒这种短墙钟 | 循环、token 预算到顶时剥掉 tool call，逼出收尾回答。有可用结果则 `completed`，再标 `loop_capped` / `token_capped` / `turn_capped`；没有可用结果才 `failed` |
| OpenAI Agents SDK | `max_turns` 默认 10，可传 `None` 关掉 | 没有整次运行墙钟。工具可单独设超时 | 默认抛 `MaxTurnsExceeded`。`error_handlers["max_turns"]` 可改成返回一段收尾文本。工具超时默认 `error_as_result`，把超时文案交回模型 |
| Claude Agent SDK | `max_turns`、`max_budget_usd` 默认都不设 | `API_TIMEOUT_MS` 默认 600000，是单次请求超时，主循环和子代理都用它 | 命中上限得到 `error_max_turns` 或 `error_max_budget_usd`。单次 `query()` 先交出这条结果再抛错 |
| smolagents | `max_steps` 默认 20，或模型调用 `final_answer` | 超时在代码执行上（文档中的执行超时），不在整次运行上 | 步数用尽后 `provide_final_answer`，用已有日志写一个答案。`interrupt()` 在当前步结束后停 |
| LangGraph | `recursion_limit`。1.0.6 起默认 1000 个 super-step | 超时挂在节点上：`run_timeout` 是单次尝试墙钟，`idle_timeout` 在有进度时重置 | 超步数抛 `GraphRecursionError`。`RemainingSteps` 用来在撞墙前收尾。`request_drain()` 等当前 super-step 跑完再停，检查点可恢复 |

### pi

循环在还有工具调用或插话时继续。没有 max turns，也没有整次运行超时。停的方式是：

- `agent.abort()`：取消当前操作。
- `shouldStopAfterTurn`：本轮模型和工具都正常结束后返回 true，发出 `agent_end`，不再拉队列、不再发起下一次模型调用。不打断流，不取消工具。
- 工具结果可以带 `terminate: true`，且这一批每个结果都这样才提前停。

[issue #2381](https://github.com/badlogic/pi-mono/issues/2381) 记录的缺口是反的：模型流或工具 promise 永不返回时，循环会永远挂着。下游补丁加的是 `assistantResponseTimeoutMs` 和 `toolExecutionTimeoutMs`，超时后发出终止事件。那是「单次调用卡住才失败」，不是「整次运行两分钟没做完就失败」。

来源：[packages/agent/README.md](https://github.com/badlogic/pi-mono/blob/main/packages/agent/README.md)，[agent-loop.ts](https://github.com/badlogic/pi-mono/blob/main/packages/agent/src/agent-loop.ts)。

### DeerFlow

主代理走 LangGraph，Gateway 默认 `recursion_limit: 100`，`max_recursion_limit` 默认 1000。请求里可以覆盖，但不能超过天花板。

子代理才有整段墙钟：`timeout_seconds` 默认 1800。内置 general-purpose 默认 150 轮，bash 默认 60 轮、300 秒。

到顶时的兜底是同一套：

- 重复工具：默认 3 次警告，5 次硬停。硬停剥掉 `tool_calls`，不抛异常，让循环自然结束并写出已有结果，标记 `loop_capped`。
- token 预算：先警告「收尾、别再开新工具」；硬阈值同样剥掉 tool call，标记 `token_capped`。源码注释写明 hard stop does not raise。
- 轮数撞上 `GraphRecursionError`：能恢复出最后一条 AI 消息就 `completed` + `turn_capped`，没有可用输出才 `failed` + `turn_capped`。

来源：[Subagents](https://deerflow.tech/en/docs/harness/subagents)，[README recursion_limit](https://github.com/bytedance/deer-flow/blob/main/README.md)，[token_budget_middleware.py](https://github.com/bytedance/deer-flow/blob/main/backend/packages/harness/deerflow/agents/middlewares/token_budget_middleware.py)，[loop_detection_middleware.py](https://github.com/bytedance/deer-flow/blob/main/backend/packages/harness/deerflow/agents/middlewares/loop_detection_middleware.py)，[PR #3980](https://github.com/bytedance/deer-flow/pull/3980)。

### OpenAI Agents SDK

一轮 = 一次模型调用（含该轮工具）。默认最多 10 轮。超过则 `MaxTurnsExceeded`，除非 `error_handlers["max_turns"]` 返回 `final_output`。

异步函数工具的超时默认 `timeout_behavior="error_as_result"`：超时文案回到模型，模型可以改做法。`raise_exception` 才会让整次运行失败。

来源：[Running agents](https://openai.github.io/openai-agents-python/running_agents/)，[Tools](https://openai.github.io/openai-agents-python/tools/)。

### Claude Agent SDK

`max_turns` 只数带工具的回合，不设就是不限。`max_budget_usd` 按客户端费用估计停，子代理花费算进总额。两者都不设时，循环一直跑到模型自己结束。文档建议生产环境用预算，而不是短墙钟。

请求级超时是环境变量 `API_TIMEOUT_MS`，默认 10 分钟，主循环和子代理共用。重试另有次数上限，每次重试有自己的超时窗口。

来源：[How the agent loop works](https://code.claude.com/docs/en/agent-sdk/agent-loop)，[Configure your agent](https://code.claude.com/docs/en/agent-sdk/configuration)，[Python SDK reference](https://code.claude.com/docs/en/agent-sdk/python)。

### smolagents

默认跑到 `final_answer` 或 20 步。步数用尽后 `_handle_max_steps_reached` 调用 `provide_final_answer`，用交互日志写答案，而不是只返回错误。`interrupt()` 在当前步结束时停。

来源：[agents.py](https://github.com/huggingface/smolagents/blob/main/src/smolagents/agents.py)，[Guided tour](https://huggingface.co/docs/smolagents/main/en/guided_tour)。

### LangGraph

超步数是硬错误。1.0.6 起默认 `recursion_limit` 为 1000。`RemainingSteps` 让图在撞墙前自己收尾。

节点超时分成两种：`run_timeout` 限制单次尝试的墙钟；`idle_timeout` 在有流式输出或心跳时重置，长任务只要还在动就不会被掐。超时取消的是这一次节点尝试。`request_drain()` 不杀正在跑的节点，当前 super-step 结束后停，检查点可以接着跑。

来源：[GRAPH_RECURSION_LIMIT](https://docs.langchain.com/oss/python/langgraph/errors/GRAPH_RECURSION_LIMIT)，[Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api)，[Fault tolerance](https://docs.langchain.com/oss/python/langgraph/fault-tolerance)。

## 结论

没有一家把「两分钟没做完」当成主停止条件。墙钟要么不存在（pi、OpenAI Agents 的运行级），要么是十几到三十分钟的防挂死（DeerFlow 子代理、Claude 单次请求 10 分钟），并且优先看「这一步是不是已经卡住」，而不是「整次运行花了多久」。

到顶之后的共同兜底是：停掉新工具，用已经拿到的结果写回复，用 stop reason 标明是被截断的，而不是把运行标成失败。只有完全没有可用输出时才失败。当前循环的步数上限和运行上限都走这条路。
