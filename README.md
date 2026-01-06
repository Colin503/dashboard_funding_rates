# 🏹 Variational Funding Monitor

[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://variationalfundingrates.streamlit.app/)

A real-time dashboard to monitor and analyze funding rates on **Variational Omni**. This tool helps traders identify high-yield opportunities (APR) and potential market imbalances.

## 🔗 Live Dashboard
**Access the hosted app here: [https://variationalfundingrates.streamlit.app/](https://variationalfundingrates.streamlit.app/)**

## ✨ Features

- **Live Data**: Fetches real-time statistics directly from the Variational Public REST API.
- **APR Tracking**: Automatically calculates the Annual Percentage Rate (APR) for all listings.
- **Periodic Rates**: Displays the funding rate per specific interval (e.g., 4h or 8h) as shown on the exchange interface.
- **Extreme Funding Detection**: Instantly identifies the Top 10 markets where Longs pay Shorts (High Positive APR) and where Shorts pay Longs (High Negative APR).
- **Volume Metrics**: Integrates 24h trading volume to filter significant opportunities.

## 🛠️ Technical Stack

- **Language**: Python
- **Dashboard**: Streamlit
- **Data Visualization**: Plotly
- **API**: Variational Omni Client API (`https://omni-client-api.prod.ap-northeast-1.variational.io/metadata/stats`)

## 🚀 How to Run Locally

1. **Clone the repository**:
   ```bash
   git clone [https://github.com/votre-username/variational_funding_rates.git](https://github.com/votre-username/variational_funding_rates.git)
   cd variational_funding_rates
