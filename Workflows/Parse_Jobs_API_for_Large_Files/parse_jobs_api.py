"""
Parse Jobs API for processing large documents with LandingAI ADE
"""

import os
import json
import time
import requests
from pathlib import Path
from typing import Dict, Any, Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
BASE_URL = 'https://api.va.landing.ai/'


def submit_document(file_path: str, api_key: str) -> Optional[str]:
    """
    Upload a PDF to LandingAI's ADE endpoint and get back the job_id.
    Returns the job_id string when the POST succeeds, else None.
    """
    # Resolve & sanity-check the path
    p = Path(file_path).expanduser().resolve()
    if not p.exists():
        print(f"❌ File not found: {p}")
        return None

    print(f"📄 File: {p.name}  |  📏 {p.stat().st_size / 1_048_576:.1f} MB")

    # Prepare request
    url = f'{BASE_URL}/v1/ade/parse/jobs'
    headers = {"Authorization": f"Bearer {api_key}"}

    with p.open("rb") as fh:
        files = {"document": fh}
        resp = requests.post(url, headers=headers, files=files, timeout=30)

    # Handle response
    if resp.status_code in (200, 202):
        data = resp.json()
        job_id = data.get("job_id")
        if job_id:
            print(f"✅ Job accepted — job_id: {job_id}")
            return job_id
        else:
            print("❌ Response missing job_id:", data)
            return None

    print(f"❌ Upload failed ({resp.status_code}): {resp.text}")
    return None


def check_job_status(job_id: str, api_key: str) -> Dict[str, Any]:
    """
    Check the status of an async job.

    Args:
        job_id: The job ID from submission
        api_key: Your API key

    Returns:
        Status dictionary with progress and results
    """
    url = f'{BASE_URL}/v1/ade/parse/jobs/{job_id}'
    headers = {'Authorization': f'Bearer {api_key}'}

    try:
        response = requests.get(url, headers=headers)

        if response.status_code == 200:
            data = response.json()
            status = data.get('status')
            progress = data.get('progress', 0) * 100

            print(f"Status: {status} | Progress: {progress:.0f}%")
            return data
        else:
            print(f"❌ Error checking status: {response.status_code}")
            return None

    except Exception as e:
        print(f"❌ Error: {e}")
        return None


def wait_for_completion(job_id: str, api_key: str, timeout: int = 3600):
    """
    Wait for job to complete with polling.
    """
    start_time = time.time()

    while time.time() - start_time < timeout:
        status_data = check_job_status(job_id, api_key)

        if status_data:
            status = status_data.get('status')

            if status == 'completed':
                print("✅ Job completed!")
                return status_data
            elif status == 'failed':
                print(f"❌ Job failed: {status_data.get('failure_reason')}")
                return None

        time.sleep(30)  # Poll every 30 seconds

    print("⏱️ Timeout waiting for completion")
    return None


def get_results(job_id: str, api_key: str, save_to_file: bool = True) -> Optional[str]:
    """
    Retrieve results from a completed job, handling both direct data responses
    (for small files) and fetching from an output URL (for large files).

    Args:
        job_id: The job ID.
        api_key: Your API key.
        save_to_file: Whether to save the markdown content to a file.

    Returns:
        Markdown content if successful, otherwise None.
    """
    # Check the job status
    status_data = check_job_status(job_id, api_key)
    if not status_data or status_data.get('status') != 'completed':
        status = status_data.get('status', 'unknown') if status_data else 'unknown'
        print(f"⚠️ Job not completed yet. Current status: '{status}'")
        return None

    markdown = ''

    # Check if results are returned directly (for smaller files)
    if status_data.get('data') is not None:
        print("✅ Job complete. Results found directly in API response.")
        data = status_data.get('data', {})
        markdown = data.get('markdown', '')

    # If not, fetch results from the output URL (for larger files)
    else:
        output_url = status_data.get('output_url')
        if not output_url:
            print("❌ Job is complete, but no output URL or direct data was found.")
            return None

        print("✅ Job complete. Fetching results from URL for large file...")
        try:
            response = requests.get(output_url)
            response.raise_for_status()
            results_data = response.json()
            markdown = results_data.get('markdown', '')
        except requests.exceptions.RequestException as e:
            print(f"❌ Failed to fetch results from URL: {e}")
            return None
        except json.JSONDecodeError:
            print("❌ Failed to parse the fetched results as JSON.")
            return None

    # Process the markdown
    if markdown:
        print(f"📄 Retrieved {len(markdown)} characters of markdown.")

        if save_to_file:
            output_file = f'{job_id}_output.md'
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(markdown)
            print(f"💾 Saved to: {output_file}")

        # Display metadata
        metadata = status_data.get('metadata', {})
        if metadata:
            print(f"\n📊 Processing stats:")
            print(f"  • Pages: {metadata.get('page_count', 'N/A')}")
            print(f"  • Time: {metadata.get('duration_ms', 0) / 1000:.1f}s")
            print(f"  • Credits: {metadata.get('credit_usage', 'N/A')}")

        return markdown
    else:
        print("❌ No markdown content found in the results.")
        return None


def process_large_document(file_path: str, api_key: str):
    """
    Complete workflow for processing a large document.
    """
    print("🚀 ASYNC DOCUMENT PROCESSING WORKFLOW")
    print("="*50)

    # Step 1: Submit
    print("\n1️⃣ Submitting document...")
    job_id = submit_document(file_path, api_key)

    if not job_id:
        print("Failed to submit document")
        return

    # Step 2: Wait for completion
    print("\n2️⃣ Waiting for processing...")
    result = wait_for_completion(job_id, api_key)

    if not result:
        print("Processing failed or timed out")
        return

    # Step 3: Get results
    print("\n3️⃣ Retrieving results...")
    markdown = get_results(job_id, api_key)

    if not markdown:
        print("Failed to retrieve results")
        return

    return {
        'job_id': job_id,
        'markdown': markdown,
    }


def preview_markdown(file_path: str, num_chars: int = 1000):
    """
    Prints the first few characters of a text file.

    Args:
        file_path: The path to the file you want to preview.
        num_chars: The number of characters to display.
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            preview_content = f.read(num_chars)

            print(f"📄 Previewing first {num_chars} characters of '{file_path}':")
            print("--------------------- START OF FILE ---------------------")
            print(preview_content)
            print("---------------------- END OF PREVIEW ----------------------")

            if len(preview_content) == num_chars:
                print("(File continues...)")

    except FileNotFoundError:
        print(f"❌ Error: The file '{file_path}' was not found.")
    except Exception as e:
        print(f"An error occurred: {e}")