"""Interactive dashboard over the warehouse.

Run from the repo root:  streamlit run src/dashboard.py
"""

import sqlite3

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from analytics import coverage, price_history, quality_summary, risk_return

DB_PATH = "data/market.db"

# Palette: validated categorical order (fixed, never cycled), diverging poles,
# and recessive chrome. Light theme only (see .streamlit/config.toml).
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
POSITIVE, NEGATIVE = "#2a78d6", "#e34948"
OTHER = "#c3c2b7"
SURFACE, INK, INK_2, MUTED, GRID, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
# A scatter puts every pair of colors on screen at once; only the first three
# slots stay distinguishable under colorblind simulation, so cap highlights at 3.
MAX_HIGHLIGHT = 3
MAX_LINES = len(SERIES)

LOOKBACKS = {"1 month": 21, "3 months": 63, "6 months": 126, "12 months": 252}
VOL_WINDOWS = {"1 month": 21, "3 months": 63, "6 months": 126}

st.set_page_config(page_title="Market Warehouse", layout="wide")


def query(fn, *args):
    conn = sqlite3.connect(DB_PATH)
    try:
        return fn(conn, *args)
    finally:
        conn.close()


@st.cache_data
def load_risk_return(lookback, window):
    return query(risk_return, lookback, window)


@st.cache_data
def load_prices(symbols, lookback):
    return query(price_history, list(symbols), lookback)


@st.cache_data
def load_quality():
    return query(quality_summary)


@st.cache_data
def load_coverage():
    return query(coverage)


def style(fig: go.Figure, height: int = 520) -> go.Figure:
    axis = dict(gridcolor=GRID, linecolor=AXIS, zerolinecolor=AXIS, tickfont=dict(color=MUTED), title_font=dict(color=INK_2))
    fig.update_layout(
        height=height,
        paper_bgcolor=SURFACE,
        plot_bgcolor=SURFACE,
        font=dict(color=INK, size=13),
        margin=dict(l=8, r=8, t=24, b=8),
        hoverlabel=dict(bgcolor="white", font_color=INK, bordercolor=GRID),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, font=dict(color=INK_2)),
        xaxis=axis,
        yaxis=axis,
    )
    return fig


# ---------- Filters ----------

st.title("Market Warehouse")

with st.sidebar:
    st.header("Parameters")
    lookback_label = st.select_slider("Momentum lookback", list(LOOKBACKS), value="12 months")
    window_label = st.select_slider("Volatility window", list(VOL_WINDOWS), value="3 months")
    lookback, window = LOOKBACKS[lookback_label], VOL_WINDOWS[window_label]

df = load_risk_return(lookback, window)
sectors = sorted(df["sector"].unique())

with st.sidebar:
    highlight = st.multiselect(
        "Highlight sectors",
        sectors,
        max_selections=MAX_HIGHLIGHT,
        help=f"Up to {MAX_HIGHLIGHT}; everything else is drawn in gray.",
    )
    st.caption(f"{len(df)} symbols with enough history · {lookback} / {window} trading days")

# Color follows the sector, assigned by selection order, so adding a third
# sector never repaints the first two.
sector_color = {s: SERIES[i] for i, s in enumerate(highlight)}

tab_rr, tab_mom, tab_px, tab_dq = st.tabs(["Risk vs return", "Momentum ranking", "Price paths", "Data quality"])

# ---------- Risk vs return ----------

