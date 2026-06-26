# AGENTS.md

## Cursor Cloud specific instructions

GenericAgent is a single Python product: a minimalist self-evolving autonomous agent. The core is the agent loop in `agent_loop.py` driven by `agentmain.py`; `llmcore.py` is the LLM client layer and `ga.py` holds the tools. Many frontends (`frontends/`, `launch.pyw`, `hub.pyw`) are alternate surfaces over the same agent — all optional.

- Use `python3` (there is no `python` alias on this VM). Interpreter must be 3.10–3.13; do not use 3.14 (pywebview incompatibility).
- Dependencies follow `pyproject.toml`: the update script installs only the core (`pip install -e .`). Install extras on demand, never all at once — `.[ui]` (streamlit/pywebview/textual, needs a display for the GUI) or `.[all-frontends]` (chat-bot SDKs). This selective approach is intentional per the comment atop `pyproject.toml`.
- An LLM endpoint is the only hard runtime requirement. Copy `mykey_template.py` → `mykey.py` (gitignored) and fill exactly one config. The **variable name** (not the model name) selects the protocol: `native_oai_config`/`native_claude_config` (native tool-calling, recommended), or `oai_*`/`claude_*` (text-protocol). Without `mykey.py`, the agent fails fast at startup: `mykey.py or mykey.json not found`.
- For plumbing tests when no real API key exists, point `mykey.py` at any local OpenAI-compatible server (`native_oai_config` with `stream: False`); the real agent loop and tools then run unchanged.
- Secrets gotcha: the provided `OPENAI_API_BASE` / `OPENAI_API_KEY` are swapped (the *base* holds the `ms-…` key, the *key* holds the `https://…/v1` URL). `mykey.py` detects each by shape (`'://'` ⇒ base) so it works regardless. The endpoint is a ModelScope-style relay. Names containing `glm`/`minimax`/`kimi` auto-switch to the `_cn` tool schema in `agentmain.py`.
- Preferred model failover (user preference): use `MixinSession` with this priority — `ZhipuAI/GLM-5.2` → `deepseek-ai/DeepSeek-V4-Pro` → `Qwen/Qwen3.5-397B-A17B` → `MiniMax/MiniMax-M3` → `Qwen/Qwen3-235B-A22B-Instruct-2507`. Configure in `mykey.py` via a `mixin_config = {'llm_nos': [<model names in order>], 'max_retries': 4}` plus one `native_oai_*config` per model (same base/key, differing `model`). Make `mixin_config` the first non-underscore var so it becomes the default `llmclients[0]`. On any `!!!Error:` the loop advances to the next model and springs back to the primary after `spring_back` seconds (default 300). Note: the relay frequently returns HTTP 429 (`limit_burst_rate` / `insufficient_quota`) for GLM-5.2 and DeepSeek-V4-Pro, so failover commonly lands on the Qwen models — expected, not a bug.

### Run / test
- CLI (core, simplest): `python3 agentmain.py` then type a task at the `>` prompt. The REPL reads stdin, so piping one command and then EOF prints a harmless `EOFError` traceback *after* the task finishes — not a failure.
- One-shot file-IO mode: `python3 agentmain.py --task <name> --input "..."` (backgrounds itself unless `--nobg`).
- GUI: `python3 launch.pyw` (Streamlit in a pywebview window; needs a display). TUI: `python3 frontends/tuiapp.py`.
- Tests: `python3 -m unittest tests.test_tgapp_stream_segments` (the only test file; uses stubbed imports, no LLM needed).
- No linter/formatter is configured in the repo; `python3 -m py_compile <files>` is the available static check.
