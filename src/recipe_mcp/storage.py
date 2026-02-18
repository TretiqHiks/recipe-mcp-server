from __future__ import annotations
from typing import List, Optional
from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine, async_sessionmaker
from sqlalchemy import text
from .models import Recipe, PantryItem
import json


class SqliteStore:
    def __init__(self, db_url: str):
        self.engine: AsyncEngine = create_async_engine(db_url, future=True)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def init(self) -> None:
        async with self.engine.begin() as conn:
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS recipes (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    recipe_json TEXT NOT NULL
                )
            """))
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS pantry (
                    name TEXT PRIMARY KEY,
                    item_json TEXT NOT NULL
                )
            """))

    # --- recipes ---
    async def upsert_recipe(self, recipe: Recipe) -> str:
        rid = recipe.id or recipe.title.strip().lower().replace(" ", "-")
        payload = recipe.model_copy(update={"id": rid}).model_dump()
        async with self.session_factory() as s:
            await s.execute(
                text("INSERT OR REPLACE INTO recipes (id, title, recipe_json) VALUES (:id, :title, :json)"),
                {"id": rid, "title": payload["title"], "json": json.dumps(payload)},
            )
            await s.commit()
        return rid

    async def get_recipe(self, recipe_id: str) -> Optional[Recipe]:
        async with self.session_factory() as s:
            res = await s.execute(text("SELECT recipe_json FROM recipes WHERE id=:id"), {"id": recipe_id})
            row = res.first()
        if not row:
            return None
        return Recipe.model_validate_json(row[0])

    async def search_recipes(self, query: str = "", tag: Optional[str] = None) -> List[str]:
        # Search by title and ingredient name when query is non-empty; otherwise all recipes
        if query.strip():
            q = f"%{query.strip().lower()}%"
            sql = """
                SELECT id, recipe_json FROM recipes
                WHERE LOWER(title) LIKE :q
                   OR EXISTS (
                       SELECT 1 FROM json_each(recipe_json, '$.ingredients') AS ing
                       WHERE LOWER(json_extract(ing.value, '$.name')) LIKE :q
                   )
            """
            params: dict = {"q": q}
        else:
            sql = "SELECT id, recipe_json FROM recipes"
            params = {}
        async with self.session_factory() as s:
            res = await s.execute(text(sql), params)
            rows = res.all()

        ids: List[str] = []
        for rid, rjson in rows:
            if tag:
                r = Recipe.model_validate_json(rjson)
                if tag not in (r.tags or []):
                    continue
            ids.append(rid)
        return ids

    # --- pantry ---
    async def list_pantry(self) -> List[PantryItem]:
        async with self.session_factory() as s:
            res = await s.execute(text("SELECT item_json FROM pantry"))
            rows = res.all()
        return [PantryItem.model_validate_json(r[0]) for r in rows]

    async def upsert_pantry_item(self, item: PantryItem) -> None:
        async with self.session_factory() as s:
            await s.execute(
                text("INSERT OR REPLACE INTO pantry (name, item_json) VALUES (:name, :json)"),
                {"name": item.name.lower(), "json": item.model_dump_json()},
            )
            await s.commit()

    async def remove_pantry_item(self, item_name: str) -> bool:
        """Remove a pantry item by name. Returns True if deleted, False if not found."""
        async with self.session_factory() as s:
            res = await s.execute(
                text("DELETE FROM pantry WHERE name = :name"),
                {"name": item_name.lower()},
            )
            await s.commit()
            return res.rowcount > 0
