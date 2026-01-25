import streamlit as st
import requests
import pandas as pd
import os
from datetime import datetime, timedelta
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

EXT_API_KEY = os.environ.get("EXT_API_KEY", "693ed8445baad0ae3b75c6d991bac4d9")
PACIFICA_API_KEY = os.environ.get("PACIFICA_API_KEY", "5h53egePzL1aM958CXWs9x4oY7FbnammiC7YiX7XErvD3TYk9L214kqP6j8GJ6wTQbnQzAk4Mbzxfo7aGKzrzP9s")

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

# --- HISTORICAL DATA FUNCTIONS ---
@st.cache_data(ttl=300) 
def get_48h_averages():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(current_dir, "funding_history.parquet")
    
    if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
        return pd.DataFrame()

    try:
        df = pd.read_parquet(file_path, engine='pyarrow')
        if 'timestamp' in df.columns:
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            cutoff = datetime.now() - timedelta(hours=48)
            df = df[df['timestamp'] >= cutoff]
        
        numeric_cols = ['Variational', 'Hyperliquid', 'Lighter', 'Extended', 'Pacifica']
        existing_cols = [c for c in numeric_cols if c in df.columns]
        
        if not existing_cols:
            return pd.DataFrame()
            
        # On calcule la moyenne par exchange pour l'utiliser plus tard
        df_avg = df.groupby('symbol')[existing_cols].mean().reset_index()
        # On renomme avec le suffixe _avg pour les identifier
        df_avg = df_avg.rename(columns={c: f"{c}_avg" for c in existing_cols})
        
        return df_avg
    except Exception:
        return pd.DataFrame()

# --- SIDEBAR SETTINGS ---
st.sidebar.header("Exchanges Selection")
all_exchanges = ['Variational', 'Hyperliquid', 'Lighter', 'Extended', 'Pacifica']
selected_exchanges = []

for ex in all_exchanges:
    if st.sidebar.checkbox(ex, value=True):
        selected_exchanges.append(ex)

show_history = st.sidebar.checkbox("Show Pair 48h Avg", value=True)

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

# Nouvelle fonction pour calculer la moyenne de la paire
def calculate_pair_history(row, active_cols):
    # 1. Identifier qui est Long et qui est Short DANS LE LIVE
    vals = row[active_cols].dropna()
    if len(vals) < 2:
        return None
        
    long_dex = vals.idxmin()  # Ex: 'Variational'
    short_dex = vals.idxmax() # Ex: 'Extended'
    
    # 2. Récupérer les moyennes historiques correspondantes
    # Les colonnes historiques s'appellent 'Variational_avg', etc.
    long_hist_col = f"{long_dex}_avg"
    short_hist_col = f"{short_dex}_avg"
    
    # 3. Vérifier si on a l'historique pour ces deux exchanges sur cette ligne
    if long_hist_col in row and short_hist_col in row:
        long_avg_val = row[long_hist_col]
        short_avg_val = row[short_hist_col]
        
        if pd.notna(long_avg_val) and pd.notna(short_avg_val):
            # Calcul du spread moyen historique : Moyenne Short - Moyenne Long
            return short_avg_val - long_avg_val
            
    return None

# --- MAIN UI ---
st.title("⚖️ Delta-Neutral Arbitrage Map")
st.markdown(f"Currently analyzing: **{', '.join(selected_exchanges)}**")

df_history = get_48h_averages()
has_history = not df_history.empty

if len(selected_exchanges) < 2:
    st.warning("Please check at least **two exchanges** in the sidebar.")
else:
    df_var, df_hl, df_li, df_ext, df_pac = fetch_data()

    # Merges Live
    df = pd.merge(df_var, df_hl, on='symbol', how='outer')
    df = pd.merge(df, df_li, on='symbol', how='outer')
    df = pd.merge(df, df_ext, on='symbol', how='outer')
    df = pd.merge(df, df_pac, on='symbol', how='outer')

    # Merge History (On attache les moyennes brutes au dataframe)
    if has_history:
        df = pd.merge(df, df_history, on='symbol', how='left')

    # Filtre Live
    df = df[df[selected_exchanges].notna().sum(axis=1) >= 2].copy()

    if not df.empty:
        # 1. Calculs Live
        df['APR Spread'] = df[selected_exchanges].max(axis=1) - df[selected_exchanges].min(axis=1)
        df['Opportunity'] = df['APR Spread'].apply(get_opportunity_score)
        df['Trade Action'] = df.apply(lambda row: get_trade_logic(row, selected_exchanges), axis=1)
        
        # 2. Calcul "Pair 48h Avg" (Seulement si demandé et dispo)
        if show_history and has_history:
            df['48h Pair Avg'] = df.apply(lambda row: calculate_pair_history(row, selected_exchanges), axis=1)

        df_final = df.sort_values('APR Spread', ascending=False)
        
        # 3. Préparation de l'affichage
        display_cols = ['symbol'] + selected_exchanges + ['APR Spread']
        
        # On insère la colonne moyenne juste après le spread actuel
        if show_history and has_history and '48h Pair Avg' in df_final.columns:
            display_cols.append('48h Pair Avg')
            
        display_cols += ['Opportunity', 'Trade Action']
        
        # Nettoyage
        final_cols = [c for c in display_cols if c in df_final.columns]
        
        # Styling
        # Styling
        def apply_styles(row):
            styles = ['' for _ in row.index]
            live_vals = row[selected_exchanges].astype(float)
            
            # 1. Couleurs Vert/Rouge pour Long/Short
            if live_vals.notna().sum() >= 2:
                min_idx = row.index.get_loc(live_vals.idxmin())
                max_idx = row.index.get_loc(live_vals.idxmax())
                styles[min_idx] = 'background-color: #006400; color: white'
                styles[max_idx] = 'background-color: #8B0000; color: white'
            
            # 2. Logique "Or/Jaune" : Détection de divergence forte
            if '48h Pair Avg' in row and pd.notna(row['48h Pair Avg']):
                current_spread = row['APR Spread']
                avg_spread = row['48h Pair Avg']
                
                spread_col_idx = row.index.get_loc('APR Spread')
                
                # Condition A : Inversion de signe (Positif <-> Négatif)
                # Ex: Moyenne était -5% (Shorts payaient Longs) et maintenant +10% (Longs paient Shorts)
                is_sign_flip = (current_spread > 0 and avg_spread < 0) or (current_spread < 0 and avg_spread > 0)
                
                # Condition B : Écart massif (ex: 2x la moyenne)
                # On évite de flagger si on passe de 0.1% à 0.2% (bruit), donc on demande un min de 5% d'écart
                is_huge_diff = abs(current_spread - avg_spread) > 5 and abs(current_spread) > abs(avg_spread) * 2

                if is_sign_flip or is_huge_diff:
                     styles[spread_col_idx] = 'color: #FFD700; font-weight: bold; background-color: #333300' 

            return styles

        st.dataframe(
            df_final[final_cols].style.apply(apply_styles, axis=1).format({
                c: "{:.2f}%" for c in final_cols if c not in ['symbol', 'Opportunity', 'Trade Action']
            }),
            use_container_width=True, hide_index=True
        )
    else:
        st.info("No common pairs found.")

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