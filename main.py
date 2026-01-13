import streamlit as st
import requests
import pandas as pd
from streamlit_autorefresh import st_autorefresh

# --- APP CONFIGURATION ---
st.set_page_config(page_title="Arbitrage Execution Map", layout="wide")

# --- AUTO-REFRESH (Every 2 minutes) ---
st_autorefresh(interval=120 * 1000, limit=None, key="funder_refresh")

# --- API CONFIGURATION ---
VAR_URL = "https://omni-client-api.prod.ap-northeast-1.variational.io/metadata/stats"
HL_URL = "https://api.hyperliquid.xyz/info"
LIGHTER_URL = "https://mainnet.zklighter.elliot.ai/api/v1/funding-rates"
EXT_URL = "https://api.starknet.extended.exchange/api/v1/info/markets"
PAC_URL = "https://api.pacifica.fi/api/v1/info"

EXT_API_KEY = "693ed8445baad0ae3b75c6d991bac4d9"
PACIFICA_API_KEY = "5h53egePzL1aM958CXWs9x4oY7FbnammiC7YiX7XErvD3TYk9L214kqP6j8GJ6wTQbnQzAk4Mbzxfo7aGKzrzP9s"

@st.cache_data(ttl=120)
def fetch_data():
    # 1. Variational
    try:
        r_var = requests.get(VAR_URL, timeout=5).json()
        df_var = pd.DataFrame(r_var['listings'])
        df_var['Variational'] = pd.to_numeric(df_var['funding_rate']) * 100
        df_var = df_var[['ticker', 'Variational']].rename(columns={'ticker': 'symbol'})
    except: df_var = pd.DataFrame(columns=['symbol', 'Variational'])

    # 2. Hyperliquid
    try:
        r_hl = requests.post(HL_URL, json={"type": "metaAndAssetCtxs"}, timeout=5).json()
        hl_data = [
            {'symbol': m['name'], 'Hyperliquid': (float(r_hl[1][i]['funding']) * 3 * 365) * 100 * 8} 
            for i, m in enumerate(r_hl[0]['universe'])
        ]
        df_hl = pd.DataFrame(hl_data)
    except: df_hl = pd.DataFrame(columns=['symbol', 'Hyperliquid'])

    # 3. Lighter
    try:
        r_li = requests.get(LIGHTER_URL, headers={"accept": "application/json"}, timeout=5).json()
        li_data = [
            {'symbol': i['symbol'].replace('1000',''), 'Lighter': (float(i['rate']) * 3 * 365) * 100} 
            for i in r_li.get('funding_rates', [])
        ]
        df_li = pd.DataFrame(li_data).groupby('symbol')['Lighter'].mean().reset_index()
    except: df_li = pd.DataFrame(columns=['symbol', 'Lighter'])

    # 4. Extended
    try:
        headers = {"X-Api-Key": EXT_API_KEY, "User-Agent": "Mozilla/5.0"}
        r_ext = requests.get(EXT_URL, headers=headers, timeout=5).json()
        ext_data = []
        for item in r_ext.get('data', []):
            stats = item.get('marketStats', {})
            sym = item.get('name', '').split('-')[0]
            rate = float(stats.get('fundingRate', 0))
            ext_data.append({'symbol': sym, 'Extended': rate * 24 * 365 * 100})
        df_ext = pd.DataFrame(ext_data)
    except: df_ext = pd.DataFrame(columns=['symbol', 'Extended'])

    # 5. Pacifica
    try:
        headers_pac = {"X-Api-Key": PACIFICA_API_KEY, "User-Agent": "Mozilla/5.0"}
        r_pac = requests.get(PAC_URL, headers=headers_pac, timeout=5).json()
        pac_data = []
        for item in r_pac.get('data', []):
            rate = float(item.get('next_funding_rate', 0))
            annual_apr = rate * 24 * 365 * 100
            pac_data.append({'symbol': item.get('symbol', '').replace('-USD', ''), 'Pacifica': annual_apr})
        df_pac = pd.DataFrame(pac_data)
    except: df_pac = pd.DataFrame(columns=['symbol', 'Pacifica'])

    return df_var, df_hl, df_li, df_ext, df_pac

# --- SIDEBAR SETTINGS (EXCHANGE SELECTOR) ---
st.sidebar.header("Exchanges Selection")
all_exchanges = ['Variational', 'Hyperliquid', 'Lighter', 'Extended', 'Pacifica']
selected_exchanges = []

# Generate a checkbox for each exchange
for ex in all_exchanges:
    if st.sidebar.checkbox(ex, value=True):
        selected_exchanges.append(ex)

# --- LOGIC FUNCTIONS ---
def get_trade_logic(row, active_cols):
    vals = row[active_cols].dropna()
    if len(vals) >= 2:
        low_dex = vals.idxmin()
        high_dex = vals.idxmax()
        return f"🟢 LONG {low_dex} / 🔴 SHORT {high_dex}"
    return "N/A"

def get_opportunity_score(spread):
    if spread > 100: return "🔥 HIGH"
    elif spread > 30: return "⚡ MEDIUM"
    return "❄️ LOW"

# --- MAIN UI ---
st.title("⚖️ Delta-Neutral Arbitrage Map")
st.markdown(f"Currently analyzing: **{', '.join(selected_exchanges)}**")

if len(selected_exchanges) < 2:
    st.warning("Please check at least **two exchanges** in the sidebar to enable spread calculation.")
else:
    df_var, df_hl, df_li, df_ext, df_pac = fetch_data()

    # Merging
    df = pd.merge(df_var, df_hl, on='symbol', how='outer')
    df = pd.merge(df, df_li, on='symbol', how='outer')
    df = pd.merge(df, df_ext, on='symbol', how='outer')
    df = pd.merge(df, df_pac, on='symbol', how='outer')

    # Filter rows that have at least 2 prices among the CHECKED exchanges
    df = df[df[selected_exchanges].notna().sum(axis=1) >= 2].copy()

    if not df.empty:
        # Dynamic Calculations
        df['APR Spread'] = df[selected_exchanges].max(axis=1) - df[selected_exchanges].min(axis=1)
        df['Opportunity'] = df['APR Spread'].apply(get_opportunity_score)
        df['Trade Action'] = df.apply(lambda row: get_trade_logic(row, selected_exchanges), axis=1)
        
        # Sort and Display
        display_cols = ['symbol'] + selected_exchanges + ['APR Spread', 'Opportunity', 'Trade Action']
        df_final = df[display_cols].sort_values('APR Spread', ascending=False)

        def apply_styles(row):
            styles = ['' for _ in row.index]
            vals = row[selected_exchanges].astype(float)
            if vals.notna().sum() >= 2:
                styles[row.index.get_loc(vals.idxmin())] = 'background-color: #006400; color: white'
                styles[row.index.get_loc(vals.idxmax())] = 'background-color: #8B0000; color: white'
            return styles

        st.dataframe(
            df_final.style.apply(apply_styles, axis=1).format({
                ex: "{:.2f}%" for ex in selected_exchanges + ['APR Spread']
            }),
            use_container_width=True, hide_index=True
        )
    else:
        st.info("No common pairs found between the checked exchanges.")

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