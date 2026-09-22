# Multi-DEX Funding Arbitrage Map

[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://fundingarbitrage.streamlit.app/)

Dashboard d'arbitrage de funding rates temps réel, en deux pages sélectionnables dans la sidebar :

- **HIP-3** — arbitrage entre les builders Hyperliquid HIP-3 (Trade[xyz], Ventuals, Felix, HyENA, Kinetiq, Dreamcash, ABCD…), comparés entre eux sur le sous-jacent.
- **Multi-DEX** — arbitrage sur **Variational Omni**, **Hyperliquid**, **Lighter**, **Extended** et **Pacifica**, séparé en deux univers : **Crypto** et **RWA** (actions, ETFs, commodities, indices, pré-IPO).

Le reste de ce document décrit la page Multi-DEX.

## Live Dashboard
**[https://fundingarbitrage.streamlit.app/](https://fundingarbitrage.streamlit.app/)**

## Fonctionnement

Le dashboard est orienté **farm Variational** : Variational est toujours une jambe du trade. Pour chaque actif, on compare les deux montages possibles et on retient le plus rentable :

| Montage | On encaisse |
|---|---|
| LONG Variational / SHORT X | `funding(X) − funding(Variational)` |
| SHORT Variational / LONG X | `funding(Variational) − funding(X)` |

- **Cellule verte** : la jambe longue. **Cellule rouge** : la jambe courte.
- **APR Spread en or** : le spread actuel diverge fortement de sa moyenne 48h (inversion de signe, ou écart > 2× la moyenne avec au moins 5 points d'écart).
- **48h Pair Avg** : spread moyen historique de la *même paire* que le trade live. La colonne est masquée tant que l'historique ne couvre pas ces paires.

## Conversion en APR

Tous les taux sont annualisés en % :

| Venue | Formule | Source crypto | Source RWA |
|---|---|---|---|
| Variational | `funding_rate × 100` | `/metadata/stats` | idem |
| Hyperliquid | `funding × 24 × 365 × 100` | `metaAndAssetCtxs` | `metaAndAssetCtxs` **dex `xyz`** |
| Lighter | `rate × 3 × 365 × 100` | `/funding-rates` | idem |
| Extended | `fundingRate × 24 × 365 × 100` | `/info/markets` | idem |
| Pacifica | `next_funding_rate × 24 × 365 × 100` | `/info` | idem |

Attention : les RWA Hyperliquid ne sont **pas** dans le perp principal : ils vivent dans le dex HIP-3 `xyz` (tickers préfixés `xyz:`), qui demande un second appel.

## Classification RWA

Aucune API n'expose de champ « catégorie ». La classification repose sur [`assets.py`](assets.py) :

1. **`RWA_REGISTRY`** — univers curé indexé sur le ticker Variational, qui sert aussi de table d'alias cross-venue (l'or = `XAU` / `xyz:GOLD` / `XAU` / `XAU` / `XAU`). Les alias s'ajoutent aux patrons par défaut de chaque venue.
2. **`looks_like_rwa()`** — heuristique sur le nom long Variational. Elle ne classe rien : elle signale dans l'UI les nouveaux listings RWA pas encore mappés, à ajouter au registre.

### Pourquoi une table curée est obligatoire

Les tickers se télescopent entre crypto et RWA :

| Ticker | Sur Variational | Ailleurs |
|---|---|---|
| `SPX` | SPX6900 (memecoin) | — |
| `CVX` | Convex Finance | `xyz:CVX` = Chevron |
| `QNT` | Quant | `xyz:QNT` = Quantinuum (= VAR `QNTX`) |
| `T` `C` `M` `A` `US` `IN` `ON` `4` | tokens | — |
| `WEN` | The Wendy's Company | memecoin Solana sur Lighter |

Une venue ambiguë est bloquée (`None`) plutôt que d'afficher un taux potentiellement faux.

### Marchés fermés

Hors séance US, les venues renvoient souvent un funding à **0 pile** sur les RWA. C'est une absence de donnée, pas un taux : ces valeurs sont traitées comme manquantes pour ne pas fabriquer de spread fantôme contre une venue encore cotée. Un badge indique l'état du marché US. La table est donc plus courte hors séance.

Les marchés Variational à `funding_interval_s = 0` (swaps : `USOILP`, `UKOILP`, `US500S`, `US100S`, `XAUS`, `XAGS`) n'ont pas de funding et sont exclus.

## Structure

| Fichier | Rôle |
|---|---|
| [`main.py`](main.py) | Dashboard Streamlit : page HIP-3 + page Multi-DEX (sections Crypto / RWA) |
| [`datafeed.py`](datafeed.py) | Fetch parallèle des 5 venues + séparation Crypto/RWA (partagé) |
| [`assets.py`](assets.py) | Registre RWA, alias cross-venue, heuristique de détection |
| [`recorder.py`](recorder.py) | Snapshot périodique → `funding_history.parquet` (7 jours glissants) |

`funding_history.parquet` porte une colonne `asset_class` (`Crypto` / `RWA`) : un même ticker peut exister des deux côtés.

## Lancer en local

```bash
pip install -r requirements.txt
streamlit run main.py
```

Aucune clé API n'est requise : les endpoints Extended et Pacifica utilisés ici sont publics.
