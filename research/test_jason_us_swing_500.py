from jason_us_swing_500 import eligible, metrics, hard_gate

def test_event_first_wave_is_blocked():
    row=dict(price=20,dollar_volume=50_000_000,spread_bps=10,sessions_since_major_event=0,
             second_confirmation=True,atr_upside_rr=2,catalyst_score=1,market_rs=1,sector_rs=1,
             volume_price_score=1,vwap_score=1,retest_score=1)
    ok,_,why=eligible(row)
    assert not ok and 'event_chase_cooldown' in why

def test_requires_second_confirmation():
    row=dict(price=20,dollar_volume=50_000_000,spread_bps=10,sessions_since_major_event=5,
             second_confirmation=False,atr_upside_rr=2)
    assert eligible(row)[0] is False

def test_gate_rejects_weak_test():
    m=metrics([.01,-.02]*20)
    ok,why=hard_gate(m,True,True,True)
    assert not ok and ('expectancy_not_positive' in why or 'profit_factor_le_1.2' in why)
