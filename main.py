import streamlit as st
import requests
import pandas as pd
import concurrent.futures
from streamlit_autorefresh import st_autorefresh
import time
import os

import datafeed
from datafeed import ANCHOR, EXCHANGES


# --- GLOBAL CONFIGURATION ---
st.set_page_config(
    page_title="Funding Terminal", 
    layout="wide", 
    page_icon="chart"
)

# Global Auto-refresh (Every 2 minutes)
st_autorefresh(interval=120 * 1000, key="global_refresh")

# Global CSS (Green Progress Bars)
st.markdown("""
    <style>
    .stProgress > div > div > div > div { background-color: #00E599; }
    </style>
""", unsafe_allow_html=True)

# ==============================================================================
#                               HELPER FUNCTIONS
# ==============================================================================
def safe_float(value):
    if value is None: return 0.0
    try: return float(value)
    except: return 0.0

def get_opportunity_score(spread):
    if spread > 100: return "HIGH"
    elif spread > 30: return "MEDIUM"
    return "LOW"

# ==============================================================================
#                               PAGE 1 : HIP-3 (BUILDERS ARBITRAGE)
# ==============================================================================
def render_hip3_page():
    st.markdown("## HIP-3 Arbitrage")
    
    HL_INFO_URL = "https://api.hyperliquid.xyz/info"
    
    # Builder Name Mapping
    BUILDER_MAPPING = {
        "km": "Kinetiq Markets", "xyz": "Trade[xyz]", "flx": "Felix",
        "hyna": "HyENA", "vntl": "Ventuals", "cash": "Dreamcash",
        "abcd": "ABCD"
    }

    def get_underlying(symbol):
        if ':' in symbol: return symbol.split(':')[-1]
        return symbol

    @st.cache_data(ttl=60)
    def fetch_and_pivot_hip3():
        try:
            dexs_resp = requests.post(HL_INFO_URL, json={"type": "perpDexs"}, timeout=5).json()
            all_assets = []

            def fetch_dex(dex_info):
                if dex_info is None: return []
                builder_name = dex_info.get('name')
                if not builder_name or builder_name == "test": return []
                try:
                    time.sleep(0.05)
                    r = requests.post(HL_INFO_URL, json={"type": "metaAndAssetCtxs", "dex": builder_name}, timeout=10).json()
                    if not r or len(r) < 2: return []
                    universe, context = r[0]['universe'], r[1]
                    rows = []
                    for i, asset in enumerate(universe):
                        ctx = context[i] if i < len(context) else {}
                        funding_apr = safe_float(ctx.get('funding')) * 24 * 365 * 100
                        rows.append({
                            "Builder": builder_name,
                            "Symbol": get_underlying(asset['name']),
                            "Funding APR": funding_apr
                        })
                    return rows
                except: return []

            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                results = list(executor.map(fetch_dex, dexs_resp))
            for res in results: all_assets.extend(res)
            
            df = pd.DataFrame(all_assets)
            if df.empty: return pd.DataFrame()
            
            df_pivot = df.pivot_table(index='Symbol', columns='Builder', values='Funding APR', aggfunc='mean')
            return df_pivot.rename(columns=BUILDER_MAPPING)
        except Exception as e:
            st.error(f"HIP-3 API Error: {e}")
            return pd.DataFrame()

    # --- HIP-3 UI ---
    df_matrix = fetch_and_pivot_hip3()
    
    if not df_matrix.empty:
        # --- FILTERS SECTION ---
        st.sidebar.subheader("Builders Filters")
        
        all_builders = list(df_matrix.columns)
        selected_builders = []
        
        # Boucle simple : une case par builder, cochée par défaut
        for b in all_builders:
            if st.sidebar.checkbox(b, value=True, key=f"h3_{b}"):
                selected_builders.append(b)
            
        if len(selected_builders) < 2:
            st.warning("Please select at least 2 builders.")
            return

        # --- DATA PROCESSING ---
        df_sel = df_matrix[selected_builders].dropna(thresh=2).copy()
        df_sel['APR Spread'] = df_sel.max(axis=1) - df_sel.min(axis=1)
        
        def get_trade_action(row):
            vals = row[selected_builders].dropna()
            if len(vals) < 2: return "-"
            return f"LONG {vals.idxmin()} / SHORT {vals.idxmax()}"

        df_sel['Trade Action'] = df_sel.apply(get_trade_action, axis=1)
        
        # Sort only (No filtering on spread or rows limit)
        df_final = df_sel.sort_values('APR Spread', ascending=False)

        st.write(f"Active Comparison: **{', '.join(selected_builders)}**")

        # Column Config
        col_config = {b: st.column_config.NumberColumn(b, format="%.2f%%", width="small") for b in selected_builders}
        col_config["APR Spread"] = st.column_config.NumberColumn("Spread", format="%.2f%%", width="small")
        col_config["Trade Action"] = st.column_config.TextColumn("Trade Action", width="large")

        # Styling
        def style_hip3(row):
            styles = ['' for _ in row.index]
            vals = row[selected_builders]
            if vals.count() >= 2:
                styles[row.index.get_loc(vals.idxmin())] = 'background-color: #006400; color: white; font-weight: bold;'
                styles[row.index.get_loc(vals.idxmax())] = 'background-color: #8B0000; color: white; font-weight: bold;'
            if row['APR Spread'] > 100:
                styles[row.index.get_loc('APR Spread')] = 'color: #FFD700; font-weight: bold;'
            return styles

        st.dataframe(
            df_final.style.apply(style_hip3, axis=1).format({c: "{:.2f}%" for c in selected_builders + ['APR Spread']}, na_rep="-"),
            use_container_width=True, 
            height=min((len(df_final)+1)*35+3, 1000),
            column_order=selected_builders + ['APR Spread', 'Trade Action'],
            column_config=col_config
        )
    else:
        st.info("Loading HIP-3 Data...")

