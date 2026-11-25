"""Offline tests for food search. They never call Open Food Facts."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.api.food_search as food_search


def names(query: str) -> list[str]:
    return [item["name"] for item in food_search.indian_food_results(query)]


def test_oats_is_found_in_local_catalogue():
    assert "Oats (rolled, dry)" in names("oats")


@pytest.mark.parametrize("query", ["oat", "OATS", "  oats  ", "Oats"])
def test_matching_ignores_case_spacing_and_plurals(query):
    assert "Oats (rolled, dry)" in names(query)


def test_branded_query_has_no_local_match():
    # "masala oats" is answered by the online database, not the local list.
    assert names("masala oats") == []


def test_exact_match_is_ranked_first():
    assert names("oats porridge")[0] == "Oats porridge (cooked with water)"


def test_off_product_without_calories_is_skipped():
    assert (
        food_search.normalize_off_product(
            {"product_name": "Mystery snack", "nutriments": {}}
        )
        is None
    )


def test_off_product_kilojoules_are_converted_to_kcal():
    product = food_search.normalize_off_product(
        {"product_name": "Test bar", "nutriments": {"energy_100g": 418.4}}
    )

    assert product is not None
    assert product["calories"] == 100.0


@pytest.fixture
def make_client(monkeypatch):
    def build(results=None, has_more=False, failed=False):
        async def fake_search(query, page, page_size):
            return (results or []), has_more, failed, failed

        monkeypatch.setattr(food_search, "search_open_food_facts", fake_search)
        food_search._cache.clear()

        api = FastAPI()
        api.include_router(food_search.router)
        return TestClient(api)

    return build


def test_search_returns_pagination_fields(make_client):
    client = make_client(
        results=[{"code": "1", "name": "Masala Oats", "calories": 380}],
        has_more=True,
    )

    body = client.get("/api/v1/foods/search?q=oats&page=1&page_size=10").json()

    assert body["page"] == 1
    assert body["page_size"] == 10
    assert body["has_more"] is True
    assert body["degraded"] is False
    # Local "oats" entries come first, then the packaged product.
    assert body["results"][-1]["name"] == "Masala Oats"


def test_local_foods_only_appear_on_the_first_page(make_client):
    client = make_client(results=[{"code": "2", "name": "Page two oats"}])

    body = client.get("/api/v1/foods/search?q=oats&page=2").json()

    assert [item["name"] for item in body["results"]] == ["Page two oats"]


def test_failed_online_search_is_reported_and_not_cached(make_client):
    client = make_client(results=[], failed=True)

    body = client.get("/api/v1/foods/search?q=masala%20oats").json()

    assert body["degraded"] is True
    assert body["results"] == []
    assert food_search._cache == {}


def test_query_must_have_two_characters(make_client):
    client = make_client()

    assert client.get("/api/v1/foods/search?q=a").status_code == 422
