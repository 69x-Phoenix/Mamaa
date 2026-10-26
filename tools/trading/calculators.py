"""Deterministic trading calculators for linear USDT-margined contracts.

Pure functions: no network, no files, no AI. Every number the assistant quotes about position size,
risk, liquidation or PnL should come from here, never from the model's head.
Educational maths only, not financial advice.
"""
from __future__ import annotations

import math
from typing import Any

NOTE = ("Educational calculation, not financial advice. Assumes a linear USDT-margined contract with isolated margin. "
        "Fees, margin tiers and liquidation formulas differ between exchanges, so check yours before trading.")
DEFAULT_MAINTENANCE_MARGIN_PERCENT = 0.5


class InputError(ValueError):
    """A clear, user-facing problem with the numbers supplied."""


def num(value: Any, name: str, *, positive: bool = False, minimum: float | None = None,
        maximum: float | None = None, required: bool = True) -> float | None:
    if value is None or value == "":
        if required:
            raise InputError(f"{name} is required")
        return None
    if isinstance(value, bool):
        raise InputError(f"{name} must be a number")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise InputError(f"{name} must be a number") from None
    if not math.isfinite(number):
        raise InputError(f"{name} must be a finite number")
    if positive and number <= 0:
        raise InputError(f"{name} must be greater than 0")
    if minimum is not None and number < minimum:
        raise InputError(f"{name} must be at least {minimum}")
    if maximum is not None and number > maximum:
        raise InputError(f"{name} must be at most {maximum}")
    return number


def side_of(value: Any) -> str:
    side = str(value or "").strip().lower()
    if side not in {"long", "short"}:
        raise InputError("side must be 'long' or 'short'")
    return side


def rnd(value: float | None, digits: int = 4) -> float | None:
    if value is None:
        return None
    return round(value, digits) + 0.0  # + 0.0 turns -0.0 into 0.0


def check_levels(side: str, entry: float, stop_loss: float | None, take_profit: float | None) -> None:
    if stop_loss is not None:
        if side == "long" and stop_loss >= entry:
            raise InputError("For a long trade the stop loss must be BELOW the entry price")
        if side == "short" and stop_loss <= entry:
            raise InputError("For a short trade the stop loss must be ABOVE the entry price")
    if take_profit is not None:
        if side == "long" and take_profit <= entry:
            raise InputError("For a long trade the take profit must be ABOVE the entry price")
        if side == "short" and take_profit >= entry:
            raise InputError("For a short trade the take profit must be BELOW the entry price")


def liquidation_price(side: str, entry: float, leverage: float, maintenance_margin_percent: float) -> float:
    """Simplified isolated-margin estimate; real exchanges add fees, tiers and funding."""
    mmr = maintenance_margin_percent / 100
    if mmr >= 1 / leverage:
        raise InputError("This leverage is too high for that maintenance margin: liquidation would be at the entry price")
    return entry * (1 - 1 / leverage + mmr) if side == "long" else entry * (1 + 1 / leverage - mmr)


def bdt_block(values: dict[str, float | None], rate: float | None) -> dict[str, Any] | None:
    if rate is None:
        return None
    out: dict[str, Any] = {f"{key}_bdt": rnd(v * rate, 2) for key, v in values.items() if v is not None}
    out["rate_used"] = f"1 USD = {rate} BDT (the rate you gave; not a live or P2P rate)"
    return out


