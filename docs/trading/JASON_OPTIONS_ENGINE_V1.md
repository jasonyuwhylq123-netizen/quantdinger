# Jason Options Engine v2 — $1,000 experiment

Research-only options layer for the Jason US Swing $1,000 workflow. Legacy filenames are retained for compatibility.

## Design

The engine uses defined-risk vertical spreads and QuantDinger's fail-closed validation philosophy.

Initial structures:

- bullish signal: bull call debit spread
- bearish signal: bear put debit spread
- 7–30 DTE only
- no 0DTE
- no naked short options
- no margin/financing/leverage
- no broker connectivity or live-order path

## $1,000 risk rules

- total experiment capital: $1,000
- default maximum defined loss per spread position: $150
- explicit A+ risk budget hard ceiling: $200
- total portfolio open-risk ceiling: $350
- minimum planned reward/risk: 1.8
- conservative planned debit: long-leg ask minus short-leg bid
- minimum open interest per leg: 200
- minimum same-session contract volume per leg: 25
- maximum bid/ask width per leg: 15% of mid
- long-leg absolute delta: 0.45–0.70
- short-leg absolute delta: 0.20–0.45

The engine never automatically treats a setup as A+. Callers must explicitly request a higher risk budget, and the code still hard-caps it at $200 and enforces the $350 portfolio open-risk ceiling.

## Validation contract

`backend_api_python/scripts/validate_jason_options_500.py` fails closed unless all three layers exist:

1. Existing Jason US Swing upstream result is PASS on real point-in-time data and reports `capital_usd = 1000`.
2. Real timestamped option-chain snapshots exist under `data/jason_options_pit/`.
3. Independent option validation evidence exists at `data/jason_options_validation/multi_engine_results.json`.

The multi-engine evidence must show:

- at least 30 independent-test trades
- positive test expectancy
- Profit Factor > 1.2
- realized reward/risk >= 1.8
- test max drawdown <= 15%
- vectorized/event-driven total-return delta < 5 percentage points
- LEAN or equivalent event-driven verification explicitly marked verified
- at least 3 of 4 positive walk-forward OOS folds
- Monte Carlo >= 2,000 paths with 5th-percentile total return > -10%

If any layer is absent or invalid, output is `REJECT / NO_TRADE` and includes `未完成多引擎验证`. Synthetic data may be used for unit/plumbing tests only and can never authorize a candidate.

## Required option-chain fields

`symbol, timestamp, expiration, option_type, strike, bid, ask, delta, open_interest, volume, underlying_price, signal_direction`

`signal_direction` must be `bull` or `bear` and must originate from the already-validated upstream directional model. The validator selects at most three research candidates from the latest real snapshot.

## Safety boundary

The engine returns research plans only. It deliberately contains no IBKR order submission function and every candidate carries `live_order: false`.
