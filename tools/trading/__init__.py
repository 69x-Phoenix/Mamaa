"""Trading tools for the agent: deterministic calculators, risk checks and a persistent trade journal.

Everything here is educational maths on numbers the user supplies. There is no exchange connection,
no order placement and no financial advice.
"""
from __future__ import annotations

from typing import Any, Callable

from tools.registry import Permission, ToolError, ToolSpec
from tools.trading import calculators as calc
from tools.trading import risk
from tools.trading.calculators import InputError, num, rnd, side_of

TRADING_TOOL_NAMES = frozenset({
    "position_size", "risk_reward", "liquidation_estimate", "pnl_calculator", "portfolio_risk",
    "daily_limit_check", "trade_stats", "journal_add", "journal_list", "journal_stats", "journal_delete",
})


def _wrap(fn: Callable[..., dict[str, Any]]) -> Callable[..., dict[str, Any]]:
    def tool(**kwargs: Any) -> dict[str, Any]:
        try:
            return fn(**kwargs)
        except InputError as exc:
            raise ToolError(str(exc)) from None

    return tool


def _prop(kind: str, text: str, **extra: Any) -> dict[str, Any]:
    return {"type": kind, "description": text, **extra}


SIDE = _prop("string", "'long' or 'short'", enum=["long", "short"])
BDT = _prop("number", "Optional: how many BDT per 1 USD. Ask the user for the rate or look it up; never guess it")


def make_trading_tools(memory: Any = None) -> list[ToolSpec]:
    """Calculators and risk tools always; journal tools only when a Memory object is given."""

    def spec(name: str, description: str, properties: dict[str, Any], required: list[str], func: Callable[..., Any],
             permission: Permission = Permission.READ_ONLY) -> ToolSpec:
        return ToolSpec(name, description, {"type": "object", "properties": properties, "required": required},
                        _wrap(func), permission, 20)

    tools = [
        spec("position_size",
             "Position size for a futures trade: how many units keep the loss at the stop loss equal to the chosen risk. "
             "Also gives required margin, liquidation estimate, RRR, fees and warnings. ALWAYS use this for position sizing; never calculate it yourself. "
             "Give exactly one of risk_percent or risk_amount.",
             {"account_balance": _prop("number", "Account balance in USDT"), "entry": _prop("number", "Entry price"),
              "stop_loss": _prop("number", "Stop loss price"), "side": SIDE,
              "risk_percent": _prop("number", "Percent of the balance to risk, e.g. 1"),
              "risk_amount": _prop("number", "Money to risk in USDT"), "take_profit": _prop("number", "Optional take profit price"),
              "leverage": _prop("number", "Optional leverage, e.g. 10"), "fee_percent": _prop("number", "Trading fee in percent per side, e.g. 0.05"),
              "maintenance_margin_percent": _prop("number", "Maintenance margin percent (default 0.5; it differs by exchange)"),
              "usd_to_bdt": BDT},
             ["account_balance", "entry", "stop_loss", "side"], calc.position_size),
        spec("risk_reward",
             "Risk-to-reward ratio, break-even win rate and (with a win rate) expectancy for a planned trade.",
             {"entry": _prop("number", "Entry price"), "stop_loss": _prop("number", "Stop loss price"),
              "take_profit": _prop("number", "Take profit price"), "side": SIDE,
              "win_rate_percent": _prop("number", "Optional expected win rate in percent")},
             ["entry", "stop_loss", "take_profit", "side"], calc.risk_reward),
        spec("liquidation_estimate",
             "Estimated liquidation price and its distance for an isolated-margin futures position, and whether the stop loss comes first.",
             {"side": SIDE, "entry": _prop("number", "Entry price"), "leverage": _prop("number", "Leverage, e.g. 20"),
              "maintenance_margin_percent": _prop("number", "Maintenance margin percent (default 0.5)"),
              "stop_loss": _prop("number", "Optional stop loss price")},
             ["side", "entry", "leverage"], calc.liquidation_estimate),
        spec("pnl_calculator",
             "Gross and net profit or loss of a futures trade including fees and funding. Give size (units) or notional or margin with leverage.",
             {"side": SIDE, "entry": _prop("number", "Entry price"), "exit_price": _prop("number", "Exit price"),
              "size": _prop("number", "Position size in units (coins)"), "notional": _prop("number", "Position value in USDT"),
              "margin": _prop("number", "Margin used in USDT (needs leverage)"), "leverage": _prop("number", "Leverage"),
              "fee_percent": _prop("number", "Fee percent per side"), "exit_fee_percent": _prop("number", "Exit fee percent if different"),
              "funding_rate_percent": _prop("number", "Funding rate percent per interval (positive: longs pay shorts)"),
              "funding_intervals": _prop("number", "How many funding intervals the trade was open"), "usd_to_bdt": BDT},
             ["side", "entry", "exit_price"], calc.pnl_calculator),
        spec("portfolio_risk",
             "Total risk, exposure and warnings across several open trades.",
             {"account_balance": _prop("number", "Account balance in USDT"),
              "trades": {"type": "array", "description": "Open trades (max 50)", "items": {"type": "object", "properties": {
                  "symbol": {"type": "string"}, "side": SIDE, "entry": {"type": "number"}, "stop_loss": {"type": "number"},
                  "size": {"type": "number", "description": "Units"}, "notional": {"type": "number", "description": "Position value in USDT"}},
                  "required": ["side", "entry", "stop_loss"]}},
              "max_total_risk_percent": _prop("number", "Optional limit for the total risk in percent")},
             ["account_balance", "trades"], risk.portfolio_risk),
        spec("daily_limit_check",
             "Checks today's losses against the user's own daily loss limit and whether a planned trade would breach it. Give exactly one of the two limit fields.",
             {"account_balance": _prop("number", "Account balance in USDT"), "loss_today": _prop("number", "Money lost so far today (positive number)"),
              "daily_loss_limit_percent": _prop("number", "Daily loss limit in percent of the balance"),
              "daily_loss_limit_amount": _prop("number", "Daily loss limit in USDT"),
              "planned_trade_risk": _prop("number", "Optional: money the next trade would risk")},
             ["account_balance", "loss_today"], risk.daily_limit_check),
        spec("trade_stats",
             "Win rate, average win and loss, expectancy, profit factor, max drawdown and losing streak from a list of trade results (R multiples or money).",
             {"results": {"type": "array", "description": "Results per trade, e.g. [2, -1, 3.5]", "items": {"type": "number"}},
              "unit": _prop("string", "'R' or a currency label (default R)"),
              "starting_balance": _prop("number", "Optional starting balance for the drawdown percent")},
             ["results"], risk.trade_stats),
    ]
    if memory is not None:
        tools += _journal_tools(memory, spec)
    return tools


