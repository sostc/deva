# Layer Model — AI Stack Classification Standard

## Layer Definitions

```
L5 App          -> Wrapper, Demo, Application (thin wrappers, tutorial projects)
L4 Agent Product -> Vertical AI product (end-user-facing agent products)
L3 Platform     -> Developer Abstraction, SDK, Framework (developer-facing)
L2 Runtime      -> Agent Runtime, Orchestration, Memory, Tool-calling Infra
L1 Model        -> Training, Inference, Fine-tune, the model itself
```

## Classification Rules (match top-down by priority)

### L1 Model
**Keywords**: training, inference, quantization, fine-tune, GGUF, ONNX, model weights, checkpoint, serving
**Core characteristics**: Primary code is model architecture definition, training loops, inference engines
**Typical projects**:
- `ggerganov/llama.cpp` — Local inference engine
- `vllm-project/vllm` — High-performance LLM serving
- `huggingface/transformers` — Model hub + training framework
- `unslothai/unsloth` — Fast fine-tuning
- `ollama/ollama` — Local model runner

### L2 Runtime
**Keywords**: runtime, orchestration, memory, tool-calling, function calling, agent loop, execution engine, state machine
**Core characteristics**: Agent execution loop, state management, tool registration/dispatch, memory storage; not directly end-user-facing
**Typical projects**:
- `microsoft/autogen` — Multi-agent conversation runtime
- `langchain-ai/langgraph` — Agent state machine runtime
- `mem0ai/mem0` — Agent memory infrastructure
- `letta-ai/letta` (formerly MemGPT) — Stateful agent runtime
- `chromadb/chroma` — Vector store (memory infra)

### L3 Platform
**Keywords**: SDK, framework, library, CLI tool, developer tool, API wrapper
**Core characteristics**: Offers `pip install` / `npm install`, README targets developers, lowers the barrier to building
**Typical projects**:
- `langchain-ai/langchain` — LLM application framework
- `run-llama/llama_index` — Data framework for LLM
- `stanfordnlp/dspy` — Programmatic prompting framework
- `jxnl/instructor` — Structured output SDK
- `BerriAI/litellm` — LLM API proxy/gateway

### L4 Agent Product
**Keywords**: assistant, copilot, IDE, UI, chat, app
**Core characteristics**: Has a complete UI, targets non-developers or specific user roles, solves a vertical use case
**Typical projects**:
- `getcursor/cursor` — AI code editor
- `continuedev/continue` — IDE AI assistant
- `paul-gauthier/aider` — AI pair programming
- `KillianLucas/open-interpreter` — Natural language computer interface
- `langgenius/dify` — LLM app platform with UI

### L5 App
**Keywords**: clone, tutorial, demo, example, wrapper, starter
**Core characteristics**: Wrappers forked from L3/L4, personal learning projects, primarily tutorials
**Typical projects**:
- Various `chatgpt-clone`, `langchain-tutorial` repos
- Simple API wrapper frontends
- Hackathon demo projects

## Edge Case Guide

| Scenario | Classification | Rationale |
|----------|---------------|-----------|
| Both SDK and UI (e.g., Dify, Flowise) | Look at the **primary user base**: mostly developers -> L3; mostly end users -> L4 | Dify = L4 (no-code focus), LangChain = L3 |
| RAG framework | Look at the **abstraction level**: pipeline engine -> L2; provides SDK -> L3 | LlamaIndex = L3, Chroma = L2 |
| Vector Database | L2 | Runtime infrastructure, part of the agent memory layer |
| Prompt engineering tool | L3 | Developer tool that lowers the barrier to prompt construction |
| AI code editor | L4 | Vertical product; targets developers as end users |
| Model benchmark/eval | L3 | Developer tool |
| MCP server/client | L2 | Tool-calling infrastructure |
| LLM API gateway/proxy | L3 | Developer abstraction layer |
| Uncertain | Label as `[L?-TBD]` | Explain in the report why classification is difficult |

## PM Priority

```
L2 > L3 > L4 > L1 > L5
```

- **L2 is most important**: Runtime layer shifts = paradigm shift; it signals that the industry's understanding of agent architecture is evolving
- **L3 is next**: The Platform layer reflects real developer demand; which framework is growing = what building approach developers are choosing
- **L4 validates the market**: Product form factors prove which use cases are viable
- **L1 is foundational**: Changes are slow but deeply impactful; a new inference engine can reshape the layers above
- **L5 has the most noise**: Usually ignored, unless a mass-fork signal emerges
