import sys,os,json,collections,importlib.util
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from kaggriculture_agent import registry
from kaggriculture_agent.local_arena import GameSpec,play_game
import kaggle_environments.envs.kaggriculture.kaggriculture as eng
PATHS={n:ROOT/f'references/kaggle-scan-2026-09-21/extracted/{d}/main.py' for n,d in [('omw','one-more-wheat'),('peak','peak2950'),('triad','triad-counter')]};PATHS['salem']=None;PATHS['economy_mix50']=None
orig=(eng._process_market,eng._parse_order,eng._commit_unit,eng._do_hire,eng._do_buy_land)
E=[];C={}
def market(state,env):
 global C
 C={'step':int(state[0].observation.step),'farms':state[0].observation.farms,'orders':[(s.action.get('market',[]) if isinstance(s.action,dict) else []) for s in state],'shed':[dict(s.observation.private['shed']) for s in state],'base':len(E),'pc':0,'slot':0}
 for p,orders in enumerate(C['orders']):
  for i,o in enumerate(orders):
   valid=isinstance(o,list) and bool(o) and o[0] in ('HIRE','BUY_LAND','BUY_SEED','BUY_PRODUCT','BUY_ANIMAL','SELL')
   if valid and o[0] not in ('HIRE','BUY_LAND'):
    valid=(len(o)>=3 and isinstance(o[2],int) and o[2]>0 and
           (o[1] in eng.PRODUCTS if o[0]=='SELL' else
            o[1] in ('WHEAT','FERTILIZER') if o[0]=='BUY_PRODUCT' else
            o[1] in eng.CROPS if o[0]=='BUY_SEED' else o[1] in eng.ANIMALS))
   if not valid or i>=10:E.append(dict(step=C['step'],p=p,slot=i,op='INVALID'))
 orig[0](state,env)
 for p in (0,1):
  for i,o in enumerate(C['orders'][p][:10]):
   if isinstance(o,list) and len(o)>=3 and o[0]=='SELL' and not any(e['p']==p and e['slot']==i and e['op']=='SELL' and e['ok'] for e in E[C['base']:]):
    E.append(dict(step=C['step'],p=p,slot=i,op='ZERO_SELL',item=o[1],requested=o[2],post_work_shed=C['shed'][p].get(o[1],0),later_sells=sum(x[0]=='SELL' for x in C['orders'][p][i+1:] if x)))
 C={}
def parse(o):
 C['slot']=C['pc']//2;C['pc']+=1
 return orig[1](o)
def commit(op,item,price,farm,private,market,cap=100):
 p=0 if farm is C['farms'][0] else 1;before=farm['money'];stock=private['shed'].get(item,0)
 ok=orig[2](op,item,price,farm,private,market,cap)
 E.append(dict(step=C['step'],p=p,slot=C['slot'],op=op,item=item,price=price,money=before,stock=stock,ok=ok))
 return ok
def hire(farm,private,size,mult=eng.FARM_HAND_COST_MULT):
 p=0 if farm is C['farms'][0] else 1;before=farm['money'];cost=eng._hire_cost(farm['hires_today'],mult)
 orig[3](farm,private,size,mult)
 E.append(dict(step=C['step'],p=p,slot=C['slot'],op='HIRE',price=cost,money=before,ok=farm['money']<before))
def land(farm,size):
 p=0 if farm is C['farms'][0] else 1;before=farm['money'];n=len(farm['unlocked_quadrants'])-1;cost=eng.LAND_PRICES[n] if n<len(eng.LAND_PRICES) else None
 orig[4](farm,size)
 E.append(dict(step=C['step'],p=p,slot=C['slot'],op='BUY_LAND',price=cost,money=before,ok=farm['money']<before))
def init():
 eng._process_market=market;eng._parse_order=parse;eng._commit_unit=commit;eng._do_hire=hire;eng._do_buy_land=land
 name='candidate_zero_sell_guard' if os.environ.get('AUDIT_VARIANT')=='zero_guard' else 'candidate'
 registry.AGENTS['_audit_c']=registry.get_agent(name)
 for n,path in PATHS.items():
  if path is None:
   registry.AGENTS['_audit_'+n]=registry.get_agent('public_salem' if n=='salem' else 'economy_mix50_waste_shield');continue
  spec=importlib.util.spec_from_file_location(f'opp_{n}_{os.getpid()}',path);m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m);registry.AGENTS['_audit_'+n]=m.agent
def run(t):
 o,seed,seat=t;E.clear();a='_audit_c';b='_audit_'+o;players=(a,b) if seat==0 else (b,a)
 r=play_game(GameSpec(f'audit-{o}-{seed}-{seat}',seed,*players,a,b,f'{o}-{seed}',seat))
 events=[e for e in E if e['p']==seat]; zeros=[e for e in events if e['op']=='ZERO_SELL'];fund=[]
 for e in zeros:e['later_executed_sells']=sum(x['step']==e['step'] and x['slot']>e['slot'] and x['op']=='SELL' and x['ok'] for x in events)
 for e in events:
  if e['op'] in ('BUY_SEED','BUY_PRODUCT','BUY_ANIMAL','HIRE','BUY_LAND') and not e['ok'] and e['price'] is not None and e['money']<e['price']:
   later=[x for x in events if x['step']==e['step'] and x['slot']>e['slot'] and x['op']=='SELL' and x['ok']]
   if later:fund.append({**e,'missing':e['price']-e['money'],'later_revenue':sum(x['price'] for x in later)})
 own,other=(r.reward_0,r.reward_1) if seat==0 else (r.reward_1,r.reward_0)
 return dict(opponent=o,seed=seed,seat=seat,status=r.status,error=r.error,reward=own,other=other,zero=zeros,funding=fund,invalid=sum(e['op']=='INVALID' for e in events),sell_success=sum(e['op']=='SELL' and e['ok'] for e in events))
if __name__=='__main__':
 seed=int(sys.argv[1]);count=int(sys.argv[2]);out=Path(sys.argv[3]);tasks=[(o,s,p) for s in range(seed,seed+count) for o in PATHS for p in (0,1)]
 with ProcessPoolExecutor(max_workers=4,initializer=init) as pool: rows=list(pool.map(run,tasks,chunksize=1))
 out.write_text(json.dumps(rows,indent=2))
 print(json.dumps(dict(games=len(rows),errors=sum(r['status']!='completed' for r in rows),zero=sum(len(r['zero']) for r in rows),funding=sum(len(r['funding']) for r in rows),fundable=sum(e['later_revenue']>=e['missing'] for r in rows for e in r['funding']))))
