"""
India Stock Screener — Streamlit App
=====================================
Run:  streamlit run stock_screener_app.py

Setups:
  1. Tight Consolidation
  2. Long Base Breakout
  3. Box Setup
"""

import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import requests
import time
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings("ignore")

# ── Page config ───────────────────────────────────────────────────
st.set_page_config(
    page_title="India Stock Screener",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ────────────────────────────────────────────────────
st.markdown("""
<style>
.main { padding-top: 1rem; }
.stButton > button {
    width: 100%;
    border-radius: 6px;
    font-weight: 500;
}
.metric-card {
    background: #f8f9fa;
    border: 1px solid #e9ecef;
    border-radius: 8px;
    padding: 12px 16px;
    margin: 4px 0;
}
.setup-badge {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 20px;
    font-size: 12px;
    font-weight: 600;
}
.tight  { background: #d1ecf1; color: #0c5460; }
.breakout { background: #d4edda; color: #155724; }
.box    { background: #fff3cd; color: #856404; }
div[data-testid="stDataFrame"] { width: 100% !important; }
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════
# NSE INDEX TICKER FETCHER
# ══════════════════════════════════════════════════════════════════

INDEX_FILES = {
    "Nifty 50":           "ind_nifty50list.csv",
    "Nifty Next 50":      "ind_niftynext50list.csv",
    "Nifty 100":          "ind_nifty100list.csv",
    "Nifty 200":          "ind_nifty200list.csv",
    "Nifty 500":          "ind_nifty500list.csv",
    "Nifty Midcap 50":    "ind_niftymidcap50list.csv",
    "Nifty Midcap 150":   "ind_niftymidcap150list.csv",
    "Nifty Smallcap 50":  "ind_niftysmallcap50list.csv",
    "Nifty Smallcap 250": "ind_niftysmallcap250list.csv",
    "Nifty Bank":         "ind_niftybanklist.csv",
    "Nifty IT":           "ind_niftyittlist.csv",
    "Nifty Pharma":       "ind_niftypharmalist.csv",
    "Nifty Auto":         "ind_niftyautolist.csv",
    "Nifty FMCG":         "ind_niftyfmcglist.csv",
}

NSE_BASE = "https://archives.nseindia.com/content/indices/"

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_index_tickers(index_name):
    """Fetch tickers from NSE for a given index."""
    url = NSE_BASE + INDEX_FILES[index_name]
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    try:
        r = requests.get(url, headers=headers, timeout=10)
        r.raise_for_status()
        from io import StringIO
        df = pd.read_csv(StringIO(r.text))
        col = next((c for c in df.columns if "symbol" in c.lower()), df.columns[0])
        tickers = [str(s).strip() + ".NS" for s in df[col].tolist()]
        sectors = {}
        for _, row in df.iterrows():
            sym = str(row[col]).strip() + ".NS"
            sec_col = next((c for c in df.columns if "sector" in c.lower() or "industry" in c.lower()), None)
            sectors[sym] = str(row[sec_col]).strip() if sec_col else "—"
        return tickers, sectors
    except Exception as e:
        st.error(f"Could not fetch {index_name} from NSE: {e}")
        return [], {}


# ══════════════════════════════════════════════════════════════════
# DATA DOWNLOAD
# ══════════════════════════════════════════════════════════════════

@st.cache_data(ttl=1800, show_spinner=False)
def download_stock_data(tickers: tuple, period="1y"):
    """Download OHLCV + info for a list of tickers."""
    data = {}
    info_cache = {}
    tickers = list(tickers)

    batch_size = 20
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i:i+batch_size]
        try:
            raw = yf.download(
                batch, period=period,
                auto_adjust=True, progress=False, threads=True
            )
            for t in batch:
                try:
                    df = raw.xs(t, axis=1, level=1).dropna() if len(batch) > 1 else raw.dropna()
                    if len(df) >= 50:
                        data[t] = df
                except Exception:
                    pass
        except Exception:
            pass
        time.sleep(0.3)

    # Fetch info (mcap) in separate calls — only for stocks that passed data download
    for t in list(data.keys()):
        try:
            info = yf.Ticker(t).info
            info_cache[t] = {
                "mcap":   info.get("marketCap", 0),
                "sector": info.get("sector", "—"),
                "name":   info.get("shortName", t.replace(".NS","")),
            }
        except Exception:
            info_cache[t] = {"mcap": 0, "sector": "—", "name": t.replace(".NS","")}
        time.sleep(0.1)

    return data, info_cache


# ══════════════════════════════════════════════════════════════════
# INDICATORS
# ══════════════════════════════════════════════════════════════════

def ema(series, span):
    return series.ewm(span=span, adjust=False).mean()

def compute_rsi(series, period=14):
    delta = series.diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    rs    = gain / loss.replace(0, np.nan)
    return 100 - 100 / (1 + rs)

def find_resistance_touches(high, close, tolerance_pct=1.5, min_touches=3, lookback=60):
    """
    Find if price has been rejected from the same resistance level
    multiple times within tolerance_pct range.
    Returns (found: bool, resistance_level: float, touch_count: int)
    """
    highs = high.tail(lookback).values
    if len(highs) < min_touches:
        return False, 0, 0

    # Cluster highs within tolerance
    sorted_h = np.sort(highs)[::-1]
    best_level = 0
    best_count = 0

    for candidate in sorted_h[:20]:  # check top 20 high values as candidates
        tol = candidate * (tolerance_pct / 100)
        touches = np.sum((highs >= candidate - tol) & (highs <= candidate + tol))
        if touches >= min_touches and touches > best_count:
            best_count = touches
            best_level = candidate

    return best_count >= min_touches, best_level, best_count


def find_support_touches(low, close, tolerance_pct=1.5, min_touches=3, lookback=60):
    """
    Find if price has been bouncing from the same support level
    multiple times within tolerance_pct range.
    """
    lows = low.tail(lookback).values
    if len(lows) < min_touches:
        return False, 0, 0

    sorted_l = np.sort(lows)
    best_level = 0
    best_count = 0

    for candidate in sorted_l[:20]:
        tol = candidate * (tolerance_pct / 100)
        touches = np.sum((lows >= candidate - tol) & (lows <= candidate + tol))
        if touches >= min_touches and touches > best_count:
            best_count = touches
            best_level = candidate

    return best_count >= min_touches, best_level, best_count


# ══════════════════════════════════════════════════════════════════
# SCREENING LOGIC
# ══════════════════════════════════════════════════════════════════

def check_common_filters(df, info, cfg):
    """Filters common to all 3 setups."""
    close  = df["Close"]
    volume = df["Volume"]

    # Volume filter
    avg_vol = volume.tail(20).mean()
    if avg_vol < cfg["min_volume"]:
        return False, "Low volume"

    # Mcap filter (in crores)
    mcap_cr = info.get("mcap", 0) / 1e7
    if mcap_cr > 0 and mcap_cr < cfg["min_mcap_cr"]:
        return False, f"Mcap ₹{mcap_cr:.0f}Cr < ₹{cfg['min_mcap_cr']}Cr"

    # Uptrend filter
    if cfg["uptrend_method"] == "52w_high":
        high_52w = close.tail(252).max()
        if close.iloc[-1] < high_52w * (1 - cfg["from_52w_high_pct"] / 100):
            return False, f"Not within {cfg['from_52w_high_pct']}% of 52w high"
    else:
        # Price progression: 1yr ago < 6mo ago < today
        if len(close) >= 252:
            p_1y  = close.iloc[-252]
            p_6m  = close.iloc[-126]
            p_now = close.iloc[-1]
            if not (p_1y < p_6m < p_now):
                return False, "Not in price progression uptrend"

    return True, "OK"


def screen_tight_consolidation(df, info, cfg):
    """
    Tight Consolidation:
    Price within ±X% for last N sessions
    + common filters
    """
    ok, reason = check_common_filters(df, info, cfg)
    if not ok:
        return False, reason, {}

    close = df["Close"]
    n     = cfg["consol_sessions"]
    pct   = cfg["consol_pct"]

    recent = close.tail(n)
    if len(recent) < n:
        return False, "Insufficient data", {}

    base_price = recent.iloc[0]
    max_dev    = ((recent.max() - recent.min()) / base_price) * 100

    if max_dev > pct * 2:
        return False, f"Range {max_dev:.1f}% > ±{pct}%", {}

    return True, "Tight Consolidation ✓", {
        "consol_range_pct": round(max_dev, 2),
        "sessions":         n,
    }


def screen_long_base_breakout(df, info, cfg):
    """
    Long Base Breakout:
    Tight consolidation + uptrend + volume + mcap
    + Resistance rejections (min 3 times)
    """
    ok, reason = check_common_filters(df, info, cfg)
    if not ok:
        return False, reason, {}

    close  = df["Close"]
    high   = df["High"]
    volume = df["Volume"]

    # Resistance touches
    res_found, res_level, res_count = find_resistance_touches(
        high, close,
        tolerance_pct=cfg["resistance_tolerance_pct"],
        min_touches=cfg["min_resistance_touches"],
        lookback=cfg["resistance_lookback"],
    )

    if not res_found:
        return False, f"< {cfg['min_resistance_touches']} resistance touches", {}

    # Check if price is near or just broke the resistance
    current_price = close.iloc[-1]
    near_breakout = current_price >= res_level * 0.98  # within 2% of resistance

    return True, "Long Base Breakout ✓", {
        "resistance_level":  round(res_level, 2),
        "resistance_touches": res_count,
        "near_breakout":     near_breakout,
    }


def screen_box_setup(df, info, cfg):
    """
    Box Setup:
    Long base breakout conditions
    + Support rejections (min 3 times)
    = defined box with both floor and ceiling
    """
    ok, reason, lbb_data = screen_long_base_breakout(df, info, cfg)
    if not ok:
        return False, reason, {}

    low   = df["Low"]
    close = df["Close"]

    # Support touches
    sup_found, sup_level, sup_count = find_support_touches(
        low, close,
        tolerance_pct=cfg["support_tolerance_pct"],
        min_touches=cfg["min_support_touches"],
        lookback=cfg["resistance_lookback"],
    )

    if not sup_found:
        return False, f"< {cfg['min_support_touches']} support touches", {}

    # Validate box: support must be below resistance
    res_level = lbb_data.get("resistance_level", 0)
    if sup_level >= res_level:
        return False, "Support not below resistance", {}

    box_height_pct = ((res_level - sup_level) / sup_level) * 100

    return True, "Box Setup ✓", {
        **lbb_data,
        "support_level":   round(sup_level, 2),
        "support_touches": sup_count,
        "box_height_pct":  round(box_height_pct, 1),
    }


# ══════════════════════════════════════════════════════════════════
# CHART
# ══════════════════════════════════════════════════════════════════

def build_chart(ticker, df, result_data, setup_type, cfg):
    """Build a Plotly candlestick chart with EMAs and signal levels."""
    close  = df["Close"]
    open_  = df["Open"]
    high   = df["High"]
    low    = df["Low"]
    volume = df["Volume"]

    fig = go.Figure()

    # Candlestick
    fig.add_trace(go.Candlestick(
        x=df.index, open=open_, high=high, low=low, close=close,
        name="Price",
        increasing_line_color="#26a69a",
        decreasing_line_color="#ef5350",
        increasing_fillcolor="#26a69a",
        decreasing_fillcolor="#ef5350",
    ))

    # EMAs
    ema_colors = {20: "#FF9800", 50: "#2196F3", 100: "#9C27B0", 200: "#F44336"}
    for span, color in ema_colors.items():
        e = ema(close, span)
        fig.add_trace(go.Scatter(
            x=df.index, y=e,
            name=f"EMA {span}",
            line=dict(color=color, width=1.5),
            opacity=0.85,
        ))

    # Resistance level
    if "resistance_level" in result_data:
        rl = result_data["resistance_level"]
        tol = rl * (cfg["resistance_tolerance_pct"] / 100)
        fig.add_hrect(
            y0=rl - tol, y1=rl + tol,
            fillcolor="rgba(239,83,80,0.12)",
            line_width=0,
            annotation_text=f"Resistance zone ({result_data['resistance_touches']}x)",
            annotation_position="top right",
            annotation_font_color="#ef5350",
        )
        fig.add_hline(
            y=rl, line_dash="dash",
            line_color="#ef5350", line_width=1.5,
        )

    # Support level
    if "support_level" in result_data:
        sl = result_data["support_level"]
        tol = sl * (cfg["support_tolerance_pct"] / 100)
        fig.add_hrect(
            y0=sl - tol, y1=sl + tol,
            fillcolor="rgba(38,166,154,0.12)",
            line_width=0,
            annotation_text=f"Support zone ({result_data['support_touches']}x)",
            annotation_position="bottom right",
            annotation_font_color="#26a69a",
        )
        fig.add_hline(
            y=sl, line_dash="dash",
            line_color="#26a69a", line_width=1.5,
        )

    # Consolidation shading (last N sessions)
    if setup_type == "Tight Consolidation":
        n = cfg["consol_sessions"]
        if len(df) >= n:
            shade_start = df.index[-n]
            fig.add_vrect(
                x0=shade_start, x1=df.index[-1],
                fillcolor="rgba(33,150,243,0.08)",
                line_width=0,
                annotation_text=f"Consolidation ({n} sessions)",
                annotation_position="top left",
                annotation_font_color="#2196F3",
            )

    # Volume bars (secondary y-axis)
    colors = ["#26a69a" if c >= o else "#ef5350"
              for c, o in zip(close, open_)]
    fig.add_trace(go.Bar(
        x=df.index, y=volume,
        name="Volume",
        marker_color=colors,
        opacity=0.4,
        yaxis="y2",
    ))

    name = ticker.replace(".NS", "")
    setup_colors = {
        "Tight Consolidation": "#0c5460",
        "Long Base Breakout":  "#155724",
        "Box Setup":           "#856404",
    }

    fig.update_layout(
        title=dict(
            text=f"<b>{name}</b> — {setup_type}",
            font=dict(size=18, color=setup_colors.get(setup_type, "#333")),
        ),
        xaxis=dict(
            rangeslider=dict(visible=False),
            type="date",
            showgrid=True,
            gridcolor="#f0f0f0",
        ),
        yaxis=dict(
            showgrid=True,
            gridcolor="#f0f0f0",
            side="right",
        ),
        yaxis2=dict(
            overlaying="y",
            side="left",
            showgrid=False,
            showticklabels=False,
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom", y=1.02,
            xanchor="left", x=0,
            font=dict(size=11),
        ),
        height=520,
        margin=dict(l=20, r=60, t=80, b=20),
        plot_bgcolor="white",
        paper_bgcolor="white",
        hovermode="x unified",
    )

    return fig


# ══════════════════════════════════════════════════════════════════
# MAIN APP
# ══════════════════════════════════════════════════════════════════

def main():
    # ── Header ────────────────────────────────────────────────────
    st.title("📈 India Stock Screener")
    st.caption("Tight Consolidation · Long Base Breakout · Box Setup")

    # ── Sidebar — Configuration ───────────────────────────────────
    with st.sidebar:
        st.header("⚙️ Configuration")

        # Setup selection
        st.subheader("Setup")
        setup_type = st.selectbox(
            "Screening setup",
            ["Tight Consolidation", "Long Base Breakout", "Box Setup"],
        )

        st.divider()

        # Stock universe
        st.subheader("Universe")
        source = st.radio("Source", ["Index", "Manual tickers"], horizontal=True)

        selected_tickers = []
        sector_map       = {}

        if source == "Index":
            index_name = st.selectbox("Select index", list(INDEX_FILES.keys()))
            if st.button("📥 Load index tickers", use_container_width=True):
                with st.spinner(f"Fetching {index_name} from NSE..."):
                    tickers, sectors = fetch_index_tickers(index_name)
                    st.session_state["loaded_tickers"] = tickers
                    st.session_state["loaded_sectors"]  = sectors
                    st.session_state["loaded_index"]    = index_name

            if "loaded_tickers" in st.session_state:
                selected_tickers = st.session_state["loaded_tickers"]
                sector_map       = st.session_state.get("loaded_sectors", {})
                st.success(f"✓ {len(selected_tickers)} tickers — {st.session_state.get('loaded_index','')}")
        else:
            raw = st.text_area(
                "Enter tickers (one per line or comma-separated)",
                placeholder="RELIANCE\nTCS\nHDFCBANK\nor: RELIANCE, TCS, INFY",
                height=120,
            )
            if raw.strip():
                parts = [t.strip().upper() for t in raw.replace(",", "\n").splitlines() if t.strip()]
                selected_tickers = [t if t.endswith(".NS") else t + ".NS" for t in parts]
                st.info(f"{len(selected_tickers)} tickers entered")

        st.divider()

        # Common filters
        st.subheader("Common Filters")
        min_volume   = st.number_input("Min avg volume (shares)", value=100000, step=10000, format="%d")
        min_mcap_cr  = st.number_input("Min market cap (₹ Crores)", value=500, step=100, format="%d")

        uptrend_method = st.selectbox(
            "Uptrend method",
            ["52w_high", "price_progression"],
            format_func=lambda x: "Within X% of 52w High" if x == "52w_high" else "Price Progression (1yr<6mo<now)"
        )
        from_52w_high_pct = 30
        if uptrend_method == "52w_high":
            from_52w_high_pct = st.slider("Max % below 52w high", 10, 50, 30)

        st.divider()

        # Tight Consolidation params
        st.subheader("Tight Consolidation")
        consol_sessions = st.slider("Sessions (N)", 3, 15, 7)
        consol_pct      = st.slider("Range (±%)", 0.5, 5.0, 2.0, step=0.5)

        if setup_type in ["Long Base Breakout", "Box Setup"]:
            st.divider()
            st.subheader("Resistance (Long Base)")
            resistance_tolerance_pct  = st.slider("Resistance tolerance (%)", 0.5, 3.0, 1.5, step=0.5)
            min_resistance_touches    = st.slider("Min resistance touches", 2, 6, 3)
            resistance_lookback       = st.slider("Lookback (sessions)", 30, 120, 60)

        if setup_type == "Box Setup":
            st.divider()
            st.subheader("Support (Box)")
            support_tolerance_pct = st.slider("Support tolerance (%)", 0.5, 3.0, 1.5, step=0.5)
            min_support_touches   = st.slider("Min support touches", 2, 6, 3)

        st.divider()

        run_btn = st.button("🔍 Run Screener", type="primary", use_container_width=True)

    # ── Build config dict ─────────────────────────────────────────
    cfg = {
        "min_volume":               min_volume,
        "min_mcap_cr":              min_mcap_cr,
        "uptrend_method":           uptrend_method,
        "from_52w_high_pct":        from_52w_high_pct,
        "consol_sessions":          consol_sessions,
        "consol_pct":               consol_pct,
        "resistance_tolerance_pct": locals().get("resistance_tolerance_pct", 1.5),
        "min_resistance_touches":   locals().get("min_resistance_touches", 3),
        "resistance_lookback":      locals().get("resistance_lookback", 60),
        "support_tolerance_pct":    locals().get("support_tolerance_pct", 1.5),
        "min_support_touches":      locals().get("min_support_touches", 3),
    }

    # ── Main content ──────────────────────────────────────────────
    if not run_btn:
        # Landing state
        st.markdown("### How to use")
        c1, c2, c3 = st.columns(3)
        with c1:
            st.info("**1. Pick a setup** from the sidebar\n\nTight Consolidation, Long Base Breakout, or Box Setup")
        with c2:
            st.info("**2. Choose universe**\n\nSelect an NSE index or type your own tickers")
        with c3:
            st.info("**3. Run screener**\n\nClick Run to scan. Then click any stock in the results to see its chart")

        st.markdown("### Setup descriptions")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown("""
**🔵 Tight Consolidation**
Price trading within a narrow ±2% range for the last N sessions.
Stock is in uptrend, liquid, and building energy before a move.
""")
        with col2:
            st.markdown("""
**🟢 Long Base Breakout**
All tight consolidation conditions, PLUS the stock has repeatedly
tested the same resistance level (min 3 times). Price coiling under a ceiling.
""")
        with col3:
            st.markdown("""
**🟡 Box Setup**
All long base breakout conditions, PLUS a clearly defined support floor
(min 3 bounces). Stock is trapped in a box — watch for the breakout.
""")
        return

    # ── Run screener ──────────────────────────────────────────────
    if not selected_tickers:
        st.warning("⚠️ No tickers selected. Load an index or enter tickers in the sidebar.")
        return

    results   = []
    failed    = []
    progress  = st.progress(0, text="Downloading data...")

    # Download
    with st.spinner(f"Downloading {len(selected_tickers)} stocks..."):
        data, info_cache = download_stock_data(tuple(selected_tickers))

    progress.progress(50, text="Running screener...")

    # Screen
    screen_fn = {
        "Tight Consolidation": screen_tight_consolidation,
        "Long Base Breakout":  screen_long_base_breakout,
        "Box Setup":           screen_box_setup,
    }[setup_type]

    for i, ticker in enumerate(selected_tickers):
        if ticker not in data:
            failed.append(ticker)
            continue

        df   = data[ticker]
        info = info_cache.get(ticker, {})

        try:
            matched, reason, extra = screen_fn(df, info, cfg)
        except Exception as e:
            matched, reason, extra = False, str(e), {}

        if matched:
            close    = df["Close"]
            volume   = df["Volume"]
            high_52w = close.tail(252).max()
            low_52w  = close.tail(252).min()
            price    = close.iloc[-1]
            avg_vol  = volume.tail(20).mean()
            mcap_cr  = info.get("mcap", 0) / 1e7

            results.append({
                "ticker":      ticker,
                "name":        info.get("name", ticker.replace(".NS","")),
                "sector":      info.get("sector") or sector_map.get(ticker, "—"),
                "price":       round(price, 2),
                "change_pct":  round((price / close.iloc[-2] - 1) * 100, 2) if len(close) > 1 else 0,
                "avg_volume":  int(avg_vol),
                "mcap_cr":     round(mcap_cr, 0),
                "52w_high":    round(high_52w, 2),
                "52w_low":     round(low_52w, 2),
                "pct_from_52w_high": round((price / high_52w - 1) * 100, 1),
                "setup":       setup_type,
                "reason":      reason,
                **extra,
                "_df":         df,
            })

        progress.progress(int(50 + 50 * (i+1) / len(selected_tickers)))

    progress.empty()

    # ── Results ───────────────────────────────────────────────────
    st.markdown(f"## Results — {setup_type}")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Scanned",  len(selected_tickers))
    col2.metric("Matched",  len(results))
    col3.metric("Failed DL", len(failed))
    col4.metric("Hit rate",  f"{len(results)/max(len(selected_tickers),1)*100:.1f}%")

    if not results:
        st.warning("No stocks matched the selected setup with current parameters. Try relaxing the filters in the sidebar.")
        return

    st.divider()

    # ── Summary Table ─────────────────────────────────────────────
    st.markdown("### 📋 Summary Table")
    st.caption("Click a row, then scroll down to see the chart")

    table_rows = []
    for r in results:
        row = {
            "Ticker":       r["ticker"].replace(".NS",""),
            "Name":         r["name"],
            "Sector":       r["sector"],
            "Price (₹)":    r["price"],
            "Day Chg %":    r["change_pct"],
            "Avg Vol":      f"{r['avg_volume']:,}",
            "MCap (Cr)":    f"₹{r['mcap_cr']:,.0f}",
            "52w High":     r["52w_high"],
            "From 52w H %": r["pct_from_52w_high"],
        }
        if "consol_range_pct" in r:
            row["Consol Range %"] = r["consol_range_pct"]
        if "resistance_level" in r:
            row["Resistance"]     = r["resistance_level"]
            row["Res Touches"]    = r["resistance_touches"]
        if "support_level" in r:
            row["Support"]        = r["support_level"]
            row["Sup Touches"]    = r["support_touches"]
        if "box_height_pct" in r:
            row["Box Height %"]   = r["box_height_pct"]
        table_rows.append(row)

    df_table = pd.DataFrame(table_rows)
    st.dataframe(
        df_table,
        use_container_width=True,
        height=min(400, 60 + len(table_rows) * 35),
    )

    st.divider()

    # ── Stock list with chart buttons ─────────────────────────────
    st.markdown("### 📊 Charts — click a stock to expand")

    badge_colors = {
        "Tight Consolidation": "tight",
        "Long Base Breakout":  "breakout",
        "Box Setup":           "box",
    }

    for r in results:
        ticker   = r["ticker"]
        name     = r["name"]
        price    = r["price"]
        chg      = r["change_pct"]
        chg_icon = "▲" if chg >= 0 else "▼"
        chg_col  = "green" if chg >= 0 else "red"

        with st.expander(
            f"**{ticker.replace('.NS','')}** — {name}  |  "
            f"₹{price:,.2f}  "
            f"{'▲' if chg>=0 else '▼'} {abs(chg):.2f}%  |  "
            f"{r['sector']}",
            expanded=False,
        ):
            # Metrics row
            m_cols = st.columns(5)
            m_cols[0].metric("Price",       f"₹{price:,.2f}", f"{chg:+.2f}%")
            m_cols[1].metric("Avg Volume",  f"{r['avg_volume']:,}")
            m_cols[2].metric("MCap",        f"₹{r['mcap_cr']:,.0f} Cr")
            m_cols[3].metric("52w High",    f"₹{r['52w_high']:,.2f}")
            m_cols[4].metric("From 52w H",  f"{r['pct_from_52w_high']:.1f}%")

            # Setup-specific metrics
            detail_cols = []
            if "consol_range_pct" in r:
                detail_cols.append(("Consol Range", f"±{r['consol_range_pct']/2:.2f}%"))
            if "resistance_level" in r:
                detail_cols.append(("Resistance", f"₹{r['resistance_level']:,.2f}"))
                detail_cols.append(("Res Touches", str(r["resistance_touches"])))
            if "support_level" in r:
                detail_cols.append(("Support", f"₹{r['support_level']:,.2f}"))
                detail_cols.append(("Sup Touches", str(r["support_touches"])))
            if "box_height_pct" in r:
                detail_cols.append(("Box Height", f"{r['box_height_pct']:.1f}%"))

            if detail_cols:
                dcols = st.columns(len(detail_cols))
                for col, (label, val) in zip(dcols, detail_cols):
                    col.metric(label, val)

            # Chart
            fig = build_chart(ticker, r["_df"], r, setup_type, cfg)
            st.plotly_chart(fig, use_container_width=True, key=f"chart_{ticker}")

    # ── Footer ────────────────────────────────────────────────────
    st.divider()
    st.caption(
        "⚠️ For educational purposes only. Not financial advice. "
        "Always do your own research before making investment decisions."
    )


if __name__ == "__main__":
    main()