# ==============================================================================
#                               PAGE 2 : MAINNET (MULTI-DEX)
# ==============================================================================
HISTORY_URL = "https://raw.githubusercontent.com/Colin503/dashboard_funding_rates/main/funding_history.parquet"

# Counterparties ticked on first load; the others stay available in the sidebar.
DEFAULT_COUNTERPARTS = {"Hyperliquid"}


@st.cache_data(ttl=120)
def load_live():
    return datafeed.fetch_all()


@st.cache_data(ttl=300)
def load_history():
    """Moyennes historiques par (symbol, asset_class)."""
    try:
        df = pd.read_parquet(HISTORY_URL, engine="pyarrow")
    except Exception as exc:  # noqa: BLE001
        print(f"Erreur lecture historique: {exc}")
        return pd.DataFrame()

    if "asset_class" not in df.columns:
        # Historique anterieur a la separation RWA : tout etait du crypto.
        df["asset_class"] = "Crypto"
    df["asset_class"] = df["asset_class"].fillna("Crypto")

    cols = [c for c in EXCHANGES if c in df.columns]
    if not cols:
        return pd.DataFrame()

    avg = df.groupby(["symbol", "asset_class"])[cols].mean().reset_index()
    return avg.rename(columns={c: f"{c}_avg" for c in cols})


def anchored_trade(row, counterparts):
    """Spread et sens du trade, Variational obligatoirement sur une jambe.

    Deux montages possibles :
      LONG Variational / SHORT X  -> on encaisse  X - Variational
      SHORT Variational / LONG X  -> on encaisse  Variational - X
    On retient le plus rentable des deux.
    """
    nan = float("nan")
    anchor_val = row.get(ANCHOR)
    if pd.isna(anchor_val):
        return nan, None, None

    vals = row[counterparts].dropna().astype(float)
    if vals.empty:
        return nan, None, None

    long_anchor_gain = vals.max() - anchor_val   # short la venue qui paie le plus
    short_anchor_gain = anchor_val - vals.min()  # long la venue qui paie le moins

    if long_anchor_gain >= short_anchor_gain:
        other = vals.idxmax()
        return long_anchor_gain, f"LONG {ANCHOR} / SHORT {other}", (ANCHOR, other)
    other = vals.idxmin()
    return short_anchor_gain, f"SHORT {ANCHOR} / LONG {other}", (other, ANCHOR)


