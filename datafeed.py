"""
Recuperation et normalisation des funding rates des 5 venues.

Partage par main.py (dashboard) et recorder.py (historique), pour que les deux
voient exactement les memes symboles et les memes conversions APR.

Deux flux distincts sont produits par venue :
  - Crypto : normalisation historique inchangee, pour ne pas casser le parquet
             deja accumule (symboles identiques a avant).
  - RWA    : resolution via assets.RWA_REGISTRY, symbole canonique = ticker
             Variational.

Note Hyperliquid : les RWA ne sont PAS dans le perp principal. Ils vivent dans
le dex HIP-3 "xyz" (prefixe xyz:), qui demande un second appel API.
"""

import concurrent.futures
import os
from datetime import datetime, timezone

import pandas as pd
import requests

import assets

VAR_URL = "https://omni-client-api.prod.ap-northeast-1.variational.io/metadata/stats"
HL_URL = "https://api.hyperliquid.xyz/info"
HL_RWA_DEX = "xyz"
LIGHTER_URL = "https://mainnet.zklighter.elliot.ai/api/v1/funding-rates"
EXT_URL = "https://api.starknet.extended.exchange/api/v1/info/markets"
PAC_URL = "https://api.pacifica.fi/api/v1/info"

EXT_API_KEY = os.environ.get("EXT_API_KEY", "")
PACIFICA_API_KEY = os.environ.get("PACIFICA_API_KEY", "")

EXCHANGES = ["Variational", "Hyperliquid", "Lighter", "Extended", "Pacifica"]
ANCHOR = "Variational"  # jambe obligatoire de tout trade

HOURLY_TO_APR = 24 * 365 * 100   # taux horaire  -> APR %
EIGHT_H_TO_APR = 3 * 365 * 100   # taux par 8h   -> APR %


# --- Fetchers bruts : renvoient {ticker_brut: APR%} -------------------------

def _fetch_variational(timeout):
    r = requests.get(VAR_URL, timeout=timeout).json()
    out, names = {}, {}
    for it in r.get("listings", []):
        tkr = it.get("ticker", "")
        if not tkr or tkr in assets.NO_FUNDING_MARKETS:
            continue
        try:
            out[tkr] = float(it["funding_rate"]) * 100
        except (TypeError, ValueError, KeyError):
            continue
        names[tkr] = it.get("name", "")
    return out, names


def _fetch_hyperliquid(timeout, dex=None):
    payload = {"type": "metaAndAssetCtxs"}
    if dex:
        payload["dex"] = dex
    r = requests.post(HL_URL, json=payload, timeout=timeout).json()
    universe, ctxs = r[0]["universe"], r[1]
    out = {}
    for i, m in enumerate(universe):
        if i >= len(ctxs):
            break
        try:
            out[m["name"]] = float(ctxs[i]["funding"]) * HOURLY_TO_APR
        except (TypeError, ValueError, KeyError):
            continue
    return out


def _fetch_lighter(timeout):
    r = requests.get(LIGHTER_URL, headers={"accept": "application/json"}, timeout=timeout).json()
    out = {}
    for it in r.get("funding_rates", []):
        try:
            out[it["symbol"]] = float(it["rate"]) * EIGHT_H_TO_APR
        except (TypeError, ValueError, KeyError):
            continue
    return out


def _fetch_extended(timeout):
    headers = {"User-Agent": "Mozilla/5.0"}
    if EXT_API_KEY:
        headers["X-Api-Key"] = EXT_API_KEY
    r = requests.get(EXT_URL, headers=headers, timeout=timeout).json()
    out = {}
    for it in r.get("data", []):
        name = it.get("name", "")
        if not name:
            continue
        try:
            rate = float(it.get("marketStats", {}).get("fundingRate", 0))
        except (TypeError, ValueError):
            continue
        out[name.split("-")[0]] = rate * HOURLY_TO_APR
    return out


def _fetch_pacifica(timeout):
    headers = {"User-Agent": "Mozilla/5.0"}
    if PACIFICA_API_KEY:
        headers["X-Api-Key"] = PACIFICA_API_KEY
    r = requests.get(PAC_URL, headers=headers, timeout=timeout).json()
    out = {}
    for it in r.get("data", []):
        sym = it.get("symbol", "")
        if not sym:
            continue
        try:
            out[sym] = float(it.get("next_funding_rate", 0)) * HOURLY_TO_APR
        except (TypeError, ValueError):
            continue
    return out


# --- Separation RWA / Crypto ------------------------------------------------

_LOOKUPS = {v: assets.build_venue_lookup(v) for v in EXCHANGES}


def _legacy_crypto_symbol(venue, raw):
    """Normalisation crypto historique - ne pas modifier, le parquet en depend."""
    if venue == "Lighter":
        return raw.replace("1000", "")
    if venue == "Pacifica":
        return raw.replace("-USD", "")
    return raw


