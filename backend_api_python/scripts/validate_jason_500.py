"""Real-data validation gate for Jason US Swing $500.

Research only. No broker connectivity or live order path.
Synthetic OHLCV is intentionally prohibited here: missing/invalid point-in-time
market, spread/liquidity, earnings and catalyst data fails closed to NO_TRADE.
"""
from __future__ import annotations
import json, os
from pathlib import Path
import numpy as np
import pandas as pd
import vectorbt as vbt
from jason_us_swing_500 import Jason500Config, features, entry_mask, exits

ROOT=Path(__file__).resolve().parents[2]
DATA=ROOT/'data'/'jason_500_pit'
RESULT=ROOT/'QUANTDINGER_JASON_500_RESULT.json'
REPORT=ROOT/'QUANTDINGER_JASON_500_REPORT.md'
CFG=Jason500Config()
REQUIRED=['symbol','timestamp','open','high','low','close','volume','bid','ask','earnings_ts','catalyst_ts','catalyst_score','market_close','sector_close']


def fail_closed(reason:str, detail:str=''):
    payload={'strategy':'Jason US Swing 500','mode':'research_only','capital_usd':500,'margin':False,'leverage':False,'broker_connected':False,'live_orders':False,'data_mode':'point_in_time_real_required','synthetic_allowed':False,'qualification':'REJECT','trade_decision':'NO_TRADE','today':'今天不交易','reason':reason,'detail':detail,'hard_gates_passed':False}
    RESULT.write_text(json.dumps(payload,indent=2,ensure_ascii=False)+'\n')
    REPORT.write_text('# QuantDinger — Jason US Swing $500 Real-Data Validation\n\n**Decision: REJECT / 今天不交易**\n\nResearch only; no IBKR, financing, leverage or live orders.\n\n## Fail-closed reason\n'+reason+(('\n\n'+detail) if detail else '')+'\n')
    print(json.dumps(payload,indent=2,ensure_ascii=False)); return payload


def load_real_pit():
    files=sorted(DATA.glob('*.parquet'))+sorted(DATA.glob('*.csv'))
    if not files: raise RuntimeError('No real point-in-time dataset found in data/jason_500_pit. Synthetic fallback is forbidden.')
    parts=[pd.read_parquet(p) if p.suffix=='.parquet' else pd.read_csv(p) for p in files]
    d=pd.concat(parts,ignore_index=True)
    missing=[c for c in REQUIRED if c not in d.columns]
    if missing: raise RuntimeError('Missing PIT fields: '+', '.join(missing))
    d['timestamp']=pd.to_datetime(d.timestamp,utc=True); d['earnings_ts']=pd.to_datetime(d.earnings_ts,utc=True,errors='coerce'); d['catalyst_ts']=pd.to_datetime(d.catalyst_ts,utc=True,errors='coerce')
    if (d.ask<d.bid).any() or (d.volume<=0).any(): raise RuntimeError('Invalid real spread/liquidity observations.')
    # Information timestamps must never be later backfilled into an earlier signal row.
    if ((d.earnings_ts.notna()) & (d.earnings_ts>d.timestamp)).any(): raise RuntimeError('Look-ahead detected in earnings timestamps.')
    if ((d.catalyst_ts.notna()) & (d.catalyst_ts>d.timestamp)).any(): raise RuntimeError('Look-ahead detected in catalyst timestamps.')
    return d.sort_values(['symbol','timestamp'])


def event_engine(close, ent, ex):
    r=[]; active=False; ep=0.
    for i,p in enumerate(close):
        if not active and bool(ent.iloc[i]): active=True; ep=float(p)
        elif active and bool(ex.iloc[i]): r.append(float(p)/ep-1); active=False
    return np.asarray(r,float)


def metrics(r):
    r=np.asarray(r,float); w=r[r>0]; l=r[r<0]; eq=np.cumprod(1+r) if len(r) else np.array([1.]); peak=np.maximum.accumulate(eq)
    return {'trades':int(len(r)),'expectancy':float(r.mean()) if len(r) else 0.,'profit_factor':float(w.sum()/abs(l.sum())) if len(l) and l.sum()!=0 else (999. if len(w) else 0.),'reward_risk':float(w.mean()/abs(l.mean())) if len(w) and len(l) else 0.,'max_drawdown':float(np.min(eq/peak-1)),'total_return':float(eq[-1]-1)}


