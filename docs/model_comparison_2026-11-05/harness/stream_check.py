import sys, time, logging, collections, uuid, re
import langchain_openai
from langchain_core.callbacks import BaseCallbackHandler
served = collections.Counter()
class CB(BaseCallbackHandler):
    def on_llm_end(self, response, **kw):
        for g in response.generations:
            for x in g:
                md = getattr(getattr(x, "message", None), "response_metadata", {}) or {}
                served[md.get("model_name") or "unknown"] += 1
_p = langchain_openai.ChatOpenAI
def wrapped(*a, **k):
    k.setdefault("callbacks", [CB()]); return _p(*a, **k)
langchain_openai.ChatOpenAI = wrapped
from src.rag.agent_chain import ExecutiveAgentChain
warn = collections.Counter(); timing = []
class H(logging.Handler):
    def emit(self, r):
        m = r.getMessage()
        if r.levelno >= logging.WARNING: warn[m[:100]] += 1
        if "[timing] total turn" in m: timing.append(float(re.search(r"([\d.]+)s", m).group(1)))
h = H()
for n in list(logging.root.manager.loggerDict):
    if any(w in n for w in ("agent_chain", "middleware", "model_config", "weaviate")):
        l = logging.getLogger(n); l.addHandler(h); l.setLevel(logging.INFO)
convs = {"de": ["Was macht den EMBA HSG besonders?", "Wie ist das Alumni-Netzwerk?", "Was kostet der EMBA?", "Welche Zulassungsvoraussetzungen gibt es?"],
         "en": ["What makes the IEMBA HSG distinctive?", "Tell me about the international modules.", "How much does emba X cost?", "I'd like to book a consultation."]}
deltas = []
for lang, qs in convs.items():
    chain = ExecutiveAgentChain(language=lang, session_id=f"uat-stream-{uuid.uuid4()}")
    for q in qs:
        t = time.time(); n = 0; first = None
        box = {"n": 0, "first": None}
        def on_delta(d, box=box, t=t):
            box["n"] += 1
            box["first"] = box["first"] or time.time() - t
        res = chain.query(q, on_delta=on_delta)
        print(lang, "|", q[:40], "| first", box["first"] and round(box["first"], 2), "s | total", round(time.time() - t, 2), "s | deltas", box["n"], flush=True)
print("TIMING total turn:", timing)
print("SERVED", dict(served))
print("WARNINGS", warn.most_common(10))
