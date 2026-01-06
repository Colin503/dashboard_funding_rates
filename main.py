import streamlit as st
import requests
import pandas as pd

API_URL = "https://omni-client-api.prod.ap-northeast-1.variational.io/metadata/stats"
st.set_page_config(page_title="Variational Monitor", layout="wide")

def fetch_data():
    try:
        response = requests.get(API_URL, timeout=10)
        return response.json()
    except:
        return None

data = fetch_data()

if data:
    df = pd.DataFrame(data['listings'])
    
    # 1. Conversion des types
    df['funding_rate_raw'] = pd.to_numeric(df['funding_rate'])
    df['funding_interval_s'] = pd.to_numeric(df['funding_interval_s'])
    df['volume_24h'] = pd.to_numeric(df['volume_24h'])

    # 2. CALCUL CORRECT (Basé sur tes screenshots)
    # L'APR est directement le funding_rate de l'API multiplié par 100
    df['funding_apr'] = df['funding_rate_raw'] * 100
    
    # Le taux par période (ex: 4h) affiché sur le site est : APR / (Nombre de périodes par an)
    # Nombre de périodes = Secondes dans l'année / Intervalle en secondes
    df['periodic_rate'] = df['funding_apr'] / (31536000 / df['funding_interval_s'])

    st.title("🏹 Variational Funding Monitor")

    config = {
        "ticker": "Asset",
        "periodic_rate": st.column_config.NumberColumn("Rate (Période)", format="%.4f%%"),
        "funding_apr": st.column_config.NumberColumn("Annual APR", format="%.2f%%"),
        "volume_24h": st.column_config.NumberColumn("Vol 24h", format="$%d")
    }

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("🔴 Top APR (Longs)")
        top_longs = df.sort_values('funding_apr', ascending=False).head(10)
        st.dataframe(top_longs[['ticker', 'periodic_rate', 'funding_apr', 'volume_24h']], 
                     column_config=config, hide_index=True)

    with col2:
        st.subheader("🟢 Top APR (Shorts)")
        top_shorts = df.sort_values('funding_apr', ascending=True).head(10)
        st.dataframe(top_shorts[['ticker', 'periodic_rate', 'funding_apr', 'volume_24h']], 
                     column_config=config, hide_index=True)