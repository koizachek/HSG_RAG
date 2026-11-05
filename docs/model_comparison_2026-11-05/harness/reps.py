import uat_override, os, sys, re, json
sys.path.insert(0, "tests")
import test_uat_llm_judge as T
C = {x.case_id: x for x in T.UAT_CASES}
for cid, n in json.loads(os.environ["CMP_REPS"]):
    rs = [T._run_and_judge_case(C[cid]) for _ in range(n)]
    errs = sum(bool(r.get("error")) for r in rs)
    alt = sum(bool(re.search(r"(?<!e)mba\.unisg\.ch|regulären? \**MBA", " ".join(t["assistant"] for t in r["transcript"][1:]))) for r in rs)
    print("REP", os.environ["CMP_MODEL"], cid, [float(r["score"]) for r in rs], "errors", errs, "mba", alt, flush=True)
