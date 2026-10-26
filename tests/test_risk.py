import pytest

from tools.trading import risk
from tools.trading.calculators import InputError

TRADES = [{"symbol": "BTCUSDT", "side": "long", "entry": 100, "stop_loss": 95, "size": 2},
          {"symbol": "ETHUSDT", "side": "short", "entry": 50, "stop_loss": 55, "size": 4}]


def test_portfolio_risk_totals_and_warnings():
    r = risk.portfolio_risk(account_balance=1000, trades=TRADES)
    assert r["total_risk_amount"] == 30.0 and r["total_risk_percent_of_balance"] == 3.0
    assert r["total_position_value"] == 400.0 and r["net_exposure_long_minus_short"] == 0.0 and r["effective_leverage"] == 0.4
    assert any("More than half" in w and "ETHUSDT" in w for w in r["warnings"])
    assert any("both long and short" in w for w in r["warnings"])
    limited = risk.portfolio_risk(account_balance=1000, trades=TRADES, max_total_risk_percent=2)
    assert any("above 2.0%" in w for w in limited["warnings"])
    big = risk.portfolio_risk(account_balance=100, trades=[{"side": "long", "entry": 100, "stop_loss": 90, "size": 5}])
    assert any("above 5.0%" in w and "guideline" in w for w in big["warnings"])


def test_portfolio_risk_accepts_notional_and_rejects_bad_trades():
    r = risk.portfolio_risk(account_balance=1000, trades=[{"side": "long", "entry": 100, "stop_loss": 90, "notional": 500}])
    assert r["total_risk_amount"] == 50.0
    for trades, text in [([], "at least one"), ([{"side": "long", "entry": 100, "stop_loss": 105, "size": 1}], "BELOW"),
                         ([{"side": "long", "entry": 100, "stop_loss": 95}], "size"), (["x"], "object"),
                         ([TRADES[0]] * 51, "At most")]:
        with pytest.raises(InputError, match=text):
            risk.portfolio_risk(account_balance=1000, trades=trades)


def test_daily_limit_states():
    ok = risk.daily_limit_check(account_balance=1000, loss_today=5, daily_loss_limit_percent=3, planned_trade_risk=10)
    assert ok["status"] == "within_limit" and ok["remaining_allowance"] == 25.0 and ok["daily_limit"] == 30.0
    breach = risk.daily_limit_check(account_balance=1000, loss_today=20, daily_loss_limit_percent=3, planned_trade_risk=15)
    assert breach["status"] == "would_breach_limit" and "at most 10.0" in breach["message"]
    done = risk.daily_limit_check(account_balance=1000, loss_today=30, daily_loss_limit_amount=30)
    assert done["status"] == "limit_reached" and done["remaining_allowance"] == 0.0
    for kwargs in [dict(), dict(daily_loss_limit_percent=3, daily_loss_limit_amount=30)]:
        with pytest.raises(InputError, match="exactly one"):
            risk.daily_limit_check(account_balance=1000, loss_today=0, **kwargs)


def test_trade_stats_with_known_values():
    r = risk.trade_stats(results=[2, -1, -1, 3, -1])
    assert r["win_rate_percent"] == 40.0 and r["average_win"] == 2.5 and r["average_loss"] == -1.0
    assert r["payoff_ratio"] == 2.5 and r["profit_factor"] == 1.667 and r["expectancy_per_trade"] == 0.4
    assert r["max_drawdown"] == 2.0 and r["longest_losing_streak"] == 2 and r["total_result"] == 2.0
    assert any("not reliable" in w for w in r["warnings"])


def test_trade_stats_drawdown_percent_edge_cases_and_limits():
    r = risk.trade_stats(results=[100, -50, 20, -30], unit="USDT", starting_balance=1000)
    assert r["max_drawdown"] == 60.0 and r["max_drawdown_percent_of_peak_equity"] == pytest.approx(5.45, abs=0.01)
    only_wins = risk.trade_stats(results=[1, 2])
    assert only_wins["profit_factor"] is None and only_wins["payoff_ratio"] is None and only_wins["longest_losing_streak"] == 0
    assert not any("not reliable" in w for w in risk.trade_stats(results=[1, -1] * 20)["warnings"])
    for bad in ([], ["a"], [float("inf")], list(range(5001))):
        with pytest.raises(InputError):
            risk.trade_stats(results=bad)