def split_venue(venue, raw_rates, rwa_raw_rates=None):
    """(serie_crypto, serie_rwa) pour une venue, indexees par symbole final."""
    lookup = _LOOKUPS[venue]

    rwa_source = raw_rates if rwa_raw_rates is None else rwa_raw_rates
    rwa = {}
    for ticker, apr in rwa_source.items():
        canonical = lookup.get(ticker)
        if canonical is None:
            continue
        # Hors heures de marche les venues renvoient un funding a 0 pile :
        # c'est une absence de donnee, pas un taux. La traiter comme un vrai 0
        # fabriquerait un spread fantome contre une venue encore cotee.
        if apr == 0.0:
            continue
        rwa.setdefault(canonical, []).append(apr)

    crypto = {}
    if rwa_raw_rates is None:
        # Meme flux pour les deux : on retire du crypto tout ticker resolu en RWA.
        for ticker, apr in raw_rates.items():
            if ticker in lookup:
                continue
            crypto.setdefault(_legacy_crypto_symbol(venue, ticker), []).append(apr)
    else:
        for ticker, apr in raw_rates.items():
            crypto.setdefault(_legacy_crypto_symbol(venue, ticker), []).append(apr)

    mean = lambda d: pd.Series({k: sum(v) / len(v) for k, v in d.items()}, dtype="float64")
    return mean(crypto).rename(venue), mean(rwa).rename(venue)


def fetch_all(timeout=6):
    """Renvoie (df_crypto, df_rwa, var_names, errors).

    df_* : colonnes [symbol, Variational, Hyperliquid, Lighter, Extended, Pacifica]
    var_names : {ticker_variational: nom_long} pour l'heuristique de detection
    errors : {venue: message} pour les venues tombees
    """
    errors = {}
    var_names = {}

    def guard(fn, label, fallback):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - on degrade, on ne casse pas la page
            errors[label] = f"{type(exc).__name__}: {exc}"
            return fallback

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
        f_var = ex.submit(guard, lambda: _fetch_variational(timeout), "Variational", ({}, {}))
        f_hl = ex.submit(guard, lambda: _fetch_hyperliquid(timeout), "Hyperliquid", {})
        f_hlx = ex.submit(guard, lambda: _fetch_hyperliquid(timeout, HL_RWA_DEX), "Hyperliquid (RWA)", {})
        f_li = ex.submit(guard, lambda: _fetch_lighter(timeout), "Lighter", {})
        f_ext = ex.submit(guard, lambda: _fetch_extended(timeout), "Extended", {})
        f_pac = ex.submit(guard, lambda: _fetch_pacifica(timeout), "Pacifica", {})

        var_raw, var_names = f_var.result()
        hl_raw, hlx_raw = f_hl.result(), f_hlx.result()
        li_raw, ext_raw, pac_raw = f_li.result(), f_ext.result(), f_pac.result()

    parts = [
        split_venue("Variational", var_raw),
        # Hyperliquid : crypto = dex principal, RWA = dex HIP-3 "xyz", flux separes.
        split_venue("Hyperliquid", hl_raw, rwa_raw_rates=hlx_raw),
        split_venue("Lighter", li_raw),
        split_venue("Extended", ext_raw),
        split_venue("Pacifica", pac_raw),
    ]

    def assemble(series_list):
        df = pd.concat(series_list, axis=1)
        for col in EXCHANGES:
            if col not in df.columns:
                df[col] = pd.NA
        df = df[EXCHANGES].apply(pd.to_numeric, errors="coerce")
        df = df.reset_index().rename(columns={"index": "symbol"})
        return df[df["symbol"].astype(bool)]

    df_crypto = assemble([p[0] for p in parts])
    df_rwa = assemble([p[1] for p in parts])

    meta = pd.DataFrame(assets.rwa_meta(), columns=["symbol", "label", "category"])
    df_rwa = df_rwa.merge(meta, on="symbol", how="left")
    df_rwa["label"] = df_rwa["label"].fillna(df_rwa["symbol"])
    df_rwa["category"] = df_rwa["category"].fillna("Other")

    return df_crypto, df_rwa, var_names, errors


def unmapped_rwa_candidates(var_names):
    """Listings Variational qui ressemblent a du RWA mais absents du registre."""
    return sorted(
        (t, n) for t, n in var_names.items() if assets.looks_like_rwa(t, n)
    )


# --- Etat du marche US ------------------------------------------------------

def us_market_session(now=None):
    """('open'|'pre'|'after'|'closed'|'weekend', libelle) en heure de New York."""
    try:
        from zoneinfo import ZoneInfo
        ny = (now or datetime.now(timezone.utc)).astimezone(ZoneInfo("America/New_York"))
    except Exception:  # noqa: BLE001 - tzdata absent : on ne bloque pas la page
        return "unknown", "US market status unavailable"

    if ny.weekday() >= 5:
        return "weekend", f"US market closed (weekend) - {ny:%a %H:%M} NY"
    minutes = ny.hour * 60 + ny.minute
    if 9 * 60 + 30 <= minutes < 16 * 60:
        return "open", f"US market open - {ny:%H:%M} NY"
    if 4 * 60 <= minutes < 9 * 60 + 30:
        return "pre", f"US pre-market - {ny:%H:%M} NY"
    if 16 * 60 <= minutes < 20 * 60:
        return "after", f"US after-hours - {ny:%H:%M} NY"
    return "closed", f"US market closed - {ny:%H:%M} NY"
