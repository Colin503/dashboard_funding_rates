"""Snapshot periodique des funding rates -> funding_history.parquet.

Lance par GitHub Actions. Enregistre crypto ET RWA dans le meme fichier, la
colonne `asset_class` distinguant les deux (un meme ticker peut exister des
deux cotes : "CL" = WTI Crude Oil en RWA, et un token en crypto sur une autre
venue).
"""

import datetime
import os

import pandas as pd

import datafeed

FILE_NAME = "funding_history.parquet"
RETENTION_DAYS = 7


def collect():
    print(f"Récupération des données... {datetime.datetime.now()}")
    df_crypto, df_rwa, _, errors = datafeed.fetch_all(timeout=10)

    for venue, msg in errors.items():
        print(f"[WARN] {venue} indisponible : {msg}")

    df_crypto["asset_class"] = "Crypto"
    df_rwa["asset_class"] = "RWA"

    cols = ["symbol", "asset_class"] + datafeed.EXCHANGES
    df = pd.concat([df_crypto[cols], df_rwa[cols]], ignore_index=True)
    df["timestamp"] = datetime.datetime.now()

    print(f"{len(df_crypto)} lignes crypto · {len(df_rwa)} lignes RWA")
    return df


def save_to_parquet(df_new):
    path = os.path.join(os.getcwd(), FILE_NAME)

    if not os.path.exists(path):
        df_new.to_parquet(path, engine="pyarrow", compression="snappy")
        print("Nouveau fichier créé.")
        return

    try:
        df_old = pd.read_parquet(path)
    except Exception as exc:  # noqa: BLE001
        print(f"[ERREUR] lecture impossible, écrasement : {exc}")
        df_new.to_parquet(path, engine="pyarrow", compression="snappy")
        return

    # Historique anterieur a la separation RWA : c'etait exclusivement du crypto.
    if "asset_class" not in df_old.columns:
        df_old["asset_class"] = "Crypto"

    df = pd.concat([df_old, df_new], ignore_index=True)
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        cutoff = datetime.datetime.now() - datetime.timedelta(days=RETENTION_DAYS)
        df = df[df["timestamp"] > cutoff]

    df.to_parquet(path, engine="pyarrow", compression="snappy")
    print(f"Historique mis à jour. Total lignes : {len(df)}")


if __name__ == "__main__":
    print("Script lancé par GitHub Action...")
    if not datafeed.EXT_API_KEY:
        print("[WARN] EXT_API_KEY manquante.")
    if not datafeed.PACIFICA_API_KEY:
        print("[WARN] PACIFICA_API_KEY manquante.")

    df = collect()
    if not df.empty:
        save_to_parquet(df)
    else:
        print("[WARN] Aucune donnée récupérée.")

    print("Fin du script (arrêt propre).")
