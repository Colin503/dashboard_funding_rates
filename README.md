# ⚖️ Multi-DEX Funding Arbitrage Map

[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://variationalfundingrates.streamlit.app/)

A real-time arbitrage dashboard that monitors and compares funding rates across **Variational Omni**, **Hyperliquid**, and **Lighter**. This tool identifies Delta-Neutral opportunities by highlighting the spread between different perpetual exchanges.

## 🔗 Live Dashboard
**Access the hosted app here: [https://variationalfundingrates.streamlit.app/](https://variationalfundingrates.streamlit.app/)**

## ✨ Features

- **Multi-DEX Aggregation**: Real-time data fetching from Variational, Hyperliquid, and Lighter APIs.
- **Smart Arbitrage Filter**: Automatically hides assets that are not available on at least two platforms to focus only on tradable opportunities.
- **Visual Trading Guide**: 
    - 🟩 **Green Cells**: Highlight the lowest funding rate for an asset (**Long Opportunity**).
    - 🟥 **Red Cells**: Highlight the highest funding rate for an asset (**Short Opportunity**).
- **Automated De-duplication**: Cleans raw API data (especially from Lighter) to ensure one unique row per ticker.
- **Profit Potential (Spread)**: Calculates the maximum APR gap between available exchanges.

## 📊 Calculation & Data Logic

To ensure fair comparison, all funding rates are converted to **Annualized Percentage Rate (APR)**:

* **Variational**: `funding_rate` * 100 (API provides raw annual base).
* **Hyperliquid**: `daily_funding` * 365 * 100.
* **Lighter**: `periodic_rate` * (Number of periods per year) * 100.

## 🛠️ Installation & Local Run

1. **Clone the repository**:
   ```bash
   git clone [https://github.com/votre-username/variational_funding_rates.git](https://github.com/votre-username/variational_funding_rates.git)
   cd variational_funding_rates
