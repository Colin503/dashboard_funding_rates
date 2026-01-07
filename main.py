import streamlit as st
import requests
import pandas as pd

# --- APP CONFIGURATION ---
st.set_page_config(page_title="Arbitrage Funding Map", layout="wide")

# API Endpoints
VAR_URL = "https://omni-client-api.prod.ap-northeast-1.variational.io/metadata/stats"
HL_URL = "https://api.hyperliquid.xyz/info"
LIGHTER_URL = "https://mainnet.zklighter.elliot.ai/api/v1/funding-rates"

def fetch_variational():
    try:
        r = requests.get(VAR_URL, timeout=5).json()
        df = pd.DataFrame(r['listings'])
        df['Variational'] = pd.to_numeric(df['funding_rate']) * 100
        return df[['ticker', 'Variational']].rename(columns={'ticker': 'symbol'})
    except: return pd.DataFrame(columns=['symbol', 'Variational'])

def fetch_hyperliquid():
    try:
        r = requests.post(HL_URL, json={"type": "metaAndAssetCtxs"}, timeout=5).json()
        hl_data = [{'symbol': m['name'], 'Hyperliquid': float(r[1][i]['funding']) * 365 * 100} 
                   for i, m in enumerate(r[0]['universe'])]
        return pd.DataFrame(hl_data)
    except: return pd.DataFrame(columns=['symbol', 'Hyperliquid'])

def fetch_lighter():
    try:
        r = requests.get(LIGHTER_URL, headers={"accept": "application/json"}, timeout=5).json()
        l_data = []
        for i in r.get('funding_rates', []):
            # Clean symbol and remove multipliers like '1000'
            symbol = i['symbol'].replace('1000','')
            if i.get('rate') is not None:
                l_data.append({'symbol': symbol, 'Lighter': float(i['rate']) * 3 * 365 * 100})
        
        df_l = pd.DataFrame(l_data)
        if not df_l.empty:
            # Group by symbol to remove duplicates (takes the average rate)
            df_l = df_l.groupby('symbol')['Lighter'].mean().reset_index()
        return df_l
    except: return pd.DataFrame(columns=['symbol', 'Lighter'])

# --- STYLING FUNCTION ---
def highlight_arbitrage(row):
    dex_cols = ['Variational', 'Hyperliquid', 'Lighter']
    styles = ['' for _ in row.index]
    vals = row[dex_cols].astype(float)
    if vals.notna().sum() >= 2:
        idx_min = vals.idxmin()
        idx_max = vals.idxmax()
        # Green for Long (lowest), Red for Short (highest)
        styles[row.index.get_loc(idx_min)] = 'background-color: #006400; color: white'
        styles[row.index.get_loc(idx_max)] = 'background-color: #8B0000; color: white'
    return styles

# --- MAIN UI ---
st.title("⚖️ Delta-Neutral Arbitrage Map")
st.markdown("""
**Visual Guide:**
* 🟩 **Green Cell**: Lowest rate -> **Open LONG position here.**
* 🟥 **Red Cell**: Highest rate -> **Open SHORT position here.**
""")

if st.button('🔄 Refresh Data'):
    st.cache_data.clear()

with st.spinner('Analyzing market opportunities...'):
    df_var = fetch_variational()
    df_hl = fetch_hyperliquid()
    df_lighter = fetch_lighter()

    # Merging data
    df = pd.merge(df_var, df_hl, on='symbol', how='outer')
    df = pd.merge(df, df_lighter, on='symbol', how='outer')
    
    dex_columns = ['Variational', 'Hyperliquid', 'Lighter']
    # Filter rows: keep only symbols available on at least 2 exchanges
    df['dex_count'] = df[dex_columns].notna().sum(axis=1)
    df_filtered = df[df['dex_count'] >= 2].copy()

    if not df_filtered.empty:
        # Calculate maximum spread
        df_filtered['Profit Delta'] = df_filtered[dex_columns].max(axis=1) - df_filtered[dex_columns].min(axis=1)
        df_display = df_filtered[['symbol', 'Variational', 'Hyperliquid', 'Lighter', 'Profit Delta']].sort_values('Profit Delta', ascending=False)

        # Apply Pandas Styling
        styled_df = df_display.style.apply(highlight_arbitrage, axis=1).format({
            'Variational': "{:.2f}%", 'Hyperliquid': "{:.2f}%", 'Lighter': "{:.2f}%", 'Profit Delta': "{:.2f}%"
        })

        st.dataframe(styled_df, use_container_width=True, hide_index=True)
        st.success(f"Found {len(df_filtered)} arbitrage opportunities.")
    else:
        st.warning("No arbitrage matches found between DEXs.")
