import asyncio
import logging
import re
import time
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Query

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/foods", tags=["foods"])

OPEN_FOOD_FACTS_URL = "https://world.openfoodfacts.org/cgi/search.pl"

# Fail fast: a slow external database should never freeze the UI for 16 s.
OFF_TIMEOUT = httpx.Timeout(7.0, connect=3.0)

# Identical searches (same text + page) are served from memory.
CACHE_TTL_SECONDS = 600
CACHE_MAX_ENTRIES = 300

_cache: dict[tuple[str, int, int], tuple[float, dict[str, Any]]] = {}
_client: httpx.AsyncClient | None = None


# Prototype estimates per 100 g, not laboratory measurements.
# Replace or validate these values against a licensed Indian nutrition dataset
# before presenting them as authoritative nutrition facts.
INDIAN_FOODS = [
    {
        "name": "Roti (plain, whole wheat)",
        "aliases": ["roti", "chapati", "chapathi", "phulka"],
        "calories": 297,
        "protein_g": 10.0,
        "carbs_g": 55.0,
        "fat_g": 3.7,
    },
    {
        "name": "Poha",
        "aliases": ["poha", "pohe", "flattened rice"],
        "calories": 180,
        "protein_g": 3.5,
        "carbs_g": 30.0,
        "fat_g": 5.0,
    },
    {
        "name": "Dal (cooked, plain)",
        "aliases": ["dal", "daal", "lentil curry", "cooked lentils"],
        "calories": 115,
        "protein_g": 7.5,
        "carbs_g": 18.0,
        "fat_g": 1.5,
    },
    {
        "name": "Thepla",
        "aliases": ["thepla", "methi thepla"],
        "calories": 270,
        "protein_g": 7.0,
        "carbs_g": 42.0,
        "fat_g": 8.0,
    },
    {
        "name": "Khichdi",
        "aliases": ["khichdi", "khichri"],
        "calories": 120,
        "protein_g": 4.0,
        "carbs_g": 21.0,
        "fat_g": 2.0,
    },
    {
        "name": "Idli",
        "aliases": ["idli", "idly"],
        "calories": 145,
        "protein_g": 4.5,
        "carbs_g": 29.0,
        "fat_g": 0.7,
    },
    {
        "name": "Cooked white rice",
        "aliases": ["rice", "cooked rice", "white rice"],
        "calories": 130,
        "protein_g": 2.7,
        "carbs_g": 28.2,
        "fat_g": 0.3,
    },
    {
        "name": "Oats (rolled, dry)",
        "aliases": ["oats", "oat", "rolled oats", "plain oats", "oatmeal"],
        "calories": 389,
        "protein_g": 16.9,
        "carbs_g": 66.3,
        "fat_g": 6.9,
    },
    {
        "name": "Oats porridge (cooked with water)",
        "aliases": ["oats porridge", "oatmeal porridge", "cooked oats", "porridge"],
        "calories": 71,
        "protein_g": 2.5,
        "carbs_g": 12.0,
        "fat_g": 1.5,
    },
    {
        "name": "Dosa (plain)",
        "aliases": ["dosa", "dosai", "plain dosa"],
        "calories": 168,
        "protein_g": 3.9,
        "carbs_g": 29.0,
        "fat_g": 3.7,
    },
    {
        "name": "Upma",
        "aliases": ["upma", "rava upma", "suji upma"],
        "calories": 130,
        "protein_g": 3.0,
        "carbs_g": 20.0,
        "fat_g": 4.5,
    },
    {
        "name": "Paratha (plain)",
        "aliases": ["paratha", "parantha", "plain paratha"],
        "calories": 290,
        "protein_g": 7.0,
        "carbs_g": 44.0,
        "fat_g": 9.0,
    },
    {
        "name": "Paneer",
        "aliases": ["paneer", "cottage cheese"],
        "calories": 265,
        "protein_g": 18.3,
        "carbs_g": 1.2,
        "fat_g": 20.8,
    },
    {
        "name": "Curd / Dahi (whole milk)",
        "aliases": ["curd", "dahi", "yogurt", "yoghurt"],
        "calories": 61,
        "protein_g": 3.5,
        "carbs_g": 4.7,
        "fat_g": 3.3,
    },
    {
        "name": "Rajma (cooked)",
        "aliases": ["rajma", "kidney beans"],
        "calories": 127,
        "protein_g": 8.7,
        "carbs_g": 22.8,
        "fat_g": 0.5,
    },
    {
        "name": "Chole (cooked chickpeas)",
        "aliases": ["chole", "chana", "chickpeas", "chana masala"],
        "calories": 150,
        "protein_g": 6.5,
        "carbs_g": 20.0,
        "fat_g": 4.5,
    },
    {
        "name": "Sambar",
        "aliases": ["sambar", "sambhar"],
        "calories": 65,
        "protein_g": 3.0,
        "carbs_g": 9.0,
        "fat_g": 1.8,
    },
    {
        "name": "Boiled egg",
        "aliases": ["egg", "eggs", "boiled egg", "anda"],
        "calories": 155,
        "protein_g": 12.6,
        "carbs_g": 1.1,
        "fat_g": 10.6,
    },
    {
        "name": "Banana",
        "aliases": ["banana", "kela"],
        "calories": 89,
        "protein_g": 1.1,
        "carbs_g": 22.8,
        "fat_g": 0.3,
    },
    {
        "name": "Milk (whole)",
        "aliases": ["milk", "doodh", "whole milk"],
        "calories": 61,
        "protein_g": 3.2,
        "carbs_g": 4.8,
        "fat_g": 3.3,
    },
]