with tab_rr:
    best = df.loc[df["return_per_vol"].idxmax()]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Median momentum", f"{df['momentum'].median():.1%}")
    c2.metric("Median volatility", f"{df['volatility'].median():.1%}")
    c3.metric("Share positive", f"{(df['momentum'] > 0).mean():.0%}")
    c4.metric("Best return / vol", best["symbol"], f"{best['return_per_vol']:.2f}", delta_color="off")

    fig = go.Figure()
    groups = [("Other", df[~df["sector"].isin(highlight)], OTHER)] + [
        (s, df[df["sector"] == s], sector_color[s]) for s in highlight
    ]
    for name, g, color in groups:
        fig.add_scatter(
            x=g["volatility"],
            y=g["momentum"],
            mode="markers",
            name=name,
            showlegend=bool(highlight),
            marker=dict(size=11, color=color, line=dict(width=2, color=SURFACE)),
            customdata=g[["symbol", "name", "sector", "return_per_vol"]],
            hovertemplate=(
                "<b>%{customdata[0]}</b> · %{customdata[1]}<br>%{customdata[2]}<br>"
                "Momentum %{y:.1%}<br>Volatility %{x:.1%}<br>Return/vol %{customdata[3]:.2f}<extra></extra>"
            ),
        )
    # Selective direct labels: the five best and worst risk-adjusted names.
    labeled = pd.concat([df.nlargest(5, "return_per_vol"), df.nsmallest(3, "return_per_vol")])
    fig.add_scatter(
        x=labeled["volatility"],
        y=labeled["momentum"],
        mode="text",
        text=labeled["symbol"],
        textposition="top center",
        textfont=dict(color=INK_2, size=11),
        hoverinfo="skip",
        showlegend=False,
    )
    fig.add_hline(y=0, line=dict(color=AXIS, width=1))
    fig.update_xaxes(title=f"Annualized volatility ({window_label})", tickformat=".0%")
    fig.update_yaxes(title=f"Momentum ({lookback_label})", tickformat=".0%")
    st.plotly_chart(style(fig, 560), width="stretch")
    st.caption("Upper-left is the best place to be: high return, low volatility. Hover any dot for details.")

    with st.expander("Table view"):
        table = df[["symbol", "name", "sector", "momentum", "volatility", "return_per_vol"]]
        st.dataframe(
            table,
            hide_index=True,
            width="stretch",
            column_config={
                "momentum": st.column_config.NumberColumn(format="percent"),
                "volatility": st.column_config.NumberColumn(format="percent"),
                "return_per_vol": st.column_config.NumberColumn("return / vol", format="%.2f"),
            },
        )
        st.download_button("Download CSV", table.to_csv(index=False), "risk_return.csv", "text/csv")

# ---------- Momentum ranking ----------

with tab_mom:
    ranked = df.sort_values("momentum")
    fig = go.Figure(
        go.Bar(
            x=ranked["momentum"],
            y=ranked["symbol"],
            orientation="h",
            marker=dict(
                color=[POSITIVE if m >= 0 else NEGATIVE for m in ranked["momentum"]],
                line=dict(width=0),
            ),
            customdata=ranked[["name", "sector", "close_start", "close_end"]],
            hovertemplate=(
                "<b>%{y}</b> · %{customdata[0]}<br>%{customdata[1]}<br>"
                "Momentum %{x:.1%}<br>$%{customdata[2]:.2f} → $%{customdata[3]:.2f}<extra></extra>"
            ),
        )
    )
    fig.update_layout(bargap=0.25)
    fig.update_xaxes(title=f"Momentum ({lookback_label})", tickformat=".0%", side="top")
    fig.update_yaxes(tickfont=dict(size=10), showgrid=False)
    st.plotly_chart(style(fig, max(500, 15 * len(ranked))), width="stretch")
    st.caption("Blue bars gained over the lookback, red bars lost.")

# ---------- Price paths ----------

with tab_px:
    default = df["symbol"].head(5).tolist()
    picked = st.multiselect(
        "Symbols",
        df["symbol"].tolist(),
        default=default,
        max_selections=MAX_LINES,
        help="Defaults to the five strongest momentum names.",
    )
    prices = load_prices(tuple(picked), lookback)
    fig = go.Figure()
    for i, sym in enumerate(picked):
        g = prices[prices["symbol"] == sym]
        fig.add_scatter(
            x=g["date"],
            y=g["indexed"],
            mode="lines",
            name=sym,
            line=dict(width=2, color=SERIES[i]),
            customdata=g[["close"]],
            hovertemplate=f"<b>{sym}</b> %{{y:.1f}} (${{customdata[0]:.2f}})<extra></extra>",
        )
        if len(g) and len(picked) <= 4:
            fig.add_annotation(
                x=g["date"].iloc[-1], y=g["indexed"].iloc[-1], text=sym, xanchor="left",
                showarrow=False, xshift=6, font=dict(color=INK_2, size=11),
            )
    fig.add_hline(y=100, line=dict(color=AXIS, width=1, dash="dot"))
    fig.update_layout(hovermode="x unified")
    fig.update_yaxes(title="Indexed close (start = 100)")
    st.plotly_chart(style(fig), width="stretch")
    st.caption(f"Each line starts at 100 at the start of the lookback window ({lookback_label}), so steady climbs and one-off jumps look different.")

# ---------- Data quality ----------

with tab_dq:
    summary, findings = load_quality()
    clean = (summary["findings"] == 0).sum()
    st.subheader(f"{clean} of {len(summary)} checks clean")
    for _, row in summary.iterrows():
        n = row["findings"]
        label = f"{'✅' if n == 0 else '⚠️'} **{row['check']}**: {'OK' if n == 0 else f'{n:,} finding(s)'}"
        if n == 0:
            st.markdown(label)
        else:
            with st.expander(label):
                st.dataframe(findings[row["check"]], hide_index=True, width="stretch")

    st.subheader("Coverage by symbol")
    cov = load_coverage()
    st.dataframe(cov, hide_index=True, width="stretch")
