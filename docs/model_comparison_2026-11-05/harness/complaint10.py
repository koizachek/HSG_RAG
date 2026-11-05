import os, sys
if os.environ.get("CMP_MODEL"): import uat_override
sys.path.insert(0, "tests")
import test_llm_fact_eval as E
from src.rag.agent_chain import ExecutiveAgentChain
case = [c for c in E.build_cases() if c["id"] == "de_price_complaint"][0]
res = []
for i in range(10):
    try: E._assert_case(case, ExecutiveAgentChain(language="de", session_id=f"eval_complaint_{i}")); res.append("pass")
    except AssertionError as e: res.append("FAIL"); print("  fail:", str(e).split("Answer:")[-1][:200].replace("\n"," "), flush=True)
print("RESULT", os.environ.get("CMP_MODEL") or "config(flash-lite)", "require_with", case["require_with"], res.count("pass"), "/10 pass", flush=True)
