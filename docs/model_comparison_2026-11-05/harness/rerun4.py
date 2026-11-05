import sys, re, json
sys.path.insert(0, "tests")
import test_uat_llm_judge as T
cases = {c.case_id: c for c in T.UAT_CASES}
for cid in ["TC-EDGE-01", "TC-EDGE-03"]:
    rows = []
    for _ in range(10):
        r = T._run_and_judge_case(cases[cid])
        a = " ".join(t["assistant"] + " " + (t.get("additional_details") or "") for t in r["transcript"][1:])
        rows.append((float(r["score"]), "mba.unisg.ch" in a or "Open Programmes" in a or "op.unisg.ch" in a, "@unisg.ch" in a, bool(re.search(r"Cyra von Müller|Kristin Fuchs|Teyuna Giger", a))))
        json.dump(r["transcript"], open(f"{sys.argv[1]}/{cid}_{len(rows)}.json", "w"), ensure_ascii=False)
    print(cid, "scores", [x[0] for x in rows], flush=True)
    print(cid, "alternative", sum(x[1] for x in rows), "email", sum(x[2] for x in rows), "named", sum(x[3] for x in rows), "of 10", flush=True)
