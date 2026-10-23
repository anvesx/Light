# Base layer + plugins: harness architectures

Researched Oct 15, 2026 by a Sonnet researcher agent through web fetches of docs and GitHub pages. **No repo was cloned and no raw source was read.** Best label: confirmed-from-docs.

## DeepSeek harness (confirmed-from-docs)
- Real. `dsh`, MIT licence, developer preview, built on the Cordis plugin framework. https://github.com/deepseek-ai/deepseek-harness , architecture: https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/architecture.md
- The model adapter, tool registry, session log and agent loop are all plugins.
- Plugins load in layers: profile bundles, then `cordis.patch.yml`, then home and `--patch` overlays. https://github.com/deepseek-ai/deepseek-harness/blob/master/apps/cli/reference/README.md
- A plugin can add tools, event hooks, prompt sections, LLM adapters, a replacement agent loop and subagent providers.
- Loop: `packages/core/agent-loop` (path from docs, not opened).

## Google Antigravity "MD to graph" (NOT confirmed)
- No graph feature found. Antigravity IDE workflows are Markdown files the agent runs step by step. They are not compiled into a graph. https://antigravity.google/docs/ide/workflows/
- Workflows stop working on Oct 19, 2026. Google is moving them to skills.
- The SDK has policies, hooks, subagents, MCP, SKILL.md skills and triggers. No graph or workflow compiler. It runs on a bundled closed binary. https://antigravity.google/docs/sdk/overview/ , https://github.com/google-antigravity/antigravity-sdk-python
- Rachit may mean a different product, or an internal behaviour that is not documented.

## Graph + loop
- LangGraph mixes fixed graph nodes and agent nodes in one graph: https://docs.langchain.com/oss/python/langgraph/overview

## Recommended base-layer components (agent's synthesis)
1. Model adapter (multi-LLM). 2. Agent loop, replaceable. 3. Tool registry and MCP client. 4. Policy and permission gate on every tool call. 5. Hook or event bus. 6. Context manager (compaction, prompt assembly). 7. Session store. 8. Plugin loader with layered config. 9. Durable runner (Temporal https://docs.temporal.io/ai-cookbook , Restate or Inngest) plus a scheduler. 10. Tracing.

## Read first
- **Pi**, repo `earendil-works/pi`. Loop: `packages/agent/src/agent-loop.ts`. Extensions: `packages/coding-agent/docs/extensions.md`. Small, many LLM providers.
- **dsh** second, for its plugin design.

## Not verified
Raw source, line counts, loader code; DSPy; Hermes skill learning (secondary only, https://hermes-agent.nousresearch.com/docs); Claude Agent SDK; opencode multi-LLM; Restate vs Inngest.
