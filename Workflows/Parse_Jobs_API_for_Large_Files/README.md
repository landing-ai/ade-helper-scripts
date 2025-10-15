# Parse Jobs API for Large Files

A Python implementation for processing large PDF documents asynchronously using LandingAI's ADE (Agentic Document Extraction) Parse Jobs API.

## Overview

This repository demonstrates how to process large PDF documents (up to 1GB / 1,000 pages) that exceed the limits of standard synchronous APIs using LandingAI's ADE Parse Jobs API. The implementation provides an asynchronous workflow for submitting, monitoring, and retrieving parsed document results.

### Key Features

- 📄 **Large Document Support**: Process PDFs up to 1GB in size and 1,000 pages
- ⚡ **Asynchronous Processing**: Non-blocking job submission with status monitoring
- 📊 **Progress Tracking**: Real-time progress updates (0-100%)
- 🔄 **Automatic Polling**: Built-in completion monitoring with configurable timeouts
- 💾 **Smart Result Handling**: Automatic handling of both inline and URL-based results

## API Comparison

| Feature | Standard Parse API | Parse Jobs API |
|---------|-------------------|----------------|
| Max Size | 50MB | 1GB |
| Max Pages | 50 | 1,000 |
| Response Type | Immediate | Job ID |
| Best For | Small documents | Large documents |

## Prerequisites

- Python 3.7+
- LandingAI ADE API key ([Get your key here](https://docs.landing.ai/ade/agentic-api-key))

## Installation

1. Clone this repository:
```bash
git clone <repository-url>
cd Parse_Jobs_API_for_Large_Files
```

2. Install required dependencies:
```bash
pip install -U requests python-dotenv
```

3. Set up your API key:
   - Create a `.env` file in the root directory
   - Add your API key:
```env
VISION_AGENT_API_KEY=your_api_key_here
```

## Usage

### Quick Start

The repository includes a Jupyter notebook (`ADE_Parse_Jobs_API.ipynb`) that provides a complete tutorial and example implementation.

### Basic Workflow

```python
from parse_jobs_api import process_large_document

# Process a large PDF document
results = process_large_document('path/to/your/document.pdf', API_KEY)

# Access the results
job_id = results['job_id']
markdown_content = results['markdown']
```

### Step-by-Step Process

1. **Submit Document**:
```python
job_id = submit_document('document.pdf', API_KEY)
```

2. **Monitor Job Status**:
```python
result = wait_for_completion(job_id, API_KEY)
```

3. **Retrieve Results**:
```python
markdown = get_results(job_id, API_KEY, save_to_file=True)
```

## Project Structure

```
Parse_Jobs_API_for_Large_Files/
│
├── ADE_Parse_Jobs_API.ipynb    # Main tutorial notebook
├── parse_jobs_api.py            # Python module with all functions
├── input_folder/                # Sample input PDF files
│   ├── one_huge_file.pdf       # 57.6 MB sample file
│   └── one_large_file.pdf      # 39.0 MB sample file
├── output_folder/               # Processed markdown outputs
│   └── *.md                     # Generated markdown files
└── README.md                    # This file
```

## API Endpoints

- **Submit Document**: `POST /v1/ade/parse/jobs`
- **Check Status**: `GET /v1/ade/parse/jobs/{job_id}`
- **List All Jobs**: `GET /v1/ade/parse/jobs`

## Key Functions

### `submit_document(file_path, api_key)`
Uploads a PDF document and returns a job ID for tracking.

### `check_job_status(job_id, api_key)`
Checks the current status and progress of a submitted job.

### `wait_for_completion(job_id, api_key, timeout=3600)`
Polls the job status until completion or timeout.

### `get_results(job_id, api_key, save_to_file=True)`
Retrieves the processed markdown content from a completed job.

### `process_large_document(file_path, api_key)`
Complete end-to-end workflow for document processing.

## Result Handling

The API optimizes performance by handling results differently based on size:

- **Small Files (< 1 MB)**: Results returned directly in the API response
- **Large Files (≥ 1 MB)**: Returns a temporary URL for downloading results

The implementation automatically handles both scenarios transparently.

## Tips and Best Practices

- **Polling Frequency**: Poll every 10-30 seconds for large documents
- **Job ID Storage**: Save job IDs immediately after submission
- **File Size Check**: Verify files are under 1GB before submission
- **Error Handling**: Implement exponential backoff for retries
- **Timeout Configuration**: Adjust timeout based on document size

## Processing Statistics

After processing, you'll receive useful metadata including:
- Page count
- Processing duration
- Credit usage

## Resources

- [LandingAI ADE Documentation](https://docs.landing.ai/ade)
- [API Key Management](https://va.landing.ai/settings/api-key)
- [Support & Issues](https://docs.landing.ai/support)

## Author

**Ava Xia** - Tutorial and implementation

## License

This project is provided as an educational resource for working with the LandingAI ADE Parse Jobs API.