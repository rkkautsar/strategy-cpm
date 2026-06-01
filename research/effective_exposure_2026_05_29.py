
import sys
sys.path.insert(0, '/Users/rkautsar/personal/scripts/strategy_cpm')
import os
import pandas as pd
import numpy as np
import cpm_live
from bull_spy_live import compute_bull_spy_weights
from ndx_sleeve_live import compute_ndx_weights, load_ndx_panel

panel = cpm_live.load_panel()
ndx_panel = load_ndx_panel()

monthly_idx = pd.DataFrame({'x': 1}, index=panel.index).groupby(pd.Grouper(freq='ME')).tail(1)
mask = (monthly_idx.index >= '2008-05-30') & (monthly_idx.index <= '2026-05-22')
sig_dates = monthly_idx.index[mask].tolist()

# Define universes and categories
ETF_UNIVERSE = {'SPY', 'QQQ', 'SPHQ', 'EFA', 'EEM', 'VNQ', 'GLD', 'TLT', 'DBC', 'SHV', 'IEF'}

# Top-7 mega-cap tech stocks
MEGA_CAP_TICKERS = {'AAPL', 'MSFT', 'AMZN', 'NVDA', 'GOOGL', 'GOOG', 'META', 'TSLA'}

results = []

for sd in sig_dates:
    cpm_w, _, _, _ = cpm_live.compute_target_weights(panel, sd)
    bull_w, _, _ = compute_bull_spy_weights(panel, sd)
    ndx_w, _, _ = compute_ndx_weights(panel, ndx_panel, sd)
    
    # Portfolio combined weights
    port_w = {}
    for t, w in cpm_w.items():
        port_w[t] = port_w.get(t, 0.0) + w * 0.60
    for t, w in bull_w.items():
        port_w[t] = port_w.get(t, 0.0) + w * 0.20
    for t, w in ndx_w.items():
        port_w[t] = port_w.get(t, 0.0) + w * 0.20
        
    # Sanity check: sum of weights
    w_sum = sum(port_w.values())
    
    # Bucketing
    us_equity = 0.0
    growth_nasdaq = 0.0
    duration_bonds = 0.0
    gold_commodity = 0.0
    intl_equity = 0.0
    real_estate = 0.0
    cash = 0.0
    
    single_stocks = {}
    
    for t, w in port_w.items():
        # Identify single stocks
        is_single_stock = t not in ETF_UNIVERSE
        if is_single_stock:
            single_stocks[t] = w
            
        # Bucketing
        # US equity % (SPY, QQQ, SPHQ, and NDX single-stock names all count as US equity)
        if t in {'SPY', 'QQQ', 'SPHQ'} or is_single_stock:
            us_equity += w
            
        # Growth/Nasdaq % (QQQ, SPHQ, NDX names)
        if t in {'QQQ', 'SPHQ'} or is_single_stock:
            growth_nasdaq += w
            
        # Duration/bonds % (TLT, IEF)
        if t in {'TLT', 'IEF'}:
            duration_bonds += w
            
        # Gold/commodity % (GLD, DBC)
        if t in {'GLD', 'DBC'}:
            gold_commodity += w
            
        # International equity % (EFA, EEM)
        if t in {'EFA', 'EEM'}:
            intl_equity += w
            
        # Real estate % (VNQ)
        if t in {'VNQ'}:
            real_estate += w
            
        # Cash % (SHV)
        if t in {'SHV'}:
            cash += w
            
    # Max single-stock weight
    raw_max_single = max(single_stocks.values()) if single_stocks else 0.0
    
    # Let's aggregate GOOG/GOOGL under 'GOOG_combined' to see if there's parent company concentration
    goog_combined_val = single_stocks.get('GOOG', 0.0) + single_stocks.get('GOOGL', 0.0)
    max_single_stock_parent = max(list(single_stocks.values()) + [goog_combined_val]) if single_stocks else 0.0
    
    # Mega-cap overlap approximation
    # Direct from NDX sleeve:
    direct_mega_cap = sum(w for t, w in single_stocks.items() if t in MEGA_CAP_TICKERS)
    # Indirect from ETFs:
    # QQQ has ~45% in top tech
    # SPHQ has ~30% in top tech
    # SPY has ~22% in top tech
    indirect_mega_cap = (
        port_w.get('QQQ', 0.0) * 0.45 +
        port_w.get('SPHQ', 0.0) * 0.30 +
        port_w.get('SPY', 0.0) * 0.22
    )
    mega_cap_total = direct_mega_cap + indirect_mega_cap
    
    results.append({
        'date': sd.strftime('%Y-%m-%d'),
        'w_sum': w_sum,
        'us_equity': us_equity,
        'growth_nasdaq': growth_nasdaq,
        'duration_bonds': duration_bonds,
        'gold_commodity': gold_commodity,
        'intl_equity': intl_equity,
        'real_estate': real_estate,
        'cash': cash,
        'max_single_stock': raw_max_single,
        'max_single_stock_parent': max_single_stock_parent,
        'mega_cap_total': mega_cap_total,
        'direct_mega_cap': direct_mega_cap,
        'indirect_mega_cap': indirect_mega_cap,
        'num_single_stocks': len(single_stocks),
        'single_stocks': list(single_stocks.keys())
    })

