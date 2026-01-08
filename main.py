import streamlit as st
import requests
import pandas as pd

# --- APP CONFIGURATION ---
st.set_page_config(page_title="Arbitrage Execution Map", layout="wide")

# API Endpoints
VAR_URL = "https://omni-client-api.prod.ap-northeast-1.variational.io/metadata/stats"
HL_URL = "https://api.hyperliquid.xyz/info"
LIGHTER_URL = "https://mainnet.zklighter.elliot.ai/api/v1/funding-rates"

@st.cache_data(ttl=30)
def fetch_data():
    # 1. Variational (APR Annuel direct en décimal)
    try:
        r_var = requests.get(VAR_URL, timeout=5).json()
        df_var = pd.DataFrame(r_var['listings'])
        df_var['Variational'] = pd.to_numeric(df_var['funding_rate']) * 100
        df_var = df_var[['ticker', 'Variational']].rename(columns={'ticker': 'symbol'})
    except: df_var = pd.DataFrame(columns=['symbol', 'Variational'])

    # 2. Hyperliquid (CORRECTIF : Taux 8h -> APR Annuel)
    try:
        r_hl = requests.post(HL_URL, json={"type": "metaAndAssetCtxs"}, timeout=5).json()
        # Le taux 'funding' de l'API HL est la moyenne sur 8 heures
        # Pour correspondre au -143.51% du site : (Rate * 3 * 365) * 100
        hl_data = [
            {
                'symbol': m['name'], 
                'Hyperliquid': (float(r_hl[1][i]['funding']) * 3 * 365) * 100 * 8
            } for i, m in enumerate(r_hl[0]['universe'])
        ]
        df_hl = pd.DataFrame(hl_data)
    except: df_hl = pd.DataFrame(columns=['symbol', 'Hyperliquid'])

    # 3. Lighter (Même logique de période 8h)
    try:
        r_li = requests.get(LIGHTER_URL, headers={"accept": "application/json"}, timeout=5).json()
        li_data = [
            {
                'symbol': i['symbol'].replace('1000',''), 
                'Lighter': (float(i['rate']) * 3 * 365) * 100
            } for i in r_li.get('funding_rates', [])
        ]
        df_li = pd.DataFrame(li_data).groupby('symbol')['Lighter'].mean().reset_index()
    except: df_li = pd.DataFrame(columns=['symbol', 'Lighter'])

    return df_var, df_hl, df_li

# --- LOGIC FUNCTIONS ---
def get_trade_logic(row):
    dex_cols = ['Variational', 'Hyperliquid', 'Lighter']
    vals = row[dex_cols].dropna()
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
st.markdown("Trade Smarter: Visual Execution Guide")

if st.button('🔄 Refresh Data'):
    st.cache_data.clear()

df_var, df_hl, df_li = fetch_data()

# Merge
df = pd.merge(df_var, df_hl, on='symbol', how='outer')
df = pd.merge(df, df_li, on='symbol', how='outer')

# Filter & Metrics
dex_cols = ['Variational', 'Hyperliquid', 'Lighter']
df = df[df[dex_cols].notna().sum(axis=1) >= 2].copy()

if not df.empty:
    df['Spread'] = df[dex_cols].max(axis=1) - df[dex_cols].min(axis=1)
    df['Opportunity'] = df['Spread'].apply(get_opportunity_score)
    df['Trade Action'] = df.apply(get_trade_logic, axis=1)
    
    # Sélection des colonnes sans les logos
    df_display = df[['symbol', 'Variational', 'Hyperliquid', 'Lighter', 'Spread', 'Opportunity', 'Trade Action']].sort_values('Spread', ascending=False)

    # Styling
    def style_rows(row):
        styles = ['' for _ in row.index]
        vals = row[['Variational', 'Hyperliquid', 'Lighter']].astype(float)
        if vals.notna().sum() >= 2:
            styles[row.index.get_loc(vals.idxmin())] = 'background-color: #006400; color: white'
            styles[row.index.get_loc(vals.idxmax())] = 'background-color: #8B0000; color: white'
        return styles

    st.dataframe(
        df_display.style.apply(style_rows, axis=1).format({
            'Variational': "{:.2f}%", 'Hyperliquid': "{:.2f}%", 'Lighter': "{:.2f}%", 'Spread': "{:.2f}%"
        }),
        use_container_width=True, 
        hide_index=True,
        column_config={
            "symbol": "Ticker",
            "Variational": "Variational APR",
            "Hyperliquid": "Hyperliquid APR",
            "Lighter": "Lighter APR",
            "Spread": "Max Spread"
        }
    )
    st.success(f"Found {len(df)} arbitrage opportunities.")
else:
    st.info("No arbitrage pairs found.")




# --- FOOTER ---
st.markdown("---")
# Layout with two columns
col_aff, col_social = st.columns([3, 1])

with col_aff:
    # Minimalist referral box with Dark Green accent
    st.markdown("""
        <div style="background-color: rgba(255, 255, 255, 0.03); padding: 12px; border-radius: 8px; border-left: 4px solid #006400;">
            <p style="margin: 0; font-size: 13px; color: #888; text-transform: uppercase; letter-spacing: 1px;">Ready to trade?</p>
            <p style="margin: 0; font-size: 15px; font-weight: 500;">
            </p>
            <a href="https://app.hyperliquid.xyz/join/CACA" target="_blank" style="color: #008000; text-decoration: none; font-weight: 600; font-size: 14px;">
                Start trading on <b>Hyperliquid</b> to capture these spreads.→
            </a>
        </div>
    """, unsafe_allow_html=True)

with col_social:
    # Minimalist social links
    st.markdown(
        """
        <div style="text-align: right; padding-top: 10px;">
            <p style="margin-bottom: 8px; font-size: 12px; color: #666;">Developer</p>
            <a href="https://x.com/C0l1n503" target="_blank" style="text-decoration: none;">
                <span style="color: #666; font-size: 12px; margin-right: 10px;">@C0l1n503</span>
                <img src="https://upload.wikimedia.org/wikipedia/commons/thumb/0/09/X_%28formerly_Twitter%29_logo_late_2025.svg/330px-X_%28formerly_Twitter%29_logo_late_2025.svg.png" width="18" style="filter: opacity(0.6);">
            </a>
        </div>
        """,
        unsafe_allow_html=True
    )