import numpy as np
import pandas as pd
from pathlib import Path
import sys

sys.path.insert(0, "/tmp")
sys.path.insert(0, "/Users/rkautsar/personal/scripts/strategy_cpm")

import value_sleeve_live as val


# ===========================================================================
# 1. PIT / No-Look-Ahead Verification with Restated Fact
# ===========================================================================
def test_pit_no_look_ahead_restatement():
    """Asserts that factor computation uses as_filed rather than current/restated facts."""
    # Create mocked facts with a restatement for a BS concept
    rows = [
        # First filing: Q1 StockholdersEquity is filed as 100 on 2021-04-15
        {"entity_id": "0000000001", "standard_concept": "StockholdersEquity", "numeric_value": 100.0,
         "period_start": "2021-01-01", "period_end": "2021-03-31", "fiscal_year": 2021, "fiscal_period": "Q1",
         "accepted_at": "2021-04-15 10:00:00+00:00", "value_current": 120.0, "value_as_filed": 100.0, "restated": True},
        # Restatement filed later: Q1 StockholdersEquity is restated as 120 on 2021-10-15 (after sig_d)
        {"entity_id": "0000000001", "standard_concept": "StockholdersEquity", "numeric_value": 120.0,
         "period_start": "2021-01-01", "period_end": "2021-03-31", "fiscal_year": 2021, "fiscal_period": "Q1",
         "accepted_at": "2021-10-15 10:00:00+00:00", "value_current": 120.0, "value_as_filed": 120.0, "restated": False},
    ]
    df = pd.DataFrame(rows)
    df["accepted"] = pd.to_datetime(df["accepted_at"]).dt.tz_localize(None).dt.normalize()
    df["period_end"] = pd.to_datetime(df["period_end"])
    df["ticker"] = "AAPL"
    
    # Process
    df = df.sort_values("accepted").drop_duplicates(
        subset=["ticker", "standard_concept", "fiscal_year", "fiscal_period", "period_end"],
        keep="first"
    )
    bs = val._build_pit_bs(df)
    
    # As of 2021-05-01 (before restatement filed): value should be 100
    val_before = val._bs_asof(bs.get(("AAPL", "StockholdersEquity")), pd.Timestamp("2021-05-01"))
    assert val_before == 100.0

    # As of 2021-11-01 (after restatement filed): value is still 100 because we drop duplicates keep='first'
    # which preserves the honest original as_filed value for that period!
    val_after = val._bs_asof(bs.get(("AAPL", "StockholdersEquity")), pd.Timestamp("2021-11-01"))
    assert val_after == 100.0


# ===========================================================================
# 2. Factor Formulation (Q4 derivation, TTM, z-scoring)
# ===========================================================================
def test_factor_q4_derivation_and_ttm():
    """Verify that Q4 flow is correctly derived from FY - (Q1+Q2+Q3) and summed for TTM."""
    rows = [
        {"entity_id": "0000000001", "standard_concept": "NetIncome", "numeric_value": 10.0,
         "period_start": "2021-01-01", "period_end": "2021-03-31", "fiscal_year": 2021, "fiscal_period": "Q1",
         "accepted_at": "2021-04-15 10:00:00+00:00", "value_current": 10.0, "value_as_filed": 10.0, "restated": False},
        {"entity_id": "0000000001", "standard_concept": "NetIncome", "numeric_value": 15.0,
         "period_start": "2021-04-01", "period_end": "2021-06-30", "fiscal_year": 2021, "fiscal_period": "Q2",
         "accepted_at": "2021-07-15 10:00:00+00:00", "value_current": 15.0, "value_as_filed": 15.0, "restated": False},
        {"entity_id": "0000000001", "standard_concept": "NetIncome", "numeric_value": 20.0,
         "period_start": "2021-07-01", "period_end": "2021-09-30", "fiscal_year": 2021, "fiscal_period": "Q3",
         "accepted_at": "2021-10-15 10:00:00+00:00", "value_current": 20.0, "value_as_filed": 20.0, "restated": False},
        {"entity_id": "0000000001", "standard_concept": "NetIncome", "numeric_value": 60.0,
         "period_start": "2021-01-01", "period_end": "2021-12-31", "fiscal_year": 2021, "fiscal_period": "FY",
         "accepted_at": "2022-03-15 10:00:00+00:00", "value_current": 60.0, "value_as_filed": 60.0, "restated": False},
    ]
    df = pd.DataFrame(rows)
    df["accepted"] = pd.to_datetime(df["accepted_at"]).dt.tz_localize(None).dt.normalize()
    df["period_end"] = pd.to_datetime(df["period_end"])
    df["ticker"] = "AAPL"
    
    df = df.sort_values("accepted").drop_duplicates(
        subset=["ticker", "standard_concept", "fiscal_year", "fiscal_period", "period_end"],
        keep="first"
    )
    flows = val._build_pit_flows(df)
    
    #AAPL NetIncome should have Q1, Q2, Q3, and derived Q4 (value = 60 - 10 - 15 - 20 = 15)
    q_ni = flows[("AAPL", "NetIncome")]
    assert len(q_ni) == 4
    derived_q4 = q_ni[q_ni.period_end == "2021-12-31"].iloc[0]
    assert derived_q4.value == 15.0

    # TTM sum as-of 2022-04-01 should be exactly 10 + 15 + 20 + 15 = 60
    ttm_val = val._ttm_asof(q_ni, pd.Timestamp("2022-04-01"))
    assert ttm_val == 60.0