df = pd.DataFrame(results)

# Calculate statistics
buckets = ['us_equity', 'growth_nasdaq', 'duration_bonds', 'gold_commodity', 'intl_equity', 'real_estate', 'cash', 'max_single_stock', 'mega_cap_total']
stats = []
for b in buckets:
    avg_val = df[b].mean()
    max_val = df[b].max()
    stats.append({
        'bucket': b,
        'avg': avg_val,
        'max': max_val
    })
df_stats = pd.DataFrame(stats)
print("=== BUCKET STATISTICS (AVERAGE & MAX) ===")
print(df_stats.to_string(index=False, formatters={'avg': '{:,.2%}'.format, 'max': '{:,.2%}'.format}))

# Percentage of months exceeding key thresholds
thresholds = {
    'us_equity': 0.60,
    'growth_nasdaq': 0.50,
    'duration_bonds': 0.50,
    'gold_commodity': 0.30,
    'max_single_stock': 0.0399, # single stock > ~4%
    'max_single_stock_parent': 0.0799, # single stock parent > ~8%
    'mega_cap_total': 0.40 # combined mega cap > 40%
}

print("\n=== THRESHOLD EXCEEDANCE ===")
for b, thresh in thresholds.items():
    pct = (df[b] > thresh).mean()
    print(f"Bucket '{b}' exceeded {thresh:,.2%}: {pct:.2%}")

# Find most-concentrated month based on US Equity %
idx_max_us = df['us_equity'].idxmax()
row_max_us = df.iloc[idx_max_us]
print("\n=== MOST CONCENTRATED MONTH (BY US EQUITY) ===")
print(f"Date: {row_max_us['date']}")
for b in buckets:
    print(f"  {b}: {row_max_us[b]:.2%}")
print(f"  Single Stocks held: {row_max_us['single_stocks']}")

# Find worst-case mega-cap stacking month
idx_max_mega = df['mega_cap_total'].idxmax()
row_max_mega = df.iloc[idx_max_mega]
print("\n=== WORST-CASE MEGA-CAP STACKING MONTH ===")
print(f"Date: {row_max_mega['date']}")
for b in buckets:
    print(f"  {b}: {row_max_mega[b]:.2%}")
print(f"  Direct Mega-Cap: {row_max_mega['direct_mega_cap']:.2%}")
print(f"  Indirect Mega-Cap: {row_max_mega['indirect_mega_cap']:.2%}")
print(f"  Single Stocks held: {row_max_mega['single_stocks']}")
