# Equity Stock Screener (India) 📈

An advanced, dual-interface stock screening tool tailored for the Indian stock market (NSE). This project includes an interactive web application built with Streamlit and a robust backend CLI engine for generating comprehensive technical watchlists. 

## 🚀 Features

### 1. Interactive Web Application (`app.py`)
A visually rich Streamlit dashboard that visualizes specific chart setups across major NSE indices.
* **Pre-defined Setups:** Scans for high-probability technical patterns:
  * *Tight Consolidation:* Low volatility periods preceding explosive moves.
  * *Long Base Breakout:* Multi-month resistance breakouts.
  * *Box Setup:* Darvas box-style trading setups.
* **NSE Index Fetcher:** Dynamically pulls the latest ticker lists for indices like Nifty 50, Nifty Next 50, Nifty Midcap 150, etc., directly from NSE archives.
* **Interactive Charts:** Beautiful candlestick charts with technical overlays using Plotly.

### 2. Nifty 500 Watchlist Engine (`screener.py`)
A highly configurable CLI screener that crunches Nifty 500 stocks to output a ranked watchlist to Excel.
* **Momentum Ranking:** Uses 12-1 month momentum scores to rank stocks.
* **Trend & Strength Filters:** Filters by 50/200 EMAs and optimal RSI ranges (50-70).
* **Liquidity Checks:** Discards stocks based on minimum average daily turnover in ₹ crores and minimum price.
* **Volume Analytics:** Evaluates up-day volume ratio and checks for breakout volume multipliers.
* **Sector Diversification:** Prevents sector concentration by limiting the number of stocks per industry.
* **Export:** Automatically generates a comprehensive Excel report (`india_watchlist.xlsx`).

## 🛠 Tech Stack

* **Language:** Python
* **Web UI:** `streamlit`
* **Market Data:** `yfinance`, `requests`
* **Data Processing:** `pandas`, `numpy`
* **Visualization:** `plotly`, `altair`
* **Export:** `openpyxl`

## ⚙️ Installation

1. Ensure you have Python installed (3.8+ recommended).
2. Activate your virtual environment (recommended):
   ```bash
   # On Windows
   .\venv\Scripts\activate
   
   # On macOS/Linux
   source venv/bin/activate
   ```
3. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## 🎯 Usage

### Running the Web Dashboard
To launch the interactive Streamlit app, run:
```bash
streamlit run app.py
```
This will open the dashboard in your default web browser (usually at `http://localhost:8501`).

### Running the CLI Engine
To run the programmatic screener and generate an Excel watchlist, run:
```bash
python screener.py
```
Check your directory for the generated `india_watchlist.xlsx` file after execution completes.

## ⚠️ Disclaimer
**For Educational Purposes Only.** The screening setups and algorithms provided in this repository do not constitute financial advice. Always perform your own due diligence and consult with a certified financial advisor before making investment decisions in the stock market.