"""Cross-engine, walk-forward and Monte Carlo validation for Jason US Swing $500."""
from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np
import pandas as pd
import vectorbt as vbt
from jason_us_swing_500 import Jason500Config, features, entry_mask, exits

ROOT=Path(__file__).resolve().parents[2]
RESULT=ROOT/'QUANTDINGER_JASON_500_RESULT.json'
REPORT=ROOT/'QUANTDINGER_JASON_500_REPORT.md'
CFG=Jason500Config()


def fixture(n=1800, seed=500):
    """Deterministic OHLCV research fixture; CI proves plumbing, not profitability."""
    rng=np.random.default_rng(seed); idx=pd.bdate_range('2019-01-01', periods=n)
    regime=np.sin(np.arange(n)/55)*0.0015
    ret=0.00025+regime+rng.normal(0,0.018,n)
    close=35*np.exp(np.cumsum(ret)); open_=close*(1+rng.normal(0,0.004,n))
    high=np.maximum(open_,close)*(1+rng.uniform(.002,.018,n)); low=np.minimum(open_,close)*(1-rng.uniform(.002,.018,n))
    vol=rng.integers(900_000,3_500_000,n).astype(float)
    # inject tradable breakout/retest/confirmation sequences without encoding future returns
    catalyst=np.zeros(n,bool)
    for k in range(60,n-5,47):
        catalyst[k:k+4]=True; vol[k:k+4]*=2.2
        close[k]*=1.04; high[k]=max(high[k],close[k]*1.01)
        close[k+1]=close[k]*0.995; low[k+1]=min(low[k+1],close[k]*0.992); open_[k+1]=close[k+1]*.995
        close[k+2]=max(close[k+2],high[k+1]*1.012); high[k+2]=close[k+2]*1.008; open_[k+2]=close[k+2]*.99
    bench=pd.Series(100*np.exp(np.cumsum(rng.normal(.00018,.009,n))),idx)
    sector=pd.Series(80*np.exp(np.cumsum(rng.normal(.00020,.011,n))),idx)
    df=pd.DataFrame({'open':open_,'high':high,'low':low,'close':close,'volume':vol,'spread_bps':rng.uniform(3,28,n),'catalyst':catalyst,'major_news':False,'earnings':False},index=idx)
    return df,bench,sector


def event_engine(close, ent, ex):
    trades=[]; active=False; ep=0.; ei=0
    for i,p in enumerate(close):
        if not active and ent.iloc[i]: active=True; ep=float(p); ei=i
        elif active and ex.iloc[i]: trades.append((float(p)/ep)-1); active=False
    return np.array(trades)


def metrics(r):
    r=np.asarray(r,float); wins=r[r>0]; losses=r[r<0]
    pf=float(wins.sum()/abs(losses.sum())) if len(losses) and losses.sum()!=0 else (999. if len(wins) else 0.)
    exp=float(r.mean()) if len(r) else 0.; rr=float(wins.mean()/abs(losses.mean())) if len(wins) and len(losses) else 0.
    eq=np.cumprod(1+r) if len(r) else np.array([1.]); peak=np.maximum.accumulate(eq); dd=float(np.min(eq/peak-1))
    return {'trades':int(len(r)),'expectancy':exp,'profit_factor':pf,'reward_risk':rr,'max_drawdown':dd,'total_return':float(eq[-1]-1)}


def monte_carlo(r, paths=2000, seed=7):
    if len(r)<2: return {'paths':paths,'p05_total_return':-1.,'p95_max_drawdown':-1.}
    rng=np.random.default_rng(seed); totals=[]; dds=[]
    for _ in range(paths):
        s=rng.choice(r,len(r),replace=True); eq=np.cumprod(1+s); peak=np.maximum.accumulate(eq)
        totals.append(eq[-1]-1); dds.append(np.min(eq/peak-1))
    return {'paths':paths,'p05_total_return':float(np.quantile(totals,.05)),'p95_max_drawdown':float(np.quantile(dds,.05))}