def pair_history(row):
    """Spread moyen historique de la MEME paire que le trade live.

    Renvoie NaN et non None quand l'historique manque : une colonne objet
    contenant des None fait planter le formatage du Styler.
    """
    pair = row.get("_pair")
    if not isinstance(pair, tuple):
        return float("nan")
    long_dex, short_dex = pair
    long_avg, short_avg = row.get(f"{long_dex}_avg"), row.get(f"{short_dex}_avg")
    if pd.notna(long_avg) and pd.notna(short_avg):
        return short_avg - long_avg
    return float("nan")


def build_table(df_live, df_hist, active, show_history):
    counterparts = [c for c in active if c != ANCHOR]
    df = df_live.copy()

    if not df_hist.empty:
        df = df.merge(df_hist, on=["symbol", "asset_class"], how="left")

    # Variational obligatoire + au moins une contrepartie cotee.
    df = df[df[ANCHOR].notna() & (df[counterparts].notna().sum(axis=1) >= 1)].copy()
    if df.empty:
        return df, counterparts

    res = df.apply(lambda r: anchored_trade(r, counterparts), axis=1, result_type="expand")
    df["APR Spread"] = pd.to_numeric(res[0], errors="coerce")
    df["Trade Action"], df["_pair"] = res[1], res[2]
    df = df[df["APR Spread"].notna()].copy()
    if df.empty:
        return df, counterparts

    df["Opportunity"] = df["APR Spread"].apply(get_opportunity_score)
    if show_history and not df_hist.empty:
        df["48h Pair Avg"] = pd.to_numeric(df.apply(pair_history, axis=1), errors="coerce")

    return df.sort_values("APR Spread", ascending=False), counterparts


def render_table(df, active, label_col, show_history):
    cols = [label_col] + active + ["APR Spread"]
    # Colonne masquee tant qu'aucun historique n'existe pour ces paires
    # (les symboles RWA sont neufs, le parquet met quelques jours a se remplir).
    if show_history and df.get("48h Pair Avg") is not None and df["48h Pair Avg"].notna().any():
        cols.append("48h Pair Avg")
    cols += ["Opportunity", "Trade Action"]
    cols = [c for c in cols if c in df.columns]

    # _pair n'est pas une colonne affichee : on la retrouve par l'index de ligne.
    pairs = df["_pair"]

    def style_row(row):
        styles = ["" for _ in row.index]
        pair = pairs.get(row.name)
        if isinstance(pair, tuple):
            long_dex, short_dex = pair
            for dex, css in ((long_dex, "background-color: #006400; color: white; font-weight: bold;"),
                             (short_dex, "background-color: #8B0000; color: white; font-weight: bold;")):
                if dex in row.index:
                    styles[row.index.get_loc(dex)] = css

        avg = row.get("48h Pair Avg")
        spread = row.get("APR Spread")
        if pd.notna(avg) and pd.notna(spread) and "APR Spread" in row.index:
            sign_flip = (spread > 0 > avg) or (spread < 0 < avg)
            huge_diff = abs(spread - avg) > 5 and abs(spread) > abs(avg) * 2
            if sign_flip or huge_diff:
                styles[row.index.get_loc("APR Spread")] = "color: #FFD700; font-weight: bold;"
        return styles

    numeric = [c for c in cols if c not in (label_col, "Opportunity", "Trade Action")]
    col_config = {c: st.column_config.NumberColumn(c, format="%.2f%%", width="small") for c in numeric}
    col_config["Trade Action"] = st.column_config.TextColumn("Trade Action", width="large")

    st.dataframe(
        df[cols].style.apply(style_row, axis=1),
        use_container_width=True,
        hide_index=True,
        height=min((len(df) + 1) * 35 + 3, 1000),
        column_order=cols,
        column_config=col_config,
    )


