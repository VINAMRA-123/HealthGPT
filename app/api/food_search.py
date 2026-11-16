
# import logging

# import httpx
# from fastapi import APIRouter, HTTPException, Query

# logger = logging.getLogger(__name__)

# router = APIRouter(
#     prefix="/api/v1/foods",
#     tags=["Food Search"],
# )

# OPEN_FOOD_FACTS_URL = "https://world.openfoodfacts.org/cgi/search.pl"


# @router.get("/search")
# async def search_foods(
#     q: str = Query(min_length=2, max_length=100),
# ):
#     params = {
#         "search_terms": q.strip(),
#         "search_simple": 1,
#         "action": "process",
#         "json": 1,
#         "page_size": 10,
#         "fields": "code,product_name,brands,quantity,nutriments",
#     }

#     try:
#         async with httpx.AsyncClient(
#             timeout=10.0,
#             headers={"User-Agent": "HealthGPT/0.1"},
#         ) as client:
#             response = await client.get(
#                 OPEN_FOOD_FACTS_URL,
#                 params=params,
#             )
#             response.raise_for_status()
#             data = response.json()

#     except httpx.HTTPStatusError as exc:
#         logger.exception(
#             "Open Food Facts returned HTTP %s",
#             exc.response.status_code,
#         )
#         raise HTTPException(
#             status_code=502,
#             detail=f"Food database returned HTTP {exc.response.status_code}.",
#         ) from exc

#     except httpx.RequestError as exc:
#         logger.exception("Could not connect to Open Food Facts")
#         raise HTTPException(
#             status_code=502,
#             detail=f"Could not connect to food database: {type(exc).__name__}.",
#         ) from exc

#     except ValueError as exc:
#         logger.exception("Invalid response from Open Food Facts")
#         raise HTTPException(
#             status_code=502,
#             detail="Food database returned an invalid response.",
#         ) from exc

#     results = []

#     for product in data.get("products", []):
#         name = product.get("product_name")
#         if not name:
#             continue

#         nutrients = product.get("nutriments") or {}

#         results.append({
#             "code": product.get("code"),
#             "name": name,
#             "brands": product.get("brands"),
#             "quantity": product.get("quantity"),
#             "basis": "per 100 g",
#             "calories": nutrients.get("energy-kcal_100g"),
#             "protein_g": nutrients.get("proteins_100g"),
#             "carbs_g": nutrients.get("carbohydrates_100g"),
#             "fat_g": nutrients.get("fat_100g"),
#         })

#     return {
#         "query": q.strip(),
#         "count": len(results),
#         "results": results,
#     }

from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/api/v1/foods", tags=["foods"])

OPEN_FOOD_FACTS_URL = (
    "https://world.openfoodfacts.org/cgi/search.pl"
)

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
]


def indian_food_results(query: str) -> list[dict[str, Any]]:
    """Find matching prototype Indian-food estimates."""
    normalized_query = query.casefold().strip()
    results = []

    for food in INDIAN_FOODS:
        searchable = [food["name"], *food["aliases"]]

        if any(
            normalized_query in term.casefold()
            or term.casefold() in normalized_query
            for term in searchable
        ):
            results.append(
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
                }
            )

    return results


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

    return {
        "code": product.get("code"),
        "name": name,
        "brands": product.get("brands") or None,
        "quantity": product.get("quantity") or None,
        "basis": "per 100 g",
        "calories": nutrients.get("energy-kcal_100g"),
        "protein_g": nutrients.get("proteins_100g"),
        "carbs_g": nutrients.get("carbohydrates_100g"),
        "fat_g": nutrients.get("fat_100g"),
        "source": "Open Food Facts",
        "is_estimate": False,
    }


async def search_open_food_facts(query: str) -> list[dict[str, Any]]:
    """Search packaged foods, prioritizing products sold in India."""
    headers = {
        "User-Agent": "HealthGPT/0.1 (food nutrition search)"
    }

    base_params = {
        "search_terms": query,
        "search_simple": 1,
        "action": "process",
        "json": 1,
        "page_size": 20,
        "fields": (
            "code,product_name,product_name_en,brands,quantity,"
            "countries,countries_tags,nutriments"
        ),
    }

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(8.0),
        follow_redirects=True,
        headers=headers,
    ) as client:
        try:
            # First try to find products tagged for India.
            response = await client.get(
                OPEN_FOOD_FACTS_URL,
                params={
                    **base_params,
                    "tagtype_0": "countries",
                    "tag_contains_0": "contains",
                    "tag_0": "india",
                },
            )
            response.raise_for_status()
            data = response.json()
            products = data.get("products", [])

            # If the country filter returns nothing, try the general index.
            # This is a fallback, not an extra request on every search.
            if not products:
                response = await client.get(
                    OPEN_FOOD_FACTS_URL,
                    params=base_params,
                )
                response.raise_for_status()
                data = response.json()
                products = data.get("products", [])

            results = []

            for product in products:
                normalized = normalize_off_product(product)

                if normalized:
                    countries = (
                        product.get("countries_tags") or []
                    )
                    countries_text = (
                        product.get("countries") or ""
                    ).casefold()

                    is_indian = (
                        "en:india" in countries
                        or "india" in countries_text
                    )

                    normalized["_india_rank"] = (
                        0 if is_indian else 1
                    )
                    results.append(normalized)

            results.sort(key=lambda item: item["_india_rank"])

            for item in results:
                item.pop("_india_rank", None)

            return results

        except (httpx.HTTPError, ValueError):
            # Let the local Indian-food catalogue remain usable
            # when the external provider is temporarily unavailable.
            return []


@router.get("/search")
async def search_foods(
    q: str = Query(..., min_length=2, max_length=100),
):
    query = q.strip()

    if len(query) < 2:
        raise HTTPException(
            status_code=422,
            detail="Enter at least 2 characters to search.",
        )

    local_results = indian_food_results(query)
    packaged_results = await search_open_food_facts(query)

    # For branded queries such as "Maggi", prioritize packaged products.
    # For common Indian dishes, show the matching local entries first.
    indian_dish_query = any(
        query.casefold() in term.casefold()
        or term.casefold() in query.casefold()
        for food in INDIAN_FOODS
        for term in [food["name"], *food["aliases"]]
    )

    if indian_dish_query:
        results = local_results + packaged_results
    else:
        results = packaged_results + local_results

    # Deduplicate packaged products by barcode and local dishes by name.
    unique_results = []
    seen = set()

    for item in results:
        identity = (
            f"barcode:{item['code']}"
            if item.get("code")
            else f"name:{item['name'].casefold()}"
        )

        if identity not in seen:
            seen.add(identity)
            unique_results.append(item)

    return {
        "query": query,
        "count": len(unique_results),
        "results": unique_results[:20],
    }