def main():
    df,b,s=fixture(); x=features(df,b,s); ent=entry_mask(x); ex=exits(x,ent)
    # QuantDinger-equivalent event-driven execution (bar-by-bar, no lookahead).
    qd=event_engine(x.close,ent,ex)
    # VectorBT independent implementation using the exact same immutable signals.
    pf=vbt.Portfolio.from_signals(x.close,entries=ent,exits=ex,init_cash=CFG.capital,fees=.001,slippage=.0005,freq='1D')
    vb=np.asarray(pf.trades.records_readable['Return']) if pf.trades.count() else np.array([])
    split=int(len(x)*.70); test_mask=np.arange(len(x))>=split
    test=event_engine(x.close.iloc[split:],ent.iloc[split:],ex.iloc[split:])
    # Walk-forward: expanding 60% train, four chronological OOS folds; strategy parameters remain frozen.
    folds=[]
    for a in np.linspace(int(len(x)*.60),int(len(x)*.90),4,dtype=int):
        z=event_engine(x.close.iloc[a:a+int(len(x)*.10)],ent.iloc[a:a+int(len(x)*.10)],ex.iloc[a:a+int(len(x)*.10)])
        folds.append(metrics(z))
    m=metrics(test); mc=monte_carlo(test)
    engine_delta=abs(metrics(qd)['total_return']-metrics(vb)['total_return']) if len(vb) else 999.
    gates={'expectancy_gt_0':m['expectancy']>0,'profit_factor_gt_1_2':m['profit_factor']>1.2,'reward_risk_gte_1_8':m['reward_risk']>=1.8,'sample_sufficient':m['trades']>=30,'max_drawdown_ok':m['max_drawdown']>=-.20,'walk_forward_stable':sum(f['expectancy']>0 for f in folds)>=3,'monte_carlo_ok':mc['p05_total_return']>-.10,'cross_engine_consistent':engine_delta<.05}
    qualified=all(gates.values())
    result={'strategy':'Jason US Swing 500','mode':'research_only','capital_usd':500,'leverage':False,'broker_connected':False,'live_orders':False,'fixture_only':True,'qualification':'PASS' if qualified else 'REJECT','important':'CI uses deterministic synthetic OHLCV only; PASS cannot authorize live trading. Real point-in-time US equities + catalyst data is required before deployment.','engines':{'quantdinger_event_driven':metrics(qd),'vectorbt':metrics(vb),'total_return_delta':engine_delta},'independent_test':m,'walk_forward':folds,'monte_carlo':mc,'gates':gates}
    RESULT.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
    lines=['# QuantDinger — Jason US Swing $500 Validation Report','','**Research only. No IBKR/broker connection, leverage, financing, or live orders.**','','## Decision',f"**{result['qualification']}** — deterministic CI fixture. This is a software-validation result, not evidence of live-market edge.",'','## Required filters implemented','- Dollar liquidity + spread ceiling','- Catalyst flag and market/sector relative strength','- Volume confirmation + rolling VWAP','- Breakout → retest → second confirmation','- ATR volatility/profit-space gate and minimum 1.8R target','- Correlation penalty helper for existing holdings','- Major news/earnings first-wave + first-pullback cooldown ban','','## Independent test',f"- Trades: {m['trades']}",f"- Expectancy: {m['expectancy']:.4%}",f"- Profit Factor: {m['profit_factor']:.3f}",f"- Realized reward/risk: {m['reward_risk']:.3f}",f"- Max drawdown: {m['max_drawdown']:.2%}",'','## Validation stack','1. QuantDinger-equivalent bar-by-bar event-driven engine.','2. VectorBT independent portfolio engine with fees/slippage.','3. Four chronological walk-forward OOS folds.','4. 2,000-path bootstrap Monte Carlo.','5. Hard rejection gates: insufficient sample, OOS deterioration, drawdown, instability, or metric failure.','','## Data limitation','The committed CI run intentionally uses a deterministic synthetic fixture so it is reproducible and needs no paid/API credentials. **It must not be treated as deployable validation.** Before any paper/live use, rerun the same gates on survivorship-bias-aware, point-in-time U.S. equities data with real spreads, corporate actions, earnings and timestamped catalysts.']
    REPORT.write_text('\n'.join(lines)+'\n')
    print(json.dumps(result,indent=2))
    if not qualified: print('REJECTED by hard gates (expected behavior when evidence is insufficient).')

if __name__=='__main__': main()
