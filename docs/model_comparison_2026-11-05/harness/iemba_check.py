import uat_override, sys, json, re, dataclasses
sys.path.insert(0, "tests")
import test_uat_llm_judge as T
c = {x.case_id: x for x in T.UAT_CASES}["TC-IEMBA-01"]
print("CASE", json.dumps({k: (v if not callable(v) else "") for k, v in dataclasses.asdict(c).items()}, ensure_ascii=False, default=str)[:3500], flush=True)
out = []
for i in range(10):
    r = T._run_and_judge_case(c)
    j = r["judgement"]
    out.append({"score": float(r["score"]), "verdict": j.get("verdict"), "issues": j.get("issues"), "missed": j.get("criteria_missed"), "fact": j.get("factuality_ok"), "transcript": r["transcript"], "error": r.get("error")})
    print("RUN", i + 1, out[-1]["score"], flush=True)
json.dump(out, open(sys.argv[1] + "/iemba_check.json", "w"), ensure_ascii=False)
