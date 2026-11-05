import json,os,re,sys,time,urllib.request
key=[l.split('=',1)[1].strip().strip('"\'') for l in open('.env') if l.startswith('OPEN_ROUTER_API_KEY=')][0]
d={m['id']:m for m in json.load(open(sys.argv[1]))['data']}
for i in ['openai/gpt-4.1','openai/gpt-4o-mini','openai/gpt-6-luna','openai/gpt-6.1-terra','openai/gpt-6.1-sol']:
    m=d.get(i); 
    if not m: print(i,'MISSING'); continue
    print(i,'in',float(m['pricing']['prompt'])*1e6,'out',float(m['pricing']['completion'])*1e6,'|',m.get('description','')[:260].replace('\n',' '))
prompt="Beantworte in etwa 80 Wörtern auf Deutsch: Was sollte man bei der Wahl eines berufsbegleitenden Executive MBA beachten?"
def run(model,effort):
    body={"model":model,"stream":True,"max_tokens":400,"messages":[{"role":"user","content":prompt}]}
    if effort: body["reasoning"]={"effort":effort}
    r=urllib.request.Request("https://openrouter.ai/api/v1/chat/completions",json.dumps(body).encode(),{"Authorization":"Bearer "+key,"Content-Type":"application/json"})
    t=time.time();first=None;n=0
    with urllib.request.urlopen(r,timeout=90) as f:
        for l in f:
            if not l.startswith(b'data: ') or l.startswith(b'data: [DONE]'): continue
            c=json.loads(l[6:]).get('choices') or [{}]
            if (c[0].get('delta') or {}).get('content'):
                first=first or time.time()-t; n+=1
    return first,time.time()-t,n
for model,effort in [('openai/gpt-4.1',None),('openai/gpt-6-luna','low'),('openai/gpt-6-luna',None),('openai/gpt-6.1-terra','low'),('openai/gpt-6.1-terra',None),('openai/gpt-6.1-sol','low')]:
    res=[]
    for _ in range(3):
        try: res.append(run(model,effort))
        except Exception as e: res.append(repr(e)[:120])
    ok=[x for x in res if isinstance(x,tuple) and x[0]]
    print(model,effort,'ttft',[round(x[0],2) for x in ok],'total',[round(x[1],2) for x in ok],'errs',[x for x in res if not isinstance(x,tuple)])
