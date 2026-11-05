import sys, json, re, concurrent.futures as cf
sys.path.insert(0, "tests")
import test_uat_llm_judge as T
c = {x.case_id: x for x in T.UAT_CASES}["TC-EDGE-03"]
print("EXPECTED", c.expected_bot_behaviour, "| CRITERIA", c.success_criteria, flush=True)
def one(_):
    r = T._run_and_judge_case(c); j = r["judgement"]
    a = r["transcript"][-1]["assistant"]
    return {"score": float(r["score"]), "missed": j.get("criteria_missed"), "answer": a, "details": r["transcript"][-1].get("additional_details"),
            "named": bool(re.search(r"Cyra von Müller|Kristin Fuchs|Teyuna Giger", a)), "contact": "@unisg.ch" in a}
with cf.ThreadPoolExecutor(5) as ex: out = list(ex.map(one, range(10)))
json.dump(out, open(sys.argv[1], "w"), ensure_ascii=False)
print("SCORES", [o["score"] for o in out], "below8", sum(o["score"] < 8 for o in out), "named", sum(o["named"] for o in out), "contact", sum(o["contact"] for o in out))
