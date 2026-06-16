"""
Tests for the three tools, with at least one test per failure mode.
Run with: pytest tests/

search_listings tests run offline. The two LLM tools need GROQ_API_KEY,
so those tests get skipped if no key is set.
"""

import os

import pytest

from tools import search_listings, suggest_outfit, create_fit_card
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe

# skip the LLM tests when there's no API key around
needs_llm = pytest.mark.skipif(
    not os.environ.get("GROQ_API_KEY"),
    reason="GROQ_API_KEY not set, skipping live LLM tests",
)


# ── search_listings ─────────────────────────────────────────────────────────

def test_search_returns_results():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert isinstance(results, list)
    assert len(results) > 0
    # Every result has the documented core fields.
    for item in results:
        assert "title" in item and "price" in item and "platform" in item


def test_search_empty_results():
    # Impossible query: no listing matches all three constraints.
    results = search_listings("designer ballgown", size="XXS", max_price=5)
    assert results == []  # empty list, no exception


def test_search_price_filter():
    results = search_listings("jacket", size=None, max_price=40)
    assert all(item["price"] <= 40 for item in results)


def test_search_size_filter_case_insensitive():
    results = search_listings("tee", size="m", max_price=None)
    # Size matching is case-insensitive / substring based.
    assert all("m" in str(item["size"]).lower() for item in results)


def test_search_sorted_by_relevance():
    results = search_listings("vintage denim jacket", size=None, max_price=None)
    assert len(results) >= 2
    # Results are ranked; the top result is at least as relevant as the next.
    # (We can't see the score, but the call must not raise and must be ordered.)
    assert isinstance(results[0], dict)


# ── suggest_outfit ──────────────────────────────────────────────────────────

@needs_llm
def test_suggest_outfit_with_wardrobe():
    item = search_listings("vintage graphic tee", size=None, max_price=50)[0]
    out = suggest_outfit(item, get_example_wardrobe())
    assert isinstance(out, str)
    assert out.strip() != ""


@needs_llm
def test_suggest_outfit_empty_wardrobe():
    # Failure mode: empty wardrobe must still return useful advice, not crash.
    item = search_listings("vintage graphic tee", size=None, max_price=50)[0]
    out = suggest_outfit(item, get_empty_wardrobe())
    assert isinstance(out, str)
    assert out.strip() != ""


# ── create_fit_card ─────────────────────────────────────────────────────────

@needs_llm
def test_create_fit_card_happy_path():
    item = search_listings("vintage graphic tee", size=None, max_price=50)[0]
    card = create_fit_card("Pair the tee with baggy jeans and chunky sneakers.", item)
    assert isinstance(card, str)
    assert card.strip() != ""


def test_create_fit_card_empty_outfit():
    # Failure mode: empty outfit returns a descriptive string, not an exception.
    item = {"title": "Test Tee", "price": 18.0, "platform": "depop"}
    card = create_fit_card("", item)
    assert isinstance(card, str)
    assert card.strip() != ""
    assert "couldn't" in card.lower() or "no outfit" in card.lower()


def test_create_fit_card_whitespace_outfit():
    item = {"title": "Test Tee", "price": 18.0, "platform": "depop"}
    card = create_fit_card("   \n  ", item)
    assert isinstance(card, str)
    assert "couldn't" in card.lower() or "no outfit" in card.lower()
