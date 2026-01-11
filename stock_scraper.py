#!/usr/bin/env python3
"""
Stock Financial Data Scraper

Fetches quarterly revenue and gross margin from Yahoo Finance for a list of tickers.
Outputs results to an Excel file.

Usage:
    python stock_scraper.py tickers.txt --output stock_financials.xlsx
"""

import argparse
import sys
import time
from pathlib import Path

import pandas as pd
import yfinance as yf
from tqdm import tqdm


def read_tickers(file_path: str) -> list[str]:
    """Read tickers from a file (supports .txt, .csv, .xlsx)."""
    path = Path(file_path)
    
    if path.suffix.lower() == '.xlsx':
        df = pd.read_excel(path, header=None)
        tickers = df.iloc[:, 0].dropna().astype(str).tolist()
    elif path.suffix.lower() == '.csv':
        df = pd.read_csv(path, header=None)
        tickers = df.iloc[:, 0].dropna().astype(str).tolist()
    else:
        # Plain text file, one ticker per line
        with open(path, 'r') as f:
            tickers = [line.strip() for line in f if line.strip()]
    
    # Clean up tickers (uppercase, remove any whitespace)
    tickers = [t.upper().strip() for t in tickers if t.strip()]
    return tickers


def get_quarterly_financials(ticker: str) -> tuple[dict, dict]:
    """
    Fetch the most recent quarterly revenue and calculate gross margin.
    
    Returns tuple of:
        - formatted result dict
        - raw data dict (all income statement line items)
    """
    result = {
        'ticker': ticker,
        'revenue': None,
        'cost_of_goods_sold': None,
        'gross_margin': None,
        'quarter_end_date': None,
        'error': None
    }
    raw_data = {'ticker': ticker}
    
    try:
        stock = yf.Ticker(ticker)
        
        # Get quarterly income statement
        income_stmt = stock.quarterly_income_stmt
        
        if income_stmt.empty:
            result['error'] = 'No income statement data available'
            return result, raw_data
        
        # Get the most recent quarter (first column)
        most_recent = income_stmt.iloc[:, 0]
        quarter_date = income_stmt.columns[0]
        
        # Store all raw income statement values
        raw_data['quarter_end_date'] = quarter_date.strftime('%Y-%m-%d') if hasattr(quarter_date, 'strftime') else str(quarter_date)
        for idx in most_recent.index:
            raw_data[idx] = most_recent[idx]
        
        # Try to find revenue (different names in Yahoo Finance)
        revenue_keys = ['Total Revenue', 'Revenue', 'Operating Revenue']
        revenue = None
        for key in revenue_keys:
            if key in most_recent.index:
                revenue = most_recent[key]
                break
        
        # Try to find cost of goods sold
        cogs_keys = ['Cost Of Revenue', 'Cost of Revenue', 'Cost Of Goods Sold', 'COGS']
        cogs = None
        for key in cogs_keys:
            if key in most_recent.index:
                cogs = most_recent[key]
                break
        
        result['revenue'] = revenue
        result['cost_of_goods_sold'] = cogs
        result['quarter_end_date'] = quarter_date.strftime('%Y-%m-%d') if hasattr(quarter_date, 'strftime') else str(quarter_date)
        
        # Calculate gross margin if we have both values
        if revenue is not None and cogs is not None and revenue != 0:
            gross_profit = revenue - cogs
            result['gross_margin'] = (gross_profit / revenue) * 100
        
    except Exception as e:
        result['error'] = str(e)
    
    return result, raw_data


def main():
    parser = argparse.ArgumentParser(
        description='Fetch quarterly revenue and gross margin from Yahoo Finance'
    )
    parser.add_argument(
        'tickers_file',
        help='Path to file containing stock tickers (one per line, or CSV/Excel)'
    )
    parser.add_argument(
        '--output', '-o',
        default='stock_financials.xlsx',
        help='Output Excel file path (default: stock_financials.xlsx)'
    )
    parser.add_argument(
        '--delay',
        type=float,
        default=0.5,
        help='Delay between requests in seconds (default: 0.5)'
    )
    
    args = parser.parse_args()
    
    # Read tickers
    print(f"Reading tickers from {args.tickers_file}...")
    try:
        tickers = read_tickers(args.tickers_file)
    except FileNotFoundError:
        print(f"Error: File not found: {args.tickers_file}")
        sys.exit(1)
    
    print(f"Found {len(tickers)} tickers to process")
    
    # Fetch data for each ticker
    results = []
    raw_data_list = []
    errors = []
    
    for ticker in tqdm(tickers, desc="Fetching data"):
        data, raw_data = get_quarterly_financials(ticker)
        results.append(data)
        raw_data_list.append(raw_data)
        
        if data['error']:
            errors.append(f"{ticker}: {data['error']}")
        
        # Small delay to avoid rate limiting
        time.sleep(args.delay)
    
    # Create formatted DataFrame
    df = pd.DataFrame(results)
    
    df_output = pd.DataFrame({
        'Ticker': df['ticker'],
        'Quarterly Revenue': df['revenue'],
        'Cost of Goods Sold': df['cost_of_goods_sold'],
        'Gross Margin (%)': df['gross_margin'].round(2),
        'Quarter End Date': df['quarter_end_date'],
        'Notes': df['error'].fillna('')
    })
    
    # Create raw data DataFrame
    df_raw = pd.DataFrame(raw_data_list)
    
    # Save to Excel with multiple sheets
    with pd.ExcelWriter(args.output, engine='openpyxl') as writer:
        df_output.to_excel(writer, sheet_name='Summary', index=False)
        df_raw.to_excel(writer, sheet_name='Raw Data', index=False)
    
    print(f"\nResults saved to {args.output}")
    print(f"  - 'Summary' sheet: Formatted financial data")
    print(f"  - 'Raw Data' sheet: All income statement line items")
    
    # Summary
    success_count = len([r for r in results if r['error'] is None])
    print(f"\nSummary:")
    print(f"  Successfully processed: {success_count}/{len(tickers)}")
    print(f"  Errors/No data: {len(errors)}")
    
    if errors:
        print(f"\nTickers with errors:")
        for err in errors:
            print(f"  - {err}")


if __name__ == '__main__':
    main()
