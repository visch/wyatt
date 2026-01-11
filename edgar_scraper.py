#!/usr/bin/env python3
"""
SEC EDGAR Financial Data Scraper

Fetches quarterly revenue and gross margin directly from SEC EDGAR filings.
Outputs results to an Excel file with both formatted and raw data sheets.

Usage:
    python edgar_scraper.py tickers.txt --output edgar_financials.xlsx --email your@email.com
"""

import argparse
import json
import sys
import time
from pathlib import Path

import pandas as pd
import requests
from tqdm import tqdm


# SEC EDGAR API endpoints
COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
COMPANY_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"

# XBRL tags for financial data we're interested in
REVENUE_TAGS = [
    'Revenues',
    'RevenueFromContractWithCustomerExcludingAssessedTax',
    'RevenueFromContractWithCustomerIncludingAssessedTax',
    'SalesRevenueNet',
    'SalesRevenueGoodsNet',
    'TotalRevenuesAndOtherIncome',
]

COGS_TAGS = [
    'CostOfRevenue',
    'CostOfGoodsAndServicesSold',
    'CostOfGoodsSold',
    'CostOfGoodsAndServiceExcludingDepreciationDepletionAndAmortization',
]


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
        with open(path, 'r') as f:
            tickers = [line.strip() for line in f if line.strip()]
    
    tickers = [t.upper().strip() for t in tickers if t.strip()]
    return tickers


def get_cik_mapping(session: requests.Session) -> dict[str, str]:
    """Fetch the ticker to CIK mapping from SEC."""
    response = session.get(COMPANY_TICKERS_URL)
    response.raise_for_status()
    
    data = response.json()
    
    # Build ticker -> CIK mapping (CIK padded to 10 digits)
    mapping = {}
    for entry in data.values():
        ticker = entry['ticker'].upper()
        cik = str(entry['cik_str']).zfill(10)
        mapping[ticker] = cik
    
    return mapping


def get_company_facts(session: requests.Session, cik: str) -> dict | None:
    """Fetch company facts from SEC EDGAR."""
    url = COMPANY_FACTS_URL.format(cik=cik)
    
    try:
        response = session.get(url)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()
    except requests.RequestException:
        return None


def extract_quarterly_value(facts: dict, tags: list[str], form: str = '10-Q') -> tuple[float | None, str | None, dict | None]:
    """
    Extract the most recent quarterly value for given XBRL tags.
    
    Returns: (value, end_date, raw_entry)
    """
    us_gaap = facts.get('facts', {}).get('us-gaap', {})
    
    for tag in tags:
        if tag not in us_gaap:
            continue
        
        tag_data = us_gaap[tag]
        units = tag_data.get('units', {})
        
        # Usually financial values are in USD
        usd_data = units.get('USD', [])
        
        if not usd_data:
            continue
        
        # Filter for quarterly filings (10-Q) and find the most recent
        quarterly_entries = [
            entry for entry in usd_data
            if entry.get('form') == form and entry.get('frame') is not None
        ]
        
        # If no framed entries, try entries without frame (less reliable but can work)
        if not quarterly_entries:
            quarterly_entries = [
                entry for entry in usd_data
                if entry.get('form') == form
            ]
        
        if not quarterly_entries:
            continue
        
        # Sort by end date, get most recent
        quarterly_entries.sort(key=lambda x: x.get('end', ''), reverse=True)
        
        # Get the most recent entry
        latest = quarterly_entries[0]
        
        return latest.get('val'), latest.get('end'), latest
    
    return None, None, None


def get_edgar_financials(session: requests.Session, ticker: str, cik_mapping: dict) -> dict:
    """
    Fetch quarterly financial data from EDGAR for a single ticker.
    
    Returns dict with formatted data and raw data.
    """
    result = {
        'ticker': ticker,
        'cik': None,
        'revenue': None,
        'revenue_date': None,
        'cost_of_goods_sold': None,
        'cogs_date': None,
        'gross_margin': None,
        'error': None,
        'raw_revenue': None,
        'raw_cogs': None,
    }
    
    # Get CIK for ticker
    cik = cik_mapping.get(ticker)
    if not cik:
        result['error'] = 'Ticker not found in SEC database (may be ETF or foreign)'
        return result
    
    result['cik'] = cik
    
    # Fetch company facts
    facts = get_company_facts(session, cik)
    if not facts:
        result['error'] = 'No EDGAR data available'
        return result
    
    # Extract revenue
    revenue, revenue_date, raw_revenue = extract_quarterly_value(facts, REVENUE_TAGS)
    result['revenue'] = revenue
    result['revenue_date'] = revenue_date
    result['raw_revenue'] = raw_revenue
    
    # Extract cost of goods sold
    cogs, cogs_date, raw_cogs = extract_quarterly_value(facts, COGS_TAGS)
    result['cost_of_goods_sold'] = cogs
    result['cogs_date'] = cogs_date
    result['raw_cogs'] = raw_cogs
    
    # Calculate gross margin
    if revenue is not None and cogs is not None and revenue != 0:
        gross_profit = revenue - cogs
        result['gross_margin'] = (gross_profit / revenue) * 100
    
    # Check for missing data
    if revenue is None and cogs is None:
        result['error'] = 'No revenue or COGS data found in filings'
    elif revenue is None:
        result['error'] = 'Revenue not found'
    elif cogs is None:
        result['error'] = 'Cost of goods sold not found (gross margin unavailable)'
    
    return result


