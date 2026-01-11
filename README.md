Disclaimer, none of this is tested use at your own risk

# Wyatt - Stock Financial Data Scraper


Pull quarterly revenue and gross margin for stocks from Yahoo Finance and SEC EDGAR.

## Setup

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
# Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh
```

## Usage

### Yahoo Finance

```bash
uv run stock_scraper.py tickers.txt --output yfinance_output.xlsx
```

### SEC EDGAR (Official Filings)

```bash
uv run edgar_scraper.py tickers.txt --email your@email.com --output edgar_output.xlsx
```

The `--email` flag is required by the SEC for API access.

## Input Format

Create a text file with one ticker per line:

```
TSLA
AAPL
MSFT
GOOGL
```

Also supports `.csv` and `.xlsx` files (tickers in the first column).

## Output

Both scripts produce Excel files with two sheets:

| Sheet | Contents |
|-------|----------|
| **Summary** | Ticker, Quarterly Revenue, Cost of Goods Sold, Gross Margin (%), Quarter End Date, Notes |
| **Raw Data** | All raw API response data for transparency |

## Options

| Flag | Description | Default |
|------|-------------|---------|
| `--output`, `-o` | Output Excel file path | `stock_financials.xlsx` / `edgar_financials.xlsx` |
| `--delay` | Delay between requests (seconds) | 0.5 (Yahoo) / 0.15 (EDGAR) |
| `--email`, `-e` | Your email (EDGAR only, required) | — |

## Notes

- ETFs (SPY, QQQ, etc.) and mutual funds (VTSAX, etc.) don't have income statements since they're not operating companies
- EDGAR data comes from official 10-Q filings; Yahoo Finance data is sourced from their API
- Gross margin is calculated as: `(Revenue - Cost of Goods Sold) / Revenue * 100`