def position_size(*, account_balance: Any, entry: Any, stop_loss: Any, side: Any, risk_percent: Any = None,
                  risk_amount: Any = None, take_profit: Any = None, leverage: Any = None, fee_percent: Any = 0,
                  maintenance_margin_percent: Any = DEFAULT_MAINTENANCE_MARGIN_PERCENT,
                  usd_to_bdt: Any = None) -> dict[str, Any]:
    """How large a position keeps the loss at the stop loss equal to the chosen risk."""
    balance = num(account_balance, "account_balance", positive=True)
    entry_p = num(entry, "entry", positive=True)
    sl = num(stop_loss, "stop_loss", positive=True)
    side_v = side_of(side)
    tp = num(take_profit, "take_profit", positive=True, required=False)
    lev = num(leverage, "leverage", minimum=1, maximum=1000, required=False)
    fee = num(fee_percent if fee_percent not in (None, "") else 0, "fee_percent", minimum=0, maximum=10)
    mmp = num(maintenance_margin_percent, "maintenance_margin_percent", positive=True, maximum=50)
    rate = num(usd_to_bdt, "usd_to_bdt", positive=True, required=False)
    risk_pct_in = num(risk_percent, "risk_percent", positive=True, maximum=100, required=False)
    risk_amt_in = num(risk_amount, "risk_amount", positive=True, required=False)
    if (risk_pct_in is None) == (risk_amt_in is None):
        raise InputError("Give exactly one of risk_percent or risk_amount")
    check_levels(side_v, entry_p, sl, tp)

    risk = risk_amt_in if risk_amt_in is not None else balance * risk_pct_in / 100
    distance = abs(entry_p - sl)
    fee_rate = fee / 100
    units = risk / (distance + fee_rate * (entry_p + sl))  # loss at the stop, fees included, equals the risk
    notional = units * entry_p
    fees_at_sl = units * fee_rate * (entry_p + sl)
    loss_at_sl = units * distance + fees_at_sl
    result: dict[str, Any] = {
        "side": side_v, "account_balance": rnd(balance, 2), "risk_amount": rnd(risk, 2),
        "risk_percent_of_balance": rnd(risk / balance * 100, 3), "entry": entry_p, "stop_loss": sl,
        "stop_distance": rnd(distance, 8), "stop_distance_percent": rnd(distance / entry_p * 100, 3),
        "position_size_units": rnd(units, 8), "position_value": rnd(notional, 2),
        "loss_at_stop_loss": rnd(loss_at_sl, 2), "fees_if_stopped_out": rnd(fees_at_sl, 4),
        "min_leverage_for_this_balance": rnd(notional / balance, 2),
    }
    warnings: list[str] = []
    money: dict[str, float | None] = {"risk_amount": risk, "position_value": notional, "loss_at_stop_loss": loss_at_sl}
    if tp is not None:
        reward_distance = abs(tp - entry_p)
        profit = units * reward_distance - units * fee_rate * (entry_p + tp)
        result.update({"take_profit": tp, "reward_to_risk_ratio": rnd(reward_distance / distance, 3),
                       "profit_at_take_profit": rnd(profit, 2), "net_reward_to_risk_after_fees": rnd(profit / loss_at_sl, 3)})
        money["profit_at_take_profit"] = profit
        if reward_distance / distance < 1:
            warnings.append("Reward is smaller than risk (RRR below 1): you need a high win rate for this to pay off.")
    if lev is not None:
        margin = notional / lev
        liq = liquidation_price(side_v, entry_p, lev, mmp)
        result.update({"leverage": lev, "required_margin": rnd(margin, 2), "estimated_liquidation_price": rnd(liq, 6),
                       "liquidation_distance_percent": rnd(abs(entry_p - liq) / entry_p * 100, 2)})
        money["required_margin"] = margin
        if margin > balance:
            warnings.append(f"The position needs {rnd(margin, 2)} margin but your balance is {rnd(balance, 2)}: raise leverage or reduce risk.")
        if (side_v == "long" and sl <= liq) or (side_v == "short" and sl >= liq):
            warnings.append("DANGER: the estimated liquidation price is hit BEFORE your stop loss. Lower the leverage or tighten the stop.")
    risk_share = risk / balance * 100
    if risk_share > 5:
        warnings.append(f"Risking {rnd(risk_share, 2)}% of the account on one trade is very high.")
    elif risk_share > 2:
        warnings.append(f"Risking {rnd(risk_share, 2)}% is above the common 1-2% per-trade guideline.")
    result["warnings"] = warnings
    result["assumptions"] = f"Maintenance margin {mmp}%, fee {fee}% per side. " + NOTE
    block = bdt_block(money, rate)
    if block:
        result["bdt"] = block
    return result


def risk_reward(*, entry: Any, stop_loss: Any, take_profit: Any, side: Any, win_rate_percent: Any = None) -> dict[str, Any]:
    entry_p = num(entry, "entry", positive=True)
    sl = num(stop_loss, "stop_loss", positive=True)
    tp = num(take_profit, "take_profit", positive=True)
    side_v = side_of(side)
    win = num(win_rate_percent, "win_rate_percent", minimum=0, maximum=100, required=False)
    check_levels(side_v, entry_p, sl, tp)
    risk_d, reward_d = abs(entry_p - sl), abs(tp - entry_p)
    ratio = reward_d / risk_d
    out: dict[str, Any] = {
        "side": side_v, "risk_per_unit": rnd(risk_d, 8), "reward_per_unit": rnd(reward_d, 8),
        "reward_to_risk_ratio": rnd(ratio, 3), "breakeven_win_rate_percent": rnd(100 / (1 + ratio), 2),
        "meaning": f"Each 1 risked aims to make {rnd(ratio, 2)}. Before fees you need to win more than "
                   f"{rnd(100 / (1 + ratio), 1)}% of such trades just to break even.",
    }
    if win is not None:
        p = win / 100
        out["expectancy_in_R"] = rnd(p * ratio - (1 - p), 3)
        out["expectancy_note"] = "Positive expectancy only holds if the stated win rate is real and the sample is large."
    out["note"] = NOTE
    return out


