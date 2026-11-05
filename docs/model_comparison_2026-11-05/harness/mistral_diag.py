import json,os,time,sys,httpx
from src.rag.prompts import PromptConfigurator
key=[l.split('=',1)[1].strip().strip('"\'') for l in open('.env') if l.startswith('OPEN_ROUTER_API_KEY=')][0]
try:
    sysp=PromptConfigurator.get_configured_agent_prompt('lead',language='de')
except Exception as e:
    sysp=None; print('prompt err',repr(e)[:150])
print('sys prompt chars',len(sysp) if sysp else None)
schema={"type":"object","properties":{"response":{"type":"string"},"appointment_requested":{"type":"boolean"}},"required":["response","appointment_requested"],"additionalProperties":False}
tools=[{"type":"function","function":{"name":"retrieve_context","description":"Search programme documents","parameters":{"type":"object","properties":{"query":{"type":"string"}},"required":["query"]}}}]
user="Was kostet der EMBA?"
def run(model,label,sysm=False,rf=False,tl=False,eff=None):
    msgs=([{"role":"system","content":sysp}] if sysm and sysp else [])+[{"role":"user","content":user}]
    b={"model":model,"stream":True,"messages":msgs,"max_tokens":1500,"temperature":0.01}
    if rf:b["response_format"]={"type":"json_schema","json_schema":{"name":"r","strict":True,"schema":schema}}
    if tl:b["tools"]=tools
    if eff:b["reasoning"]={"effort":eff}
    t=time.time();first=None;out=0;reas=0;prov=None;err=None;tc=0
    try:
        with httpx.stream("POST","https://openrouter.ai/api/v1/chat/completions",headers={"Authorization":"Bearer "+key},json=b,timeout=httpx.Timeout(90,read=90)) as r:
            if r.status_code!=200: err=f"http {r.status_code} "+r.read().decode()[:160]
            else:
              for l in r.iter_lines():
                if not l.startswith("data: ") or "[DONE]" in l: continue
                j=json.loads(l[6:]); prov=j.get("provider") or prov
                if j.get("error"): err=str(j["error"])[:160]
                for c in j.get("choices") or []:
                    dl=c.get("delta") or {}
                    if dl.get("reasoning"): reas+=len(dl["reasoning"])
                    if dl.get("content") or dl.get("tool_calls"):
                        first=first or time.time()-t; out+=len(dl.get("content") or "")+(1 if dl.get("tool_calls") else 0)
                    if dl.get("tool_calls"): tc+=1
    except Exception as e: err=repr(e)[:120]
    print(f"{model.split('/')[1]:22} {label:28} first={first and round(first,1)} total={round(time.time()-t,1)} out={out} reasoning_chars={reas} tool={tc} prov={prov} err={err}",flush=True)
for m in ["mistralai/mistral-large-4-0","mistralai/mistral-medium-3-5","anthropic/claude-haiku-5.5"]:
    run(m,"plain")
    run(m,"plain low",eff="low")
    run(m,"sysprompt low",sysm=True,eff="low")
    run(m,"sysprompt schema low",sysm=True,rf=True,eff="low")
    run(m,"sysprompt schema tools low",sysm=True,rf=True,tl=True,eff="low")
    run(m,"sysprompt schema tools noeff",sysm=True,rf=True,tl=True)
