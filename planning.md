# FitFindr - planning.md

> Complete this document before writing any implementation code.
> Your spec and agent diagram are what you'll use to direct AI tools (Claude, Copilot, etc.) to generate your implementation - the more specific they are, the more useful the generated code will be.
> Your planning.md will be reviewed as part of your submission.
> Update it before starting any stretch features.

---

## Tools

List every tool your agent will use. For each tool, fill in all four fields.
You must have at least 3 tools. The three required tools are listed - add any additional tools below them.

### Tool 1: search_listings

**What it does:**
Searches the local mock marketplace (40 secondhand listings loaded via `load_listings()`) for items that match the user's keywords, filtered by an optional size and an optional price ceiling, and returns them ranked by how well they match. This is pure local filtering and scoring - it does **not** call the LLM.

**Input parameters:**
- `description` (str): free-text keywords describing the wanted item, e.g. `"vintage graphic tee"`. Used for keyword-overlap scoring against each listing's `title`, `description`, and `style_tags`.
- `size` (str | None): size string to filter by, e.g. `"M"`. Matching is case-insensitive and substring-based so `"M"` matches `"S/M"`. `None` skips size filtering.
- `max_price` (float | None): inclusive maximum price. A listing is kept only if `price <= max_price`. `None` skips price filtering.

**What it returns:**
A `list[dict]` of matching listings sorted by relevance score, highest first. Each dict has the fields: `id` (str), `title` (str), `description` (str), `category` (str: tops/bottoms/outerwear/shoes/accessories), `style_tags` (list[str]), `size` (str), `condition` (str: excellent/good/fair), `price` (float), `colors` (list[str]), `brand` (str | None), `platform` (str: depop/thredUp/poshmark). Listings whose keyword-overlap score is 0 are dropped. Returns `[]` when nothing matches - it never raises.

**What happens if it fails or returns nothing:**
Returns an empty list. The planning loop treats `[]` as the no-results branch: it sets `session["error"]` to a specific message naming the query and suggesting the user loosen filters (raise `max_price`, drop the size, or use broader keywords), then returns the session early **without** calling `suggest_outfit` or `create_fit_card`.

---

### Tool 2: suggest_outfit

**What it does:**
Given the chosen listing and the user's wardrobe, asks the LLM (Groq `llama-3.3-70b-versatile`) to propose 1-2 complete, wearable outfits that pair the new item with specific pieces the user already owns.

**Input parameters:**
- `new_item` (dict): a single listing dict (the top search result the user is considering buying), with the fields described in Tool 1.
- `wardrobe` (dict): a wardrobe dict with an `"items"` key holding a list of wardrobe-item dicts. Each wardrobe item has `id`, `name`, `category`, `colors` (list), `style_tags` (list), and optional `notes`. The list may be empty.

**What it returns:**
A non-empty `str` containing 1-2 outfit suggestions in plain prose. When the wardrobe has items, the text names specific owned pieces (by their `name`) alongside the new item. When the wardrobe is empty, it returns general styling advice (what categories/colors/vibes pair well with the item) instead.

**What happens if it fails or returns nothing:**
If `wardrobe["items"]` is empty, the tool does not crash - it switches to a "general styling advice" prompt and still returns a useful string. The agent stores whatever string comes back in `session["outfit_suggestion"]` and proceeds; styling never blocks the run.

---

### Tool 3: create_fit_card

**What it does:**
Turns the outfit suggestion into a short, shareable social-media caption (an OOTD-style "fit card") for the thrifted find, using the LLM at a higher temperature so repeated calls vary.

**Input parameters:**
- `outfit` (str): the outfit suggestion string returned by `suggest_outfit()`.
- `new_item` (dict): the chosen listing dict, used so the caption can mention the item's `title`, `price`, and `platform` naturally (once each).

**What it returns:**
A 2-4 sentence `str` usable as an Instagram/TikTok caption - casual and authentic, capturing the outfit vibe and mentioning the item name, price, and platform once each. Higher LLM temperature makes the output differ across identical inputs.

**What happens if it fails or returns nothing:**
If `outfit` is empty or whitespace-only, the tool short-circuits and returns a descriptive error-message string (e.g. "Can't write a fit card - no outfit was provided.") rather than calling the LLM or raising. The agent stores that string in `session["fit_card"]` so the UI still has something to show.

---

### Additional Tools (if any)

None - FitFindr uses exactly the three required tools.

---

## Planning Loop

**How does your agent decide which tool to call next?**

The loop is a fixed, conditional pipeline driven by the `session` dict - each step reads the previous step's output from the session and branches on it. It is **not** an open-ended "pick a tool" loop; the tool order is fixed, but whether later tools run depends on earlier results.

