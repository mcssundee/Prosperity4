import os
import pandas as pd
import numpy as np
import dash
from dash import dcc, html, dash_table
from dash.dependencies import Input, Output
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------
DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'round4')

tr_1 = pd.read_csv(os.path.join(DATA_DIR, 'trades_round_4_day_1.csv'), sep=';')
tr_2 = pd.read_csv(os.path.join(DATA_DIR, 'trades_round_4_day_2.csv'), sep=';')
tr_3 = pd.read_csv(os.path.join(DATA_DIR, 'trades_round_4_day_3.csv'), sep=';')
px_1 = pd.read_csv(os.path.join(DATA_DIR, 'prices_round_4_day_1.csv'), sep=';')
px_2 = pd.read_csv(os.path.join(DATA_DIR, 'prices_round_4_day_2.csv'), sep=';')
px_3 = pd.read_csv(os.path.join(DATA_DIR, 'prices_round_4_day_3.csv'), sep=';')

tr_1['timestamp'] += 0
tr_2['timestamp'] += 1_000_000
tr_3['timestamp'] += 2_000_000
px_1['timestamp'] += 0
px_2['timestamp'] += 1_000_000
px_3['timestamp'] += 2_000_000

tr_comb = pd.concat([tr_1, tr_2, tr_3], ignore_index=True).sort_values('timestamp').reset_index(drop=True)
px_comb = pd.concat([px_1, px_2, px_3], ignore_index=True).sort_values('timestamp').reset_index(drop=True)

ALL_PRODUCTS = {
    'VELVETFRUIT_EXTRACT', 'HYDROGEL_PACK',
    'VEV_4000', 'VEV_4500',
    'VEV_5000', 'VEV_5100', 'VEV_5200', 'VEV_5300',
    'VEV_5400', 'VEV_5500', 'VEV_6000', 'VEV_6500',
}

