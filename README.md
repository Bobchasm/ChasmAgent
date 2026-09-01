# Chasm Agent

Local coding agent with:
- FastAPI backend
- local tool execution
- persistent SQLite sessions and login
- IDE-like web UI

## Run

```bash
conda activate coding-agent
chasm-agent serve --reload
```

Open the printed URL in your browser.

## Data

- Database: `~/.chasm/chasm.sqlite3`
- Legacy session import: `.chasm/sessions/*.json`
- Workspace memory: `<workspace>/.chasm/memory.json`

## Auth

First launch can bootstrap a local account from the UI.
You can also register and log in manually.

## DashScope

Set:

```bash
CHASM_PROVIDER=dashscope
DASHSCOPE_API_KEY=...
OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
OPENAI_MODEL=qwen3.8-flash
CHASM_ENABLE_THINKING=1
```
