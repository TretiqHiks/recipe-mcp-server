from __future__ import annotations
import os
from pathlib import Path
from typing import List, Optional
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from .models import Recipe, PantryItem
from .storage import SqliteStore

load_dotenv()

BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_URL = os.getenv("RECIPE_DB_URL", f"sqlite+aiosqlite:///{(DATA_DIR / 'recipes.db').as_posix()}")

store = SqliteStore(DB_URL)

mcp = FastMCP("recipe-system")

@mcp.tool()
async def pantry_list_items() -> List[PantryItem]:
    """
    List all pantry items currently stored in the user's pantry (this system).

    Call this whenever the user asks to list, show, or see pantry items, or what they have in the pantry.
    Use this tool to learn what ingredients are available before:
    - building a meal plan,
    - selecting recipes,
    - generating a shopping list.

    This is a READ-ONLY operation (no state changes).

    Returns:
      A list of PantryItem objects. Each item may include:
      - name (string)
      - qty (number, optional)
      - unit (string, optional)
      - expires (ISO date string, optional)

    Notes:
      - If the pantry is empty, returns an empty list.
      - Item names are treated case-insensitively in storage.
    """
    return await store.list_pantry()


@mcp.tool()
async def pantry_upsert_item(item: PantryItem) -> str:
    """
    Add a new pantry item or update an existing pantry item (upsert).

    Use this tool when the user:
    - adds ingredients to their pantry,
    - updates quantities/units,
    - records an expiry date.

    This is a WRITE operation (it modifies stored pantry state).

    Args:
      item: PantryItem containing:
        - name (required): ingredient name, e.g. "chickpeas"
        - qty (optional): numeric quantity, e.g. 2
        - unit (optional): e.g. "cans", "g", "ml"
        - expires (optional): ISO date string, e.g. "2026-02-28"

    Returns:
      "ok" if the item was saved successfully.

    Side effects:
      - Creates the item if it does not exist.
      - Overwrites the stored record for that item name if it already exists.

    Notes:
      - Prefer consistent naming (e.g., "bell pepper" vs "pepper") to reduce duplicates.
    """
    await store.upsert_pantry_item(item)
    return "ok"


@mcp.tool()
async def recipes_upsert(recipe: Recipe) -> str:
    """
    Insert a new recipe or update an existing recipe in the local recipe store (upsert).

    Use this tool to:
    - save recipes the user provides,
    - persist recipes extracted from the web (later),
    - update tags/ingredients/steps after edits.

    This is a WRITE operation (it modifies stored recipe state).

    Args:
      recipe: Recipe object (canonical format) containing:
        - title (required)
        - ingredients (optional list)
        - steps (optional list)
        - tags (optional list, e.g. ["vegetarian", "high-protein"])
        - servings (optional)
        - source_url/source_site/fetched_at (optional provenance fields)

    Returns:
      recipe_id (string) of the stored recipe.

    Side effects:
      - If recipe.id is provided, updates that recipe.
      - If recipe.id is not provided, the server may derive an id from the title.

    Notes:
      - Keep recipe steps concise and avoid copying large verbatim text from websites.
      - Always include source_url when the recipe originates from an external page.
    """
    return await store.upsert_recipe(recipe)


@mcp.tool()
async def recipes_get(recipe_id: str) -> Optional[Recipe]:
    """
    Fetch a single recipe by its recipe_id.

    Use this tool after recipes_search() returns candidate ids,
    or whenever you need the full details (ingredients/steps/tags) for a known id.

    This is a READ-ONLY operation (no state changes).

    Args:
      recipe_id: The recipe identifier returned by recipes_search() or recipes_upsert().

    Returns:
      - A Recipe object if found
      - null (None) if no recipe exists with that id

    Notes:
      - If you receive null, you should handle it gracefully:
        e.g., try a different id, broaden search, or ingest a new recipe.
    """
    return await store.get_recipe(recipe_id)


@mcp.tool()
async def recipes_search(query: str = "", tag: Optional[str] = None) -> List[str]:
    """
    Search the local recipe store and return matching recipe IDs.

    Use this tool as the FIRST step to find recipes before attempting any web search.
    Intended for quick discovery of existing, already-ingested recipes.

    This is a READ-ONLY operation (no state changes).

    Args:
      query: Free-text search term matched against recipe titles and ingredient names.
             Examples: "lentil", "pasta", "mozzarella", "chili".
             If empty, matches all recipes.
      tag: Optional tag filter. Only returns recipes that contain this tag exactly.
           Examples: "vegetarian", "high-protein", "quick", "gluten-free".

    Returns:
      A list of recipe_id strings (possibly empty).

    Notes:
      - Search matches if the query appears in the recipe title or in any ingredient name.
      - If results are empty, consider:
        - broadening the query,
        - removing the tag filter,
        - (later) using web acquisition tools to ingest more recipes.
    """
    return await store.search_recipes(query=query, tag=tag)


def main() -> None:
    # Ensure DB schema exists before serving
    import asyncio
    asyncio.run(store.init())
    mcp.run()  # stdio transport by default in FastMCP usage patterns


if __name__ == "__main__":
    main()
