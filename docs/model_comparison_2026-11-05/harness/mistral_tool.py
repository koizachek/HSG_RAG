import json,time,sys,httpx
from src.rag.prompts import PromptConfigurator
key=[l.split('=',1)[1].strip().strip('"\'') for l in open('.env') if l.startswith('OPEN_ROUTER_API_KEY=')][0]
sysp=PromptConfigurator.get_configured_agent_prompt('lead',language='de')
schema={"type":"object","properties":{"response":{"type":"string"},"appointment_requested":{"type":"boolean"}},"required":["response","appointment_requested"],"additionalProperties":False}
tools=[{"type":"function","function":{"name":"retrieve_context","description":"Search programme documents","parameters":{"type":"object","properties":{"query":{"type":"string"}},"required":["query"]}}}]
msgs=[{"role":"system","content":sysp},{"role":"user","content":"Ich habe 15 Jahre Berufserfahrung und 7 Jahre Führung. Kann ich mich für den EMBA bewerben?"},
 {"role":"assistant","content":"","tool_calls":[{"id":"call_abc123xyz","type":"function","function":{"name":"retrieve_context","arguments":"{\"query\":\"Zulassung EMBA\"}"}}]},
 {"role":"tool","tool_call_id":"call_abc123xyz","content":"[EMBA HSG | emba.unisg.ch] Zulassung: anerkannter akademischer Erstabschluss, mindestens 5 Jahre Berufserfahrung, mindestens 3 Jahre Führungserfahrung."}]
def run(m,label,stream=True,rf=True,tl=True,eff="low"):
    b={"model":m,"stream":stream,"messages":msgs,"max_tokens":1500,"temperature":0.01}
    if rf:b["response_format"]={"type":"json_schema","json_schema":{"name":"r","strict":True,"schema":schema}}
    if tl:b["tools"]=tools
    if eff:b["reasoning"]={"effort":eff}
    t=time.time();first=None;n=0;last=None;reason=None;chunks=0;err=None
    try:
        with httpx.stream("POST","https://openrouter.ai/api/v1/chat/completions",headers={"Authorization":"Bearer "+key},json=b,timeout=httpx.Timeout(75,read=75)) as r:
            if r.status_code!=200: err=f"http {r.status_code} "+r.read().decode()[:150]
            elif not stream:
                j=json.loads(r.read()); first=time.time()-t; c=j["choices"][0]; n=len(c["message"].get("content") or ""); reason=c.get("finish_reason")
            else:
              for l in r.iter_lines():
                if l.startswith(": "): chunks+=1; continue
                if not l.startswith("data: ") or "[DONE]" in l: continue
                j=json.loads(l[6:])
                if j.get("error"): err=str(j["error"])[:150]
                for c in j.get("choices") or []:
                    if c.get("finish_reason"): reason=c["finish_reason"]
                    d=c.get("delta") or {}
                    if d.get("content"): first=first or time.time()-t; n+=len(d["content"])
    except Exception as e: err=repr(e)[:90]
    print(f"{m.split('/')[1]:20} {label:26} first={first and round(first,1)} total={round(time.time()-t,1)} chars={n} finish={reason} keepalives={chunks} err={err}",flush=True)
for m in ["mistralai/mistral-large-4-0","mistralai/mistral-medium-3-5"]:
    for _ in range(2): run(m,"stream schema tools low")
    run(m,"stream schema tools noeff",eff=None)
    run(m,"stream schema notools low",tl=False)
    run(m,"stream noschema tools low",rf=False)
    run(m,"nostream schema tools low",stream=False)
