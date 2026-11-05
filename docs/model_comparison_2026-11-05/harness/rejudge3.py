import sys, json
sys.path.insert(0, "tests")
import test_uat_llm_judge as T
c = {x.case_id: x for x in T.UAT_CASES}["TC-IEMBA-01"]
print("expected", c.expected_bot_behaviour[1].replace("\n", " "))
o = json.load(open(sys.argv[1] + "/iemba_check.json"))
res = []
for r in o:
    j = T._judge_case(c, r["transcript"]); res.append((r["score"], float(j["overall_score"]), j.get("criteria_missed")))
    print("old", r["score"], "new", res[-1][1], "| missed:", str(res[-1][2])[:210], flush=True)
print("below8 old", sum(x[0] < 8 for x in res), "new", sum(x[1] < 8 for x in res))
