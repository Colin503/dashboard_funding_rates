import pandas as pd
import requests
import datetime
import os

# --- CONFIGURATION ---
# Sur GitHub, les clés sont lues via les "Secrets" (Variables d'environnement)
EXT_API_KEY = os.environ.get("EXT_API_KEY")
PACIFICA_API_KEY = os.environ.get("PACIFICA_API_KEY")
FILE_NAME = "funding_history.parquet"

# URLs
VAR_URL = "https://omni-client-api.prod.ap-northeast-1.variational.io/metadata/stats"
HL_URL = "https://api.hyperliquid.xyz/info"
LIGHTER_URL = "https://mainnet.zklighter.elliot.ai/api/v1/funding-rates"
EXT_URL = "https://api.starknet.extended.exchange/api/v1/info/markets"
PAC_URL = "https://api.pacifica.fi/api/v1/info"

def fetch_all_rates():
    print(f"🔄 Récupération des données... {datetime.datetime.now()}")
    
    # 1. Variational
    try:
        r_var = requests.get(VAR_URL, timeout=10).json()
        df_var = pd.DataFrame(r_var['listings'])
        df_var['Variational'] = pd.to_numeric(df_var['funding_rate']) * 100
        df_var = df_var[['ticker', 'Variational']].rename(columns={'ticker': 'symbol'})
    except: df_var = pd.DataFrame(columns=['symbol', 'Variational'])

    # 2. Hyperliquid
    try:
        r_hl = requests.post(HL_URL, json={"type": "metaAndAssetCtxs"}, timeout=10).json()
        hl_data = [
            {'symbol': m['name'], 'Hyperliquid': (float(r_hl[1][i]['funding']) * 3 * 365) * 100 * 8} 
            for i, m in enumerate(r_hl[0]['universe'])
        ]
        df_hl = pd.DataFrame(hl_data)
    except: df_hl = pd.DataFrame(columns=['symbol', 'Hyperliquid'])

    # 3. Lighter
    try:
        r_li = requests.get(LIGHTER_URL, headers={"accept": "application/json"}, timeout=10).json()
        li_data = [
            {'symbol': i['symbol'].replace('1000',''), 'Lighter': (float(i['rate']) * 3 * 365) * 100} 
            for i in r_li.get('funding_rates', [])
        ]
        df_li = pd.DataFrame(li_data).groupby('symbol')['Lighter'].mean().reset_index()
    except: df_li = pd.DataFrame(columns=['symbol', 'Lighter'])

    # 4. Extended
    try:
        headers = {"X-Api-Key": EXT_API_KEY, "User-Agent": "Mozilla/5.0"}
        r_ext = requests.get(EXT_URL, headers=headers, timeout=10).json()
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
        r_pac = requests.get(PAC_URL, headers=headers_pac, timeout=10).json()
        pac_data = []
        for item in r_pac.get('data', []):
            rate = float(item.get('next_funding_rate', 0))
            annual_apr = rate * 24 * 365 * 100
            pac_data.append({'symbol': item.get('symbol', '').replace('-USD', ''), 'Pacifica': annual_apr})
        df_pac = pd.DataFrame(pac_data)
    except: df_pac = pd.DataFrame(columns=['symbol', 'Pacifica'])

    # Fusion
    df = pd.merge(df_var, df_hl, on='symbol', how='outer')
    df = pd.merge(df, df_li, on='symbol', how='outer')
    df = pd.merge(df, df_ext, on='symbol', how='outer')
    df = pd.merge(df, df_pac, on='symbol', how='outer')
    
    df['timestamp'] = datetime.datetime.now()
    return df

def save_to_parquet(df_new):
    file_path = os.path.join(os.getcwd(), FILE_NAME)

    if os.path.exists(file_path):
        try:
            df_old = pd.read_parquet(file_path)
            df_combined = pd.concat([df_old, df_new], ignore_index=True)
            
            # --- NETTOYAGE (Garder 7 jours glissants) ---
            if 'timestamp' in df_combined.columns:
                df_combined['timestamp'] = pd.to_datetime(df_combined['timestamp'])
                cutoff_date = datetime.datetime.now() - datetime.timedelta(days=7)
                df_combined = df_combined[df_combined['timestamp'] > cutoff_date]
            # --------------------------------------------

            df_combined.to_parquet(file_path, engine='pyarrow', compression='snappy')
            print(f"✅ Historique mis à jour ! Total lignes : {len(df_combined)}")
        except Exception as e:
            print(f"❌ Erreur lecture, écrasement : {e}")
            df_new.to_parquet(file_path, engine='pyarrow', compression='snappy')
    else:
        df_new.to_parquet(file_path, engine='pyarrow', compression='snappy')
        print(f"✅ Nouveau fichier créé.")

if __name__ == "__main__":
    print("🚀 Script lancé par GitHub Action...")
    
    # Vérification des clés
    if not EXT_API_KEY: print("⚠️ Warning: EXT_API_KEY manquante.")
    if not PACIFICA_API_KEY: print("⚠️ Warning: PACIFICA_API_KEY manquante.")

    df = fetch_all_rates()
    if not df.empty:
        save_to_parquet(df)
    else:
        print("⚠️ Aucune donnée récupérée.")
    
    print("🏁 Fin du script (Arrêt propre).")
