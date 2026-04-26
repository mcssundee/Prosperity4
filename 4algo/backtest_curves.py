"""
Run all three isolated trader files and plot per-timestamp PnL curves.
Usage: python3 4algo/backtest_curves.py
"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'utils'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backtesting'))
os.chdir(os.path.join(os.path.dirname(__file__), '..'))

from local_backtest import run_day, load_prices
import io, contextlib
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import importlib.util

ROUND = 4
DAYS  = [1, 2, 3]
DAY_OFFSETS = {1: 0, 2: 1_000_000, 3: 2_000_000}

TRADERS = {
    'HYDROGEL_PACK':        '4algo/trader_hydrogel.py',
    'VELVETFRUIT_EXTRACT':  '4algo/trader_velvetfruit.py',
    'VEV Options':          '4algo/trader_options.py',
}
COLOURS = {
    'HYDROGEL_PACK':       '#2ecc71',
    'VELVETFRUIT_EXTRACT': '#7c9ef5',
    'VEV Options':         '#f1c40f',
}


def load_trader(path):
    spec = importlib.util.spec_from_file_location("trader", path)
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.Trader()


def run_trader(trader_path):
    """Returns list of (global_timestamp, realized_pnl, mtm_pnl, total_pnl)."""
    curve   = []
    td      = ""
    pos     = {}
    cum_cash = 0.0

    for day in DAYS:
        offset = DAY_OFFSETS[day]
        trader = load_trader(trader_path)
        with contextlib.redirect_stdout(io.StringIO()):
            cash, mtm, pnl_log, td = run_day(
                trader, round_num=ROUND, day=day,
                positions=pos, trader_data=td if day > 1 else ""
            )

        # Build running cash + position from pnl_log, matched with price data
        price_data = load_prices(ROUND, day)
        all_ts = sorted(price_data.keys())

        running_cash = cum_cash
        running_pos  = dict(pos)  # position at start of day
        fill_idx     = 0
        log_sorted   = sorted(pnl_log, key=lambda x: x[0])

        for ts in all_ts:
            # Apply all fills at this timestamp
            while fill_idx < len(log_sorted) and log_sorted[fill_idx][0] == ts:
                _, sym, px, qty, delta = log_sorted[fill_idx]
                running_cash += delta
                running_pos[sym] = running_pos.get(sym, 0) + qty
                fill_idx += 1

            # Compute MTM at this timestamp
            mtm_now = 0.0
            for sym, p in running_pos.items():
                if p == 0:
                    continue
                if sym in price_data[ts]:
                    od, mid = price_data[ts][sym]
                    if mid is not None:
                        mtm_now += p * mid

            curve.append((ts + offset, running_cash, mtm_now, running_cash + mtm_now))

        # Carry cash and positions into next day
        cum_cash = running_cash
        pos = {k: v for k, v in running_pos.items() if v != 0}

    return curve


print("Running backtests...")
results = {}
for name, path in TRADERS.items():
    print(f"  {name}...")
    results[name] = run_trader(path)
    d = results[name]
    final = d[-1][3] if d else 0
    print(f"    Final PnL: {final:,.0f}")

# ---- Plot ----
fig = make_subplots(
    rows=3, cols=1,
    shared_xaxes=True,
    subplot_titles=list(TRADERS.keys()),
    vertical_spacing=0.08,
)

for i, (name, curve) in enumerate(results.items(), start=1):
    ts    = [c[0] for c in curve]
    total = [c[3] for c in curve]
    real  = [c[1] for c in curve]
    mtm   = [c[2] for c in curve]
    col   = COLOURS[name]

    fig.add_trace(go.Scatter(
        x=ts, y=total, mode='lines',
        line=dict(color=col, width=2),
        name=f'{name} total',
        hovertemplate='%{x}<br>Total PnL: %{y:,.0f}<extra></extra>',
    ), row=i, col=1)
    fig.add_trace(go.Scatter(
        x=ts, y=real, mode='lines',
        line=dict(color=col, width=1, dash='dot'),
        name=f'{name} realized',
        hovertemplate='Realized: %{y:,.0f}<extra></extra>',
    ), row=i, col=1)
    fig.add_hline(y=0, line=dict(color='#444', dash='dot', width=1), row=i, col=1)

    # Day boundary lines
    for off in [1_000_000, 2_000_000]:
        fig.add_vline(x=off, line=dict(color='#555', dash='dot', width=1), row=i, col=1)

fig.update_layout(
    paper_bgcolor='#0d1117', plot_bgcolor='#161b22',
    font=dict(color='#aaaaaa', family='monospace'),
    title=dict(text='Backtest PnL curves — solid=total (realized+MTM)  dotted=realized only',
               font=dict(color='#00e5ff', size=13)),
    legend=dict(bgcolor='#161b22', bordercolor='#30363d', font=dict(size=10)),
    margin=dict(l=60, r=20, t=60, b=40),
    hovermode='x unified',
    height=900,
)
fig.update_xaxes(gridcolor='#1f1f1f', zerolinecolor='#30363d')
fig.update_yaxes(gridcolor='#1f1f1f', zerolinecolor='#30363d', title_text='PnL')
fig.update_annotations(font_color='#00e5ff', font_size=11)

out = os.path.join(os.path.dirname(__file__), 'backtest_curves.html')
fig.write_html(out)
print(f"\nSaved to {out}")

import webbrowser
webbrowser.open(f'file://{os.path.abspath(out)}')