1. **Initialize.** `session = _new_session(query, wardrobe)`.
2. **Parse the query.** Extract `description`, `size`, and `max_price` from the natural-language `query` using regex/string parsing (e.g. `"under $30"` -> `max_price=30.0`, `"size M"` -> `size="M"`, remaining words -> `description`). Store the three values in `session["parsed"]`.
3. **Search.** Call `search_listings(description, size, max_price)`; store the list in `session["search_results"]`.
   - **Branch - empty:** if `search_results == []`, set `session["error"]` to a helpful message that names the query and suggests loosening filters, then `return session` immediately. `selected_item`, `outfit_suggestion`, and `fit_card` stay `None`. **Do not call the remaining tools.**
   - **Branch - non-empty:** continue.
4. **Select.** Set `session["selected_item"] = search_results[0]` (top-ranked match).
5. **Style.** Call `suggest_outfit(selected_item, wardrobe)`; store the string in `session["outfit_suggestion"]`. This always returns a usable string (general advice if the wardrobe is empty), so there is no early-return branch here.
6. **Caption.** Call `create_fit_card(outfit_suggestion, selected_item)`; store the string in `session["fit_card"]`. If the outfit string was empty, this returns an error-message string rather than crashing.
7. **Done.** `return session`. The loop knows it is finished once `fit_card` is set (or once it returned early on the empty-search branch).

---

## State Management

**How does information from one tool get passed to the next?**

A single `session` dict (created by `_new_session()`) is the one source of truth for an interaction. Tools are pure functions - they take explicit arguments and return values; the planning loop is the only thing that reads from and writes to the session, so data flow is explicit and inspectable.

Tracked fields:
- `query` (str) - the original user input.
- `parsed` (dict) - `{description, size, max_price}` extracted in step 2.
- `search_results` (list[dict]) - output of `search_listings`.
- `selected_item` (dict | None) - `search_results[0]`, the input to both `suggest_outfit` and `create_fit_card`.
- `wardrobe` (dict) - the wardrobe passed in at the start, fed to `suggest_outfit`.
- `outfit_suggestion` (str | None) - output of `suggest_outfit`, the input to `create_fit_card`.
- `fit_card` (str | None) - output of `create_fit_card`.
- `error` (str | None) - set only on the early-return path; `None` means the run completed.

Passing between tools: `parsed` -> args to `search_listings` -> `search_results` -> `selected_item` -> args to `suggest_outfit` -> `outfit_suggestion` -> args to `create_fit_card` -> `fit_card`. Nothing is re-derived or re-prompted; each tool gets exactly the object the previous step stored.

---

## Error Handling

For each tool, describe the specific failure mode you're handling and what the agent does in response.

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| search_listings | No results match the query | Tool returns `[]`. Agent sets `session["error"]` to a specific message - e.g. *"No listings matched 'designer ballgown' under $5 in size XXS. Try raising your price limit, dropping the size filter, or using broader keywords."* - and returns early. `fit_card` stays `None`; `suggest_outfit`/`create_fit_card` are never called. |
| suggest_outfit | Wardrobe is empty | Tool detects `wardrobe["items"] == []` and calls the LLM with a general-advice prompt instead of crashing. Agent shows styling ideas for the item ("pairs well with relaxed denim and chunky sneakers; leans streetwear/casual") and notes the user can add wardrobe items for personalized combos. The run still proceeds to `create_fit_card`. |
| create_fit_card | Outfit input is missing or incomplete | Tool guards against an empty/whitespace `outfit` and returns a descriptive string - e.g. *"Couldn't generate a fit card: no outfit suggestion was available to caption."* - instead of raising. Agent stores it in `session["fit_card"]` so the UI panel still displays a clear, non-crashing message. |

---

## Architecture

```
                                User query  +  wardrobe choice
                                        │
                                        ▼
      ┌──────────────────────────  Planning Loop (run_agent)  ──────────────────────────┐
      │                                                                                  │
      │  Step 2: parse query  ──>  Session.parsed = {description, size, max_price}        │
      │                                        │                                         │
      │                                        ▼                                         │
      │  Step 3: search_listings(description, size, max_price)                           │
      │                                        │                                         │
      │                  ┌─────────────────────┴─────────────────────┐                   │
      │       results == []                                  results == [item, ...]       │
      │            │                                                  │                   │
      │            ▼                                                  ▼                   │
      │   Session.error =                                  Session.search_results = [...] │
      │   "No listings matched ...                         Session.selected_item = [0] ───┤
      │    try loosening filters"                                     │                   │
      │            │                                                  ▼                   │
      │   [ERROR PATH] return session ◄──────────┐        Step 5: suggest_outfit(         │
      │   (outfit & fit_card stay None)          │            selected_item, wardrobe)    │
      │                                          │                    │                   │
      │                                          │     ┌──────────────┴──────────────┐    │
      │                                          │  wardrobe empty           wardrobe has  │
      │                                          │  -> general advice         items -> combos│
      │                                          │     └──────────────┬──────────────┘    │
      │                                          │                    ▼                   │
      │                                          │   Session.outfit_suggestion = "..."    │
      │                                          │                    │                   │
      │                                          │                    ▼                   │
      │                                          │   Step 6: create_fit_card(             │
      │                                          │       outfit_suggestion, selected_item)│
      │                                          │                    │                   │
      │                              outfit empty │     ┌─────────────┴────────┐          │
      │                              -> error str ─┘  outfit ok -> caption        │          │
      │                                                          └──────┬───────┘          │
      │                                                                 ▼                  │
      │                                              Session.fit_card = "..."              │
      │                                                                 │                  │
      └─────────────────────────────────────────────────────────────── │ ─────────────────┘
                                                                        ▼
                                                              Return session  ──>  UI panels
                                                              (listing | outfit | fit card)

   Session state (single source of truth, read/written only by the planning loop):
   { query, parsed, search_results, selected_item, wardrobe, outfit_suggestion, fit_card, error }
```

