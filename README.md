# Stock Trade Data Visualizer

A Python tool for parsing and visualizing stock trade data from German brokers. Generates an interactive HTML dashboard with charts and statistics.

## Supported Data Sources

- **ZERO Broker**: CSV export files (`ZERO-*.csv`)
- **Trade Republic**: PDF account statements (`Kontoauszug.pdf`)

## Features

- Parse transactions from CSV and PDF files
- Automatic duplicate detection and removal
- German number and date format handling
- Interactive HTML dashboard with:
  - Summary statistics (deposits, withdrawals, realized P&L, dividends, tax refunds)
  - Trade volume charts by month and weekday
  - Open and closed positions tables with sorting
  - P&L over time chart
  - Scatter plots showing hold time vs. returns
  - Logarithmic scale toggle for volume charts

## Requirements

- Python 3.10+
- pdfplumber (optional, for PDF parsing)

## Installation

```bash
pip install -r requirements.txt
```

## Usage

1. Place your data files in the same directory as `parse_trades.py`:
   - CSV files from ZERO broker (named `ZERO-*.csv`)
   - PDF statements from Trade Republic

2. Run the script:

```bash
python parse_trades.py
```

3. Open the generated `trades_overview.html` in a browser.

## Output

The script generates `trades_overview.html` containing:

- **Stats Cards**: Deposits, withdrawals, realized P&L, invested capital, tax refunds, dividends, total volume, trade count
- **Volume Charts**: Monthly and weekday trading volume breakdown (buy/sell)
- **Open Positions Table**: Currently held positions with average cost basis
- **Closed Positions Table**: Fully closed trades with realized P&L
- **All Trades Table**: Chronological list of all trades with sorting
- **P&L Timeline**: Cumulative profit/loss over time
- **Scatter Plots**: Hold duration vs. returns (percentage and absolute)

## Supported Transaction Types

- Orders (buy/sell)
- Savings plans (Sparplan)
- Fractional shares (Bruchstucke)
- Dividends
- Tax optimizations (Steuerausgleich)
- Deposits and withdrawals
- Knock-out settlements (WP-Abrechnung)

## License

MIT
