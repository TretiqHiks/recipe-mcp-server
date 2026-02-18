# MCP Recipe System

Recipe assistant with a local MCP server (pantry, recipes) and Ollama. Use via CLI or the web chat UI.

## Prerequisites

- Python 3.10+
- [Ollama](https://ollama.ai) running locally with a model (e.g. `llama3.1`)
- (Optional) Install deps: `pip install -r requirements.txt`

## Run the backend (HTTP API + frontend)

From the **project root**:

```bash
# Windows
set PYTHONPATH=%CD%
python -m uvicorn src.chat_api:app --reload --host 0.0.0.0 --port 8000

# Linux / macOS
export PYTHONPATH=.
python -m uvicorn src.chat_api:app --reload --host 0.0.0.0 --port 8000
```

- **Base URL:** `http://localhost:8000`
- **Frontend:** open http://localhost:8000/ in a browser (served by the same process).
- **API:** `POST http://localhost:8000/api/chat`

## Run the CLI (no HTTP)

```bash
# From project root
set PYTHONPATH=%CD%
python -m src.olama_mcp_host
```

Then type messages at the `You:` prompt. Empty line to exit.

## Chat API

**Endpoint:** `POST /api/chat`

**Request:** JSON body with full conversation history (user and assistant messages). The backend adds the system prompt and runs one assistant turn (including tool calls).

```json
{
  "messages": [
    { "role": "user", "content": "List all pantry items" },
    { "role": "assistant", "content": "Your pantry has …" },
    { "role": "user", "content": "Add 2 cans of chickpeas" }
  ]
}
```

**Response:** Non-streamed JSON with the new assistant reply.

```json
{
  "content": "I've added 2 cans of chickpeas to your pantry."
}
```

- **Streaming:** No. The backend uses Ollama with `stream: false`.
- **Errors:** On failure (e.g. MCP or Ollama down), the API returns `502` with a `detail` string.

## Frontend

- **Location:** `frontend/index.html` (single file, no build).
- **Served at:** `/` when the backend is running (same origin).
- **API base URL:** By default the page uses relative URLs (`/api`). To point at another host, set `window.CHAT_API_BASE` before load (e.g. `https://api.example.com`) or use a build step that injects it.

## Logging (tool-call transparency)

When the LLM calls tools, each call is logged at **INFO** level:

- **tool_call** – tool name and arguments (e.g. `pantry_upsert_items`, `recipes_search`).
- **tool_result** – tool name and a short preview of the result (truncated if long).

Logs go to stderr. When running the **CLI**, the host configures logging on startup. When running the **API** (uvicorn), the app configures logging on startup so the same lines appear in the server console. Use these logs to see which tools were used for each request without changing what the user sees in the chat.

## Data

- Recipe and pantry data is stored in `data/recipes.db` (SQLite). The MCP server creates it on first run.