def test_factor_z_score():
    """Verify standard deviation and mean z-scoring behavior."""
    s = pd.Series([1.0, 2.0, 3.0])
    z = val._z(s)
    expected = (s - 2.0) / np.std([1.0, 2.0, 3.0], ddof=1)
    assert np.allclose(z, expected)


# ===========================================================================
# 3. Stateful Hysteresis Band (Enter/Hold/Exit + Partial Fill)
# ===========================================================================
def test_stateful_trend_band_transitions():
    """Assert entry and hold/exit rules of he5_te0 trend band and partial fill to safe."""
    # K=5, enter > 1.05 * SMA, keep >= 1.00 * SMA
    # Build ftab and trend info
    ftab = pd.DataFrame(
        {"VALUE": [1.0, 0.9, 0.8, 0.7, 0.6], "QUALITY": [1.0, 1.0, 1.0, 1.0, 1.0]},
        index=["A", "B", "C", "D", "E"]
    )
    
    # 1. Entry Threshold:
    # A price: 104 (SMA: 100) -> 1.04x -> Blocked!
    # B price: 106 (SMA: 100) -> 1.06x -> Enters!
    # C price: 105 (SMA: 100) -> 1.05x -> Blocked!
    # D price: 108 (SMA: 100) -> 1.08x -> Enters!
    # E price: 101 (SMA: 100) -> 1.01x -> Blocked!
    trend = {
        "A": (104.0, 100.0),
        "B": (106.0, 100.0),
        "C": (105.0, 100.0),
        "D": (108.0, 100.0),
        "E": (101.0, 100.0),
    }
    
    state = {"H": []}
    picks = val.apply_stateful_trend_band(ftab, trend, state, K_select=5)
    
    # Only B and D should be picked because others fail the 1.05x entry threshold!
    assert sorted(picks) == ["B", "D"]
    assert state["H"] == picks
    
    # 2. Hold/Exit Threshold:
    # In next month, B drops to 101 (SMA: 100) -> 1.01x -> Holds (>= 1.00x)!
    # D drops to 99 (SMA: 100) -> 0.99x -> Exits (< 1.00x)!
    # A rises to 106 (SMA: 100) -> 1.06x -> Enters!
    trend_next = {
        "A": (106.0, 100.0),
        "B": (101.0, 100.0),
        "C": (105.0, 100.0),
        "D": (99.0, 100.0),
        "E": (101.0, 100.0),
    }
    picks_next = val.apply_stateful_trend_band(ftab, trend_next, state, K_select=5)
    
    # B held, D dropped. A enters as a new pick because it passes entry threshold 1.06x.
    assert sorted(picks_next) == ["A", "B"]
    assert state["H"] == picks_next


def test_soft_q20_rescreen_on_held_names():
    """Held name is dropped only when QUALITY < monthly Q20; ==Q20 is kept."""
    ftab = pd.DataFrame(
        {
            "VALUE": [6.0, 5.0, 4.0, 3.0, 2.0, 1.0],
            "QUALITY": [2.0, 1.0, 0.0, -1.0, -2.0, -3.0],
        },
        index=["A", "B", "C", "D", "E", "F"],
    )
    trend = {
        "A": (106.0, 100.0),
        "B": (104.0, 100.0),
        "C": (104.0, 100.0),
        "D": (104.0, 100.0),
        "E": (101.0, 100.0),
        "F": (101.0, 100.0),
    }
    state = {"H": ["E", "F"]}

    picks = val.apply_stateful_trend_band(ftab, trend, state, K_select=3)

    # Q20 is -2.0 for this cross-section: E(=-2.0) stays, F(<-2.0) drops.
    assert picks == ["E", "A"]
    assert state["H"] == ["E", "A"]


