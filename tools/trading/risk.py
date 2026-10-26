"""Account-level risk maths: several trades at once, daily loss limits and performance statistics."""
from __future__ import annotations

from typing import Any

from tools.trading.calculators import NOTE, InputError, check_levels, num, rnd, side_of

MAX_TRADES = 50
MAX_RESULTS = 5000


def portfolio_risk(*, account_balance: Any, trades: Any, max_total_risk_percent: Any = None) -> dict[str, Any]:
    """Total money at risk and exposure across several open trades."""
    balance = num(account_balance, "account_balance", positive=True)
    limit = num(max_total_risk_percent, "max_total_risk_percent", positive=True, maximum=100, required=False)
    if not isinstance(trades, (list, tuple)) or not trades:
        raise InputError("Provide at least one trade in 'trades'")
    if len(trades) > MAX_TRADES:
        raise InputError(f"At most {MAX_TRADES} trades at a time")
    rows: list[dict[str, Any]] = []
    total_risk = total_notional = long_notional = short_notional = 0.0
    for index, raw in enumerate(trades, start=1):
        if not isinstance(raw, dict):
            raise InputError(f"Trade {index} must be an object with side, entry, stop_loss and size")
        label = str(raw.get("symbol") or f"trade {index}")[:30]
        side = side_of(raw.get("side"))
        entry = num(raw.get("entry"), f"{label}: entry", positive=True)
        stop = num(raw.get("stop_loss"), f"{label}: stop_loss", positive=True)
        check_levels(side, entry, stop, None)
        size = num(raw.get("size"), f"{label}: size", positive=True, required=False)
        notional_in = num(raw.get("notional"), f"{label}: notional", positive=True, required=False)
        if size is None and notional_in is None:
            raise InputError(f"{label}: give size (units) or notional")
        units = size if size is not None else notional_in / entry
        notional = units * entry
        risk = units * abs(entry - stop)
        total_risk += risk
        total_notional += notional
        long_notional += notional if side == "long" else 0
        short_notional += notional if side == "short" else 0
        rows.append({"symbol": label, "side": side, "position_value": rnd(notional, 2), "risk_amount": rnd(risk, 2),
                     "risk_percent_of_balance": rnd(risk / balance * 100, 3)})
    warnings: list[str] = []
    total_pct = total_risk / balance * 100
    threshold = limit if limit is not None else 5.0
    if total_pct > threshold:
        warnings.append(f"Total risk {rnd(total_pct, 2)}% is above {threshold}%"
                        + ("" if limit is not None else " (a common upper guideline when no limit is given)") + ".")
    biggest = max(rows, key=lambda r: r["risk_amount"])
    if len(rows) > 1 and total_risk > 0 and biggest["risk_amount"] / total_risk > 0.5:
        warnings.append(f"More than half of the risk sits in one trade ({biggest['symbol']}).")
    if long_notional and short_notional:
        warnings.append("You hold both long and short positions; the net exposure below is what moves with the market.")
    effective = total_notional / balance
    if effective > 10:
        warnings.append(f"Effective leverage across all positions is {rnd(effective, 1)}x.")
    return {
        "trades": rows, "total_risk_amount": rnd(total_risk, 2), "total_risk_percent_of_balance": rnd(total_pct, 3),
        "total_position_value": rnd(total_notional, 2), "net_exposure_long_minus_short": rnd(long_notional - short_notional, 2),
        "effective_leverage": rnd(effective, 2), "warnings": warnings,
        "note": "Assumes every stop loss is hit and ignores correlation (many crypto assets fall together, so real risk can be higher). " + NOTE,
    }


