#!/usr/bin/env python3
"""
Example usage of the SEC EDGAR Filing Pipeline

This script demonstrates how to use the pipeline programmatically
for different use cases.
"""

from sec_pipeline import SECEdgarPipeline
from datetime import datetime, timedelta

def example_basic_usage():
    """Example 1: Basic usage for fetching 10-K and 8-K filings."""
    print("=== Example 1: Basic Usage ===")
    
    # Initialize pipeline
    pipeline = SECEdgarPipeline(user_agent="Example Company example@company.com")
    
    # Define tickers and filing types
    tickers = ['AAPL', 'MSFT', 'GOOGL']
    filing_types = ['10-K', '8-K']
    
    # Process tickers
    results = pipeline.process_tickers(
        tickers=tickers,
        filing_types=filing_types,
        download_filings=True
    )
    
    # Save results
    results_file = pipeline.save_results(results)
    print(f"Results saved to: {results_file}")
    
    # Generate and print summary
    summary = pipeline.generate_summary_report(results)
    print(summary)

def example_with_date_filtering():
    """Example 2: Fetch filings with date filtering."""
    print("\n=== Example 2: Date Filtering ===")
    
    pipeline = SECEdgarPipeline(user_agent="Example Company example@company.com")
    
    # Define date range (last 2 years)
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=730)).strftime("%Y-%m-%d")
    
    tickers = ['TSLA', 'NVDA']
    filing_types = ['8-K']  # Only 8-K filings
    
    results = pipeline.process_tickers(
        tickers=tickers,
        filing_types=filing_types,
        download_filings=True,
        start_date=start_date,
        end_date=end_date
    )
    
    # Save results with custom filename
    results_file = pipeline.save_results(results, "tesla_nvidia_8k_results.json")
    print(f"Results saved to: {results_file}")
    
    # Print summary
    summary = pipeline.generate_summary_report(results)
    print(summary)

def example_metadata_only():
    """Example 3: Fetch metadata only without downloading files."""
    print("\n=== Example 3: Metadata Only ===")
    
    pipeline = SECEdgarPipeline(user_agent="Example Company example@company.com")
    
    tickers = ['META', 'AMZN']
    filing_types = ['10-K', '10-Q']
    
    results = pipeline.process_tickers(
        tickers=tickers,
        filing_types=filing_types,
        download_filings=False  # Don't download files
    )
    
    # Print filing metadata
    for ticker, data in results['tickers'].items():
        print(f"\n{ticker} filings:")
        for filing in data['filings'][:5]:  # Show first 5 filings
            print(f"  - {filing['form_type']} on {filing['filing_date']}")
            print(f"    Accession: {filing['accession_number']}")
            if filing.get('description'):
                print(f"    Description: {filing['description']}")

def example_single_company_analysis():
    """Example 4: Detailed analysis for a single company."""
    print("\n=== Example 4: Single Company Analysis ===")
    
    pipeline = SECEdgarPipeline(user_agent="Example Company example@company.com")
    
    ticker = 'AAPL'
    filing_types = ['10-K', '8-K', '10-Q']
    
    results = pipeline.process_tickers(
        tickers=[ticker],
        filing_types=filing_types,
        download_filings=True
    )
    
    if ticker in results['tickers']:
        data = results['tickers'][ticker]
        company_name = data['company_info']['company_name']
        
        print(f"\nAnalysis for {ticker} ({company_name}):")
        print(f"Total filings found: {len(data['filings'])}")
        print(f"Files downloaded: {len(data['downloaded_files'])}")
        
        # Group filings by type
        filings_by_type = {}
        for filing in data['filings']:
            form_type = filing['form_type']
            if form_type not in filings_by_type:
                filings_by_type[form_type] = []
            filings_by_type[form_type].append(filing)
        
        print("\nFilings by type:")
        for form_type, filings in filings_by_type.items():
            print(f"  {form_type}: {len(filings)} filings")
            for filing in filings[:3]:  # Show first 3 of each type
                print(f"    - {filing['filing_date']}: {filing['accession_number']}")

def main():
    """Run all examples."""
    print("SEC EDGAR Filing Pipeline Examples")
    print("=" * 40)
    
    try:
        example_basic_usage()
        example_with_date_filtering()
        example_metadata_only()
        example_single_company_analysis()
        
        print("\n" + "=" * 40)
        print("All examples completed successfully!")
        print("Check the 'sec_filings' directory for downloaded files.")
        print("Check 'sec_pipeline.log' for detailed processing logs.")
        
    except Exception as e:
        print(f"Error running examples: {e}")
        print("Make sure you have installed the required dependencies:")
        print("pip install -r requirements.txt")

if __name__ == "__main__":
    main() 