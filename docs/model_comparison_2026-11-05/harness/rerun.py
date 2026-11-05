import uat_override, os, logging, collections, sys
sys.path.insert(0, "tests")
warns = collections.Counter(); models = collections.Counter()
class H(logging.Handler):
    def emit(self, r):
        m = r.getMessage()
        if r.levelno >= logging.WARNING: warns[m[:90]] += 1
        if "Initialized" in m and "model" in m: models[m[:90]] += 1
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
    k.setdefault("callbacks", [CB()])
    return _p(*a, **k)
langchain_openai.ChatOpenAI = wrapped
import test_uat_llm_judge as T
for l in [logging.getLogger()] + [logging.getLogger(n) for n in logging.root.manager.loggerDict]:
    l.addHandler(H())
cases = {c.case_id: c for c in T.UAT_CASES}
for cid, n in [("TC-EDGE-03", 3), ("TC-EMBA-03", 1)]:
    print(os.environ["CMP_EFFORT"] or "standard", cid, [float(T._run_and_judge_case(cases[cid])["score"]) for _ in range(n)], flush=True)
print("served", dict(served)); print("warnings", warns.most_common(6))
