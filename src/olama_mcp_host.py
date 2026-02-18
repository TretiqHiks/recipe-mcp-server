import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from mcp.client.session import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters

logger = logging.getLogger(__name__)


OLLAMA_CHAT_URL = "http://localhost:11434/api/chat"
MODEL = "llama3.1"

SYSTEM_PROMPT = (
    "You are a recipe assistant. Use tools when the user asks about pantry or recipes. "
    "Prefer searching local recipes before inventing.\n"
    "\n"
    "*** YOUR REPLY MUST BE PLAIN TEXT ONLY ***\n"
    "Never in your reply: no function/tool names (e.g. pantry_upsert_items, recipes_search), no JSON, no code, "
    "no 'I will use the following tools', no 'Here is the JSON', no numbered steps of what you will do, "
    "no 'To answer your request I will...', no describing how you will call tools. "
    "Just do the actions (using the tools silently) and then write a short, natural answer with the result. "
    "Example: User says 'add 2 sausages and suggest a recipe'. You reply only something like: "
    "'Done. I added 2 sausages to your pantry. Here's a recipe you could try: [recipe name and brief summary].' "
    "Never say what tools you used or show any technical details.\n"
    "\n"
    "IMPORTANT: When the user asks for multiple actions (e.g. add X then suggest a recipe), do ALL of them in order, then reply once with the outcome. "
    "SOURCE OF TRUTH: Only the tools know the current pantry and recipes. Always use the list-pantry and search/get-recipe tools when suggesting recipes; never use old chat or memory.\n"
    "\n"
    "Tool usage: Use the tools to list/add/remove pantry items and to search or get recipes. Use multiple tools in sequence when needed. "
    "When listing pantry items, report only what the list tool returns."
)


def project_root() -> Path:
    # <root>/src/ollama_mcp_host.py -> <root>
    return Path(__file__).resolve().parent.parent


def ollama_chat(messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]) -> Dict[str, Any]:
    payload = {
        "model": MODEL,
        "stream": False,
        "messages": messages,
        "tools": tools,
    }
    r = requests.post(OLLAMA_CHAT_URL, json=payload, timeout=120)
    r.raise_for_status()
    return r.json()


#convert MCP to OLLAMA

def mcp_tools_to_ollama_tools(mcp_list_tools_response) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for t in mcp_list_tools_response.tools:
        out.append(
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description or "",
                    "parameters": t.inputSchema or {"type": "object", "properties": {}},
                },
            }
        )
    return out


def normalize_tool_arguments(args: Any) -> Dict[str, Any]:
    # Ollama sometimes returns arguments as a JSON string
    if args is None:
        return {}
    if isinstance(args, str):
        return json.loads(args)
    if isinstance(args, dict):
        return args
    return dict(args)


def _tool_result_preview(content: Any, max_len: int = 120) -> str:
    """Short summary of tool result for logs (avoid huge payloads)."""
    if content is None:
        return "null"
    if isinstance(content, list):
        if not content:
            return "[]"
        first = content[0]
        if hasattr(first, "text"):
            text = getattr(first, "text", str(first))[:max_len]
        else:
            text = str(first)[:max_len]
        return f"[{len(content)} item(s)] " + (text + "..." if len(text) >= max_len else text)
    if isinstance(content, (str, int, float, bool)):
        s = str(content)
        return s[:max_len] + "..." if len(s) > max_len else s
    s = json.dumps(content, default=str)[:max_len]
    return s + "..." if len(s) >= max_len else s


def tool_result_content_to_json_string(content: Any) -> str:
    if content is None:
        return "{}"
    if isinstance(content, (str, int, float, bool)):
        return json.dumps(content)
    if isinstance(content, list):
        parts = []
        for block in content:
            if hasattr(block, "model_dump"):
                parts.append(block.model_dump())
            elif hasattr(block, "text"):
                parts.append({"type": "text", "text": block.text})
            else:
                parts.append(str(block))
        return json.dumps(parts)
    if isinstance(content, dict):
        return json.dumps(content)
    return json.dumps(str(content))


async def run_chat_turn(
    messages: List[Dict[str, Any]],
    ollama_tools: List[Dict[str, Any]],
    mcp_session: ClientSession,
) -> str:
    """Run one assistant turn (tool loop until no more tool_calls). Mutates messages. Returns final assistant text."""
    for _ in range(20):
        resp = ollama_chat(messages, ollama_tools)
        msg = resp.get("message", {})
        tool_calls = msg.get("tool_calls") or []
        content = (msg.get("content") or "").strip()
        if not tool_calls:
            return content or "(no content)"
        messages.append(msg)
        for tc in tool_calls:
            fn = tc.get("function", {})
            tool_name = fn.get("name")
            tool_args = normalize_tool_arguments(fn.get("arguments"))
            if not tool_name:
                continue
            logger.info("tool_call name=%s args=%s", tool_name, json.dumps(tool_args, default=str))
            mcp_result = await mcp_session.call_tool(tool_name, tool_args)
            result_preview = _tool_result_preview(mcp_result.content)
            logger.info("tool_result name=%s -> %s", tool_name, result_preview)
            messages.append(
                {
                    "role": "tool",
                    "name": tool_name,
                    "content": tool_result_content_to_json_string(mcp_result.content),
                }
            )
    return "(stopped after too many tool steps)"


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    root = project_root()

    env = os.environ.copy()
    env["PYTHONPATH"] = str(root)


    server = StdioServerParameters(
        command=sys.executable,
        args=["-m", "src.recipe_mcp.server"],
        env=env,
        cwd=root,
    )

    async with stdio_client(server) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as mcp_session:
            await mcp_session.initialize()

            mcp_tools = await mcp_session.list_tools()
            ollama_tools = mcp_tools_to_ollama_tools(mcp_tools)

            messages: List[Dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]

            while True:
                user_text = input("You: ").strip()
                if not user_text:
                    print("Goodbye.")
                    break
                messages.append({"role": "user", "content": user_text})
                content = await run_chat_turn(messages, ollama_tools, mcp_session)
                messages.append({"role": "assistant", "content": content})
                print(f"\nAssistant: {content}")

if __name__ == "__main__":
    asyncio.run(main())
