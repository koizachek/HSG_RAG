import sys, json, os, statistics as st, concurrent.futures as cf
sys.path.insert(0, "tests")
import test_uat_llm_judge as T
b = sys.argv[1]
C = {c.case_id: c for c in T.UAT_CASES}
print("judge", T.DEFAULT_JUDGE_MODEL)
dirs = {"gpt-5.6-luna": ["final_luna56", "cmp_luna56"], "flash-lite": ["final_flashlite", "cmp_flashlite"], "gpt-4.1": ["uat_gpt41"]}
def one(name, cid, d):
    s = [float(T._judge_case(C[cid], d["transcript"])["overall_score"]) for _ in range(2)]
    return name, cid, d["score"], s
jobs = []
with cf.ThreadPoolExecutor(8) as ex:
    for name, ds in dirs.items():
        for cid in C:
            for dd in ds:
                p = f"{b}/{dd}/{cid}.json"
                if os.path.exists(p):
                    d = json.load(open(p))
                    if not d.get("error"):
                        jobs.append(ex.submit(one, name, cid, d)); break
    res = [j.result() for j in jobs]
for name in dirs:
    r = sorted(x for x in res if x[0] == name)
    new = [st.mean(x[3]) for x in r]; old = [x[2] for x in r]
    print(f"{name}: cases {len(r)} judge41 avg {st.mean(old):.2f} min {min(old)} | gemini avg {st.mean(new):.2f} min {min(new)} below8 {[x[1] for x in r if st.mean(x[3]) < 8]}")
    for x in r: print("  ", x[1], "4.1:", x[2], "gemini:", x[3])