# ---------------------------------------------------------------------------
# Text matching helpers
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.casefold())


def _stem(token: str) -> str:
    """Very small plural-stripper so 'oat' and 'oats' match each other."""
    if len(token) > 3 and token.endswith("s"):
        return token[:-1]
    return token


def _stems(text: str) -> list[str]:
    return [_stem(token) for token in _tokenize(text)]


def _tokens_match(query_stems: list[str], text: str) -> bool:
    """True when every query word is a prefix of (or equal to) a word in text."""
    if not query_stems:
        return False

    text_stems = _stems(text)

    return all(
        any(ts.startswith(qs) or qs.startswith(ts) for ts in text_stems)
        for qs in query_stems
    )


def indian_food_results(query: str) -> list[dict[str, Any]]:
    """Find matching prototype Indian-food estimates (typo-tolerant on plurals)."""
    query_stems = _stems(query)
    normalized_query = " ".join(_tokenize(query))
    scored: list[tuple[int, dict[str, Any]]] = []

    for food in INDIAN_FOODS:
        terms = [food["name"], *food["aliases"]]

        if not any(_tokens_match(query_stems, term) for term in terms):
            continue

        exact = any(
            " ".join(_tokenize(term)) == normalized_query for term in terms
        )

        scored.append(
            (
                0 if exact else 1,
                {
                    "code": None,
                    "name": food["name"],
                    "brands": None,
                    "quantity": None,
                    "basis": "per 100 g",
                    "calories": food["calories"],
                    "protein_g": food["protein_g"],
                    "carbs_g": food["carbs_g"],
                    "fat_g": food["fat_g"],
                    "source": "HealthGPT prototype estimate",
                    "is_estimate": True,
                },
            )
        )

    scored.sort(key=lambda pair: pair[0])
    return [item for _, item in scored]


# ---------------------------------------------------------------------------
# Open Food Facts
# ---------------------------------------------------------------------------

def _get_client() -> httpx.AsyncClient:
    """One shared client keeps the TLS connection alive between searches."""
    global _client

    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=OFF_TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": "HealthGPT/0.1 (food nutrition search)"},
            limits=httpx.Limits(
                max_connections=10,
                max_keepalive_connections=5,
            ),
        )

    return _client


def _round(value: Any) -> float | None:
    if value is None:
        return None

    try:
        return round(float(value), 1)
    except (TypeError, ValueError):
        return None


def normalize_off_product(product: dict[str, Any]) -> dict[str, Any] | None:
    """Convert an Open Food Facts product into HealthGPT's response format."""
    name = (
        product.get("product_name")
        or product.get("product_name_en")
        or ""
    ).strip()

    if not name:
        return None

    nutrients = product.get("nutriments") or {}

    calories = _round(nutrients.get("energy-kcal_100g"))

    if calories is None:
        # Fall back to kilojoules when kcal is not provided.
        kilojoules = _round(nutrients.get("energy_100g"))
        calories = round(kilojoules / 4.184, 1) if kilojoules else None

    # A product with no calorie data is useless for meal logging.
    if calories is None:
        return None

    return {
        "code": product.get("code"),
        "name": name,
        "brands": product.get("brands") or None,
        "quantity": product.get("quantity") or None,
        "basis": "per 100 g",
        "calories": calories,
        "protein_g": _round(nutrients.get("proteins_100g")),
        "carbs_g": _round(nutrients.get("carbohydrates_100g")),
        "fat_g": _round(nutrients.get("fat_100g")),
        "source": "Open Food Facts",
        "is_estimate": False,
    }