tr_all = tr_comb[tr_comb['symbol'].isin(ALL_PRODUCTS)].copy().reset_index(drop=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def popmid(df):
    df = df.copy()
    bid_prices = df[['bid_price_1', 'bid_price_2', 'bid_price_3']].values
    ask_prices = df[['ask_price_1', 'ask_price_2', 'ask_price_3']].values
    bid_vols_f = df[['bid_volume_1', 'bid_volume_2', 'bid_volume_3']].fillna(0).values
    ask_vols_f = df[['ask_volume_1', 'ask_volume_2', 'ask_volume_3']].fillna(0).values
    total_bid = bid_vols_f.sum(axis=1)
    total_ask = ask_vols_f.sum(axis=1)
    pop_bid = bid_prices[range(len(df)), bid_vols_f.argmax(axis=1)]
    pop_ask = ask_prices[range(len(df)), ask_vols_f.argmax(axis=1)]
    pop_bid = np.where(total_bid > 0, pop_bid, np.nan)
    pop_ask = np.where(total_ask > 0, pop_ask, np.nan)
    df['pop_mid'] = (pop_bid + pop_ask) / 2
    return df


px_dict = {}
for product in ALL_PRODUCTS:
    sub = px_comb[px_comb['product'] == product].copy().reset_index(drop=True)
    if len(sub):
        px_dict[product] = popmid(sub)

px_spot = px_dict['VELVETFRUIT_EXTRACT']


def trader_forward_returns(product, lookahead=10000):
    px = px_dict.get(product)
    if px is None:
        return pd.DataFrame()

    tr = tr_all[tr_all['symbol'] == product].copy().reset_index(drop=True)
    if len(tr) == 0:
        return pd.DataFrame()

    tr = tr.drop(columns=[c for c in tr.columns if 'pop_mid' in c], errors='ignore')
    tr = pd.merge_asof(
        tr.sort_values('timestamp'),
        px[['timestamp', 'pop_mid', 'bid_price_1', 'ask_price_1']].sort_values('timestamp'),
        on='timestamp', direction='nearest'
    ).reset_index(drop=True)

    all_traders = sorted(set(tr['buyer'].dropna()) | set(tr['seller'].dropna()))
    MIN_TRADES, EDGE_THR = 30, 0.5
    rows = []

    for trader in all_traders:
        buys  = tr[tr['buyer']  == trader]
        sells = tr[tr['seller'] == trader]
        buy_rets, sell_rets = [], []
        n_agg = 0

        for _, row in buys.iterrows():
            if pd.isna(row['pop_mid']): continue
            idx = px['timestamp'].searchsorted(row['timestamp'] + lookahead)
            if idx >= len(px): continue
            fm = px.iloc[idx]['pop_mid']
            if pd.isna(fm): continue
            buy_rets.append(fm - row['pop_mid'])
            if pd.notna(row['ask_price_1']) and row['price'] >= row['ask_price_1']:
                n_agg += 1

        for _, row in sells.iterrows():
            if pd.isna(row['pop_mid']): continue
            idx = px['timestamp'].searchsorted(row['timestamp'] + lookahead)
            if idx >= len(px): continue
            fm = px.iloc[idx]['pop_mid']
            if pd.isna(fm): continue
            sell_rets.append(row['pop_mid'] - fm)
            if pd.notna(row['bid_price_1']) and row['price'] <= row['bid_price_1']:
                n_agg += 1

        all_rets    = buy_rets + sell_rets
        n_total     = len(buys) + len(sells)
        mean_signed = round(np.mean(all_rets), 3) if all_rets else np.nan
        pct_agg     = round(n_agg / max(n_total, 1) * 100, 1)

        if n_total < MIN_TRADES or pd.isna(mean_signed):
            tag = 'UNKNOWN'
        elif mean_signed > EDGE_THR:
            tag = 'INFORMED'
        elif mean_signed < -EDGE_THR:
            tag = 'DUMB'
        else:
            tag = 'MM'

        rows.append({
            'trader':          trader,
            'n_buys':          len(buys),
            'buy_mean_ret':    round(np.mean(buy_rets),  3) if buy_rets  else np.nan,
            'buy_pct_pos':     round(np.mean([r > 0 for r in buy_rets])  * 100, 1) if buy_rets  else np.nan,
            'n_sells':         len(sells),
            'sell_mean_ret':   round(np.mean(sell_rets), 3) if sell_rets else np.nan,
            'sell_pct_pos':    round(np.mean([r > 0 for r in sell_rets]) * 100, 1) if sell_rets else np.nan,
            'mean_signed_ret': mean_signed,
            'pct_aggressive':  pct_agg,
            'tag':             tag,
        })

    return pd.DataFrame(rows).set_index('trader').sort_values('mean_signed_ret', ascending=False)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
ALL_TRADERS  = sorted(set(tr_all['buyer'].dropna()) | set(tr_all['seller'].dropna()))
AVAIL_PRODS  = sorted(px_dict.keys())
TS_MIN       = int(tr_all['timestamp'].min())
TS_MAX       = int(tr_all['timestamp'].max())

PALETTE      = ['#e74c3c', '#2ecc71', '#f1c40f', '#3498db', '#9b59b6', '#e67e22', '#ff69b4', '#adff2f']
TRADER_COLOR = {t: PALETTE[i % len(PALETTE)] for i, t in enumerate(ALL_TRADERS)}


# ---------------------------------------------------------------------------
# PnL helper — returns dict of trader -> DataFrame(timestamp, pnl, pos)
# ---------------------------------------------------------------------------
def compute_pnl(product, px_df):
    tr = tr_all[tr_all['symbol'] == product].sort_values('timestamp').reset_index(drop=True)
    if len(tr) == 0 or px_df is None or len(px_df) == 0:
        return {}

    px_ts  = px_df['timestamp'].values
    px_mid = px_df['pop_mid'].values

    traders = sorted(set(tr['buyer'].dropna()) | set(tr['seller'].dropna()))
    result  = {}

    for trader in traders:
        mask   = (tr['buyer'] == trader) | (tr['seller'] == trader)
        t_rows = tr[mask]
        if len(t_rows) == 0:
            continue

        cash, pos = 0.0, 0.0
        records   = []
        for _, row in t_rows.iterrows():
            qty = float(row['quantity'])
            prc = float(row['price'])
            if row['buyer'] == trader:
                cash -= prc * qty
                pos  += qty
            else:
                cash += prc * qty
                pos  -= qty
            idx = np.searchsorted(px_ts, row['timestamp'], side='right') - 1
            idx = max(0, min(idx, len(px_mid) - 1))
            mtm = px_mid[idx]
            records.append({
                'timestamp': row['timestamp'],
                'pnl': cash + pos * mtm if not np.isnan(mtm) else np.nan,
                'pos': pos,
            })

        result[trader] = pd.DataFrame(records)

    return result


# ---------------------------------------------------------------------------
# Shadow strategy helper
# ---------------------------------------------------------------------------
def compute_shadow_pnl(product, px_df, focus_trader, mom_thr, obi_thr):
    """
    Simulate copying focus_trader's trades one price-tick later.
    Returns (blind_df, filtered_df) — each has columns (timestamp, pnl).
    blind    = copy every trade unconditionally
    filtered = only copy when |momentum| < mom_thr AND |obi| < obi_thr at trade time
    """
    tr = tr_all[tr_all['symbol'] == product].sort_values('timestamp').reset_index(drop=True)
    focus = tr[(tr['buyer'] == focus_trader) | (tr['seller'] == focus_trader)]
    if len(focus) == 0 or px_df is None or len(px_df) == 0:
        return pd.DataFrame(), pd.DataFrame()

    px_ts   = px_df['timestamp'].values
    px_mid  = px_df['pop_mid'].values
    px_bid1 = px_df['bid_price_1'].values
    px_ask1 = px_df['ask_price_1'].values

    bv    = px_df[['bid_volume_1', 'bid_volume_2', 'bid_volume_3']].fillna(0).sum(axis=1).values
    av    = px_df[['ask_volume_1', 'ask_volume_2', 'ask_volume_3']].fillna(0).sum(axis=1).values
    total = bv + av
    obi   = np.where(total > 0, (bv - av) / total, 0.0)
    mom   = pd.Series(px_mid).diff(500).values

    b_cash, b_pos = 0.0, 0.0
    f_cash, f_pos = 0.0, 0.0
    blind_rec, filt_rec = [], []

    for _, row in focus.iterrows():
        ts  = row['timestamp']
        qty = float(row['quantity'])
        direction = 1 if row['buyer'] == focus_trader else -1

        # execute at the next tick's ask (if buying) or bid (if selling) — spread cost
        next_idx = int(np.searchsorted(px_ts, ts, side='right'))
        if next_idx >= len(px_ts):
            continue
        exec_p = px_ask1[next_idx] if direction == 1 else px_bid1[next_idx]
        if np.isnan(exec_p):
            exec_p = px_mid[next_idx]  # fall back to mid if no quote
        if np.isnan(exec_p):
            continue

        # regime at the moment of the observed trade
        reg_idx = max(0, next_idx - 1)
        mom_val = mom[reg_idx]
        obi_val = obi[reg_idx]

        # mark-to-market using mid at execution tick
        mtm = px_mid[next_idx]

        # blind copy
        b_cash -= direction * exec_p * qty
        b_pos  += direction * qty
        blind_rec.append({'timestamp': ts,
                          'pnl': b_cash + b_pos * mtm if not np.isnan(mtm) else np.nan})

        # filtered copy
        in_regime = (not np.isnan(mom_val)) and (abs(mom_val) < mom_thr) and (abs(obi_val) < obi_thr)
        if in_regime:
            f_cash -= direction * exec_p * qty
            f_pos  += direction * qty
        filt_rec.append({'timestamp': ts,
                         'pnl': f_cash + f_pos * mtm if not np.isnan(mtm) else np.nan})

    return pd.DataFrame(blind_rec), pd.DataFrame(filt_rec)


# ---------------------------------------------------------------------------
# App layout helpers
# ---------------------------------------------------------------------------
def info_box(text):
    """Inline ⓘ that expands to show a description on click."""
    return html.Details([
        html.Summary("ⓘ", style={
            'cursor': 'pointer', 'color': '#3498db', 'fontSize': '13px',
            'userSelect': 'none', 'listStyle': 'none', 'display': 'inline',
        }),
        html.Span(text, style={
            'color': '#aaaaaa', 'fontSize': '11px',
            'marginLeft': '8px', 'fontStyle': 'italic',
        }),
    ], style={'display': 'inline-block', 'verticalAlign': 'middle', 'marginLeft': '8px'})


app = dash.Dash(__name__)
app.title = "IMC Trade Visualizer"

METRIC_OPTIONS = [
    {'label': ' Bid-Ask Spread',             'value': 'spread'},
    {'label': ' Order Book Imbalance (OBI)', 'value': 'obi'},
    {'label': ' Price Momentum',             'value': 'momentum'},
    {'label': ' Net Position',               'value': 'position'},
    {'label': ' Informed Counterparty Flow', 'value': 'informed'},
]

app.layout = html.Div(style={'backgroundColor': '#0d1117', 'minHeight': '100vh', 'fontFamily': 'monospace'}, children=[

    html.H2("IMC Round 4 — Trade Visualizer",
            style={'color': '#00e5ff', 'padding': '12px 20px', 'margin': 0}),

    html.Div(style={'display': 'flex', 'flexWrap': 'wrap', 'gap': '20px', 'padding': '0 20px 12px'}, children=[

        html.Div([
            html.Label("Product", style={'color': '#aaaaaa', 'fontSize': '12px'}),
            dcc.Dropdown(
                id='product-dd',
                options=[{'label': p, 'value': p} for p in AVAIL_PRODS],
                value='VELVETFRUIT_EXTRACT',
                clearable=False,
                style={'width': '220px', 'backgroundColor': '#161b22', 'color': '#000'}
            )
        ]),

        html.Div([
            html.Label("Traders", style={'color': '#aaaaaa', 'fontSize': '12px'}),
            dcc.Dropdown(
                id='trader-dd',
                options=[{'label': t, 'value': t} for t in ALL_TRADERS],
                value=ALL_TRADERS,
                multi=True,
                style={'width': '340px', 'backgroundColor': '#161b22', 'color': '#000'}
            )
        ]),

        html.Div([
            html.Label("Lookback (ticks)", style={'color': '#aaaaaa', 'fontSize': '12px'}),
            dcc.Slider(
                id='lookback-sl',
                min=1000, max=100000, step=1000, value=10000,
                marks={1000: '1k', 25000: '25k', 50000: '50k', 100000: '100k'},
                tooltip={'placement': 'bottom', 'always_visible': True},
            )
        ], style={'width': '280px'}),

    ]),

    html.Div(style={'padding': '0 20px 8px'}, children=[
        html.Label("Timestamp Range", style={'color': '#aaaaaa', 'fontSize': '12px'}),
        dcc.RangeSlider(
            id='ts-slider',
            min=TS_MIN, max=TS_MAX, step=100,
            value=[TS_MIN, min(TS_MIN + 100000, TS_MAX)],
            marks={
                TS_MIN:           'Day 1',
                TS_MIN + 1000000: 'Day 2',
                TS_MIN + 2000000: 'Day 3',
            },
            tooltip={'placement': 'bottom', 'always_visible': True},
        )
    ]),

    dcc.Graph(id='main-chart', style={'height': '60vh'}),

    html.Div(style={'padding': '0 20px 4px', 'display': 'flex', 'alignItems': 'center', 'gap': '12px'}, children=[
        html.H4("Trader PnL", style={'color': '#00e5ff', 'margin': 0}),
        info_box("Mark-to-market PnL over time for each selected trader on the chosen product. "
                 "Cash flows from trades + current position × mid price."),
        dcc.Checklist(
            id='pnl-toggle',
            options=[{'label': ' Show PnL curves', 'value': 'show'}],
            value=['show'],
            style={'color': '#aaaaaa', 'fontSize': '13px'},
        ),
    ]),
    dcc.Graph(id='pnl-chart', style={'height': '40vh'}),

    html.Div(style={'display': 'flex', 'gap': '20px', 'padding': '0 20px 20px'}, children=[

        html.Div(style={'flex': '0 0 520px'}, children=[
            html.H4("Trader Classification", style={'color': '#00e5ff', 'margin': '8px 0 4px'}),
            info_box("Traders ranked by mean signed forward return over the lookback window. "
                     "INFORMED = consistently profits from direction; DUMB = loses; MM = earns spread passively; UNKNOWN = too few trades."),
            html.Div(id='tag-table')
        ]),

        html.Div(style={'flex': 1}, children=[
            html.H4("Trades in Window", style={'color': '#00e5ff', 'margin': '8px 0 4px'}),
            info_box("All executed trades for the selected product in the current timestamp range."),
            html.Div(id='trade-table')
        ]),
    ]),

    # ---- Trader Deep Dive ----
    html.Div(style={'padding': '0 20px 4px', 'borderTop': '1px solid #30363d', 'marginTop': '8px'}, children=[
        html.H3("Trader Deep Dive", style={'color': '#00e5ff', 'margin': '12px 0 4px', 'display': 'inline'}),
        info_box("Pick one trader and overlay their PnL with market metrics to find what conditions "
                 "cause them to make or lose money."),
        html.Br(),
        html.Div(style={'display': 'flex', 'flexWrap': 'wrap', 'gap': '32px', 'alignItems': 'flex-start'}, children=[
            html.Div([
                html.Label("Focus Trader", style={'color': '#aaaaaa', 'fontSize': '12px'}),
                dcc.Dropdown(
                    id='focus-trader-dd',
                    options=[{'label': t, 'value': t} for t in ALL_TRADERS],
                    value='Mark 14',
                    clearable=False,
                    style={'width': '200px', 'backgroundColor': '#161b22', 'color': '#000'}
                ),
            ]),
            html.Div([
                html.Label("Overlay Metrics", style={'color': '#aaaaaa', 'fontSize': '12px'}),
                dcc.Checklist(
                    id='metric-checks',
                    options=METRIC_OPTIONS,
                    value=[],
                    style={'color': '#c9d1d9', 'fontSize': '13px', 'lineHeight': '2'},
                ),
                html.Div(style={'marginTop': '8px'}, children=[
                    info_box("Bid-Ask Spread: ask_price_1 − bid_price_1. Wide = more MM profit opportunity."),
                    html.Br(),
                    info_box("OBI (Order Book Imbalance): (total bid vol − total ask vol) / total vol. "
                             "Ranges −1 to +1. Strong positive = buy pressure; negative = sell pressure. Predicts short-term price direction."),
                    html.Br(),
                    info_box("Price Momentum: rolling price change over last 500 ticks. "
                             "Large positive = sustained uptrend; negative = downtrend. MMs lose when momentum is strong."),
                    html.Br(),
                    info_box("Net Position: trader's running inventory (buys − sells). "
                             "Large position = exposed to adverse price moves."),
                    html.Br(),
                    info_box("Informed Flow: number of trades per time bucket involving INFORMED-tagged traders. "
                             "Spikes here mean smart money is active — MMs often lose when this is high."),
                ]),
            ]),
        ]),
    ]),
    dcc.Graph(id='deepdive-chart', style={'height': '70vh', 'padding': '0 0 20px'}),

    # ---- Shadow Strategy ----
    html.Div(style={'padding': '0 20px 4px', 'borderTop': '1px solid #30363d', 'marginTop': '8px'}, children=[
        html.H3("Shadow Strategy", style={'color': '#00e5ff', 'margin': '12px 0 4px', 'display': 'inline'}),
        info_box("Simulates copying a trader's trades one tick later at realistic aggressive prices "
                 "(you pay ask_price_1 to buy, hit bid_price_1 to sell). "
                 "Blind copy = follow every trade. Filtered copy = only follow when momentum and OBI are calm, "
                 "avoiding periods where the trader's edge disappears."),
        html.Br(),
        html.Div(style={'display': 'flex', 'flexWrap': 'wrap', 'gap': '32px', 'alignItems': 'flex-start'}, children=[
            html.Div([
                html.Label("Copy Trader", style={'color': '#aaaaaa', 'fontSize': '12px'}),
                dcc.Dropdown(
                    id='shadow-trader-dd',
                    options=[{'label': t, 'value': t} for t in ALL_TRADERS],
                    value='Mark 14',
                    clearable=False,
                    style={'width': '200px', 'backgroundColor': '#161b22', 'color': '#000'},
                ),
            ]),
            html.Div([
                html.Label("Momentum filter  |mom| <", style={'color': '#aaaaaa', 'fontSize': '12px'}),
                dcc.Slider(
                    id='mom-thr-sl',
                    min=10, max=300, step=10, value=80,
                    marks={10: '10', 100: '100', 200: '200', 300: '300'},
                    tooltip={'placement': 'bottom', 'always_visible': True},
                ),
            ], style={'width': '260px'}),
            html.Div([
                html.Label("OBI filter  |OBI| <", style={'color': '#aaaaaa', 'fontSize': '12px'}),
                dcc.Slider(
                    id='obi-thr-sl',
                    min=0.05, max=1.0, step=0.05, value=0.3,
                    marks={0.05: '0.05', 0.5: '0.5', 1.0: '1.0'},
                    tooltip={'placement': 'bottom', 'always_visible': True},
                ),
            ], style={'width': '260px'}),
        ]),
    ]),
    dcc.Graph(id='shadow-chart', style={'height': '45vh', 'padding': '0 0 20px'}),

    # ---- HYDROGEL ACF + Rolling Heatmap ----
    html.Div(style={'padding': '0 20px 4px', 'borderTop': '1px solid #30363d', 'marginTop': '8px'}, children=[
        html.H3("HYDROGEL_PACK — Return Autocorrelation",
                style={'color': '#00e5ff', 'margin': '12px 0 4px', 'display': 'inline'}),
        info_box("ACF = Autocorrelation Function. Measures how correlated price changes are with their own past. "
                 "Lag k answers: 'does a move k ticks ago predict the current move?' "
                 "Positive bar = momentum at that lag. Negative bar = mean reversion. "
                 "Green bars exceed the 95% significance threshold — grey bars are likely noise."),
        html.Br(),
        html.Div(style={'display': 'flex', 'gap': '32px', 'flexWrap': 'wrap', 'padding': '8px 0'}, children=[
            html.Div([
                html.Label("Max lag (ticks)", style={'color': '#aaaaaa', 'fontSize': '12px'}),
                dcc.Slider(
                    id='rel-lag-sl',
                    min=10, max=500, step=10, value=100,
                    marks={10: '10', 100: '100', 250: '250', 500: '500'},
                    tooltip={'placement': 'bottom', 'always_visible': True},
                ),
            ], style={'width': '300px'}),
            html.Div([
                html.Label("Heatmap window (ticks)", style={'color': '#aaaaaa', 'fontSize': '12px'}),
                dcc.Slider(
                    id='acf-window-sl',
                    min=20000, max=500000, step=10000, value=100000,
                    marks={20000: '20k', 100000: '100k', 300000: '300k', 500000: '500k'},
                    tooltip={'placement': 'bottom', 'always_visible': True},
                ),
            ], style={'width': '300px'}),
        ]),
    ]),
    dcc.Graph(id='rel-acf-chart',     style={'height': '40vh'}),
    html.Div(style={'padding': '4px 20px 0'}, children=[
        html.H4("Rolling ACF Heatmap", style={'color': '#00e5ff', 'margin': '4px 0', 'display': 'inline'}),
        info_box("Each column is the ACF computed over a rolling window centred at that timestamp. "
                 "Red = strong positive autocorrelation (momentum) at that lag. "
                 "Blue = strong negative autocorrelation (mean reversion). "
                 "A consistent colour across all columns = stable structural signal worth trading. "
                 "Colour that changes = regime-dependent, be careful."),
    ]),
    dcc.Graph(id='acf-heatmap', style={'height': '45vh', 'paddingBottom': '40px'}),
])


# ---------------------------------------------------------------------------
# PnL chart visibility toggle
# ---------------------------------------------------------------------------
@app.callback(
    Output('pnl-chart', 'style'),
    Input('pnl-toggle', 'value'),
)
def toggle_pnl(value):
    if 'show' in (value or []):
        return {'height': '40vh'}
    return {'height': '40vh', 'display': 'none'}


# ---------------------------------------------------------------------------
# PnL chart callback
# ---------------------------------------------------------------------------
@app.callback(
    Output('pnl-chart', 'figure'),
    Input('product-dd',  'value'),
    Input('trader-dd',   'value'),
    Input('ts-slider',   'value'),
    Input('pnl-toggle',  'value'),
)
def update_pnl(product, selected_traders, ts_range, pnl_toggle):
    selected_traders = selected_traders or []
    start, end = ts_range

    fig = go.Figure()
    fig.update_layout(
        paper_bgcolor='#0d1117', plot_bgcolor='#161b22',
        font=dict(color='#aaaaaa', family='monospace'),
        legend=dict(bgcolor='#161b22', bordercolor='#30363d', font=dict(size=10)),
        margin=dict(l=50, r=20, t=30, b=30),
        hovermode='x unified',
        yaxis_title='Mark-to-Market PnL',
        xaxis_title='Timestamp',
        xaxis=dict(gridcolor='#1f1f1f', zerolinecolor='#30363d'),
        yaxis=dict(gridcolor='#1f1f1f', zerolinecolor='#30363d'),
    )

    if 'show' not in (pnl_toggle or []):
        return fig

    px_prod  = px_dict.get(product, px_spot)
    pnl_data = compute_pnl(product, px_prod)

    for trader in selected_traders:
        df = pnl_data.get(trader)
        if df is None or len(df) == 0:
            continue
        df_w = df[(df['timestamp'] >= start) & (df['timestamp'] <= end)]
        if len(df_w) == 0:
            continue
        color = TRADER_COLOR.get(trader, '#ffffff')
        fig.add_trace(go.Scatter(
            x=df_w['timestamp'], y=df_w['pnl'],
            mode='lines', line=dict(color=color, width=1.5),
            name=trader,
            hovertemplate=f"<b>{trader}</b><br>PnL: %{{y:.1f}}<extra></extra>",
        ))

    fig.add_hline(y=0, line=dict(color='#555555', dash='dot', width=1))
    return fig


# ---------------------------------------------------------------------------
# Trader Deep Dive callback
# ---------------------------------------------------------------------------
@app.callback(
    Output('deepdive-chart', 'figure'),
    Input('focus-trader-dd', 'value'),
    Input('metric-checks',   'value'),
    Input('product-dd',      'value'),
    Input('ts-slider',       'value'),
    Input('lookback-sl',     'value'),
)
def update_deepdive(focus_trader, metrics, product, ts_range, lookahead):
    metrics = metrics or []
    start, end = ts_range
    px_prod = px_dict.get(product, px_spot)

    # Always show PnL row; add one row per selected metric
    n_rows   = 1 + len(metrics)
    row_h    = [0.4] + [0.6 / len(metrics)] * len(metrics) if metrics else [1.0]
    subtitles = ['PnL'] + [m.upper() for m in metrics]

    fig = make_subplots(
        rows=n_rows, cols=1,
        shared_xaxes=True,
        row_heights=row_h,
        vertical_spacing=0.04,
        subplot_titles=subtitles,
    )

    # -- Row 1: PnL --
    pnl_data = compute_pnl(product, px_prod)
    df_trader = pnl_data.get(focus_trader, pd.DataFrame())
    color = TRADER_COLOR.get(focus_trader, '#00e5ff')

    if len(df_trader):
        df_w = df_trader[(df_trader['timestamp'] >= start) & (df_trader['timestamp'] <= end)]
        fig.add_trace(go.Scatter(
            x=df_w['timestamp'], y=df_w['pnl'],
            mode='lines', line=dict(color=color, width=2),
            name='PnL', showlegend=False,
            hovertemplate='PnL: %{y:.1f}<extra></extra>',
        ), row=1, col=1)
    fig.add_hline(y=0, line=dict(color='#444444', dash='dot', width=1), row=1, col=1)

    # -- Metric rows --
    px_w = px_prod[(px_prod['timestamp'] >= start) & (px_prod['timestamp'] <= end)].copy()

    for i, metric in enumerate(metrics, start=2):

        if metric == 'spread':
            spread = px_w['ask_price_1'] - px_w['bid_price_1']
            fig.add_trace(go.Scatter(
                x=px_w['timestamp'], y=spread,
                mode='lines', line=dict(color='#f1c40f', width=1),
                name='Spread', showlegend=False,
                hovertemplate='Spread: %{y:.2f}<extra></extra>',
            ), row=i, col=1)

        elif metric == 'obi':
            bv = px_w[['bid_volume_1', 'bid_volume_2', 'bid_volume_3']].fillna(0).sum(axis=1)
            av = px_w[['ask_volume_1', 'ask_volume_2', 'ask_volume_3']].fillna(0).sum(axis=1)
            total = bv + av
            obi = np.where(total > 0, (bv - av) / total, 0.0)
            fig.add_trace(go.Scatter(
                x=px_w['timestamp'], y=obi,
                mode='lines', line=dict(color='#3498db', width=1),
                name='OBI', showlegend=False,
                hovertemplate='OBI: %{y:.3f}<extra></extra>',
            ), row=i, col=1)
            fig.add_hline(y=0, line=dict(color='#444444', dash='dot', width=1), row=i, col=1)

        elif metric == 'momentum':
            # rolling difference over ~500 price ticks
            mom = px_w['pop_mid'].diff(500)
            fig.add_trace(go.Scatter(
                x=px_w['timestamp'], y=mom,
                mode='lines', line=dict(color='#e67e22', width=1),
                name='Momentum', showlegend=False,
                hovertemplate='Momentum: %{y:.2f}<extra></extra>',
            ), row=i, col=1)
            fig.add_hline(y=0, line=dict(color='#444444', dash='dot', width=1), row=i, col=1)

        elif metric == 'position':
            if len(df_trader):
                df_w2 = df_trader[(df_trader['timestamp'] >= start) & (df_trader['timestamp'] <= end)]
                fig.add_trace(go.Scatter(
                    x=df_w2['timestamp'], y=df_w2['pos'],
                    mode='lines', line=dict(color='#9b59b6', width=1),
                    name='Net Position', showlegend=False,
                    hovertemplate='Position: %{y:.0f}<extra></extra>',
                ), row=i, col=1)
            fig.add_hline(y=0, line=dict(color='#444444', dash='dot', width=1), row=i, col=1)

        elif metric == 'informed':
            # get informed tags for this product using current lookahead
            fwd  = trader_forward_returns(product, lookahead)
            tags = fwd['tag'].to_dict() if len(fwd) else {}
            informed = {t for t, tag in tags.items() if tag == 'INFORMED'}

            tr_prod_w = tr_all[
                (tr_all['symbol'] == product) &
                (tr_all['timestamp'] >= start) &
                (tr_all['timestamp'] <= end)
            ]
            inf_trades = tr_prod_w[
                tr_prod_w['buyer'].isin(informed) | tr_prod_w['seller'].isin(informed)
            ]
            if len(inf_trades):
                # bin trade counts into ~500-tick buckets for a smooth bar
                bin_size = max(1, (end - start) // 200)
                inf_trades = inf_trades.copy()
                inf_trades['bucket'] = (inf_trades['timestamp'] // bin_size) * bin_size
                counts = inf_trades.groupby('bucket').size().reset_index(name='count')
                fig.add_trace(go.Bar(
                    x=counts['bucket'], y=counts['count'],
                    marker_color='#2ecc71', opacity=0.7,
                    name='Informed flow', showlegend=False,
                    hovertemplate='Informed trades: %{y}<extra></extra>',
                ), row=i, col=1)

    fig.update_layout(
        paper_bgcolor='#0d1117', plot_bgcolor='#161b22',
        font=dict(color='#aaaaaa', family='monospace'),
        margin=dict(l=50, r=20, t=40, b=30),
        hovermode='x unified',
        showlegend=False,
        title=dict(text=f'{focus_trader} — {product}', font=dict(color='#00e5ff', size=13)),
    )
    fig.update_xaxes(gridcolor='#1f1f1f', zerolinecolor='#30363d')
    fig.update_yaxes(gridcolor='#1f1f1f', zerolinecolor='#30363d')
    fig.update_xaxes(title_text='Timestamp', row=n_rows, col=1)
    fig.update_annotations(font_color='#00e5ff', font_size=11)

    return fig


# ---------------------------------------------------------------------------
# Shadow strategy callback
# ---------------------------------------------------------------------------
@app.callback(
    Output('shadow-chart', 'figure'),
    Input('shadow-trader-dd', 'value'),
    Input('mom-thr-sl',       'value'),
    Input('obi-thr-sl',       'value'),
    Input('product-dd',       'value'),
    Input('ts-slider',        'value'),
    Input('lookback-sl',      'value'),
)
def update_shadow(focus_trader, mom_thr, obi_thr, product, ts_range, lookahead):
    start, end = ts_range
    px_prod  = px_dict.get(product, px_spot)
    pnl_data = compute_pnl(product, px_prod)

    blind_df, filt_df = compute_shadow_pnl(product, px_prod, focus_trader, mom_thr, obi_thr)

    fig = go.Figure()

    # Original trader PnL
    orig = pnl_data.get(focus_trader, pd.DataFrame())
    if len(orig):
        w = orig[(orig['timestamp'] >= start) & (orig['timestamp'] <= end)]
        fig.add_trace(go.Scatter(
            x=w['timestamp'], y=w['pnl'],
            mode='lines', line=dict(color='#7c9ef5', width=1.5, dash='dot'),
            name=f'{focus_trader} (actual)',
            hovertemplate='Actual PnL: %{y:.1f}<extra></extra>',
        ))

    # Blind copy
    if len(blind_df):
        w = blind_df[(blind_df['timestamp'] >= start) & (blind_df['timestamp'] <= end)]
        fig.add_trace(go.Scatter(
            x=w['timestamp'], y=w['pnl'],
            mode='lines', line=dict(color='#e74c3c', width=1.5),
            name='Blind copy',
            hovertemplate='Blind copy PnL: %{y:.1f}<extra></extra>',
        ))

    # Filtered copy
    if len(filt_df):
        w = filt_df[(filt_df['timestamp'] >= start) & (filt_df['timestamp'] <= end)]
        fig.add_trace(go.Scatter(
            x=w['timestamp'], y=w['pnl'],
            mode='lines', line=dict(color='#2ecc71', width=2),
            name=f'Filtered copy  (|mom|<{mom_thr}, |OBI|<{obi_thr})',
            hovertemplate='Filtered PnL: %{y:.1f}<extra></extra>',
        ))

    fig.add_hline(y=0, line=dict(color='#444444', dash='dot', width=1))
    fig.update_layout(
        paper_bgcolor='#0d1117', plot_bgcolor='#161b22',
        font=dict(color='#aaaaaa', family='monospace'),
        legend=dict(bgcolor='#161b22', bordercolor='#30363d', font=dict(size=11)),
        margin=dict(l=50, r=20, t=30, b=40),
        hovermode='x unified',
        xaxis=dict(title='Timestamp', gridcolor='#1f1f1f', zerolinecolor='#30363d'),
        yaxis=dict(title='Mark-to-Market PnL', gridcolor='#1f1f1f', zerolinecolor='#30363d'),
    )
    return fig


# ---------------------------------------------------------------------------
# Main callback
# ---------------------------------------------------------------------------
@app.callback(
    Output('main-chart',  'figure'),
    Output('tag-table',   'children'),
    Output('trade-table', 'children'),
    Input('product-dd',  'value'),
    Input('trader-dd',   'value'),
    Input('ts-slider',   'value'),
    Input('lookback-sl', 'value'),
)
def update(product, selected_traders, ts_range, lookahead):
    selected_traders = selected_traders or []
    start, end = ts_range

    fwd  = trader_forward_returns(product, lookahead)
    tags = fwd['tag'].to_dict() if len(fwd) else {}

    px_prod   = px_dict.get(product, px_spot)
    px_prod_w = px_prod[(px_prod['timestamp'] >= start) & (px_prod['timestamp'] <= end)]
    px_spot_w = px_spot[(px_spot['timestamp'] >= start) & (px_spot['timestamp'] <= end)]

    tr_w = tr_all[
        (tr_all['symbol'] == product) &
        (tr_all['timestamp'] >= start) &
        (tr_all['timestamp'] <= end)
    ]
    tr_sel = tr_w[tr_w['buyer'].isin(selected_traders) | tr_w['seller'].isin(selected_traders)]

    spot_label = f'{product} — pop_mid' if product == 'VELVETFRUIT_EXTRACT' else f'VELVETFRUIT_EXTRACT vs {product} — pop_mid'
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                        row_heights=[0.3, 0.7], vertical_spacing=0.04,
                        subplot_titles=[spot_label, product])

    fig.add_trace(go.Scatter(
        x=px_spot_w['timestamp'], y=px_spot_w['pop_mid'],
        mode='lines', line=dict(color='#7c9ef5', width=1),
        name='VELVETFRUIT_EXTRACT', showlegend=(product != 'VELVETFRUIT_EXTRACT')
    ), row=1, col=1)

    if product != 'VELVETFRUIT_EXTRACT':
        fig.add_trace(go.Scatter(
            x=px_prod_w['timestamp'], y=px_prod_w['pop_mid'],
            mode='lines', line=dict(color='#f39c12', width=1),
            name=product, showlegend=True
        ), row=1, col=1)

    fig.add_trace(go.Scatter(
        x=px_prod_w['timestamp'], y=px_prod_w['pop_mid'],
        mode='lines', line=dict(color='#7c9ef5', width=1),
        name=f'{product} pop_mid', showlegend=False
    ), row=2, col=1)

    seen = set()
    for trader in selected_traders:
        tag   = tags.get(trader, 'UNKNOWN')
        color = TRADER_COLOR.get(trader, '#ffffff')
        buys  = tr_sel[tr_sel['buyer']  == trader]
        sells = tr_sel[tr_sel['seller'] == trader]
        label = f"{trader} [{tag}]"

        if len(buys):
            fig.add_trace(go.Scatter(
                x=buys['timestamp'], y=buys['price'],
                mode='markers+text',
                marker=dict(symbol='triangle-up', size=11, color='#2ecc71',
                            line=dict(color=color, width=1)),
                text=[f"{trader}<br>[{tag}] ×{int(q)}" for q in buys['quantity']],
                textposition='top center',
                textfont=dict(size=9, color=color),
                name=label, legendgroup=trader,
                showlegend=(label not in seen),
                hovertemplate=f"<b>{trader}</b> BUY<br>Price: %{{y}}<br>Tag: {tag}<extra></extra>",
            ), row=2, col=1)
            seen.add(label)

        if len(sells):
            fig.add_trace(go.Scatter(
                x=sells['timestamp'], y=sells['price'],
                mode='markers+text',
                marker=dict(symbol='triangle-down', size=11, color='#e74c3c',
                            line=dict(color=color, width=1)),
                text=[f"{trader}<br>[{tag}] ×{int(q)}" for q in sells['quantity']],
                textposition='bottom center',
                textfont=dict(size=9, color=color),
                name=label, legendgroup=trader,
                showlegend=(label not in seen),
                hovertemplate=f"<b>{trader}</b> SELL<br>Price: %{{y}}<br>Tag: {tag}<extra></extra>",
            ), row=2, col=1)
            seen.add(label)

    fig.update_layout(
        paper_bgcolor='#0d1117', plot_bgcolor='#161b22',
        font=dict(color='#aaaaaa', family='monospace'),
        legend=dict(bgcolor='#161b22', bordercolor='#30363d', font=dict(size=10)),
        margin=dict(l=50, r=20, t=40, b=20),
        hovermode='x unified',
    )
    fig.update_xaxes(gridcolor='#1f1f1f', zerolinecolor='#30363d')
    fig.update_yaxes(gridcolor='#1f1f1f', zerolinecolor='#30363d')
    fig.update_yaxes(title_text='pop_mid',     row=1, col=1)
    fig.update_yaxes(title_text='Trade Price', row=2, col=1)
    fig.update_xaxes(title_text='Timestamp',   row=2, col=1)
    fig.update_annotations(font_color='#00e5ff')

    if len(fwd):
        fwd_disp = fwd[['mean_signed_ret', 'pct_aggressive', 'tag', 'n_buys', 'n_sells']].reset_index()
        tag_tbl = dash_table.DataTable(
            data=fwd_disp.to_dict('records'),
            columns=[{'name': c, 'id': c} for c in fwd_disp.columns],
            style_table={'overflowX': 'auto'},
            style_cell={'backgroundColor': '#161b22', 'color': '#c9d1d9',
                        'border': '1px solid #30363d', 'fontSize': '12px',
                        'fontFamily': 'monospace', 'textAlign': 'center', 'padding': '6px'},
            style_header={'backgroundColor': '#0d1117', 'color': '#00e5ff',
                          'fontWeight': 'bold', 'border': '1px solid #30363d'},
            style_data_conditional=[
                {'if': {'filter_query': '{tag} = "INFORMED"', 'column_id': 'tag'},
                 'color': '#2ecc71', 'fontWeight': 'bold'},
                {'if': {'filter_query': '{tag} = "DUMB"', 'column_id': 'tag'},
                 'color': '#e74c3c', 'fontWeight': 'bold'},
                {'if': {'filter_query': '{tag} = "MM"', 'column_id': 'tag'},
                 'color': '#f1c40f', 'fontWeight': 'bold'},
            ]
        )
    else:
        tag_tbl = html.P("No data", style={'color': '#aaaaaa'})

    if len(tr_w):
        tr_disp = tr_w[['timestamp', 'symbol', 'buyer', 'seller', 'price', 'quantity']]\
            .sort_values('timestamp').reset_index(drop=True)
        trade_tbl = dash_table.DataTable(
            data=tr_disp.to_dict('records'),
            columns=[{'name': c, 'id': c} for c in tr_disp.columns],
            page_size=15,
            style_table={'overflowX': 'auto'},
            style_cell={'backgroundColor': '#161b22', 'color': '#c9d1d9',
                        'border': '1px solid #30363d', 'fontSize': '12px',
                        'fontFamily': 'monospace', 'textAlign': 'center', 'padding': '6px'},
            style_header={'backgroundColor': '#0d1117', 'color': '#00e5ff',
                          'fontWeight': 'bold', 'border': '1px solid #30363d'},
        )
    else:
        trade_tbl = html.P("No trades in window", style={'color': '#aaaaaa'})

    return fig, tag_tbl, trade_tbl


# ---------------------------------------------------------------------------
# HYDROGEL ACF
# ---------------------------------------------------------------------------
@app.callback(
    Output('rel-acf-chart', 'figure'),
    Output('acf-heatmap',   'figure'),
    Input('rel-lag-sl',    'value'),
    Input('acf-window-sl', 'value'),
    Input('ts-slider',     'value'),
)
def update_relationship(max_lag, window, ts_range):
    start, end = ts_range
    GRID = '#1f1f1f'
    ZERO = '#30363d'

    def base_layout(title=''):
        return dict(
            paper_bgcolor='#0d1117', plot_bgcolor='#161b22',
            font=dict(color='#aaaaaa', family='monospace'),
            legend=dict(bgcolor='#161b22', bordercolor='#30363d', font=dict(size=10)),
            margin=dict(l=60, r=20, t=35, b=40),
            bargap=0.1,
            title=dict(text=title, font=dict(color='#00e5ff', size=12)),
        )

    hydro = px_dict.get('HYDROGEL_PACK')
    empty = go.Figure()
    empty.update_layout(**base_layout())
    if hydro is None:
        return empty, empty

    df = hydro[['timestamp', 'pop_mid']].copy()
    df = df[(df['timestamp'] >= start) & (df['timestamp'] <= end)].reset_index(drop=True)

    if len(df) < max_lag + 10:
        return empty, empty

    h_ret = np.diff(df['pop_mid'].values, prepend=df['pop_mid'].values[0])
    sig   = 1.96 / np.sqrt(len(df))
    lags  = list(range(1, max_lag + 1))

    # ---- ACF bar chart ----
    acf_vals   = [np.corrcoef(h_ret[k:], h_ret[:-k])[0, 1] for k in lags]
    acf_colors = ['#2ecc71' if abs(c) > sig else '#3a3a5c' for c in acf_vals]

    fig_acf = go.Figure()
    fig_acf.add_trace(go.Bar(
        x=lags, y=acf_vals, marker_color=acf_colors, showlegend=False,
        hovertemplate='Lag %{x}: ACF=%{y:.4f}<extra></extra>',
    ))
    fig_acf.add_hline(y= sig, line=dict(color='#ffffff', dash='dot', width=1))
    fig_acf.add_hline(y=-sig, line=dict(color='#ffffff', dash='dot', width=1))
    fig_acf.update_layout(
        **base_layout(f'Full-window ACF   95% band ±{sig:.4f}'),
        xaxis=dict(title='Lag (ticks)', gridcolor=GRID, zerolinecolor='#888'),
        yaxis=dict(title='Autocorrelation', gridcolor=GRID, zerolinecolor=ZERO),
    )

    # ---- Rolling ACF heatmap — always uses full 3-day dataset ----
    hydro_full  = hydro[['timestamp', 'pop_mid']].copy().reset_index(drop=True)
    h_ret_full  = np.diff(hydro_full['pop_mid'].values, prepend=hydro_full['pop_mid'].values[0])
    ts_full     = hydro_full['timestamp'].values
    n_full      = len(h_ret_full)
    # convert window from ticks to rows (prices every 100 ticks)
    win_rows    = max(max_lag + 20, window // 100)
    step_rows   = max(1, win_rows // 30)   # ~30 columns per window
    centers     = []
    acf_mat     = []

    for i in range(0, n_full - win_rows, step_rows):
        chunk = h_ret_full[i:i + win_rows]
        row = [np.corrcoef(chunk[k:], chunk[:-k])[0, 1] for k in lags]
        acf_mat.append(row)
        centers.append(int(ts_full[min(i + win_rows // 2, n_full - 1)]))

    if acf_mat:
        z = np.array(acf_mat).T   # shape: (n_lags, n_windows)
        fig_heat = go.Figure(go.Heatmap(
            x=centers,
            y=lags,
            z=z,
            colorscale='RdBu_r',
            zmid=0,
            zmin=-0.3, zmax=0.3,
            colorbar=dict(title='ACF', thickness=12,
                          tickfont=dict(color='#aaaaaa', size=10)),
            hovertemplate='Timestamp: %{x}<br>Lag: %{y}<br>ACF: %{z:.4f}<extra></extra>',
        ))
        fig_heat.update_layout(
            **base_layout(f'Rolling ACF heatmap   window={window:,} ticks   '
                          f'red=momentum · blue=mean-reversion'),
            xaxis=dict(title='Timestamp', gridcolor=GRID),
            yaxis=dict(title='Lag (ticks)', gridcolor=GRID, autorange='reversed'),
        )
    else:
        fig_heat = empty

    return fig_acf, fig_heat


if __name__ == '__main__':
    app.run(debug=False, port=8050)