def daily_limit_check(*, account_balance: Any, loss_today: Any, daily_loss_limit_percent: Any = None,
                      daily_loss_limit_amount: Any = None, planned_trade_risk: Any = None) -> dict[str, Any]:
    """Compare today's losses with your own daily loss limit."""
    balance = num(account_balance, "account_balance", positive=True)
    lost = num(loss_today, "loss_today", minimum=0)
    pct = num(daily_loss_limit_percent, "daily_loss_limit_percent", positive=True, maximum=100, required=False)
    amount = num(daily_loss_limit_amount, "daily_loss_limit_amount", positive=True, required=False)
    planned = num(planned_trade_risk, "planned_trade_risk", minimum=0, required=False)
    if (pct is None) == (amount is None):
        raise InputError("Give exactly one of daily_loss_limit_percent or daily_loss_limit_amount")
    limit = amount if amount is not None else balance * pct / 100
    remaining = max(limit - lost, 0.0)
    out: dict[str, Any] = {"daily_limit": rnd(limit, 2), "loss_today": rnd(lost, 2), "remaining_allowance": rnd(remaining, 2),
                           "limit_used_percent": rnd(lost / limit * 100, 1)}
    if lost >= limit:
        out["status"] = "limit_reached"
        out["message"] = "Your own daily loss limit is already reached. Your rule says no more trades today."
    elif planned is not None and planned > remaining:
        out["status"] = "would_breach_limit"
        out["message"] = f"This trade risks {rnd(planned, 2)} but only {rnd(remaining, 2)} is left. Reduce the size so the risk is at most {rnd(remaining, 2)}."
    else:
        out["status"] = "within_limit"
        out["message"] = "Within your daily loss limit."
    out["note"] = "The limit is the one you set yourself; this tool only checks the arithmetic."
    return out


def trade_stats(*, results: Any, unit: Any = "R", starting_balance: Any = None) -> dict[str, Any]:
    """Win rate, average win/loss, expectancy, profit factor and drawdown from a list of trade results."""
    if not isinstance(results, (list, tuple)) or not results:
        raise InputError("Provide a non-empty list of trade results")
    if len(results) > MAX_RESULTS:
        raise InputError(f"At most {MAX_RESULTS} results at a time")
    values = [num(v, f"results[{i}]") for i, v in enumerate(results)]
    start = num(starting_balance, "starting_balance", positive=True, required=False)
    unit_text = str(unit or "R")[:10]
    n = len(values)
    wins = [v for v in values if v > 0]
    losses = [v for v in values if v < 0]
    total = sum(values)
    equity = peak = 0.0
    max_dd = max_dd_pct = 0.0
    longest = current = 0
    for v in values:
        equity += v
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
        if start:
            peak_total = start + peak
            max_dd_pct = max(max_dd_pct, (peak - equity) / peak_total * 100 if peak_total > 0 else 0)
        current = current + 1 if v < 0 else 0
        longest = max(longest, current)
    avg_win = sum(wins) / len(wins) if wins else None
    avg_loss = sum(losses) / len(losses) if losses else None
    out: dict[str, Any] = {
        "trades": n, "unit": unit_text, "wins": len(wins), "losses": len(losses), "breakeven": n - len(wins) - len(losses),
        "win_rate_percent": rnd(len(wins) / n * 100, 2), "average_win": rnd(avg_win), "average_loss": rnd(avg_loss),
        "payoff_ratio": rnd(avg_win / abs(avg_loss), 3) if avg_win and avg_loss else None,
        "profit_factor": rnd(sum(wins) / abs(sum(losses)), 3) if losses else None,
        "expectancy_per_trade": rnd(total / n), "total_result": rnd(total), "best_trade": rnd(max(values)),
        "worst_trade": rnd(min(values)), "max_drawdown": rnd(max_dd), "longest_losing_streak": longest,
        "warnings": [],
    }
    if start:
        out["max_drawdown_percent_of_peak_equity"] = rnd(max_dd_pct, 2)
    if n < 30:
        out["warnings"].append(f"Only {n} trades: these statistics are not reliable yet (aim for 30 or more).")
    out["note"] = "Past results do not predict future results. " + NOTE
    return out
