"""
Registre des actifs RWA et classification RWA / Crypto.

Aucune API des 5 exchanges n'expose de champ "categorie". La classification
repose donc sur deux mecanismes complementaires :

1. RWA_REGISTRY (source de verite) : univers cure, indexe sur le ticker
   Variational. C'est aussi la table d'alias qui permet de reconcilier un
   meme actif entre les venues (l'or = XAU / xyz:GOLD / XAU / XAU / XAU).

2. looks_like_rwa() (filet de securite) : heuristique sur le champ `name` de
   Variational. Elle ne classe rien, elle sert uniquement a signaler dans l'UI
   les nouveaux listings RWA pas encore mappes.

Pieges connus, d'ou l'obligation d'une table curee :
  - VAR "SPX"  = SPX6900 (memecoin), pas le S&P 500
  - VAR "CVX"  = Convex Finance,     alors que HL "xyz:CVX" = Chevron
  - VAR "QNT"  = Quant,              alors que HL "xyz:QNT" = Quantinuum (= VAR "QNTX")
  - VAR "T"/"C"/"M"/"A"/"US"/"IN"/"ON"/"4" sont tous des tokens
"""

# Categories
EQUITY = "Equity"
ETF = "ETF / Index"
COMMODITY = "Commodity"
PRE_IPO = "Pre-IPO"

# Patrons de ticker par venue. {s} = symbole canonique (= ticker Variational).
# Plusieurs patrons = on essaie dans l'ordre, le premier trouve gagne.
VENUE_PATTERNS = {
    "Variational": ["{s}"],
    "Hyperliquid": ["xyz:{s}"],
    "Lighter":     ["{s}", "{s}USD"],
    "Extended":    ["{s}_24_5", "{s}"],
    "Pacifica":    ["{s}"],
}

