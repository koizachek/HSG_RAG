import sys, json
sys.path.insert(0, "tests")
import test_uat_llm_judge as T
cases = {c.case_id: c for c in T.UAT_CASES}
b = sys.argv[1]
c = cases["TC-EDGE-01"]
full = json.load(open(f"{b}/fix_uat/TC-EDGE-01.json"))["transcript"]
print("FULLUAT answer tail:", full[-1]["assistant"][-330:].replace("\n"," "))
print("details:", (full[-1].get("additional_details") or "")[:200])
print("orig 7.5 rejudged", [float(T._judge_case(c, full)["overall_score"]) for _ in range(6)], flush=True)
for i, label in [(1, "orig 10.0"), (4, "orig 6.5"), (2, "orig 7.0")]:
    t = json.load(open(f"{b}/fix_rep_json/TC-EDGE-01_{i}.json"))
    print(label, "rejudged", [float(T._judge_case(c, t)["overall_score"]) for _ in range(6)], "has_mba", "mba.unisg.ch" in t[-1]["assistant"], flush=True)
    print("  tail:", t[-1]["assistant"][-200:].replace("\n"," "), flush=True)
