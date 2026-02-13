import streamlit as st
import requests
import pandas as pd
import concurrent.futures
from streamlit_autorefresh import st_autorefresh
import time
import os
from datetime import datetime, timedelta

# --- GLOBAL CONFIGURATION ---
st.set_page_config(
    page_title="Funding Terminal", 
    layout="wide", 
    page_icon="⚡"
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
    if spread > 100: return "🔥 HIGH"
    elif spread > 30: return "⚡ MEDIUM"
    return "❄️ LOW"

# ==============================================================================
#                               PAGE 1 : HIP-3 (BUILDERS ARBITRAGE)
# ==============================================================================
def render_hip3_page():
    st.markdown("## 🏗️ HIP-3 Arbitrage")
    
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
        st.sidebar.subheader("🔎 Builders Filters")
        
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
            return f"🟢 LONG {vals.idxmin()} / 🔴 SHORT {vals.idxmax()}"

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
def render_mainnet_page():
    st.markdown("## 🌐 Multi-DEX Arbitrage")
    
    VAR_URL = "https://omni-client-api.prod.ap-northeast-1.variational.io/metadata/stats"
    HL_URL = "https://api.hyperliquid.xyz/info"
    LIGHTER_URL = "https://mainnet.zklighter.elliot.ai/api/v1/funding-rates"
    EXT_URL = "https://api.starknet.extended.exchange/api/v1/info/markets"
    PAC_URL = "https://api.pacifica.fi/api/v1/info"

    EXT_API_KEY = os.environ.get("EXT_API_KEY", "693ed8445baad0ae3b75c6d991bac4d9")
    PACIFICA_API_KEY = os.environ.get("PACIFICA_API_KEY", "5h53egePzL1aM958CXWs9x4oY7FbnammiC7YiX7XErvD3TYk9L214kqP6j8GJ6wTQbnQzAk4Mbzxfo7aGKzrzP9s")

    @st.cache_data(ttl=120)
    def fetch_mainnet_data():
        def get_var():
            try:
                r = requests.get(VAR_URL, timeout=3).json()
                df = pd.DataFrame(r['listings'])
                df['Variational'] = pd.to_numeric(df['funding_rate']) * 100
                return df[['ticker', 'Variational']].rename(columns={'ticker': 'symbol'})
            except: return pd.DataFrame(columns=['symbol', 'Variational'])

        def get_hl():
            try:
                r = requests.post(HL_URL, json={"type": "metaAndAssetCtxs"}, timeout=3).json()
                data = [{'symbol': m['name'], 'Hyperliquid': (float(r[1][i]['funding']) * 3 * 365 * 100 * 8)} for i, m in enumerate(r[0]['universe'])]
                return pd.DataFrame(data)
            except: return pd.DataFrame(columns=['symbol', 'Hyperliquid'])

        def get_lighter():
            try:
                r = requests.get(LIGHTER_URL, headers={"accept": "application/json"}, timeout=3).json()
                data = [{'symbol': i['symbol'].replace('1000',''), 'Lighter': (float(i['rate']) * 3 * 365 * 100)} for i in r.get('funding_rates', [])]
                if data: return pd.DataFrame(data).groupby('symbol')['Lighter'].mean().reset_index()
                return pd.DataFrame(columns=['symbol', 'Lighter'])
            except: return pd.DataFrame(columns=['symbol', 'Lighter'])

        def get_ext():
            try:
                r = requests.get(EXT_URL, headers={"X-Api-Key": EXT_API_KEY}, timeout=3).json()
                data = [{'symbol': i['name'].split('-')[0], 'Extended': float(i['marketStats']['fundingRate']) * 24 * 365 * 100} for i in r.get('data', [])]
                return pd.DataFrame(data)
            except: return pd.DataFrame(columns=['symbol', 'Extended'])

        def get_pac():
            try:
                r = requests.get(PAC_URL, headers={"X-Api-Key": PACIFICA_API_KEY}, timeout=3).json()
                data = [{'symbol': i['symbol'].replace('-USD',''), 'Pacifica': float(i['next_funding_rate']) * 24 * 365 * 100} for i in r.get('data', [])]
                return pd.DataFrame(data)
            except: return pd.DataFrame(columns=['symbol', 'Pacifica'])

        with concurrent.futures.ThreadPoolExecutor() as executor:
            f_var, f_hl = executor.submit(get_var), executor.submit(get_hl)
            f_li, f_ext = executor.submit(get_lighter), executor.submit(get_ext)
            f_pac = executor.submit(get_pac)
            return f_var.result(), f_hl.result(), f_li.result(), f_ext.result(), f_pac.result()

    @st.cache_data(ttl=300) 
    def get_48h_averages():
        url = "https://raw.githubusercontent.com/Colin503/dashboard_funding_rates/main/funding_history.parquet"
        try:
            df = pd.read_parquet(url, engine='pyarrow')
            cols = ['Variational', 'Hyperliquid', 'Lighter', 'Extended', 'Pacifica']
            existing = [c for c in cols if c in df.columns]
            if not existing: return pd.DataFrame()
            df_avg = df.groupby('symbol')[existing].mean().reset_index()
            return df_avg.rename(columns={c: f"{c}_avg" for c in existing})
        except: return pd.DataFrame()

    st.sidebar.subheader("🔎 Mainnet Filters")
    exchanges = ['Variational', 'Hyperliquid', 'Lighter', 'Extended', 'Pacifica']
    selected_ex = [e for e in exchanges if st.sidebar.checkbox(e, value=True, key=f"main_{e}")]
    show_history = st.sidebar.checkbox("Show Pair 48h Avg", value=True)

    if len(selected_ex) < 2:
        st.warning("Please select at least 2 exchanges.")
        return

    df_var, df_hl, df_li, df_ext, df_pac = fetch_mainnet_data()
    df = pd.merge(df_var, df_hl, on='symbol', how='outer')
    for d in [df_li, df_ext, df_pac]: df = pd.merge(df, d, on='symbol', how='outer')

    df_hist = get_48h_averages()
    has_history = not df_hist.empty
    if has_history: df = pd.merge(df, df_hist, on='symbol', how='left')

    df_live = df[df[selected_ex].notna().sum(axis=1) >= 2].copy()

    if not df_live.empty:
        df_live['APR Spread'] = df_live[selected_ex].max(axis=1) - df_live[selected_ex].min(axis=1)
        df_live['Opportunity'] = df_live['APR Spread'].apply(get_opportunity_score)
        
        def get_main_trade(row):
            vals = row[selected_ex].dropna()
            return f"🟢 LONG {vals.idxmin()} / 🔴 SHORT {vals.idxmax()}"
        df_live['Trade Action'] = df_live.apply(get_main_trade, axis=1)

        def calc_pair_history(row):
            vals = row[selected_ex].dropna()
            if len(vals) < 2: return None
            long, short = vals.idxmin(), vals.idxmax()
            l_hist, s_hist = f"{long}_avg", f"{short}_avg"
            if l_hist in row and s_hist in row and pd.notna(row[l_hist]) and pd.notna(row[s_hist]):
                return row[s_hist] - row[l_hist]
            return None

        if show_history and has_history:
            df_live['48h Pair Avg'] = df_live.apply(calc_pair_history, axis=1)

        df_final = df_live.sort_values('APR Spread', ascending=False)

        cols = ['symbol'] + selected_ex + ['APR Spread']
        if show_history and has_history and '48h Pair Avg' in df_final.columns: cols.append('48h Pair Avg')
        cols += ['Opportunity', 'Trade Action']
        final_cols = [c for c in cols if c in df_final.columns]

        def style_main(row):
            styles = ['' for _ in row.index]
            vals = row[selected_ex].astype(float)
            if vals.notna().sum() >= 2:
                styles[row.index.get_loc(vals.idxmin())] = 'background-color: #006400; color: white'
                styles[row.index.get_loc(vals.idxmax())] = 'background-color: #8B0000; color: white'
            
            if '48h Pair Avg' in row and pd.notna(row['48h Pair Avg']):
                curr, avg = row['APR Spread'], row['48h Pair Avg']
                flip = (curr > 0 and avg < 0) or (curr < 0 and avg > 0)
                diff = abs(curr - avg) > 5 and abs(curr) > abs(avg) * 2
                if flip or diff:
                    styles[row.index.get_loc('APR Spread')] = 'color: #FFD700; font-weight: bold; background-color: #333300'
            return styles

        st.dataframe(
            df_final[final_cols].style.apply(style_main, axis=1).format({
                c: "{:.2f}%" for c in final_cols if c not in ['symbol', 'Opportunity', 'Trade Action']
            }, na_rep="-"),
            use_container_width=True, hide_index=True,
            column_config={"Trade Action": st.column_config.TextColumn("Trade Action", width="large")}
        )
    else:
        st.info("No common pairs found.")

# ==============================================================================
#                               SIDEBAR NAVIGATION
# ==============================================================================

st.sidebar.title("🧭 Navigation")
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