# symbole_canonique: (libelle, categorie, alias_par_venue)
# Les alias s'AJOUTENT aux patrons par defaut : une venue peut coter le meme
# actif sous deux tickers (Extended liste "GOOGL" et "GOOG_24_5"), et un alias
# absent des donnees d'une venue est simplement ignore.
# Un alias a None bloque explicitement la venue (collision de ticker connue).
RWA_REGISTRY = {
    # --- Equities -----------------------------------------------------------
    "AAOI":  ("Applied Optoelectronics", EQUITY, {}),
    "AAPL":  ("Apple", EQUITY, {}),
    "ALAB":  ("Astera Labs", EQUITY, {}),
    "AMAT":  ("Applied Materials", EQUITY, {}),
    "AMD":   ("Advanced Micro Devices", EQUITY, {}),
    "AMZN":  ("Amazon", EQUITY, {}),
    "ARM":   ("Arm Holdings", EQUITY, {}),
    "AVGO":  ("Broadcom", EQUITY, {}),
    "BABA":  ("Alibaba", EQUITY, {}),
    "BBX":   ("BlackBerry", EQUITY, {"Hyperliquid": "xyz:BB", "Lighter": "BB", "Extended": "BB"}),
    "BMNR":  ("Bitmine Immersion", EQUITY, {}),
    "BNC":   ("CEA Industries", EQUITY, {}),
    "BOT":   ("RoboStrategy", EQUITY, {}),
    "BRKB":  ("Berkshire Hathaway", EQUITY, {}),
    "BX":    ("Blackstone", EQUITY, {}),
    "CAT":   ("Caterpillar", EQUITY, {"Lighter": None, "Extended": None, "Pacifica": None}),
    "CBRS":  ("Cerebras Systems", EQUITY, {}),
    "CIEN":  ("Ciena", EQUITY, {}),
    "COIN":  ("Coinbase Global", EQUITY, {}),
    "COST":  ("Costco", EQUITY, {}),
    "CRCL":  ("Circle Internet Group", EQUITY, {}),
    "CRDO":  ("Credo Technology", EQUITY, {}),
    "CRM":   ("Salesforce", EQUITY, {}),
    "CRWD":  ("CrowdStrike", EQUITY, {}),
    "CRWV":  ("CoreWeave", EQUITY, {}),
    "CSCO":  ("Cisco Systems", EQUITY, {}),
    "DELL":  ("Dell Technologies", EQUITY, {}),
    "DIS":   ("Walt Disney", EQUITY, {}),
    "DKNG":  ("DraftKings", EQUITY, {}),
    "EBAY":  ("eBay", EQUITY, {}),
    "FWDI":  ("Forward Industries", EQUITY, {}),
    "GME":   ("GameStop", EQUITY, {}),
    "GOOGL": ("Alphabet", EQUITY, {"Extended": "GOOG_24_5"}),
    "GPRO":  ("GoPro", EQUITY, {}),
    "HD":    ("Home Depot", EQUITY, {}),
    "HIMS":  ("Hims & Hers Health", EQUITY, {}),
    "HOOD":  ("Robinhood Markets", EQUITY, {}),
    "HPE":   ("Hewlett Packard Enterprise", EQUITY, {}),
    "IBM":   ("IBM", EQUITY, {}),
    "INTC":  ("Intel", EQUITY, {}),
    "IREN":  ("IREN", EQUITY, {}),
    "JPM":   ("JPMorgan Chase", EQUITY, {}),
    "KLAC":  ("KLA Corporation", EQUITY, {}),
    # VAR LITE = Lumentum. "LITE" est ambigu sur Lighter/Extended -> HL seul.
    "LITE":  ("Lumentum Holdings", EQUITY, {"Lighter": None, "Extended": None}),
    "LLY":   ("Eli Lilly", EQUITY, {}),
    "META":  ("Meta Platforms", EQUITY, {}),
    "MRNA":  ("Moderna", EQUITY, {}),
    "MRVL":  ("Marvell Technology", EQUITY, {}),
    "MSFT":  ("Microsoft", EQUITY, {}),
    "MSTR":  ("Strategy (MicroStrategy)", EQUITY, {}),
    "MU":    ("Micron Technology", EQUITY, {}),
    "NBIS":  ("Nebius Group", EQUITY, {}),
    "NFLX":  ("Netflix", EQUITY, {}),
    "NOK":   ("Nokia", EQUITY, {}),
    "NVDA":  ("NVIDIA", EQUITY, {}),
    "NVO":   ("Novo Nordisk", EQUITY, {}),
    "ORCL":  ("Oracle", EQUITY, {}),
    "PAYP":  ("PayPay", EQUITY, {}),
    "PLTR":  ("Palantir Technologies", EQUITY, {}),
    "QCOM":  ("QUALCOMM", EQUITY, {}),
    # VAR QNTX = Quantinuum, HL "xyz:QNT" aussi. Lighter et Extended listent un
    # "QNT" nu, impossible de trancher entre Quantinuum et le token Quant : on
    # les bloque plutot que d'afficher un taux potentiellement faux.
    "QNTX":  ("Quantinuum", EQUITY, {"Hyperliquid": "xyz:QNT", "Lighter": None, "Extended": None}),
    "RDDT":  ("Reddit", EQUITY, {}),
    "RIVN":  ("Rivian Automotive", EQUITY, {}),
    "RKLB":  ("Rocket Lab USA", EQUITY, {}),
    "SHAZ":  ("SharonAI Holdings", EQUITY, {}),
    "SKHY":  ("SK hynix", EQUITY, {"Pacifica": "SKHYNIX"}),
    "SMCI":  ("Super Micro Computer", EQUITY, {}),
    "SNDK":  ("Sandisk", EQUITY, {}),
    "SNOW":  ("Snowflake", EQUITY, {}),
    "SONY":  ("Sony Group", EQUITY, {}),
    "STRC":  ("Strategy Inc (STRC)", EQUITY, {}),
    "STXX":  ("Seagate Technology", EQUITY, {}),
    "TER":   ("Teradyne", EQUITY, {}),
    "TSLA":  ("Tesla", EQUITY, {}),
    "TSM":   ("Taiwan Semiconductor", EQUITY, {}),
    "TTWO":  ("Take-Two Interactive", EQUITY, {}),
    "TXN":   ("Texas Instruments", EQUITY, {}),
    "UBER":  ("Uber Technologies", EQUITY, {}),
    "USAR":  ("USA Rare Earth", EQUITY, {}),
    "VISA":  ("Visa", EQUITY, {}),
    # VAR WEN = The Wendy's Company ; "WEN" sur Lighter est un memecoin Solana.
    "WEN":   ("Wendy's", EQUITY, {"Lighter": None, "Extended": None, "Pacifica": None}),
    "WMT":   ("Walmart", EQUITY, {}),
    "ZM":    ("Zoom Communications", EQUITY, {}),

    # --- ETF / Indices ------------------------------------------------------
    "DRAM":  ("Roundhill Memory ETF", ETF, {}),
    "EWJ":   ("iShares MSCI Japan", ETF, {}),
    "EWT":   ("iShares MSCI Taiwan", ETF, {}),
    "EWY":   ("iShares MSCI South Korea", ETF, {}),
    "EWZ":   ("iShares MSCI Brazil", ETF, {}),
    "IWM":   ("iShares Russell 2000", ETF, {}),
    "KSTR":  ("KraneShares SSE STAR 50", ETF, {}),
    "QQQ":   ("Invesco QQQ Trust", ETF, {"Hyperliquid": None, "Extended": "TECH100m"}),
    "SOXL":  ("Direxion Semiconductor Bull 3X", ETF, {}),
    "SOXS":  ("Direxion Semiconductor Bear 3X", ETF, {}),
    "SPCX":  ("SPAC and New Issue ETF", ETF, {}),
    "TMF":   ("Direxion 20Y+ Treasury Bull 3X", ETF, {}),
    "TZA":   ("Direxion Small Cap Bear 3X", ETF, {}),
    "URNM":  ("Sprott Uranium Miners", ETF, {}),
    "US500": ("S&P 500", ETF, {"Hyperliquid": "xyz:SP500", "Pacifica": "SP500", "Extended": "SPX500m"}),
    "UVXY":  ("ProShares Ultra VIX Short-Term", ETF, {}),
    "XBI":   ("SPDR S&P Biotech", ETF, {}),
    "XLE":   ("SPDR Energy Select Sector", ETF, {}),

    # --- Commodities --------------------------------------------------------
    "BZ":     ("Brent Crude Oil", COMMODITY, {"Hyperliquid": "xyz:BRENTOIL", "Lighter": "BRENTOIL", "Extended": "XBR"}),
    "CL":     ("WTI Crude Oil", COMMODITY, {"Lighter": "WTI", "Extended": "WTI"}),
    "COPPER": ("Copper", COMMODITY, {"Lighter": "XCU", "Extended": "XCU"}),
    "NATGAS": ("Natural Gas", COMMODITY, {"Extended": "XNG"}),
    "XAG":    ("Silver", COMMODITY, {"Hyperliquid": "xyz:SILVER"}),
    "XAU":    ("Gold", COMMODITY, {"Hyperliquid": "xyz:GOLD"}),
    "XPD":    ("Palladium", COMMODITY, {"Hyperliquid": "xyz:PALLADIUM"}),
    "XPT":    ("Platinum", COMMODITY, {"Hyperliquid": "xyz:PLATINUM", "Pacifica": "PLATINUM"}),

    # --- Pre-IPO ------------------------------------------------------------
    "ANTHROPIC": ("Anthropic", PRE_IPO, {"Hyperliquid": None, "Extended": "ANTHROP"}),
    "OPENAI":    ("OpenAI", PRE_IPO, {"Hyperliquid": None}),
}

