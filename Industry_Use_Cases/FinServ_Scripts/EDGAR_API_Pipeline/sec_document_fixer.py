"""
SEC Document URL Fixer - Standalone Tool
Tests and implements the correct URL format for downloading SEC EDGAR documents.
"""

import requests
import time
import re
from pathlib import Path

def test_sec_url_formats():
    """Test different SEC document URL formats to find the working one."""
    
    # Test parameters
    cik = "0000320193"  # Apple
    accession_number = "0000320193-23-000106"
    primary_document = "aapl-20230930.htm"
    
    # Clean accession number (remove dashes)
    clean_accession = accession_number.replace('-', '')
    
    # Different URL formats to test based on SEC documentation
    url_formats = [
        # Format 1: Current format (not working)
        f"https://data.sec.gov/Archives/edgar/data/{clean_accession[:10]}/{clean_accession}/{primary_document}",
        
        # Format 2: Using www.sec.gov instead of data.sec.gov
        f"https://www.sec.gov/Archives/edgar/data/{clean_accession[:10]}/{clean_accession}/{primary_document}",
        
        # Format 3: Using the old SEC format
        f"https://www.sec.gov/Archives/edgar/data/{clean_accession[:10]}/{clean_accession}/{primary_document}",
        
        # Format 4: Using .txt extension
        f"https://www.sec.gov/Archives/edgar/data/{clean_accession[:10]}/{clean_accession}/{primary_document.replace('.htm', '.txt')}",
        
        # Format 5: Using different document name format
        f"https://www.sec.gov/Archives/edgar/data/{clean_accession[:10]}/{clean_accession}/d{clean_accession[10:]}{primary_document}",
        
        # Format 6: Using the SEC's new API format
        f"https://www.sec.gov/Archives/edgar/data/{clean_accession[:10]}/{clean_accession}/{primary_document}",
        
        # Format 7: Using the SEC's REST API
        f"https://data.sec.gov/Archives/edgar/data/{clean_accession[:10]}/{clean_accession}/{primary_document}",
        
        # Format 8: Using the SEC's new document format
        f"https://www.sec.gov/Archives/edgar/data/{clean_accession[:10]}/{clean_accession}/{primary_document.replace('.htm', '')}.htm",
    ]
    
    headers = {
        'User-Agent': 'Financial Analysis Tool v1.0 (yourname@example.com)',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    }
    
    print("Testing SEC Document URL Formats")
    print("=" * 60)
    
    working_urls = []
    
    for i, url in enumerate(url_formats, 1):
        print(f"\nTesting Format {i}:")
        print(f"URL: {url}")
        
        try:
            # Rate limiting - be very conservative
            time.sleep(1.0)  # Wait 1 second between requests
            
            response = requests.get(url, headers=headers, timeout=15)
            print(f"Status: {response.status_code}")
            
            if response.status_code == 200:
                print("✓ SUCCESS - Document found!")
                print(f"Content length: {len(response.content)} bytes")
                print(f"Content type: {response.headers.get('content-type', 'unknown')}")
                
                # Check if it's actually HTML content
                if 'html' in response.headers.get('content-type', '').lower() or 'text' in response.headers.get('content-type', '').lower():
                    print("✓ Valid document content detected")
                    working_urls.append((i, url))
                    
                    # Save a sample
                    sample_file = f"test_document_{i}.html"
                    with open(sample_file, "w", encoding='utf-8') as f:
                        f.write(response.text[:2000])  # First 2000 chars
                    print(f"Sample saved to: {sample_file}")
                else:
                    print("⚠️ Response received but may not be valid document content")
                    
            elif response.status_code == 404:
                print("✗ 404 - Not found")
            elif response.status_code == 403:
                print("✗ 403 - Forbidden (rate limiting?)")
            elif response.status_code == 429:
                print("✗ 429 - Too Many Requests (rate limiting)")
            else:
                print(f"✗ {response.status_code} - Other error")
                
        except requests.exceptions.Timeout:
            print("✗ Timeout")
        except requests.exceptions.ConnectionError:
            print("✗ Connection Error")
        except Exception as e:
            print(f"✗ Error: {e}")
    
    print("\n" + "=" * 60)
    print("URL format testing completed!")
    
    if working_urls:
        print(f"\n✅ Found {len(working_urls)} working URL format(s):")
        for i, url in working_urls:
            print(f"  Format {i}: {url}")
        return working_urls[0]  # Return the first working format
    else:
        print("\n❌ No working URL formats found")
        return None

def test_alternative_approaches():
    """Test alternative approaches to get SEC documents."""
    print("\n=== Testing Alternative Approaches ===")
    
    # Test 1: Using SEC's RSS feeds
    print("\n1. Testing SEC RSS feeds...")
    rss_url = "https://www.sec.gov/Archives/edgar/data/0000320193/000032019323000106/feed.xml"
    try:
        response = requests.get(rss_url, timeout=10)
        print(f"RSS Status: {response.status_code}")
        if response.status_code == 200:
            print("✓ RSS feed accessible")
    except Exception as e:
        print(f"✗ RSS Error: {e}")
    
    # Test 2: Using SEC's index files
    print("\n2. Testing SEC index files...")
    index_url = "https://www.sec.gov/Archives/edgar/data/0000320193/000032019323000106/index.json"
    try:
        response = requests.get(index_url, timeout=10)
        print(f"Index Status: {response.status_code}")
        if response.status_code == 200:
            print("✓ Index file accessible")
            print(f"Content: {response.text[:200]}...")
    except Exception as e:
        print(f"✗ Index Error: {e}")
    
    # Test 3: Using SEC's document list
    print("\n3. Testing SEC document list...")
    doc_list_url = "https://www.sec.gov/Archives/edgar/data/0000320193/000032019323000106/"
    try:
        response = requests.get(doc_list_url, timeout=10)
        print(f"Doc List Status: {response.status_code}")
        if response.status_code == 200:
            print("✓ Document list accessible")
    except Exception as e:
        print(f"✗ Doc List Error: {e}")

def main():
    """Main function to test SEC document URLs."""
    print("SEC Document URL Fixer")
    print("=" * 60)
    
    # Test URL formats
    working_format = test_sec_url_formats()
    
    # Test alternative approaches
    test_alternative_approaches()
    
    print("\n" + "=" * 60)
    print("Testing completed!")
    
    if working_format:
        format_num, url = working_format
        print(f"\n✅ Working URL format found: Format {format_num}")
        print(f"URL pattern: {url}")
        print("\nRecommendation: Update the script to use this URL format.")
    else:
        print("\n❌ No working URL format found.")
        print("Recommendation: Research current SEC API documentation or use alternative data sources.")

if __name__ == "__main__":
    main() 