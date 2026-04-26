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
# PnL helper
# ---------------------------------------------------------------------------
def compute_pnl(product, px_df):
    """Return dict of trader -> DataFrame(timestamp, pnl) using mark-to-market."""
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
            records.append({'timestamp': row['timestamp'],
                            'pnl': cash + pos * mtm if not np.isnan(mtm) else np.nan})

        result[trader] = pd.DataFrame(records)

    return result


# ---------------------------------------------------------------------------
# App layout
# ---------------------------------------------------------------------------
app = dash.Dash(__name__)
app.title = "IMC Trade Visualizer"

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
        dcc.Checklist(
            id='pnl-toggle',
            options=[{'label': ' Show PnL curves', 'value': 'show'}],
            value=[],
            style={'color': '#aaaaaa', 'fontSize': '13px'},
        ),
    ]),
    dcc.Graph(id='pnl-chart', style={'height': '40vh', 'display': 'none'}),

    html.Div(style={'display': 'flex', 'gap': '20px', 'padding': '0 20px 20px'}, children=[

        html.Div(style={'flex': '0 0 520px'}, children=[
            html.H4("Trader Classification", style={'color': '#00e5ff', 'margin': '8px 0 4px'}),
            html.Div(id='tag-table')
        ]),

        html.Div(style={'flex': 1}, children=[
            html.H4("Trades in Window", style={'color': '#00e5ff', 'margin': '8px 0 4px'}),
            html.Div(id='trade-table')
        ]),
    ]),

    html.Div(style={'padding': '0 20px 20px'}, children=[
        html.H4("PnL vs Lot Size", style={'color': '#00e5ff', 'margin': '8px 0 4px'}),
        dcc.Graph(id='lotsize-chart', style={'height': '45vh'}),
    ]),
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

    px_prod = px_dict.get(product, px_spot)
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
            mode='lines',
            line=dict(color=color, width=1.5),
            name=trader,
            hovertemplate=f"<b>{trader}</b><br>PnL: %{{y:.1f}}<extra></extra>",
        ))

    fig.add_hline(y=0, line=dict(color='#555555', dash='dot', width=1))
    return fig


# ---------------------------------------------------------------------------
# Lot-size vs PnL scatter
# ---------------------------------------------------------------------------
@app.callback(
    Output('lotsize-chart', 'figure'),
    Input('product-dd',  'value'),
    Input('trader-dd',   'value'),
    Input('lookback-sl', 'value'),
)
def update_lotsize(product, selected_traders, lookahead):
    selected_traders = set(selected_traders or [])
    px_prod = px_dict.get(product, px_spot)
    pnl_data = compute_pnl(product, px_prod)
    fwd = trader_forward_returns(product, lookahead)
    tags = fwd['tag'].to_dict() if len(fwd) else {}

    tr_prod = tr_all[tr_all['symbol'] == product]

    TAG_COLOR = {'INFORMED': '#2ecc71', 'DUMB': '#e74c3c', 'MM': '#f1c40f', 'UNKNOWN': '#888888'}

    rows = []
    for trader, df in pnl_data.items():
        if len(df) == 0:
            continue
        t_trades = tr_prod[(tr_prod['buyer'] == trader) | (tr_prod['seller'] == trader)]
        avg_lot  = t_trades['quantity'].mean()
        n_trades = len(t_trades)
        final_pnl = df['pnl'].dropna().iloc[-1] if len(df['pnl'].dropna()) else 0
        tag = tags.get(trader, 'UNKNOWN')
        rows.append({'trader': trader, 'avg_lot': avg_lot, 'pnl': final_pnl,
                     'n_trades': n_trades, 'tag': tag,
                     'selected': trader in selected_traders})

    fig = go.Figure()
    if not rows:
        return fig

    df_scatter = pd.DataFrame(rows)

    for tag, grp in df_scatter.groupby('tag'):
        color = TAG_COLOR.get(tag, '#888888')
        for _, row in grp.iterrows():
            opacity = 1.0 if row['selected'] else 0.25
            fig.add_trace(go.Scatter(
                x=[row['avg_lot']], y=[row['pnl']],
                mode='markers+text',
                marker=dict(size=max(8, min(30, row['n_trades'] / 5)),
                            color=color, opacity=opacity,
                            line=dict(color='#ffffff' if row['selected'] else color, width=1)),
                text=[row['trader']],
                textposition='top center',
                textfont=dict(size=9, color=color if row['selected'] else '#555555'),
                name=tag,
                legendgroup=tag,
                showlegend=False,
                hovertemplate=(
                    f"<b>{row['trader']}</b><br>"
                    f"Tag: {tag}<br>"
                    f"Avg lot: {row['avg_lot']:.1f}<br>"
                    f"PnL: {row['pnl']:.1f}<br>"
                    f"Trades: {row['n_trades']}<extra></extra>"
                ),
            ))

    # One legend entry per tag
    for tag, color in TAG_COLOR.items():
        fig.add_trace(go.Scatter(
            x=[None], y=[None], mode='markers',
            marker=dict(size=10, color=color),
            name=tag, legendgroup=tag, showlegend=True,
        ))

    fig.add_hline(y=0, line=dict(color='#555555', dash='dot', width=1))
    fig.update_layout(
        paper_bgcolor='#0d1117', plot_bgcolor='#161b22',
        font=dict(color='#aaaaaa', family='monospace'),
        legend=dict(bgcolor='#161b22', bordercolor='#30363d', font=dict(size=10)),
        margin=dict(l=50, r=20, t=20, b=40),
        hovermode='closest',
        xaxis=dict(title='Avg Lot Size', gridcolor='#1f1f1f', zerolinecolor='#30363d'),
        yaxis=dict(title='Total PnL (mark-to-market)', gridcolor='#1f1f1f', zerolinecolor='#30363d'),
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


if __name__ == '__main__':
    app.run(debug=False, port=8050)