def liquidation_estimate(*, side: Any, entry: Any, leverage: Any, maintenance_margin_percent: Any = DEFAULT_MAINTENANCE_MARGIN_PERCENT,
                         stop_loss: Any = None) -> dict[str, Any]:
    side_v = side_of(side)
    entry_p = num(entry, "entry", positive=True)
    lev = num(leverage, "leverage", minimum=1, maximum=1000)
    mmp = num(maintenance_margin_percent, "maintenance_margin_percent", positive=True, maximum=50)
    sl = num(stop_loss, "stop_loss", positive=True, required=False)
    check_levels(side_v, entry_p, sl, None)
    liq = liquidation_price(side_v, entry_p, lev, mmp)
    out: dict[str, Any] = {"side": side_v, "entry": entry_p, "leverage": lev, "maintenance_margin_percent": mmp,
                           "estimated_liquidation_price": rnd(liq, 6),
                           "distance_to_liquidation_percent": rnd(abs(entry_p - liq) / entry_p * 100, 2), "warnings": []}
    if sl is not None:
        before = (side_v == "long" and sl <= liq) or (side_v == "short" and sl >= liq)
        out["stop_loss_is_hit_before_liquidation"] = not before
        if before:
            out["warnings"].append("DANGER: liquidation comes before the stop loss.")
    if out["distance_to_liquidation_percent"] < 5:
        out["warnings"].append("Liquidation is less than 5% away: normal price swings can wipe the position out.")
    out["note"] = "Estimate only. " + NOTE
    return out


def pnl_calculator(*, side: Any, entry: Any, exit_price: Any, size: Any = None, notional: Any = None, margin: Any = None,
                   leverage: Any = None, fee_percent: Any = 0, exit_fee_percent: Any = None,
                   funding_rate_percent: Any = 0, funding_intervals: Any = 0, usd_to_bdt: Any = None) -> dict[str, Any]:
    """Gross and net profit or loss, including trading fees and funding."""
    side_v = side_of(side)
    entry_p = num(entry, "entry", positive=True)
    exit_p = num(exit_price, "exit_price", positive=True)
    size_in = num(size, "size", positive=True, required=False)
    notional_in = num(notional, "notional", positive=True, required=False)
    margin_in = num(margin, "margin", positive=True, required=False)
    lev = num(leverage, "leverage", minimum=1, maximum=1000, required=False)
    fee_in = num(fee_percent if fee_percent not in (None, "") else 0, "fee_percent", minimum=0, maximum=10)
    fee_out = num(exit_fee_percent, "exit_fee_percent", minimum=0, maximum=10, required=False)
    fee_out = fee_in if fee_out is None else fee_out
    f_rate = num(funding_rate_percent if funding_rate_percent not in (None, "") else 0, "funding_rate_percent", minimum=-5, maximum=5)
    f_n = num(funding_intervals if funding_intervals not in (None, "") else 0, "funding_intervals", minimum=0, maximum=100000)
    rate = num(usd_to_bdt, "usd_to_bdt", positive=True, required=False)

    if size_in is not None:
        units = size_in
    elif notional_in is not None:
        units = notional_in / entry_p
    elif margin_in is not None and lev is not None:
        units = margin_in * lev / entry_p
    else:
        raise InputError("Give size (units), or notional, or margin together with leverage")
    position_value = units * entry_p
    gross = (exit_p - entry_p) * units if side_v == "long" else (entry_p - exit_p) * units
    fees = units * entry_p * fee_in / 100 + units * exit_p * fee_out / 100
    funding_cost = position_value * f_rate / 100 * f_n * (1 if side_v == "long" else -1)  # long pays when the rate is positive
    net = gross - fees - funding_cost
    move = (exit_p - entry_p) / entry_p * 100 * (1 if side_v == "long" else -1)
    result: dict[str, Any] = {
        "side": side_v, "size_units": rnd(units, 8), "position_value": rnd(position_value, 2),
        "price_move_in_your_favour_percent": rnd(move, 3), "gross_pnl": rnd(gross, 2), "trading_fees": rnd(fees, 4),
        "funding_cost": rnd(funding_cost, 4), "net_pnl": rnd(net, 2),
        "funding_note": "Positive funding_cost means you paid; negative means you received.",
    }
    used_margin = margin_in if margin_in is not None else (position_value / lev if lev else None)
    if used_margin:
        result["margin_used"] = rnd(used_margin, 2)
        result["net_roi_on_margin_percent"] = rnd(net / used_margin * 100, 2)
    result["note"] = NOTE
    block = bdt_block({"gross_pnl": gross, "trading_fees": fees, "net_pnl": net}, rate)
    if block:
        result["bdt"] = block
    return result