---

## AI Tool Plan

**Milestone 3 - Individual tool implementations:**

- **search_listings:** I'll give Claude the Tool 1 block above (inputs, return fields, the empty-list failure mode) plus the `load_listings()` docstring, and ask it to implement the function in `tools.py` using `load_listings()` - no re-reading files. Before running, I'll verify the generated code (a) filters by `max_price` and `size` only when they're non-`None`, (b) scores by keyword overlap across `title`/`description`/`style_tags`, (c) drops score-0 listings and sorts descending, and (d) returns `[]` rather than raising on no match. Then I'll run the three pytest cases (results, empty, price filter).
- **suggest_outfit:** I'll give Claude the Tool 2 block plus a sample `new_item` and the example/empty wardrobe shapes, and ask it to call Groq `llama-3.3-70b-versatile`. I'll check it branches on `wardrobe["items"]` being empty and returns a non-empty string in both cases. I'll verify by calling it once with the example wardrobe (should name owned pieces) and once with the empty wardrobe (should give general advice).
- **create_fit_card:** I'll give Claude the Tool 3 block and ask for the empty-`outfit` guard plus a higher LLM temperature. I'll verify by calling it 3× on the same input and confirming the captions differ, and once with `outfit=""` to confirm it returns an error string, not an exception.

**Milestone 4 - Planning loop and state management:**

- I'll give Claude the **Architecture** diagram plus the **Planning Loop** and **State Management** sections above, along with the `run_agent()` stub and `_new_session()`. I'll ask it to implement `run_agent()` following the seven steps. Before running, I'll confirm the code (a) branches on `search_listings` returning `[]` and returns early with `session["error"]` set, (b) only calls `suggest_outfit`/`create_fit_card` on the non-empty branch, (c) writes each result into the documented session field and re-uses it as the next tool's input (no re-prompting / hardcoding). I'll verify with the happy-path query and the no-results query already in `agent.py`'s `__main__`, asserting `session["fit_card"] is None` on the no-results path.

---

## A Complete Interaction (Step by Step)

Write out what a full user interaction looks like from start to finish - tool call by tool call. Use a specific example query.

**What FitFindr needs to do:** FitFindr is a thrift-shopping agent that takes a natural-language request and finds secondhand listings, then styles the best find against the user's existing wardrobe and writes a shareable caption for it. `search_listings` is triggered first whenever the user describes an item they want (with optional size/price limits); `suggest_outfit` fires once a candidate item is chosen, pairing it with the user's wardrobe; and `create_fit_card` fires last to turn that outfit into a post caption. On failure, each tool degrades gracefully instead of crashing - `search_listings` returns an empty list so the agent can tell the user nothing matched and offer to loosen filters, `suggest_outfit` falls back to general styling advice when the wardrobe is empty, and `create_fit_card` returns a descriptive error string when the outfit input is missing or incomplete.

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

**Step 1:** `run_agent` initializes the session and parses the query -> `parsed = {description: "vintage graphic tee", size: None, max_price: 30.0}`. It calls `search_listings("vintage graphic tee", size=None, max_price=30.0)`. The tool filters the 40 listings to those priced ≤ $30, scores each by keyword overlap with "vintage graphic tee", drops score-0 listings, and returns the ranked list. `session["search_results"]` is set.

**Step 2:** The list is non-empty, so the agent sets `session["selected_item"] = search_results[0]` (the top-scoring tee). It calls `suggest_outfit(selected_item, wardrobe)` with the example wardrobe (which includes baggy straight-leg jeans and chunky sneakers). The LLM returns 1-2 outfits naming those owned pieces; `session["outfit_suggestion"]` is set.

**Step 3:** The agent calls `create_fit_card(outfit_suggestion, selected_item)`. The outfit string is non-empty, so the LLM (higher temperature) returns a casual 2-4 sentence caption mentioning the tee's title, price, and platform once each. `session["fit_card"]` is set, and `run_agent` returns the session.

**Final output to user:** Three UI panels populated from the session - **🛍️ Top listing found** shows the formatted `selected_item` (title, price, condition, platform); **👗 Outfit idea** shows `outfit_suggestion` (the tee styled with their baggy jeans + chunky sneakers); **✨ Your fit card** shows `fit_card` (the shareable caption). `session["error"]` is `None`, so no error is shown.
