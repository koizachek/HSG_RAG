"""Production smoke tests over the public Gradio API (6 checks).

Usage (repo venv has gradio_client):

    venv/bin/python .claude/skills/hsg-rag-diagnostics-and-tooling/scripts/public_smoke_test.py

Covers: consent decline, consent accept + booking widget, DE retrieval (USP),
DE pricing (verified facts), DE advisor handover, EN language switch.
Each chat turn is a real LLM call in production — run when needed, not in a loop.
Exit code 0 = all passed. Baseline runtime ~45 s (2026-07-07).

API notes that will save you an hour:
- Named endpoints: /on_decline, /on_accept, /on_language_change, /_chat
  (discover with Client(URL).view_api(all_endpoints=True)).
- Handlers returning gr.update(...) arrive client-side as dicts {'value': ...}
  — unwrap before slicing, or you get KeyError: slice(...).
- One Client instance = one session; consent/agent state persists across
  predict() calls on the same Client, so accept first, then chat.
"""
import sys
import time

from gradio_client import Client

URL = "https://chatbot.emba.unisg.ch/"

ERR_SNIPPETS = [
    "keine hilfreiche Antwort geben",     # QUERY_EXCEPTION_MESSAGE de
    "cannot provide a helpful response",  # QUERY_EXCEPTION_MESSAGE en
    "not properly initialized",           # agent state is None
]

results = []


def check(name, ok, detail=""):
    results.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))


def val(x):
    """gr.update() returns arrive as dicts {'value': ...}."""
    if isinstance(x, dict):
        return x.get("value", "") or ""
    return x if isinstance(x, str) else str(x)


def ask(client, msg):
    t0 = time.time()
    resp = client.predict(message=msg, api_name="/_chat")
    return (resp if isinstance(resp, str) else str(resp)), time.time() - t0


# --- Session 1: decline flow (DE) ---
c = Client(URL, verbose=False)
decline_info, _ = (val(x) for x in c.predict(api_name="/on_decline"))
check("consent decline shows notice + contact",
      "Ohne Ihre Einwilligung" in decline_info and "emba@unisg.ch" in decline_info)

# --- Session 2: accept + DE chat ---
c = Client(URL, verbose=False)
_, widget_html = (val(x) for x in c.predict(api_name="/on_accept"))
check("booking widget HTML present after accept", len(widget_html) > 100)

text, dt = ask(c, "Was macht die HSG besonders?")
check("DE USP question returns real retrieval content",
      len(text) > 200 and not any(s in text for s in ERR_SNIPPETS), f"{dt:.1f}s")

text, dt = ask(c, "Was kostet der EMBA und wie lange dauert er?")
check("DE pricing question answered",
      len(text) > 100 and not any(s in text for s in ERR_SNIPPETS), f"{dt:.1f}s")

text, dt = ask(c, "Ich möchte gerne einen persönlichen Beratungstermin vereinbaren. Wie geht das?")
check("DE handover offers advisor/booking path",
      any(k in text for k in ["Termin", "Beratung", "buchen", "emba@unisg.ch"])
      and not any(s in text for s in ERR_SNIPPETS), f"{dt:.1f}s")

# --- Session 3: EN ---
c = Client(URL, verbose=False)
c.predict(language_label="English", api_name="/on_language_change")
c.predict(api_name="/on_accept")
text, dt = ask(c, "What makes the Executive MBA at the University of St. Gallen special?")
looks_english = sum(text.lower().count(w) for w in [" the ", " and ", " of "]) >= 3
check("EN question returns English content",
      len(text) > 200 and looks_english and not any(s in text for s in ERR_SNIPPETS), f"{dt:.1f}s")

failed = [n for n, ok in results if not ok]
print(f"\n{len(results) - len(failed)}/{len(results)} passed")
sys.exit(1 if failed else 0)
