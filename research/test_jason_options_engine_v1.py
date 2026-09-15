from jason_options_engine_v1 import build_debit_spreads, underlying_gate_ok, CFG


def _call(strike, bid, ask, delta, dte='2026-10-02T20:00:00Z', **extra):
    row={'symbol':'SPY','timestamp':'2026-09-15T15:00:00Z','expiration':dte,'option_type':'call','strike':strike,'bid':bid,'ask':ask,'delta':delta,'open_interest':1000,'volume':150,'underlying_price':660.0}
    row.update(extra); return row


def test_v2_capital_and_risk_defaults():
    assert CFG.capital_usd==1000.0
    assert CFG.default_max_risk_per_trade_usd==150.0
    assert CFG.absolute_max_risk_per_trade_usd==200.0
    assert CFG.portfolio_open_risk_cap_usd==350.0


def test_bull_call_is_defined_risk_cost_adjusted_and_research_only():
    chain=[_call(660,2.40,2.50,0.60),_call(665,1.60,1.70,0.35)]
    plans=build_debit_spreads(chain,'bull'); assert len(plans)==1; p=plans[0]
    assert p['strategy']=='BULL_CALL_DEBIT_SPREAD'
    assert p['max_loss_usd']<=CFG.default_max_risk_per_trade_usd
    assert p['reward_risk']>=1.8 and p['net_reward_risk']>=1.8
    assert p['estimated_round_trip_cost_usd']>0
    assert p['live_order'] is False


def test_a_plus_budget_is_hard_capped_at_200():
    plans=build_debit_spreads([_call(660,2.40,2.50,0.60),_call(665,1.60,1.70,0.35)],'bull',risk_budget_usd=999)
    assert plans and plans[0]['risk_budget_usd']==200.0 and plans[0]['max_loss_usd']<=200.0


def test_portfolio_open_risk_cap_blocks_new_trade():
    assert build_debit_spreads([_call(660,2.40,2.50,0.60),_call(665,1.60,1.70,0.35)],'bull',current_open_risk_usd=350)==[]


def test_zero_dte_is_rejected():
    assert build_debit_spreads([_call(660,2.40,2.50,0.60,'2026-09-15T20:00:00Z'),_call(665,1.60,1.70,0.35,'2026-09-15T20:00:00Z')],'bull')==[]


def test_wide_quote_is_rejected():
    assert build_debit_spreads([_call(660,1.00,2.00,0.60),_call(665,1.60,1.70,0.35)],'bull')==[]


def test_high_iv_rank_is_rejected_when_real_field_is_supplied():
    chain=[_call(660,2.40,2.50,0.60,iv_rank=90),_call(665,1.60,1.70,0.35,iv_rank=90)]
    assert build_debit_spreads(chain,'bull')==[]


def test_near_earnings_is_rejected_when_real_field_is_supplied():
    chain=[_call(660,2.40,2.50,0.60,days_to_earnings=2),_call(665,1.60,1.70,0.35,days_to_earnings=2)]
    assert build_debit_spreads(chain,'bull')==[]


def test_v2_1_ranking_uses_iv_greeks_liquidity_and_net_cost():
    chain=[_call(660,2.40,2.50,0.60,iv_rank=35,vega=.10,theta=-.03,open_interest=3000,volume=700),_call(665,1.60,1.70,0.35,iv_rank=35,vega=.05,theta=-.015,open_interest=3000,volume=700)]
    p=build_debit_spreads(chain,'bull')[0]
    assert 'ranking_score' in p and p['iv_rank_used']==35.0 and p['net_vega']>=0 and p['net_theta']>=0


def test_upstream_must_be_real_pit_pass():
    ok,why=underlying_gate_ok({'qualification':'REJECT','data_mode':'point_in_time_real','synthetic_allowed':False}); assert not ok and why=='UPSTREAM_MULTI_ENGINE_NOT_PASS'
    ok,why=underlying_gate_ok({'qualification':'PASS','hard_gates_passed':True,'data_mode':'synthetic','synthetic_allowed':True}); assert not ok and why=='UPSTREAM_REAL_PIT_NOT_VERIFIED'