def main():
    parser = argparse.ArgumentParser(
        description='Fetch quarterly revenue and gross margin from SEC EDGAR'
    )
    parser.add_argument(
        'tickers_file',
        help='Path to file containing stock tickers (one per line, or CSV/Excel)'
    )
    parser.add_argument(
        '--output', '-o',
        default='edgar_financials.xlsx',
        help='Output Excel file path (default: edgar_financials.xlsx)'
    )
    parser.add_argument(
        '--email', '-e',
        required=True,
        help='Your email address (required by SEC for API access)'
    )
    parser.add_argument(
        '--delay',
        type=float,
        default=0.15,
        help='Delay between requests in seconds (default: 0.15, SEC allows 10/sec)'
    )
    
    args = parser.parse_args()
    
    # Set up session with required User-Agent
    session = requests.Session()
    session.headers.update({
        'User-Agent': f'StockScraper/1.0 ({args.email})',
        'Accept-Encoding': 'gzip, deflate',
    })
    
    # Read tickers
    print(f"Reading tickers from {args.tickers_file}...")
    try:
        tickers = read_tickers(args.tickers_file)
    except FileNotFoundError:
        print(f"Error: File not found: {args.tickers_file}")
        sys.exit(1)
    
    print(f"Found {len(tickers)} tickers to process")
    
    # Fetch CIK mapping
    print("Fetching SEC ticker-to-CIK mapping...")
    try:
        cik_mapping = get_cik_mapping(session)
        print(f"Loaded {len(cik_mapping)} ticker mappings")
    except requests.RequestException as e:
        print(f"Error fetching CIK mapping: {e}")
        sys.exit(1)
    
    # Fetch data for each ticker
    results = []
    raw_data_rows = []
    errors = []
    
    for ticker in tqdm(tickers, desc="Fetching EDGAR data"):
        data = get_edgar_financials(session, ticker, cik_mapping)
        results.append(data)
        
        # Collect raw data for raw sheet
        raw_row = {
            'ticker': ticker,
            'cik': data['cik'],
            'revenue_raw_json': json.dumps(data['raw_revenue']) if data['raw_revenue'] else None,
            'cogs_raw_json': json.dumps(data['raw_cogs']) if data['raw_cogs'] else None,
        }
        
        # Flatten raw data fields if available
        if data['raw_revenue']:
            for key, val in data['raw_revenue'].items():
                raw_row[f'revenue_{key}'] = val
        if data['raw_cogs']:
            for key, val in data['raw_cogs'].items():
                raw_row[f'cogs_{key}'] = val
        
        raw_data_rows.append(raw_row)
        
        if data['error']:
            errors.append(f"{ticker}: {data['error']}")
        
        time.sleep(args.delay)
    
    # Create formatted DataFrame
    df_formatted = pd.DataFrame({
        'Ticker': [r['ticker'] for r in results],
        'CIK': [r['cik'] for r in results],
        'Quarterly Revenue': [r['revenue'] for r in results],
        'Revenue Quarter End': [r['revenue_date'] for r in results],
        'Cost of Goods Sold': [r['cost_of_goods_sold'] for r in results],
        'COGS Quarter End': [r['cogs_date'] for r in results],
        'Gross Margin (%)': [round(r['gross_margin'], 2) if r['gross_margin'] else None for r in results],
        'Notes': [r['error'] if r['error'] else '' for r in results],
    })
    
    # Create raw DataFrame
    df_raw = pd.DataFrame(raw_data_rows)
    
    # Save to Excel with multiple sheets
    with pd.ExcelWriter(args.output, engine='openpyxl') as writer:
        df_formatted.to_excel(writer, sheet_name='Summary', index=False)
        df_raw.to_excel(writer, sheet_name='Raw Data', index=False)
    
    print(f"\nResults saved to {args.output}")
    print(f"  - 'Summary' sheet: Formatted financial data")
    print(f"  - 'Raw Data' sheet: Raw EDGAR API response data")
    
    # Summary
    success_count = len([r for r in results if r['revenue'] is not None])
    print(f"\nSummary:")
    print(f"  Tickers with revenue data: {success_count}/{len(tickers)}")
    print(f"  Errors/No data: {len(errors)}")
    
    if errors:
        print(f"\nTickers with issues:")
        for err in errors:
            print(f"  - {err}")


if __name__ == '__main__':
    main()
