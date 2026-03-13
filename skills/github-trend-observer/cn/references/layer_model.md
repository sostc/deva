# Layer Model — AI Stack 分层标准

## 分层定义

```
L5 App          → Wrapper、Demo、Application（套壳产品、教程项目）
L4 Agent Product → 垂直 AI 产品形态（面向终端用户的 agent 产品）
L3 Platform     → Developer Abstraction、SDK、Framework（面向开发者）
L2 Runtime      → Agent Runtime、Orchestration、Memory、Tool-calling Infra
L1 Model        → 训练、推理、Fine-tune、模型本体
```

## 判定规则（按优先级从上到下匹配）

### L1 Model
**关键词**：training, inference, quantization, fine-tune, GGUF, ONNX, model weights, checkpoint, serving
**核心特征**：主要代码是模型架构定义、训练循环、推理引擎
**典型项目**：
- `ggerganov/llama.cpp` — 本地推理引擎
- `vllm-project/vllm` — 高性能 LLM serving
- `huggingface/transformers` — 模型库 + 训练框架
- `unslothai/unsloth` — 快速 fine-tuning
- `ollama/ollama` — 本地模型运行

### L2 Runtime
**关键词**：runtime, orchestration, memory, tool-calling, function calling, agent loop, execution engine, state machine
**核心特征**：agent 执行循环、状态管理、工具注册/调度、记忆存储，不直接面向终端用户
**典型项目**：
- `microsoft/autogen` — multi-agent conversation runtime
- `langchain-ai/langgraph` — agent 状态机 runtime
- `mem0ai/mem0` — agent memory infrastructure
- `letta-ai/letta` (原 MemGPT) — stateful agent runtime
- `chromadb/chroma` — vector store (memory infra)

### L3 Platform
**关键词**：SDK, framework, library, CLI tool, developer tool, API wrapper
**核心特征**：提供 `pip install` / `npm install`，README 面向开发者，降低构建门槛
**典型项目**：
- `langchain-ai/langchain` — LLM application framework
- `run-llama/llama_index` — data framework for LLM
- `stanfordnlp/dspy` — programmatic prompting framework
- `jxnl/instructor` — structured output SDK
- `BerriAI/litellm` — LLM API proxy/gateway

### L4 Agent Product
**关键词**：assistant, copilot, IDE, UI, chat, app
**核心特征**：有完整 UI，面向非开发者或特定角色用户，解决某个垂直场景
**典型项目**：
- `getcursor/cursor` — AI code editor
- `continuedev/continue` — IDE AI assistant
- `paul-gauthier/aider` — AI pair programming
- `KillianLucas/open-interpreter` — natural language computer interface
- `langgenius/dify` — LLM app platform with UI

### L5 App
**关键词**：clone, tutorial, demo, example, wrapper, starter
**核心特征**：fork 自 L3/L4 的 wrapper，个人学习项目，教程为主
**典型项目**：
- 各种 `chatgpt-clone`, `langchain-tutorial`
- 简单的 API wrapper 前端
- Hackathon demo 项目

## 边界情况指南

| 情况 | 判定 | 理由 |
|------|------|------|
| 既是 SDK 又有 UI (如 Dify, Flowise) | 看**核心用户群**：开发者为主 → L3，终端用户为主 → L4 | Dify = L4（主打 no-code），LangChain = L3 |
| RAG 框架 | 看**抽象层级**：pipeline engine → L2，提供 SDK → L3 | LlamaIndex = L3，Chroma = L2 |
| Vector Database | L2 | Runtime 基础设施，agent memory 的一部分 |
| Prompt engineering 工具 | L3 | 开发者工具，降低 prompt 构建门槛 |
| AI code editor | L4 | 垂直产品，面向开发者但作为终端用户 |
| Model benchmark/eval | L3 | 开发者工具 |
| MCP server/client | L2 | Tool-calling infrastructure |
| LLM API gateway/proxy | L3 | Developer abstraction layer |
| 不确定 | 标注 `[L?-待确认]` | 在报告中说明判断困难的原因 |

## PM 关注优先级

```
L2 > L3 > L4 > L1 > L5
```

- **L2 最重要**：Runtime 层变动 = paradigm shift，说明行业对 agent 架构的理解在进化
- **L3 其次**：Platform 层反映开发者真实需求，哪个 Framework 增长 = 开发者选择了什么构建方式
- **L4 验证市场**：产品形态验证了哪些 use case 成立
- **L1 基础设施**：变化慢但影响深远，新推理引擎可能重塑上层生态
- **L5 噪声最多**：通常忽略，除非出现大规模 fork 信号
