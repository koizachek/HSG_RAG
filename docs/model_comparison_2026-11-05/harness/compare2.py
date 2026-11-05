import uat_override, os, sys, re, json, collections, statistics as st
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
sys.path.insert(0, "tests")
import test_uat_llm_judge as T
name = os.environ["CMP_MODEL"]
def alt(tr):
    a = " ".join(t["assistant"] + " " + (t.get("additional_details") or "") for t in tr[1:])
    return bool(re.search(r"(?<!e)mba\.unisg\.ch|regulären? \**MBA", a))
res = [T._run_and_judge_case(c) for c in T.UAT_CASES]
sc = {r["case"].case_id: float(r["score"]) for r in res}
errs = [r["case"].case_id for r in res if r.get("error")]
el = [t["elapsed_s"] for r in res for t in r["transcript"] if t.get("message_type") != "greeting" and t.get("elapsed_s", 0) > 0.5]
c = {x.case_id: x for x in T.UAT_CASES}["TC-EDGE-01"]
ed = [T._run_and_judge_case(c) for _ in range(5)]
ie = [float(T._run_and_judge_case({x.case_id: x for x in T.UAT_CASES}["TC-IEMBA-01"])["score"]) for _ in range(5)]
out = {"model": name, "avg": round(st.mean(sc.values()), 2), "min": min(sc.values()), "below8": [k for k, v in sc.items() if v < 8], "errors": errs,
       "median_s": round(st.median(el), 2) if el else None, "mean_s": round(st.mean(el), 2) if el else None, "max_s": max(el) if el else None,
       "iemba01": ie, "edge01": [float(r["score"]) for r in ed], "edge01_mba": sum(alt(r["transcript"]) for r in ed), "served": dict(served), "scores": sc}
print("RESULT " + json.dumps(out, ensure_ascii=False), flush=True)