def _journal_tools(memory: Any, spec: Callable[..., ToolSpec]) -> list[ToolSpec]:
    def journal_add(*, symbol: Any, side: Any, entry: Any, exit_price: Any = None, stop_loss: Any = None,
                    take_profit: Any = None, size: Any = None, pnl: Any = None, notes: Any = "") -> dict[str, Any]:
        side_v = side_of(side)
        entry_p = num(entry, "entry", positive=True)
        exit_p = num(exit_price, "exit_price", positive=True, required=False)
        sl = num(stop_loss, "stop_loss", positive=True, required=False)
        tp = num(take_profit, "take_profit", positive=True, required=False)
        units = num(size, "size", positive=True, required=False)
        result = num(pnl, "pnl", required=False)
        calc.check_levels(side_v, entry_p, sl, tp)
        name = str(symbol or "").strip().upper()[:30]
        if not name:
            raise InputError("symbol is required")
        risk_amount = units * abs(entry_p - sl) if units and sl else None
        gross_note = ""
        if result is None and exit_p is not None and units:
            result = (exit_p - entry_p) * units if side_v == "long" else (entry_p - exit_p) * units
            gross_note = " (gross, before fees)"
        r_multiple = result / risk_amount if result is not None and risk_amount else None
        trade_id = memory.journal_add({
            "symbol": name, "side": side_v, "entry": entry_p, "exit_price": exit_p, "stop_loss": sl, "take_profit": tp,
            "size": units, "risk_amount": rnd(risk_amount, 4), "pnl": rnd(result, 4), "r_multiple": rnd(r_multiple, 4),
            "notes": str(notes or "")[:500]})
        return {"message": f"✅ Saved trade #{trade_id} ({name} {side_v}) to your journal"
                           + (f", result {rnd(result, 2)}{gross_note}" if result is not None else "") + ".",
                "trade_id": trade_id, "r_multiple": rnd(r_multiple, 3)}

    def journal_list(*, limit: Any = 20) -> dict[str, Any]:
        rows = memory.journal_list(int(num(limit, "limit", minimum=1, maximum=100)))
        return {"count": len(rows), "trades": rows}

    def journal_stats(*, unit: Any = "R", limit: Any = 500) -> dict[str, Any]:
        use_r = str(unit or "R").strip().upper() == "R"
        rows = memory.journal_list(int(num(limit, "limit", minimum=1, maximum=1000)))
        values = [r["r_multiple" if use_r else "pnl"] for r in rows if r.get("r_multiple" if use_r else "pnl") is not None]
        if not values:
            raise InputError("The journal has no trades with " + ("R multiples (they need size and stop loss)" if use_r else "PnL") + " yet")
        out = risk.trade_stats(results=list(reversed(values)), unit="R" if use_r else "USDT")
        out["trades_without_data_skipped"] = len(rows) - len(values)
        return out

    def journal_delete(*, trade_id: Any) -> dict[str, Any]:
        number = int(num(trade_id, "trade_id", positive=True))
        if not memory.journal_delete(number):
            raise InputError(f"No journal trade with id {number}")
        return {"message": f"🗑️ Deleted trade #{number} from your journal."}

    return [
        spec("journal_add",
             "Save a trade to the user's persistent trading journal (needs the user's approval). R multiple is worked out when size, stop loss and PnL are known.",
             {"symbol": _prop("string", "e.g. BTCUSDT"), "side": SIDE, "entry": _prop("number", "Entry price"),
              "exit_price": _prop("number", "Exit price if closed"), "stop_loss": _prop("number", "Stop loss"),
              "take_profit": _prop("number", "Take profit"), "size": _prop("number", "Units"),
              "pnl": _prop("number", "Net result in USDT if known"), "notes": _prop("string", "Short note: setup, mistake, lesson (max 500 characters)")},
             ["symbol", "side", "entry"], journal_add, Permission.SAFE_WRITE),
        spec("journal_list", "Show the most recent journal trades.",
             {"limit": _prop("integer", "How many trades, 1-100 (default 20)")}, [], journal_list),
        spec("journal_stats",
             "Performance statistics (win rate, average R, expectancy, drawdown) from the saved journal.",
             {"unit": _prop("string", "'R' (default) or 'USDT'"), "limit": _prop("integer", "How many recent trades to include (default 500)")},
             [], journal_stats),
        spec("journal_delete", "Delete one trade from the journal by id (needs the user's approval).",
             {"trade_id": _prop("integer", "Journal trade id")}, ["trade_id"], journal_delete, Permission.SAFE_WRITE),
    ]