def render_mainnet_page():
    st.markdown("## Multi-DEX Arbitrage")

    st.sidebar.subheader("Exchanges Selection")
    st.sidebar.checkbox(ANCHOR, value=True, disabled=True, key="anchor_locked")
    active = [ANCHOR] + [
        ex for ex in EXCHANGES
        if ex != ANCHOR and st.sidebar.checkbox(ex, value=ex in DEFAULT_COUNTERPARTS, key=f"mn_{ex}")
    ]
    show_history = st.sidebar.checkbox("Show Pair 48h Avg", value=True, key="mn_hist")

    df_crypto, df_rwa, var_names, errors = load_live()
    df_crypto["asset_class"] = "Crypto"
    df_rwa["asset_class"] = "RWA"
    df_hist = load_history()

    if errors:
        st.warning("Unavailable venues: " + " · ".join(f"**{k}**" for k in errors))

    if len(active) < 2:
        st.warning(f"Select at least **one exchange** besides {ANCHOR}.")
        return

    st.write(f"Counterparties: **{', '.join(c for c in active if c != ANCHOR)}**")

    st.subheader("Crypto")
    table, _ = build_table(df_crypto, df_hist, active, show_history)
    if table.empty:
        st.info(f"No crypto pair quoted on {ANCHOR} and a counterparty.")
    else:
        st.caption(f"{len(table)} crypto pairs tradable from {ANCHOR}.")
        render_table(table, active, "symbol", show_history)

    st.divider()

    st.subheader("RWA")
    state, label = datafeed.us_market_session()
    (st.success if state == "open" else st.info)(label)

    table, _ = build_table(df_rwa, df_hist, active, show_history)
    if table.empty:
        st.info(f"No RWA pair quoted on {ANCHOR} and a counterparty.")
    else:
        st.caption(f"{len(table)} RWA pairs tradable from {ANCHOR}.")
        render_table(table, active, "label", show_history)

    pending = datafeed.unmapped_rwa_candidates(var_names)
    if pending:
        with st.expander(f"{len(pending)} unmapped {ANCHOR} listing(s) that look like RWA"):
            st.caption("Add them to `RWA_REGISTRY` in `assets.py` if they really are RWA.")
            st.table(pd.DataFrame(pending, columns=["ticker", "name"]))

# ==============================================================================
#                               SIDEBAR NAVIGATION
# ==============================================================================

st.sidebar.title("Navigation")
page = st.sidebar.radio("Select Dashboard:", ["HIP-3", "Multi-DEX"])
st.sidebar.markdown("---")

if page == "HIP-3":
    render_hip3_page()
else:
    render_mainnet_page()

# --- FOOTER ---
st.markdown("<br>", unsafe_allow_html=True)
col_aff, col_social = st.columns([3, 1])

with col_aff:
    st.markdown("""
        <div style="background-color: rgba(255, 255, 255, 0.03); padding: 15px; border-radius: 8px; border-left: 4px solid #006400;">
            <p style="margin: 0; font-size: 13px; color: #888; text-transform: uppercase; letter-spacing: 1px;">Ready to trade ?</p>
            <a href="https://app.hyperliquid.xyz/join/CACA" target="_blank" style="color: #008000; text-decoration: none; font-weight: 600; font-size: 14px;">
            Capture these spreads on Hyperliquid.</a>
        </div>
    """, unsafe_allow_html=True)

with col_social:
    st.markdown("""
         <div style="text-align: right; padding-top: 10px;">
            <p style="margin-bottom: 8px; font-size: 12px; color: #666;">Developer</p>
            <a href="https://x.com/C0l1n503" target="_blank" style="text-decoration: none;">
                <span style="color: #666; font-size: 12px; margin-right: 10px;">@C0l1n503</span>
                <img src="https://upload.wikimedia.org/wikipedia/commons/thumb/0/09/X_%28formerly_Twitter%29_logo_late_2025.svg/330px-X_%28formerly_Twitter%29_logo_late_2025.svg.png" width="18" style="filter: opacity(0.6);">
            </a>
        </div>
    """, unsafe_allow_html=True)



