import uat_override, sys, time, logging, faulthandler, uuid
faulthandler.dump_traceback_later(270, exit=True)
sys.path.insert(0, "tests")
T0 = time.time()
class F(logging.Formatter):
    def format(self, r):
        return f"[{time.time()-T0:7.1f}s] {r.name[:18]:18} {r.levelname[:4]} {r.getMessage()[:170]}"
h = logging.StreamHandler(sys.stdout); h.setFormatter(F())
import test_uat_llm_judge as T
from src.rag.agent_chain import ExecutiveAgentChain
wanted = ("httpx", "openai", "agent_chain", "middleware", "weaviate", "model_config")
for n in list(logging.root.manager.loggerDict) :
    if any(w in n for w in wanted):
        l = logging.getLogger(n); l.addHandler(h); l.setLevel(logging.INFO); l.propagate = False
for n in ("httpx", "openai._base_client"):
    l = logging.getLogger(n); l.addHandler(h); l.setLevel(logging.INFO); l.propagate = False
c = {x.case_id: x for x in T.UAT_CASES}["TC-EMBA-01"]
chain = ExecutiveAgentChain(language=c.expected_language or "de", session_id=f"uat-trace-{uuid.uuid4()}")
for i, q in enumerate(c.user_turns, 1):
    t = time.time(); print(f"=== TURN {i} start at {t-T0:.1f}s", flush=True)
    r = chain.query(q)
    print(f"=== TURN {i} took {time.time()-t:.1f}s", flush=True)
