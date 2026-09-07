# QuantDinger — Jason US Swing $500 Validation Report

**Research only. No IBKR/broker connection, leverage, financing, or live orders.**

## Decision
**REJECT** — deterministic CI fixture. This is a software-validation result, not evidence of live-market edge.

## Required filters implemented
- Dollar liquidity + spread ceiling
- Catalyst flag and market/sector relative strength
- Volume confirmation + rolling VWAP
- Breakout → retest → second confirmation
- ATR volatility/profit-space gate and minimum 1.8R target
- Correlation penalty helper for existing holdings
- Major news/earnings first-wave + first-pullback cooldown ban

## Independent test
- Trades: 3
- Expectancy: -4.0829%
- Profit Factor: 0.000
- Realized reward/risk: 0.000
- Max drawdown: -7.43%

## Validation stack
1. QuantDinger-equivalent bar-by-bar event-driven engine.
2. VectorBT independent portfolio engine with fees/slippage.
3. Four chronological walk-forward OOS folds.
4. 2,000-path bootstrap Monte Carlo.
5. Hard rejection gates: insufficient sample, OOS deterioration, drawdown, instability, or metric failure.

## Data limitation
The committed CI run intentionally uses a deterministic synthetic fixture so it is reproducible and needs no paid/API credentials. **It must not be treated as deployable validation.** Before any paper/live use, rerun the same gates on survivorship-bias-aware, point-in-time U.S. equities data with real spreads, corporate actions, earnings and timestamped catalysts.
