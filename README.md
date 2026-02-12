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

## Data

- Recipe and pantry data is stored in `data/recipes.db` (SQLite). The MCP server creates it on first run.
