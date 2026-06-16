# FitFindr 🛍️

FitFindr is a multi-tool agent that helps you shop secondhand. You describe what
you're after in plain language; FitFindr searches a mock marketplace, picks the
best match, styles it against your existing wardrobe, and writes a shareable
"fit card" caption for the find.

It runs a fixed three-tool pipeline - **search -> style -> caption** - where each
step's behavior depends on the previous step's result.

---

## Setup

```bash
pip install -r requirements.txt
```

Set your Groq API key in a `.env` file in the project root (free key at
[console.groq.com](https://console.groq.com)):

```
GROQ_API_KEY=your_key_here
```

## Running it

**Web UI (Gradio):**
```bash
python app.py
```
Then open the URL printed in your terminal (usually http://localhost:7860).
Type a query, pick a wardrobe, and the three panels populate: the top listing,
an outfit idea, and a fit-card caption.

**CLI smoke test:**
```bash
python agent.py        # runs a happy-path query and the no-results path
```

**Tests:**
```bash
pytest tests/          # 10 tests; LLM tests auto-skip if GROQ_API_KEY is unset
```

---

## Architecture at a glance

```
user query + wardrobe -> run_agent (planning loop) -> session dict -> 3 UI panels
                              │
       search_listings ──> suggest_outfit ──> create_fit_card
       (local filter)       (Groq LLM)         (Groq LLM)
```

See [planning.md](planning.md) for the full spec, agent diagram, and a
step-by-step interaction walkthrough.

---

## Tool inventory

### 1. `search_listings(description, size, max_price) -> list[dict]`
Searches the 40-item mock marketplace (loaded via `load_listings()`) for items
matching the keywords, filtered by optional size and price ceiling, ranked by
relevance. Pure local filtering - **no LLM call**.

- **Inputs:** `description` (str, keywords), `size` (str | None, case-insensitive
  substring match so `"M"` matches `"S/M"`), `max_price` (float | None, inclusive).
- **Output:** a `list[dict]` sorted by keyword-overlap score, highest first. Each
  dict has `id`, `title`, `description`, `category`, `style_tags`, `size`,
  `condition`, `price`, `colors`, `brand`, `platform`. Returns `[]` when nothing
  matches - never raises.

### 2. `suggest_outfit(new_item, wardrobe) -> str`
Asks Groq `llama-3.3-70b-versatile` to propose 1-2 complete outfits pairing the
chosen item with the user's wardrobe.

- **Inputs:** `new_item` (dict, a listing), `wardrobe` (dict with an `"items"`
  list; each item has `name`, `category`, `colors`, `style_tags`, optional `notes`).
- **Output:** a non-empty `str`. With wardrobe items it names specific owned
  pieces; with an empty wardrobe it gives general styling advice instead.

### 3. `create_fit_card(outfit, new_item) -> str`
Turns the outfit into a short, shareable OOTD caption using the LLM at high
temperature (so repeated calls vary).

- **Inputs:** `outfit` (str, from `suggest_outfit`), `new_item` (dict, so the
  caption can mention the title, price, and platform).
- **Output:** a 2-4 sentence caption `str`. If `outfit` is empty/whitespace,
  returns a descriptive error string instead of calling the LLM.

---

## How the planning loop works

`run_agent(query, wardrobe)` in [agent.py](agent.py) is a **fixed, conditional
pipeline** - not an open-ended "pick a tool" loop. The order is fixed, but
*whether* later tools run depends on earlier results:

1. **Initialize** a `session` dict (the single source of truth).
2. **Parse** the query into `{description, size, max_price}` with regex
   (`"under $30"` -> `max_price=30.0`, `"size M"` -> `size="M"`, the rest ->
   `description`). No LLM is used for parsing.
3. **Search** with those parameters.
   - **If the result is empty** -> set `session["error"]` to a helpful message and
     **return early**. `suggest_outfit` and `create_fit_card` are *never* called.
   - **If non-empty** -> continue.
4. **Select** the top-ranked listing (`search_results[0]`).
5. **Style** it against the wardrobe (always returns a usable string).
6. **Caption** the outfit (returns a guard message if the outfit was empty).
7. **Return** the session.

The key design property: the agent behaves differently for different inputs. A
no-results query stops after step 3 with only an error set; a matching query
flows through all three tools.

## State management

A single `session` dict, created by `_new_session()`, carries everything through
the run. Tools are pure functions (args in, value out); the planning loop is the
only thing that reads/writes the session, so data flow is explicit:

```
parsed -> search_listings -> search_results -> selected_item
       -> suggest_outfit -> outfit_suggestion -> create_fit_card -> fit_card
```

Tracked fields: `query`, `parsed`, `search_results`, `selected_item`, `wardrobe`,
`outfit_suggestion`, `fit_card`, `error` (`None` unless the run ended early).
Nothing is re-derived or re-prompted between steps - each tool receives exactly
the object the previous step stored. (Verified: `session["selected_item"] is
session["search_results"][0]` is `True`.)

---

## Error handling per tool

| Tool | Failure mode | What the agent does |
|------|-------------|---------------------|
| `search_listings` | No results match | Returns `[]`; the loop sets `session["error"]` and returns early without calling the other tools. |
| `suggest_outfit` | Wardrobe is empty | Detects `wardrobe["items"] == []` and switches to a general-advice prompt; still returns a useful string and the run continues. |
| `create_fit_card` | Outfit missing/empty | Guards against empty/whitespace `outfit` and returns a descriptive message string instead of raising. |

**Concrete examples from testing** (Milestone 5):

- **No results** - `search_listings("designer ballgown", size="XXS", max_price=5)`
  returns `[]`, and the agent responds:
  > *No listings matched 'designer ballgown', size XXS, under $5. Try raising your
  > price limit, dropping the size filter, or using broader keywords.*
- **Empty wardrobe** - `suggest_outfit(item, get_empty_wardrobe())` returns general
  advice ("pair it with distressed denim or a flowy skirt ... neutral sneakers")
  rather than crashing.
- **Empty outfit** - `create_fit_card("", item)` returns:
  > *Couldn't generate a fit card: no outfit suggestion was available to caption.*

---

## How I used AI to build this

**Tools (`tools.py`).** I gave Claude the per-tool blocks from my planning.md (the
inputs, return values, and failure modes) plus the `load_listings()` docstring and
had it draft each function. The first version of `search_listings` scored every
word equally, so common words like "looking" and "under" were inflating the match
counts. I added a stopword list to fix that, and changed the size check to a
substring match so "M" would match the "S/M" sizes in the data. Then I ran my three
search tests before moving on.

**Planning loop (`agent.py`).** I gave it my architecture diagram and the planning
loop / state sections and asked for `run_agent`. I made sure it actually branches on
the empty search result and returns early instead of calling all three tools no
matter what, and that each step reads its input from the session. I checked the
state was really being passed by asserting `selected_item` is the same object as
`search_results[0]`.

---

## Spec reflection

Doing planning.md first definitely helped. Since I'd already written down each
tool's inputs, outputs, and what happens when it fails, writing the actual code was
pretty straightforward and the planning loop basically followed my seven steps. The
part that was harder than I expected was parsing the query. It sounds simple to
"get the description," but pulling out the price and size while keeping the rest of
the keywords took more regex than I planned for. Keeping everything in one session
dict made debugging easy, since I could print it at any point and see exactly what
each tool had produced.

---

## Project layout

```
ai201-project2-fitfindr-starter/
├── agent.py                  # run_agent planning loop + query parser
├── app.py                    # Gradio UI + handle_query
├── tools.py                  # the three tools
├── tests/
│   └── test_tools.py         # pytest tests incl. each failure mode
├── data/
│   ├── listings.json         # 40 mock secondhand listings
│   └── wardrobe_schema.json  # wardrobe format + example/empty wardrobes
├── utils/
│   └── data_loader.py        # data loading helpers
├── planning.md               # spec, agent diagram, interaction walkthrough
└── requirements.txt
```