# Marches Variational sans funding (funding_interval_s == 0) : ce sont des swaps,
# pas des perps. Ils n'ont pas de funding a arbitrer -> exclus des deux onglets.
NO_FUNDING_MARKETS = {"UKOILP", "US100S", "US500S", "USOILP", "XAGS", "XAUS"}


def candidate_tickers(canonical, venue):
    """Tickers a essayer sur `venue` pour l'actif canonique donne. [] si bloque."""
    entry = RWA_REGISTRY.get(canonical)
    if entry is None:
        return []

    aliases = entry[2]
    if venue in aliases and aliases[venue] is None:
        return []

    tickers = [p.format(s=canonical) for p in VENUE_PATTERNS.get(venue, ["{s}"])]

    extra = aliases.get(venue)
    if isinstance(extra, str):
        extra = [extra]
    for alias in extra or []:
        if alias not in tickers:
            tickers.append(alias)
    return tickers


def build_venue_lookup(venue):
    """{ticker_venue: symbole_canonique} pour resoudre un flux brut en RWA."""
    lookup = {}
    for canonical in RWA_REGISTRY:
        for ticker in candidate_tickers(canonical, venue):
            # Le premier patron gagne : on n'ecrase pas un mapping deja pose.
            lookup.setdefault(ticker, canonical)
    return lookup


def rwa_meta():
    """DataFrame-friendly : [(symbol, label, category), ...]"""
    return [(s, v[0], v[1]) for s, v in RWA_REGISTRY.items()]


# --- Heuristique de detection (signalement uniquement, ne classe pas) --------
_RWA_NAME_KEYWORDS = (
    "inc", "corp", "corporation", "ltd", "plc", "co.", "company", "etf",
    "trust", "index", "shares", "holdings", "oyj", "n.v.", "limited",
    "& co", "sector", "spdr", "ishares", "direxion", "proshares", "invesco",
    "sprott", "kraneshares", "vaneck", "global x", "swap on", "crude", "oil",
    "natural gas", "gold", "silver", "copper", "platinum", "palladium",
    "uranium", "common stock", "depositary",
)

# Noms crypto qui declenchent l'heuristique a tort (Adventure Gold, ETHGas...).
_HEURISTIC_FALSE_POSITIVES = {
    "AGLD", "C", "ELSA", "F", "GAS", "GWEI", "KAS", "ONG", "PAXG", "PIEVERSE",
    "SUPER", "TREE", "TWT", "UB", "XAUT", "ZBT", "QNT", "CVX", "SPX",
}


def looks_like_rwa(ticker, name):
    """Heuristique sur le nom long Variational. Sert a SIGNALER un RWA
    potentiellement non mappe, jamais a classer une ligne."""
    if ticker in RWA_REGISTRY or ticker in _HEURISTIC_FALSE_POSITIVES:
        return False
    low = (name or "").lower()
    return any(
        low == kw or low.endswith(" " + kw) or low.endswith(kw)
        or (" " + kw + " ") in low or low.startswith(kw + " ")
        for kw in _RWA_NAME_KEYWORDS
    )