def monte_carlo(r,paths=5000,seed=500):
    if len(r)<30:return {'paths':paths,'p05_total_return':-1.,'p95_max_drawdown':-1.}
    rng=np.random.default_rng(seed); totals=[]; dds=[]
    for _ in range(paths):
        s=rng.choice(r,len(r),replace=True); eq=np.cumprod(1+s); peak=np.maximum.accumulate(eq); totals.append(eq[-1]-1); dds.append(np.min(eq/peak-1))
    return {'paths':paths,'p05_total_return':float(np.quantile(totals,.05)),'p95_max_drawdown':float(np.quantile(dds,.05))}


def main():
    try:d=load_real_pit()
    except Exception as e:return fail_closed('REAL_PIT_DATA_UNAVAILABLE_OR_INVALID',str(e))
    all_q=[]; all_v=[]
    for symbol,g in d.groupby('symbol',sort=False):
        g=g.set_index('timestamp').copy(); g['spread_bps']=((g.ask-g.bid)/((g.ask+g.bid)/2)*10000).clip(lower=0); g['catalyst']=g.catalyst_ts.notna(); g['earnings']=g.earnings_ts.notna(); g['major_news']=g.catalyst
        b=pd.Series(g.market_close.values,index=g.index); s=pd.Series(g.sector_close.values,index=g.index)
        x=features(g,b,s); ent=entry_mask(x); ex=exits(x,ent); q=event_engine(x.close,ent,ex); all_q.extend(q.tolist())
        pf=vbt.Portfolio.from_signals(x.close,entries=ent,exits=ex,init_cash=CFG.capital,fees=.001,slippage=.0005,freq='1D'); all_v.extend(np.asarray(pf.trades.records_readable['Return']).tolist() if pf.trades.count() else [])
    q=np.asarray(all_q); vb=np.asarray(all_v); cut=int(len(q)*.70); test=q[cut:]; m=metrics(test)
    folds=[metrics(z) for z in np.array_split(test,4)]; mc=monte_carlo(test); delta=abs(metrics(q)['total_return']-metrics(vb)['total_return']) if len(vb) else 999.
    gates={'expectancy_gt_0':m['expectancy']>0,'profit_factor_gt_1_2':m['profit_factor']>1.2,'reward_risk_gte_1_8':m['reward_risk']>=1.8,'sample_sufficient':m['trades']>=30,'max_drawdown_ok':m['max_drawdown']>=-.15,'walk_forward_stable':sum(f['expectancy']>0 for f in folds)>=3,'monte_carlo_ok':mc['p05_total_return']>-.10,'cross_engine_consistent':delta<.05}
    ok=all(gates.values()); payload={'strategy':'Jason US Swing 500','mode':'research_only','capital_usd':500,'margin':False,'leverage':False,'holding_days':'1-10','preferred_efficiency_days':'1-5','broker_connected':False,'live_orders':False,'data_mode':'point_in_time_real','synthetic_allowed':False,'qualification':'PASS' if ok else 'REJECT','trade_decision':'RESEARCH_CANDIDATES_ONLY' if ok else 'NO_TRADE','today':'仅研究候选，不自动交易' if ok else '今天不交易','independent_test':m,'walk_forward':folds,'vectorbt':metrics(vb),'event_driven':metrics(q),'engine_total_return_delta':delta,'monte_carlo':mc,'gates':gates}
    RESULT.write_text(json.dumps(payload,indent=2,ensure_ascii=False)+'\n'); REPORT.write_text('# QuantDinger — Jason US Swing $500 Real-Data Validation\n\n**'+payload['qualification']+' — '+payload['today']+'**\n\nNo IBKR/broker connection; no financing, leverage or live orders.\n\n```json\n'+json.dumps(payload,indent=2,ensure_ascii=False)+'\n```\n'); print(json.dumps(payload,indent=2,ensure_ascii=False)); return payload

if __name__=='__main__': main()