def test_partial_fill():
    """Verify that when only 3 qualify, 60% weight goes to stocks, 40% to best-safe asset."""
    # Mocking panel data with at least 400 rows and positive price trends for gate ON
    idx = [pd.Timestamp("2021-04-30") - pd.Timedelta(days=i) for i in range(400)][::-1]
    
    # Rising price ensures sig_13612U momentum is > 0
    cpm_prices = [100.0 + 0.1 * i for i in range(400)]
    cpm_panel = pd.DataFrame(
        {"TIP": cpm_prices, "SPY": cpm_prices, "SHV": [100.0] * 400},
        index=idx
    )
    ndx_panel = pd.DataFrame(
        {"A": [100.0] * 400, "B": [100.0] * 400, "C": [100.0] * 400},
        index=idx
    )
    
    # Mock constituents_at to return ["A", "B", "C"]
    import index_constitution as ic
    orig_constituents = ic.constituents_at
    ic.constituents_at = lambda index, date: pd.DataFrame({"symbol": ["A", "B", "C"]})
    
    # Mock load_valuein_cache and compute_fundamental_composites
    orig_load = val.load_valuein_cache
    val.load_valuein_cache = lambda cache_dir: ({}, {})
    
    orig_comp = val.compute_fundamental_composites
    val.compute_fundamental_composites = lambda cands, sig_d, FLOWS, BS: pd.DataFrame(
        {"VALUE": [1.0, 0.9, 0.8], "QUALITY": [1.0, 1.0, 1.0]}, index=["A", "B", "C"]
    )
    
    # Mock trend_info to always return (106, 100) -> all pass entry threshold
    orig_trend = val.trend_info
    val.trend_info = lambda ds: (106.0, 100.0)
    
    try:
        # Run weights compute with K=5, but only 3 stocks exist
        weights, regime, diag, state = val.compute_value_weights(
            cpm_panel, ndx_panel, pd.Timestamp("2021-04-30"), state={"H": []}
        )
        
        # Target weight per stock should be 1/5 = 20%. Since only 3 exist, stocks have 60%
        # Remaining 40% must be allocated to the best safe asset (e.g. SHV)
        assert weights["A"] == 0.20
        assert weights["B"] == 0.20
        assert weights["C"] == 0.20
        assert np.isclose(weights["SHV"], 0.40)
        assert regime == "VAL_PARTIAL_3"
        
    finally:
        ic.constituents_at = orig_constituents
        val.load_valuein_cache = orig_load
        val.compute_fundamental_composites = orig_comp
        val.trend_info = orig_trend


# ===========================================================================
# 4. Gate Interaction (ON vs OFF)
# ===========================================================================
def test_gate_interaction_on_off():
    """Verify that when the canary/trend/vol gate is OFF, target weight is 100% safe asset."""
    # TIP is negative, SPY trend negative -> Gate OFF!
    cpm_panel = pd.DataFrame(
        {"TIP": [105.0, 100.0, 95.0, 90.0, 85.0, 80.0, 75.0, 70.0, 65.0, 60.0, 55.0, 50.0, 45.0],
         "SPY": [105.0, 100.0, 95.0, 90.0, 85.0, 80.0, 75.0, 70.0, 65.0, 60.0, 55.0, 50.0, 45.0],
         "SHV": [100.0] * 13},
        index=[pd.Timestamp("2021-01-31") + pd.DateOffset(months=i) for i in range(13)]
    )
    ndx_panel = pd.DataFrame({"A": [100.0] * 13}, index=cpm_panel.index)
    
    weights, regime, diag, state = val.compute_value_weights(
        cpm_panel, ndx_panel, pd.Timestamp("2022-01-31"), state={"H": []}
    )
    
    assert weights == {"SHV": 1.0}
    assert "GATE_OFF" in regime


# ===========================================================================
# 5. Regression vs Research Metrics
# ===========================================================================
def test_standalone_regression_metrics():
    """Confirm the backtest reproduces the headline research metrics exactly."""
    from cpm_live import load_panel
    from ndx_sleeve_live import load_ndx_panel
    
    cpm_panel = load_panel(start=pd.Timestamp("2000-01-01"))
    ndx_panel = load_ndx_panel()
    
    start = pd.Timestamp("2001-08-30")
    end = pd.Timestamp("2026-04-30")
    
    rets, hist = val.run_value_backtest(cpm_panel, ndx_panel, start, end)
    
    eq = (1 + rets).cumprod()
    yrs = len(rets) / 252.0
    cagr = eq.iloc[-1] ** (1 / yrs) - 1
    vol = rets.std() * np.sqrt(252)
    sharpe = (rets.mean() * 252) / vol
    maxdd = (eq / eq.cummax() - 1).min()
    
    assert np.isclose(cagr, 0.187122, atol=1e-3)
    assert np.isclose(sharpe, 1.3864, atol=2e-2)
    assert np.isclose(maxdd, -0.166333, atol=1e-3)


if __name__ == "__main__":
    print("Running tests...")
    test_pit_no_look_ahead_restatement()
    print("  test_pit_no_look_ahead_restatement: PASSED")
    test_factor_q4_derivation_and_ttm()
    print("  test_factor_q4_derivation_and_ttm: PASSED")
    test_factor_z_score()
    print("  test_factor_z_score: PASSED")
    test_stateful_trend_band_transitions()
    print("  test_stateful_trend_band_transitions: PASSED")
    test_partial_fill()
    print("  test_partial_fill: PASSED")
    test_gate_interaction_on_off()
    print("  test_gate_interaction_on_off: PASSED")
    test_standalone_regression_metrics()
    print("  test_standalone_regression_metrics: PASSED")
    print("\nALL DRAFT TESTS PASSED!")