async def _fetch_off_page(
    query: str,
    page: int,
    page_size: int,
    india_only: bool,
) -> tuple[list[dict[str, Any]], int]:
    params: dict[str, Any] = {
        "search_terms": query,
        "search_simple": 1,
        "action": "process",
        "json": 1,
        "page": page,
        "page_size": page_size,
        "fields": (
            "code,product_name,product_name_en,brands,quantity,"
            "countries_tags,nutriments"
        ),
    }

    if india_only:
        params.update(
            {
                "tagtype_0": "countries",
                "tag_contains_0": "contains",
                "tag_0": "india",
            }
        )

    response = await _get_client().get(OPEN_FOOD_FACTS_URL, params=params)
    response.raise_for_status()
    data = response.json()

    try:
        total = int(data.get("count") or 0)
    except (TypeError, ValueError):
        total = 0

    return data.get("products") or [], total


async def search_open_food_facts(
    query: str,
    page: int,
    page_size: int,
) -> tuple[list[dict[str, Any]], bool, bool, bool]:
    """
    Search packaged foods, prioritising products sold in India.

    Both searches (India-tagged and worldwide) run at the same time, so the
    total wait is the slowest single request instead of the sum of both.

    Returns (results, has_more, any_failed, all_failed).
    """
    outcomes = await asyncio.gather(
        _fetch_off_page(query, page, page_size, india_only=True),
        _fetch_off_page(query, page, page_size, india_only=False),
        return_exceptions=True,
    )

    failures = 0
    totals: list[int] = []
    merged: dict[str, dict[str, Any]] = {}
    query_stems = _stems(query)

    for label, outcome in zip(("India", "worldwide"), outcomes):
        if isinstance(outcome, BaseException):
            failures += 1
            logger.warning(
                "Open Food Facts %s search failed: %s: %s",
                label,
                type(outcome).__name__,
                outcome,
            )
            continue

        products, total = outcome
        totals.append(total)

        for product in products:
            normalized = normalize_off_product(product)

            if not normalized:
                continue

            tags = product.get("countries_tags") or []
            is_indian = "en:india" in tags or label == "India"

            identity = (
                f"barcode:{normalized['code']}"
                if normalized.get("code")
                else f"name:{normalized['name'].casefold()}"
            )

            existing = merged.get(identity)

            if existing is None:
                normalized["_india"] = 0 if is_indian else 1
                merged[identity] = normalized
            elif is_indian:
                existing["_india"] = 0

    def sort_key(item: dict[str, Any]) -> tuple[int, int]:
        searchable = f"{item['name']} {item.get('brands') or ''}"
        relevance = 0 if _tokens_match(query_stems, searchable) else 1
        return (relevance, item["_india"])

    results = sorted(merged.values(), key=sort_key)

    for item in results:
        item.pop("_india", None)

    has_more = bool(totals) and page * page_size < max(totals)

    return results, has_more, failures > 0, failures == len(outcomes)


# ---------------------------------------------------------------------------
# Tiny in-memory cache
# ---------------------------------------------------------------------------

def _cache_get(key: tuple[str, int, int]) -> dict[str, Any] | None:
    entry = _cache.get(key)

    if entry is None:
        return None

    expires_at, payload = entry

    if expires_at < time.monotonic():
        _cache.pop(key, None)
        return None

    return payload


def _cache_set(key: tuple[str, int, int], payload: dict[str, Any]) -> None:
    if len(_cache) >= CACHE_MAX_ENTRIES:
        oldest = min(_cache, key=lambda k: _cache[k][0])
        _cache.pop(oldest, None)

    _cache[key] = (time.monotonic() + CACHE_TTL_SECONDS, payload)


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------

@router.get("/search")
async def search_foods(
    q: str = Query(..., min_length=2, max_length=100),
    page: int = Query(1, ge=1, le=50),
    page_size: int = Query(10, ge=1, le=30),
):
    query = " ".join(q.split())

    if len(query) < 2:
        raise HTTPException(
            status_code=422,
            detail="Enter at least 2 characters to search.",
        )

    cache_key = (query.casefold(), page, page_size)
    cached = _cache_get(cache_key)

    if cached is not None:
        return cached

    # Local dishes are small and instant; they only appear on page 1.
    local_results = indian_food_results(query) if page == 1 else []

    packaged_results, has_more, any_failed, all_failed = (
        await search_open_food_facts(query, page, page_size)
    )

    # Local matches only exist for common dishes ("oats", "poha"), so they
    # lead the list. Brand-style queries ("maggi", "masala oats") have no
    # local match and are answered by the packaged-food results alone.
    results = local_results + packaged_results

    payload = {
        "query": query,
        "page": page,
        "page_size": page_size,
        "count": len(results),
        "has_more": has_more,
        # True when the online food database could not be reached, so the
        # UI can explain why the list is short instead of showing nothing.
        "degraded": all_failed,
        "results": results,
    }

    # Never cache a response built from a failed external call.
    if not any_failed:
        _cache_set(cache_key, payload)

    return payload
