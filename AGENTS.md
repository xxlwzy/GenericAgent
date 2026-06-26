# AGENTS.md

## Cursor Cloud specific instructions

GenericAgent is a single Python product: a minimalist self-evolving autonomous agent. The core is the agent loop in `agent_loop.py` driven by `agentmain.py`; `llmcore.py` is the LLM client layer and `ga.py` holds the tools. Many frontends (`frontends/`, `launch.pyw`, `hub.pyw`) are alternate surfaces over the same agent — all optional.

- Use `python3` (there is no `python` alias on this VM). Interpreter must be 3.10–3.13; do not use 3.14 (pywebview incompatibility).
- Dependencies follow `pyproject.toml`: the update script installs only the core (`pip install -e .`). Install extras on demand, never all at once — `.[ui]` (streamlit/pywebview/textual, needs a display for the GUI) or `.[all-frontends]` (chat-bot SDKs). This selective approach is intentional per the comment atop `pyproject.toml`.
- An LLM endpoint is the only hard runtime requirement. Copy `mykey_template.py` → `mykey.py` (gitignored) and fill exactly one config. The **variable name** (not the model name) selects the protocol: `native_oai_config`/`native_claude_config` (native tool-calling, recommended), or `oai_*`/`claude_*` (text-protocol). Without `mykey.py`, the agent fails fast at startup: `mykey.py or mykey.json not found`.
- For plumbing tests when no real API key exists, point `mykey.py` at any local OpenAI-compatible server (`native_oai_config` with `stream: False`); the real agent loop and tools then run unchanged.
- Secrets gotcha: the provided `OPENAI_API_BASE` / `OPENAI_API_KEY` are swapped (the *base* holds the `ms-…` key, the *key* holds the `https://…/v1` URL). `mykey.py` detects each by shape (`'://'` ⇒ base) so it works regardless. The endpoint is a ModelScope-style relay; default model is `Qwen/Qwen3-235B-A22B-Instruct-2507` (override with `GA_MODEL`). Names containing `glm`/`minimax`/`kimi` auto-switch to the `_cn` tool schema in `agentmain.py`.

### Run / test
- CLI (core, simplest): `python3 agentmain.py` then type a task at the `>` prompt. The REPL reads stdin, so piping one command and then EOF prints a harmless `EOFError` traceback *after* the task finishes — not a failure.
- One-shot file-IO mode: `python3 agentmain.py --task <name> --input "..."` (backgrounds itself unless `--nobg`).
- GUI: `python3 launch.pyw` (Streamlit in a pywebview window; needs a display). TUI: `python3 frontends/tuiapp.py`.
- Tests: `python3 -m unittest tests.test_tgapp_stream_segments` (the only test file; uses stubbed imports, no LLM needed).
- No linter/formatter is configured in the repo; `python3 -m py_compile <files>` is the available static check.
