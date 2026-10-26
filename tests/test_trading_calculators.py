import math

import pytest

from tools.trading import calculators as c
from tools.trading.calculators import InputError


def sizing(**over):
    args = dict(account_balance=1000, risk_percent=1, entry=100, stop_loss=95, side="long")
    args.update(over)
    return c.position_size(**args)


def test_long_position_size_with_known_values():
    r = sizing(take_profit=110, leverage=10)
    assert r["risk_amount"] == 10.0 and r["position_size_units"] == 2.0 and r["position_value"] == 200.0
    assert r["required_margin"] == 20.0 and r["loss_at_stop_loss"] == 10.0
    assert r["reward_to_risk_ratio"] == 2.0 and r["profit_at_take_profit"] == 20.0
    assert r["estimated_liquidation_price"] == 90.5 and r["liquidation_distance_percent"] == 9.5
    assert r["warnings"] == [] and "not financial advice" in r["assumptions"]


def test_fees_are_included_so_the_loss_at_the_stop_equals_the_risk():
    r = sizing(fee_percent=0.05, take_profit=110)
    assert r["position_size_units"] == pytest.approx(1.96174595, rel=1e-6)
    assert r["loss_at_stop_loss"] == 10.0
    assert r["profit_at_take_profit"] == 19.41 and r["net_reward_to_risk_after_fees"] == pytest.approx(1.941)


def test_short_position_and_liquidation_before_the_stop_is_flagged():
    r = sizing(side="short", risk_percent=None, risk_amount=20, entry=100, stop_loss=105, take_profit=90, leverage=20)
    assert r["position_size_units"] == 4.0 and r["estimated_liquidation_price"] == 104.5
    assert any("BEFORE your stop loss" in w for w in r["warnings"])
    safe = sizing(side="short", entry=100, stop_loss=105, leverage=10)
    assert safe["estimated_liquidation_price"] == 109.5 and safe["warnings"] == []
    danger = sizing(leverage=25)  # long, liquidation 96.5 is above the stop at 95
    assert any("BEFORE your stop loss" in w for w in danger["warnings"])


def test_warnings_for_high_risk_small_rrr_and_missing_margin():
    assert any("above the common 1-2%" in w for w in sizing(risk_percent=3)["warnings"])
    assert any("very high" in w for w in sizing(risk_percent=6)["warnings"])
    assert any("smaller than risk" in w for w in sizing(take_profit=102)["warnings"])
    assert any("needs" in w and "margin" in w for w in sizing(account_balance=100, risk_percent=50, leverage=2)["warnings"])


def test_bdt_conversion_uses_only_the_rate_given():
    r = sizing(usd_to_bdt=120, take_profit=110)
    assert r["bdt"]["risk_amount_bdt"] == 1200.0 and r["bdt"]["profit_at_take_profit_bdt"] == 2400.0
    assert "not a live or P2P rate" in r["bdt"]["rate_used"]
    assert "bdt" not in sizing()


@pytest.mark.parametrize("over, text", [
    (dict(stop_loss=105), "BELOW the entry"),
    (dict(side="short"), "ABOVE the entry"),
    (dict(take_profit=90), "ABOVE the entry"),
    (dict(risk_amount=5), "exactly one"),
    (dict(risk_percent=None), "exactly one"),
    (dict(risk_percent=-1), "greater than 0"),
    (dict(account_balance=float("nan")), "finite"),
    (dict(account_balance="abc"), "must be a number"),
    (dict(entry=True), "must be a number"),
    (dict(side="up"), "long' or 'short"),
    (dict(leverage=0.5), "at least"),
    (dict(leverage=250), "too high"),
    (dict(stop_loss=100), "BELOW the entry"),
])
def test_bad_input_gives_a_clear_message(over, text):
    with pytest.raises(InputError, match=text):
        sizing(**over)


def test_risk_reward_and_expectancy():
    r = c.risk_reward(entry=100, stop_loss=95, take_profit=110, side="long", win_rate_percent=50)
    assert r["reward_to_risk_ratio"] == 2.0 and r["breakeven_win_rate_percent"] == 33.33 and r["expectancy_in_R"] == 0.5
    assert "expectancy_in_R" not in c.risk_reward(entry=100, stop_loss=105, take_profit=90, side="short")
    with pytest.raises(InputError):
        c.risk_reward(entry=100, stop_loss=95, take_profit=90, side="long")


def test_liquidation_estimate():
    r = c.liquidation_estimate(side="long", entry=100, leverage=10, stop_loss=91)
    assert r["estimated_liquidation_price"] == 90.5 and r["distance_to_liquidation_percent"] == 9.5
    assert r["stop_loss_is_hit_before_liquidation"] is True and r["warnings"] == []
    bad = c.liquidation_estimate(side="long", entry=100, leverage=10, stop_loss=90)
    assert bad["stop_loss_is_hit_before_liquidation"] is False and bad["warnings"]
    assert any("less than 5%" in w for w in c.liquidation_estimate(side="short", entry=100, leverage=50)["warnings"])


def test_pnl_with_fees_and_funding_for_both_sides():
    long = c.pnl_calculator(side="long", entry=100, exit_price=110, size=2, fee_percent=0.05, funding_rate_percent=0.01, funding_intervals=3)
    assert long["gross_pnl"] == 20.0 and long["trading_fees"] == 0.21 and long["funding_cost"] == 0.06 and long["net_pnl"] == 19.73
    short = c.pnl_calculator(side="short", entry=100, exit_price=110, size=2, fee_percent=0.05, funding_rate_percent=0.01, funding_intervals=3)
    assert short["gross_pnl"] == -20.0 and short["funding_cost"] == -0.06 and short["net_pnl"] == -20.15  # shorts receive positive funding
    by_margin = c.pnl_calculator(side="long", entry=100, exit_price=110, margin=20, leverage=10)
    assert by_margin["size_units"] == 2.0 and by_margin["net_roi_on_margin_percent"] == 100.0
    assert c.pnl_calculator(side="long", entry=100, exit_price=90, notional=200, usd_to_bdt=100)["bdt"]["net_pnl_bdt"] == -2000.0


def test_pnl_needs_a_position_size():
    with pytest.raises(InputError, match="size"):
        c.pnl_calculator(side="long", entry=100, exit_price=110)


def test_no_negative_zero_and_everything_is_finite():
    r = c.pnl_calculator(side="long", entry=100, exit_price=100, size=1)
    assert r["net_pnl"] == 0.0 and math.copysign(1, r["net_pnl"]) == 1.0
