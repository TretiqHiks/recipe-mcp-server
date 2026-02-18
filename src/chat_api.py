"""
Minimal HTTP API for the recipe chat (MCP + Ollama).
Serves the chat UI and exposes POST /api/chat for one assistant turn.
"""
import logging
import os
import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

# Add project root so we can import olama_mcp_host and run recipe_mcp server
_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from src.olama_mcp_host import (
    SYSTEM_PROMPT,
    mcp_tools_to_ollama_tools,
    project_root,
    run_chat_turn,
)
from mcp.client.session import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters

app = FastAPI(title="Recipe Chat API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.on_event("startup")
def _configure_logging() -> None:
    """Ensure tool-call logs from olama_mcp_host are visible."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        force=True,
    )

# --- Request/Response ---


class ChatMessage(BaseModel):
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(..., min_length=1)


class ChatResponse(BaseModel):
    content: str


# --- Chat endpoint ---


@app.post("/api/chat", response_model=ChatResponse)
async def api_chat(body: ChatRequest) -> ChatResponse:
    """Run one assistant turn. Send conversation history; returns the new assistant reply."""
    root = project_root()
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root)
    server = StdioServerParameters(
        command=sys.executable,
        args=["-m", "src.recipe_mcp.server"],
        env=env,
        cwd=root,
    )
    try:
        async with stdio_client(server) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as mcp_session:
                await mcp_session.initialize()
                mcp_tools = await mcp_session.list_tools()
                ollama_tools = mcp_tools_to_ollama_tools(mcp_tools)

                messages = [{"role": "system", "content": SYSTEM_PROMPT}]
                for m in body.messages:
                    messages.append({"role": m.role, "content": m.content})

                content = await run_chat_turn(messages, ollama_tools, mcp_session)
                return ChatResponse(content=content)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Chat failed: {e!s}")


# --- Serve frontend ---

FRONTEND_DIR = _root / "frontend"


@app.get("/")
async def index():
    """Serve the chat UI."""
    index_path = FRONTEND_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="Frontend not found. Create frontend/index.html")
    return FileResponse(index_path)


if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
