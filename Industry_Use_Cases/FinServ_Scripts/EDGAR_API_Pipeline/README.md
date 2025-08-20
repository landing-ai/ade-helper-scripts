# SEC EDGAR Filing Pipeline

A comprehensive Python pipeline for fetching 10-K and 8-K filings from the SEC's EDGAR database for a list of stock market tickers.

## Features

- **Multi-ticker support**: Process multiple stock tickers in a single run
- **Multiple filing types**: Support for 10-K, 8-K, 10-Q, and DEF 14A filings
- **Rate limiting**: Built-in rate limiting to comply with SEC API restrictions
- **Date filtering**: Filter filings by date range
- **Automatic downloads**: Download filing documents to local storage
- **PDF conversion**: Convert HTML filings to PDF format
- **Comprehensive logging**: Detailed logs for debugging and monitoring
- **Error handling**: Robust error handling with retry logic
- **Summary reports**: Generate detailed summary reports of processing results

## Installation

1. Clone or download this repository
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

**Note**: The pipeline uses Selenium with Chrome for PDF conversion. Make sure you have Chrome browser installed on your system.

## Quick Start

For programmatic usage examples, see `example_usage.py`:
```bash
python example_usage.py
```

## Usage

### Basic Usage

Fetch 10-K and 8-K filings for multiple tickers:

```bash
python sec_pipeline.py --tickers AAPL MSFT GOOGL --filing-types 10-K 8-K
```

### Advanced Usage

Fetch specific filing types with date filtering and PDF conversion:

```bash
python sec_pipeline.py \
    --tickers AAPL MSFT GOOGL TSLA \
    --filing-types 10-K 8-K \
    --start-date 2023-01-01 \
    --end-date 2024-01-01 \
    --user-agent "Your Company Name yourname@example.com" \
    --convert-to-pdf \
    --interactive
```

### Command Line Arguments

- `--tickers`: List of stock ticker symbols (required)
- `--filing-types`: Types of filings to fetch (default: 10-K, 8-K)
  - Options: 10-K, 8-K, 10-Q, DEF 14A
- `--start-date`: Start date filter in YYYY-MM-DD format
- `--end-date`: End date filter in YYYY-MM-DD format
- `--download`: Download filing documents (default: True)
- `--convert-to-pdf`: Convert HTML filings to PDF format
- `--interactive`: Use interactive mode for PDF conversion (shows browser)
- `--user-agent`: User agent string for SEC API requests
- `--output`: Output filename for results JSON

### Examples

1. **Fetch recent 10-K filings for major tech companies:**
   ```bash
   python sec_pipeline.py --tickers AAPL MSFT GOOGL AMZN META
   ```

2. **Fetch 8-K filings from the last year with PDF conversion:**
   ```bash
   python sec_pipeline.py \
       --tickers TSLA NVDA AMD \
       --filing-types 8-K \
       --start-date 2023-01-01 \
       --convert-to-pdf
   ```

3. **Fetch all filing types for a single company with interactive PDF conversion:**
   ```bash
   python sec_pipeline.py \
       --tickers AAPL \
       --filing-types 10-K 8-K 10-Q DEF 14A \
       --convert-to-pdf \
       --interactive
   ```

## Output Structure

The pipeline creates the following directory structure:

```
EDGAR_API_Pipeline/
├── sec_pipeline.py
├── requirements.txt
├── README.md
├── example_usage.py
├── sec_document_fixer.py
├── sec_filings/                      # Downloaded filing documents
│   ├── 0000320193_10-K_20231027.txt
│   ├── 0000320193_10-K_20231027.pdf  # PDF version (if converted)
│   ├── 0000320193_8-K_20231102.txt
│   ├── 0000320193_8-K_20231102.pdf   # PDF version (if converted)
│   └── ...
├── sec_results_20241201_143022.json  # Results data
├── summary_20241201_143022.txt       # Summary report
└── sec_pipeline.log                  # Processing logs
```

### Output Files

1. **JSON Results File**: Contains detailed metadata for all processed tickers and filings
2. **Summary Report**: Human-readable summary of processing results
3. **Log File**: Detailed processing logs for debugging
4. **Filing Documents**: Downloaded SEC filing documents (HTML and PDF formats)
5. **PDF Files**: Converted PDF versions of HTML filings (when enabled)

## API Rate Limiting

The pipeline implements rate limiting to comply with SEC API restrictions:
- Maximum 0.5 requests per second (1 request every 2 seconds)
- Automatic delays between requests
- Respectful API usage to avoid being blocked

## Error Handling

The pipeline includes robust error handling:
- Network timeout handling
- Invalid ticker symbol handling
- Missing filing data handling
- Automatic retry logic for failed requests
- Detailed error logging

## PDF Conversion

The pipeline can convert HTML filings to PDF format using two methods:

1. **WeasyPrint**: Fast, headless PDF conversion
2. **Selenium with Chrome**: Interactive PDF conversion with browser rendering

To enable PDF conversion, use the `--convert-to-pdf` flag. For interactive mode (shows browser), add `--interactive`.

## Customization

### Modifying Rate Limits

Edit the `requests_per_second` parameter in the `SECEdgarPipeline` class:

```python
self.requests_per_second = 0.5  # Adjust as needed (1 request every 2 seconds)
```

### Adding New Filing Types

Add new filing types to the `filing_types` dictionary:

```python
self.filing_types = {
    '10-K': '10-K',
    '8-K': '8-K',
    '10-Q': '10-Q',
    'DEF 14A': 'DEF 14A',
    'NEW_TYPE': 'NEW_TYPE'  # Add new types here
}
```

### Custom User Agent

Always use a proper user agent when making requests to the SEC API:

```bash
python sec_pipeline.py \
    --tickers AAPL \
    --user-agent "Your Company Name yourname@example.com"
```

## Troubleshooting

### Common Issues

1. **"Could not find company info for ticker"**
   - Verify the ticker symbol is correct
   - Some companies may use different ticker symbols in SEC filings
   - Try using the company's CIK number directly

2. **Rate limiting errors**
   - The pipeline automatically handles rate limiting
   - If you encounter issues, reduce the `requests_per_second` value

3. **Download failures**
   - Check your internet connection
   - Verify the SEC API is accessible
   - Check the log file for specific error messages

4. **PDF conversion issues**
   - Ensure Chrome browser is installed
   - For interactive mode, make sure Chrome can launch
   - Check that all dependencies are installed: `pip install selenium webdriver-manager`

### Log Files

Check the `sec_pipeline.log` file for detailed information about:
- Processing progress
- Error messages
- Download status
- API request details
- PDF conversion status

## Dependencies

The pipeline requires the following Python packages:
- `requests>=2.31.0`: HTTP requests
- `pandas>=2.0.0`: Data manipulation
- `pathlib2>=2.3.7`: Path handling
- `weasyprint>=61.0`: PDF conversion
- `selenium`: Browser automation for PDF conversion
- `webdriver-manager`: Chrome driver management

## Legal and Compliance

- Always use a proper user agent when accessing SEC data
- Respect rate limits to avoid being blocked
- Use the data in compliance with SEC terms of service
- Consider data retention policies for downloaded filings

## Contributing

Feel free to submit issues, feature requests, or pull requests to improve the pipeline.

## License

This project is provided as-is for educational and research purposes. 