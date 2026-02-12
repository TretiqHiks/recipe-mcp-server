import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from mcp.client.session import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters


OLLAMA_CHAT_URL = "http://localhost:11434/api/chat"
MODEL = "llama3.1"


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


def mcp_tools_to_ollama_tools(mcp_list_tools_response) -> List[Dict[str, Any]]:
    """
    Convert MCP tool definitions into Ollama's `tools` format.
    MCP: tools.tools[*].name, .description, .inputSchema
    Ollama expects: [{type:"function", function:{name, description, parameters}}]
    """
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


def tool_result_content_to_json_string(content: Any) -> str:
    """Convert MCP CallToolResult.content (list of ContentBlock e.g. TextContent) to a string for Ollama."""
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


async def main() -> None:
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

            messages: List[Dict[str, Any]] = [
                {
                    "role": "system",
                    "content": (
                        "You are a recipe assistant. Use tools when helpful. "
                        "Prefer searching local recipes before inventing. "
                        "When the user asks to list, show, or check pantry items (or what's in the pantry), "
                        "you MUST call pantry_list_items and report exactly what it returns—never list common or example pantry items from memory."
                    ),
                },
            ]

            while True:
                user_text = input("You: ").strip()
                if not user_text:
                    print("Goodbye.")
                    break
                messages.append({"role": "user", "content": user_text})

                for step in range(20):
                    resp = ollama_chat(messages, ollama_tools)
                    msg = resp.get("message", {})
                    tool_calls = msg.get("tool_calls") or []
                    content = (msg.get("content") or "").strip()
                    if not tool_calls:
                        if content:
                            print(f"\nAssistant: {content}")
                        else:
                            print("\nAssistant: (no content)")
                        messages.append(msg)
                        break
                    messages.append(msg)
                    for tc in tool_calls:
                        fn = tc.get("function", {})
                        tool_name = fn.get("name")
                        tool_args = normalize_tool_arguments(fn.get("arguments"))
                        if not tool_name:
                            continue
                        mcp_result = await mcp_session.call_tool(tool_name, tool_args)
                        messages.append(
                            {
                                "role": "tool",
                                "name": tool_name,
                                "content": tool_result_content_to_json_string(mcp_result.content),
                            }
                        )
                else:
                    print("\nAssistant: (stopped after too many tool steps)")
                    messages.append(msg)

if __name__ == "__main__":
    asyncio.run(main())
