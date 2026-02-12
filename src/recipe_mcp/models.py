from __future__ import annotations
from typing import List, Optional
from pydantic import BaseModel, Field, HttpUrl


class Ingredient(BaseModel):
    name: str = Field(..., min_length=1)
    qty: Optional[float] = None
    unit: Optional[str] = None
    note: Optional[str] = None


class Recipe(BaseModel):
    id: Optional[str] = None
    title: str
    servings: Optional[int] = None
    ingredients: List[Ingredient] = []
    steps: List[str] = []
    tags: List[str] = []
    source_url: Optional[HttpUrl] = None
    source_site: Optional[str] = None
    fetched_at: Optional[str] = None 


class PantryItem(BaseModel):
    name: str
    qty: Optional[float] = None
    unit: Optional[str] = None
    expires: Optional[str] = None 
