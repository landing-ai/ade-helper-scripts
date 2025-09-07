"""
SEC EDGAR Filing Pipeline
==========================

This script provides a pipeline to pull 10-K and 8-K filings from the SEC's EDGAR database
for a given list of stock market tickers.

Features:
- Fetches 10-K and 8-K filings from SEC EDGAR API
- Handles rate limiting and API restrictions
- Supports multiple tickers in batch processing
- Saves filings to local storage
- Provides filing metadata and download links
- Error handling and retry logic

Usage:
    python sec_pipeline.py --tickers AAPL MSFT GOOGL --filing-types 10-K 8-K
"""

import requests
import json
import time
import os
import argparse
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import logging
from pathlib import Path
import pandas as pd
from urllib.parse import urljoin
import re
import threading
from weasyprint import HTML
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('sec_pipeline.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class SECEdgarPipeline:
    """
    Pipeline for fetching SEC EDGAR filings for given stock tickers.
    """
    
    TICKER_CIK_URL = "https://www.sec.gov/files/company_tickers_exchange.json"
    TICKER_CIK_CACHE = Path("sec_filings/ticker_cik_cache.json")
    TICKER_CIK_LOCK = threading.Lock()

    def __init__(self, user_agent: str = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"):
        """
        Initialize the SEC EDGAR pipeline.
        
        Args:
            user_agent: User agent string for SEC API requests
        """
        self.base_url = "https://data.sec.gov"
        self.headers = {
            'User-Agent': user_agent,
            'Accept': 'application/json',
            'Host': 'data.sec.gov'
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        
        # Rate limiting settings - very conservative for document downloads
        self.requests_per_second = 0.5  # Reduced to 1 request every 2 seconds
        self.last_request_time = 0
        
        # Create output directories
        self.output_dir = Path("sec_filings")
        self.output_dir.mkdir(exist_ok=True)
        
        # Filing type mappings
        self.filing_types = {
            '10-K': '10-K',
            '8-K': '8-K',
            '10-Q': '10-Q',
            'DEF 14A': 'DEF 14A'
        }
        self.ticker_cik_map = self._load_ticker_cik_map()
    
    def _rate_limit(self):
        """Implement rate limiting for SEC API requests."""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        min_interval = 1.0 / self.requests_per_second
        
        if time_since_last < min_interval:
            sleep_time = min_interval - time_since_last
            time.sleep(sleep_time)
        
        self.last_request_time = time.time()
    
    def _make_request(self, url: str, params: Optional[Dict] = None) -> Optional[Dict]:
        """
        Make a rate-limited request to the SEC API.
        
        Args:
            url: API endpoint URL
            params: Query parameters
            
        Returns:
            Response data as dictionary or None if failed
        """
        self._rate_limit()
        
        try:
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed for {url}: {e}")
            return None
    
    def _load_ticker_cik_map(self) -> dict:
        """
        Download and cache the SEC's ticker-to-CIK mapping file.
        Returns a dict mapping tickers to CIKs.
        """
        with self.TICKER_CIK_LOCK:
            if self.TICKER_CIK_CACHE.exists():
                try:
                    with open(self.TICKER_CIK_CACHE, 'r') as f:
                        data = json.load(f)
                        return {k.upper(): v for k, v in data.items()}
                except Exception as e:
                    logger.warning(f"Failed to load cached ticker-CIK map: {e}")
            
            # Try to download from SEC
            try:
                logger.info("Downloading SEC ticker-to-CIK mapping file...")
                resp = requests.get(self.TICKER_CIK_URL, headers=self.headers, timeout=30)
                resp.raise_for_status()
                data = resp.json()
                # The SEC file is a dict of {int: {cik_str, ticker, title}}
                ticker_map = {v['ticker'].upper(): v['cik_str'].zfill(10) for v in data.values()}
                with open(self.TICKER_CIK_CACHE, 'w') as f:
                    json.dump(ticker_map, f)
                return ticker_map
            except Exception as e:
                logger.error(f"Failed to download SEC ticker-to-CIK mapping: {e}")
                logger.info("Using fallback ticker mappings...")
                # Fallback to common ticker mappings
                fallback_map = {
                    'AAPL': '0000320193', 'MSFT': '0000789019', 'GOOGL': '0001652044',
                    'AMZN': '0001018724', 'META': '0001326801', 'TSLA': '0001318605',
                    'NVDA': '0001045810', 'AMD': '0000002488', 'NFLX': '0001065280',
                    'CRM': '0001108524', 'ORCL': '0001341439', 'INTC': '0000050863',
                    'CSCO': '0000858877', 'ADBE': '0000794338', 'PYPL': '0001633917',
                    'IBM': '0000051143', 'QCOM': '0000804328', 'AVGO': '0001730168',
                    'TXN': '0000097416', 'COST': '0000909832', 'JPM': '0000019617',
                    'JNJ': '0000200402', 'PG': '0000080424', 'UNH': '0000731766',
                    'HD': '0000354950', 'DIS': '0001001039', 'BAC': '0000070858',
                    'V': '0001403161', 'MA': '0001141391', 'WMT': '0000104169'
                }
                return fallback_map

    def get_company_info(self, ticker: str) -> Optional[Dict]:
        """
        Get company information and CIK from ticker symbol.
        
        Args:
            ticker: Stock ticker symbol
            
        Returns:
            Company information dictionary or None if not found
        """
        cik = self.ticker_cik_map.get(ticker.upper())
        if cik:
            cik_url = f"{self.base_url}/submissions/CIK{cik}.json"
            company_data = self._make_request(cik_url)
            if company_data:
                return {
                    'ticker': ticker,
                    'cik': cik,
                    'company_name': company_data.get('name', 'Unknown'),
                    'filings': company_data.get('filings', {}).get('recent', {})
                }
        # If not found, try direct CIK lookup (for cases where ticker might be CIK)
        cik_url = f"{self.base_url}/submissions/CIK{ticker.zfill(10)}.json"
        company_data = self._make_request(cik_url)
        if company_data:
            return {
                'ticker': ticker,
                'cik': ticker.zfill(10),
                'company_name': company_data.get('name', 'Unknown'),
                'filings': company_data.get('filings', {}).get('recent', {})
            }
        logger.warning(f"Could not find CIK for ticker {ticker}")
        return None
    
    def get_filings(self, cik: str, filing_types: List[str], 
                    start_date: Optional[str] = None, 
                    end_date: Optional[str] = None,
                    years: Optional[List[int]] = None,
                    quarters: Optional[List[int]] = None) -> List[Dict]:
        """
        Get filings for a specific CIK and filing types, with optional year/quarter filtering.
        Args:
            cik: Company CIK (10-digit zero-padded)
            filing_types: List of filing types to fetch
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            years: List of years to filter (for 10-K, 8-K)
            quarters: List of quarters to filter (for 8-K)
        Returns:
            List of filing dictionaries
        """
        url = f"{self.base_url}/submissions/CIK{cik}.json"
        company_data = self._make_request(url)
        if not company_data:
            logger.error(f"Failed to get company data for CIK {cik}")
            return []
        filings = company_data.get('filings', {}).get('recent', {})
        if not filings:
            logger.warning(f"No filings found for CIK {cik}")
            return []
        filing_data = []
        for i in range(len(filings.get('form', []))):
            form_type = filings['form'][i]
            filing_date = filings['filingDate'][i]
            year = int(filing_date[:4])
            quarter = (int(filing_date[5:7]) - 1) // 3 + 1
            if form_type in filing_types:
                # 10-K: filter by year
                if form_type == '10-K' and years and year not in years:
                    continue
                # 8-K: filter by year and quarter
                if form_type == '8-K':
                    if years and year not in years:
                        continue
                    if quarters and quarter not in quarters:
                        continue
                # Apply date filters if provided
                if start_date and filing_date < start_date:
                    continue
                if end_date and filing_date > end_date:
                    continue
                filing_info = {
                    'cik': cik,
                    'form_type': form_type,
                    'filing_date': filing_date,
                    'accession_number': filings['accessionNumber'][i],
                    'primary_document': filings['primaryDocument'][i],
                    'file_number': filings.get('fileNumber', [None])[i] if 'fileNumber' in filings else None,
                    'description': filings.get('description', [''])[i] if 'description' in filings else '',
                    'year': year,
                    'quarter': quarter
                }
                filing_data.append(filing_info)
        return filing_data
    
    def convert_html_to_pdf(self, html_filepath: str) -> Optional[str]:
        """
        Convert an HTML file to PDF using WeasyPrint.
        
        Args:
            html_filepath: Path to the HTML file
            
        Returns:
            Path to the generated PDF file or None if failed
        """
        try:
            html_path = Path(html_filepath)
            pdf_path = html_path.with_suffix('.pdf')
            
            # Convert HTML to PDF
            HTML(filename=str(html_path)).write_pdf(str(pdf_path))
            
            logger.info(f"Converted to PDF: {pdf_path.name}")
            return str(pdf_path)
            
        except Exception as e:
            logger.error(f"Failed to convert {html_filepath} to PDF: {e}")
            return None

    def print_webpage_to_pdf(self, url: str, pdf_filepath: str, interactive: bool = False) -> Optional[str]:
        """
        Print a webpage to PDF using Selenium with Chrome headless browser.
        
        Args:
            url: URL of the webpage to print
            pdf_filepath: Path where to save the PDF
            
        Returns:
            Path to the generated PDF file or None if failed
        """
        try:
            # Set up Chrome options to appear more human-like
            chrome_options = Options()
            if not interactive:
                chrome_options.add_argument("--headless")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--window-size=1920,1080")
            chrome_options.add_argument("--disable-blink-features=AutomationControlled")
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option('useAutomationExtension', False)
            
            # Set a more realistic user agent
            chrome_options.add_argument("--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
            
            # Set up print preferences
            print_prefs = {
                "print.default_destination_selection_rules": {
                    "kind": "local",
                    "namePattern": "Save as PDF"
                },
                "print.save_as_pdf": {
                    "print.background": True,
                    "print.margins.top": 0.4,
                    "print.margins.bottom": 0.4,
                    "print.margins.left": 0.4,
                    "print.margins.right": 0.4,
                    "print.scale": 1.0,
                    "print.paper_width": 8.5,
                    "print.paper_height": 11.0,
                    "print.orientation": "portrait"
                }
            }
            chrome_options.add_experimental_option("prefs", print_prefs)
            
            # Initialize the driver
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=chrome_options)
            
            try:
                # Execute script to remove webdriver property
                driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
                
                # Navigate to the page
                driver.get(url)
                
                # Wait for page to load with random delay to appear more human
                import random
                time.sleep(random.uniform(2, 4))
                driver.implicitly_wait(10)
                
                # Check if we got blocked
                page_source = driver.page_source
                if "Your Request Originates from an Undeclared Automated Tool" in page_source:
                    logger.warning(f"SEC blocked automated access for {url}")
                    if interactive:
                        logger.info("Browser is open for manual verification. Please complete any CAPTCHA and press Enter when ready...")
                        input("Press Enter after completing verification...")
                        # Re-check the page after manual intervention
                        page_source = driver.page_source
                        if "Your Request Originates from an Undeclared Automated Tool" in page_source:
                            logger.error("Still blocked after manual verification")
                            return None
                    else:
                        return None
                
                # Print to PDF
                result = driver.execute_cdp_cmd("Page.printToPDF", {
                    "printBackground": True,
                    "preferCSSPageSize": True,
                    "paperWidth": 8.5,
                    "paperHeight": 11.0,
                    "marginTop": 0.4,
                    "marginBottom": 0.4,
                    "marginLeft": 0.4,
                    "marginRight": 0.4,
                    "scale": 1.0
                })
                
                # Save the PDF
                import base64
                pdf_data = base64.b64decode(result['data'])
                with open(pdf_filepath, 'wb') as f:
                    f.write(pdf_data)
                
                logger.info(f"Printed webpage to PDF: {pdf_filepath}")
                return pdf_filepath
                
            finally:
                driver.quit()
                
        except Exception as e:
            logger.error(f"Failed to print webpage {url} to PDF: {e}")
            return None

    def download_filing(self, accession_number: str, primary_document: str, convert_to_pdf: bool = True, interactive: bool = False) -> Optional[str]:
        """
        Download a specific filing document and optionally convert to PDF.
        
        Args:
            accession_number: SEC accession number
            primary_document: Primary document filename
            convert_to_pdf: Whether to convert the HTML to PDF
            
        Returns:
            Path to downloaded file (HTML or PDF) or None if failed
        """
        # Remove dashes from accession number for URL
        clean_accession = accession_number.replace('-', '')
        
        # Construct document URL using the correct SEC format
        # Use www.sec.gov instead of data.sec.gov for document downloads
        doc_url = f"https://www.sec.gov/Archives/edgar/data/{clean_accession[:10]}/{clean_accession}/{primary_document}"
        
        # Create filename for PDF
        pdf_filename = f"{accession_number}_{primary_document.replace('.htm', '.pdf')}"
        pdf_filepath = self.output_dir / pdf_filename
        
        # Try to print the webpage directly to PDF
        if convert_to_pdf:
            logger.info(f"Attempting to print webpage to PDF: {doc_url}")
            pdf_result = self.print_webpage_to_pdf(doc_url, str(pdf_filepath), interactive)
            if pdf_result:
                return pdf_result
        
        # If PDF printing fails, try traditional download approach
        if not pdf_result:
            logger.info(f"PDF printing failed, trying traditional download: {doc_url}")
        else:
            return pdf_result
        
        # Use more browser-like headers for document downloads
        download_headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0',
        }
        
        # Retry logic for failed downloads
        max_retries = 3
        for attempt in range(max_retries):
            try:
                self._rate_limit()
                
                response = self.session.get(doc_url, headers=download_headers, timeout=60)
                response.raise_for_status()
                
                # Create filename
                filename = f"{accession_number}_{primary_document}"
                filepath = self.output_dir / filename
                
                # Save file
                with open(filepath, 'wb') as f:
                    f.write(response.content)
                
                logger.info(f"Downloaded: {filename}")
                
                # Convert to PDF if requested
                if convert_to_pdf:
                    pdf_filepath = self.convert_html_to_pdf(str(filepath))
                    if pdf_filepath:
                        return pdf_filepath
                    else:
                        # If PDF conversion fails, return the HTML file
                        logger.warning(f"PDF conversion failed, returning HTML file: {filepath}")
                        return str(filepath)
                else:
                    return str(filepath)
                
            except requests.exceptions.RequestException as e:
                logger.warning(f"Attempt {attempt + 1}/{max_retries} failed for {primary_document}: {e}")
                if attempt < max_retries - 1:
                    # Wait longer between retries
                    time.sleep(2 ** attempt)  # Exponential backoff: 1s, 2s, 4s
                else:
                    logger.error(f"Failed to download {primary_document} after {max_retries} attempts")
                    return None
    
    def process_tickers(self, tickers: List[str], filing_types: List[str],
                       download_filings: bool = True, 
                       start_date: Optional[str] = None,
                       end_date: Optional[str] = None,
                       years: Optional[List[int]] = None,
                       quarters: Optional[List[int]] = None,
                       convert_to_pdf: bool = True,
                       interactive: bool = False) -> Dict:
        """
        Process a list of tickers and fetch their filings.
        Args:
            tickers: List of stock ticker symbols
            filing_types: List of filing types to fetch
            download_filings: Whether to download filing documents
            start_date: Start date filter (YYYY-MM-DD)
            end_date: End date filter (YYYY-MM-DD)
            years: List of years to filter (for 10-K, 8-K)
            quarters: List of quarters to filter (for 8-K)
        Returns:
            Dictionary containing results for each ticker
        """
        results = {
            'summary': {
                'total_tickers': len(tickers),
                'processed_tickers': 0,
                'total_filings': 0,
                'downloaded_filings': 0,
                'errors': []
            },
            'tickers': {}
        }
        for ticker in tickers:
            logger.info(f"Processing ticker: {ticker}")
            try:
                company_info = self.get_company_info(ticker)
                if not company_info:
                    error_msg = f"Could not find company info for ticker {ticker}"
                    logger.error(error_msg)
                    results['summary']['errors'].append(error_msg)
                    continue
                filings = self.get_filings(
                    company_info['cik'], 
                    filing_types, 
                    start_date, 
                    end_date,
                    years,
                    quarters
                )
                # Error if user requested a year/quarter not found
                requested_10k_years = set(years or []) if '10-K' in filing_types else set()
                found_10k_years = {f['year'] for f in filings if f['form_type'] == '10-K'}
                missing_10k_years = requested_10k_years - found_10k_years
                for y in missing_10k_years:
                    error_msg = f"10-K for year {y} not available for {ticker}"
                    logger.error(error_msg)
                    results['summary']['errors'].append(error_msg)
                requested_8k = set((y, q) for y in (years or []) for q in (quarters or [])) if '8-K' in filing_types and years and quarters else set()
                found_8k = set((f['year'], f['quarter']) for f in filings if f['form_type'] == '8-K')
                missing_8k = requested_8k - found_8k
                for y, q in missing_8k:
                    error_msg = f"8-K for {ticker} in {y} Q{q} not available"
                    logger.error(error_msg)
                    results['summary']['errors'].append(error_msg)
                ticker_results = {
                    'company_info': company_info,
                    'filings': filings,
                    'downloaded_files': []
                }
                if download_filings:
                    for filing in filings:
                        filepath = self.download_filing(
                            filing['accession_number'],
                            filing['primary_document'],
                            convert_to_pdf=convert_to_pdf,
                            interactive=interactive
                        )
                        if filepath:
                            ticker_results['downloaded_files'].append(filepath)
                            results['summary']['downloaded_filings'] += 1
                results['tickers'][ticker] = ticker_results
                results['summary']['processed_tickers'] += 1
                results['summary']['total_filings'] += len(filings)
                logger.info(f"Completed {ticker}: {len(filings)} filings found")
            except Exception as e:
                error_msg = f"Error processing {ticker}: {str(e)}"
                logger.error(error_msg)
                results['summary']['errors'].append(error_msg)
        return results
    
    def save_results(self, results: Dict, filename: str = None) -> str:
        """
        Save results to JSON file.
        
        Args:
            results: Results dictionary
            filename: Output filename (optional)
            
        Returns:
            Path to saved file
        """
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"sec_results_{timestamp}.json"
        
        filepath = self.output_dir / filename
        
        with open(filepath, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        
        logger.info(f"Results saved to: {filepath}")
        return str(filepath)
    
    def generate_summary_report(self, results: Dict) -> str:
        """
        Generate a summary report of the pipeline results.
        
        Args:
            results: Results dictionary
            
        Returns:
            Summary report as string
        """
        summary = results['summary']
        
        # Calculate download success rate
        total_attempted = sum(len(data['filings']) for data in results['tickers'].values())
        download_success_rate = (summary['downloaded_filings'] / total_attempted * 100) if total_attempted > 0 else 0
        
        report = f"""
        SEC EDGAR Filing Pipeline Summary Report
        ========================================

        Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

        Processing Summary:
        - Total tickers processed: {summary['processed_tickers']}/{summary['total_tickers']}
        - Total filings found: {summary['total_filings']}
        - Files downloaded: {summary['downloaded_filings']}
        - Download success rate: {download_success_rate:.1f}%
        - Errors encountered: {len(summary['errors'])}

        Ticker Details:
        """

        for ticker, data in results['tickers'].items():
            company_name = data['company_info']['company_name']
            filing_count = len(data['filings'])
            download_count = len(data['downloaded_files'])
            success_rate = (download_count / filing_count * 100) if filing_count > 0 else 0
            
            report += f"\n{ticker} ({company_name}):"
            report += f"\n  - Filings found: {filing_count}"
            report += f"\n  - Files downloaded: {download_count} ({success_rate:.1f}%)"
            
            if data['filings']:
                report += "\n  - Recent filings:"
                for filing in data['filings'][:3]:  # Show first 3
                    report += f"\n    * {filing['form_type']} - {filing['filing_date']} (Year: {filing.get('year', 'N/A')}, Q{filing.get('quarter', 'N/A')})"
        
        if summary['errors']:
            report += "\n\nErrors:"
            for error in summary['errors']:
                report += f"\n- {error}"
        
        return report


def main():
    """Main function to run the SEC filing pipeline."""
    parser = argparse.ArgumentParser(description='SEC EDGAR Filing Pipeline')
    parser.add_argument('--tickers', nargs='+', required=True,
                       help='List of stock ticker symbols')
    parser.add_argument('--filing-types', nargs='+', 
                       default=['10-K', '8-K'],
                       choices=['10-K', '8-K', '10-Q', 'DEF 14A'],
                       help='Types of filings to fetch')
    parser.add_argument('--start-date', type=str,
                       help='Start date filter (YYYY-MM-DD)')
    parser.add_argument('--end-date', type=str,
                       help='End date filter (YYYY-MM-DD)')
    parser.add_argument('--download', action='store_true', default=True,
                       help='Download filing documents (default: True)')
    parser.add_argument('--metadata-only', action='store_true',
                       help='Only fetch metadata, skip downloads')
    parser.add_argument('--no-pdf', action='store_true',
                       help='Skip PDF conversion, keep HTML files only')
    parser.add_argument('--interactive', action='store_true',
                       help='Use non-headless browser for manual CAPTCHA/verification')
    parser.add_argument('--user-agent', type=str,
                       default='Your Company Name yourname@example.com',
                       help='User agent for SEC API requests')
    parser.add_argument('--output', type=str,
                       help='Output filename for results')
    parser.add_argument('--years', nargs='+', type=int,
                       help='Year(s) to fetch (for 10-K and 8-K)')
    parser.add_argument('--quarters', nargs='+', type=int, choices=[1,2,3,4],
                       help='Quarter(s) to fetch (for 8-K, e.g., 1 2 3 4)')
    args = parser.parse_args()
    pipeline = SECEdgarPipeline(user_agent=args.user_agent)
    logger.info(f"Starting pipeline for {len(args.tickers)} tickers")
    
    # Handle metadata-only flag
    download_filings = args.download and not args.metadata_only
    
    # Determine if we should convert to PDF
    convert_to_pdf = not args.no_pdf and download_filings
    
    results = pipeline.process_tickers(
        tickers=args.tickers,
        filing_types=args.filing_types,
        download_filings=download_filings,
        start_date=args.start_date,
        end_date=args.end_date,
        years=args.years,
        quarters=args.quarters,
        convert_to_pdf=convert_to_pdf,
        interactive=args.interactive
    )
    results_file = pipeline.save_results(results, args.output)
    summary = pipeline.generate_summary_report(results)
    print(summary)
    summary_file = pipeline.output_dir / f"summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(summary_file, 'w') as f:
        f.write(summary)
    logger.info(f"Pipeline completed. Results saved to: {results_file}")
    logger.info(f"Summary saved to: {summary_file}")


if __name__ == "__main__":
    main()