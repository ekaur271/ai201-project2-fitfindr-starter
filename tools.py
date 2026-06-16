"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Complete and test each tool before moving to agent.py.

Tools:
    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)              → str
    create_fit_card(outfit, new_item)               → str
"""

import os
import re

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()

MODEL = "llama-3.3-70b-versatile"

# common filler words I don't want to count when scoring search relevance
STOPWORDS = {
    "a", "an", "and", "the", "for", "with", "in", "of", "to", "or", "i",
    "im", "looking", "want", "need", "some", "something", "that", "this",
    "under", "size", "please", "find", "me", "my",
}


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


def _tokenize(text):
    """Lowercase the text and return the set of useful words in it."""
    words = re.findall(r"[a-z0-9]+", text.lower())
    return {w for w in words if w not in STOPWORDS and len(w) > 1}


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    Args:
        description: Keywords describing what the user is looking for
                     (e.g., "vintage graphic tee").
        size:        Size string to filter by, or None to skip size filtering.
                     Matching is case-insensitive (e.g., "M" matches "S/M").
        max_price:   Maximum price (inclusive), or None to skip price filtering.

    Returns:
        A list of matching listing dicts, sorted by relevance (best match first).
        Returns an empty list if nothing matches — does NOT raise an exception.

    Each listing dict has the following fields:
        id, title, description, category, style_tags (list), size,
        condition, price (float), colors (list), brand, platform

    TODO:
        1. Load all listings with load_listings().
        2. Filter by max_price and size (if provided).
        3. Score each remaining listing by keyword overlap with `description`.
        4. Drop any listings with a score of 0 (no relevant matches).
        5. Sort by score, highest first, and return the listing dicts.

    Before writing code, fill in the Tool 1 section of planning.md.
    """
    listings = load_listings()
    query_tokens = _tokenize(description)
    size_filter = size.lower().strip() if size else None

    scored = []
    for listing in listings:
        # skip anything over budget or in the wrong size
        if max_price is not None and listing["price"] > max_price:
            continue
        if size_filter and size_filter not in str(listing["size"]).lower():
            continue

        # score by how many query words show up in the listing text
        text = " ".join([
            listing["title"],
            listing["description"],
            " ".join(listing["style_tags"]),
            listing["category"],
        ])
        score = len(query_tokens & _tokenize(text))

        # if they gave real keywords, drop the ones that don't match any
        if query_tokens and score == 0:
            continue
        scored.append((score, listing))

    # best matches first
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [listing for _, listing in scored]


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' key containing a list of
                  wardrobe item dicts. May be empty — handle this gracefully.

    Returns:
        A non-empty string with outfit suggestions.
        If the wardrobe is empty, offer general styling advice for the item
        rather than raising an exception or returning an empty string.

    TODO:
        1. Check whether wardrobe['items'] is empty.
        2. If empty: call the LLM with a prompt for general styling ideas
           (what kinds of items pair well, what vibe it suits, etc.).
        3. If not empty: format the wardrobe items into a prompt and ask
           the LLM to suggest specific outfit combinations using the new item
           and named pieces from the wardrobe.
        4. Return the LLM's response as a string.

    Before writing code, fill in the Tool 2 section of planning.md.
    """
    item_desc = (
        f"{new_item.get('title', 'an item')} "
        f"(category: {new_item.get('category', 'unknown')}, "
        f"colors: {', '.join(new_item.get('colors', [])) or 'n/a'}, "
        f"style: {', '.join(new_item.get('style_tags', [])) or 'n/a'})"
    )

    items = wardrobe.get("items", []) if wardrobe else []

    if not items:
        # no wardrobe yet, so just give general advice for the item
        prompt = (
            f"A shopper is considering this secondhand piece: {item_desc}.\n\n"
            "They have not entered any wardrobe items yet. Give friendly, general "
            "styling advice in 3-5 sentences: what kinds of pieces (categories, "
            "colors, footwear) pair well with it and what overall vibe it suits. "
            "Do not invent specific items they own. End by inviting them to add "
            "wardrobe items for personalized outfit combinations."
        )
    else:
        # build a readable list of their wardrobe so the model can name pieces
        wardrobe_lines = []
        for it in items:
            colors = ", ".join(it.get("colors", []))
            tags = ", ".join(it.get("style_tags", []))
            notes = it.get("notes", "")
            line = f"- {it.get('name', 'item')} [{it.get('category', '')}]"
            if colors:
                line += f", colors: {colors}"
            if tags:
                line += f", style: {tags}"
            if notes:
                line += f" ({notes})"
            wardrobe_lines.append(line)
        wardrobe_text = "\n".join(wardrobe_lines)

        prompt = (
            f"A shopper is considering this secondhand piece: {item_desc}.\n\n"
            f"Here is their existing wardrobe:\n{wardrobe_text}\n\n"
            "Suggest 1-2 complete, wearable outfits that pair the new piece with "
            "specific items from their wardrobe. Refer to the wardrobe pieces by "
            "their names. Keep it concise (a short paragraph or two) and practical."
        )

    client = _get_groq_client()
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are FitFindr, a warm, knowledgeable personal stylist who "
                    "helps people style secondhand and thrifted clothing."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.7,
    )
    return response.choices[0].message.content.strip()


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit:   The outfit suggestion string from suggest_outfit().
        new_item: The listing dict for the thrifted item.

    Returns:
        A 2–4 sentence string usable as an Instagram/TikTok caption.
        If outfit is empty or missing, return a descriptive error message
        string — do NOT raise an exception.

    The caption should:
    - Feel casual and authentic (like a real OOTD post, not a product description)
    - Mention the item name, price, and platform naturally (once each)
    - Capture the outfit vibe in specific terms
    - Sound different each time for different inputs (use higher LLM temperature)

    TODO:
        1. Guard against an empty or whitespace-only outfit string.
        2. Build a prompt that gives the LLM the item details and the outfit,
           and asks for a caption matching the style guidelines above.
        3. Call the LLM and return the response.

    Before writing code, fill in the Tool 3 section of planning.md.
    """
    # nothing to caption, so return a message instead of crashing
    if not outfit or not outfit.strip():
        return (
            "Couldn't generate a fit card: no outfit suggestion was available "
            "to caption."
        )

    title = new_item.get("title", "this thrifted find")
    price = new_item.get("price")
    price_text = f"${price:.0f}" if isinstance(price, (int, float)) else "a steal"
    platform = new_item.get("platform", "secondhand")

    prompt = (
        f"Write a short, shareable OOTD caption (2-4 sentences) for an Instagram "
        f"or TikTok post about a thrifted find.\n\n"
        f"Item: {title}\n"
        f"Price: {price_text}\n"
        f"Platform: {platform}\n"
        f"Outfit it's styled in: {outfit}\n\n"
        "Make it sound casual and authentic, like a real person posting their "
        "fit, not a product description. Mention the item name, price, and "
        "platform naturally, once each. Capture the specific vibe of the outfit. "
        "Return only the caption text."
    )

    client = _get_groq_client()
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a stylish Gen-Z thrift enthusiast writing punchy, "
                    "authentic social media captions for your secondhand finds."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        temperature=1.0,  # bump temp so the captions vary between runs
    )
    return response.choices[0].message.content.strip()
