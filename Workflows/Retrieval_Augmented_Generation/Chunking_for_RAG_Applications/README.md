# Document Parser for RAG Applications

This project provides everything you need to prepare documents for a RAG system. It processes any number of documents in a batch, extracting structured text chunks with visual grounding coordinates. While the included example data focuses on medical research about the common cold, **the scripts work with any document type or domain**.

## Key Features

### Document Parsing (`rag_parser.py`)
- ✅ **Domain-agnostic**: Works with any document type (legal, medical, financial, research, etc.)
- ✅ **Parallel processing**: Process multiple documents simultaneously for faster throughput
- ✅ **Flexible output**: Choose between combined or per-document CSV files
- ✅ **Visual grounding**: Extract bounding box coordinates for each text chunk
- ✅ **Chunk image extraction**: Optionally save individual chunks as PNG images with visual boundaries
- ✅ **Clean text extraction**: Get both raw and cleaned versions of chunk content
- ✅ **Rich metadata**: 19 CSV columns optimized for RAG applications

## Use Cases

This script can be applied to any document collection:

- 📚 **Research & Academia**: Parse scientific papers, dissertations, literature reviews
- ⚖️ **Legal**: Process contracts, case law, compliance documents
- 🏥 **Healthcare**: Process research papers, clinical trial reports, internal lab notes
- 💼 **Business**: Analyze reports, proposals, white papers, technical documentation
- 📰 **Media**: Parse news articles, press releases, archived documents
- 🏛️ **Government**: Process policy documents, regulations, public records

## Setup

### 1. Create a virtual environment

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**Dependencies include:**
- `landingai-ade` - LandingAI ADE Python library
- `pandas` - CSV data manipulation
- `aiolimiter` - Async rate limiting
- `python-dotenv` - Environment variable management
- `Pillow` - Image processing (for chunk image extraction)
- `pymupdf` - PDF rendering (for chunk image extraction)

### 2. Set your API key

Create a `.env` file in this directory with your Vision Agent API key:

```bash
echo "VISION_AGENT_API_KEY=your-api-key-here" > .env
```

Or export it directly:
```bash
export VISION_AGENT_API_KEY=your-api-key-here
```

## Usage

### Basic usage (uses default directories)
```bash
python rag_parser.py
```

This will:
- Read files from `input_folder/`
- Save JSON responses to `results_folder/json/`
- Save markdown to `results_folder/markdown/`
- Save chunks CSV to `results_folder/chunks/all_chunks.csv`
- (Optionally save chunk images to `results_folder/chunk_images/` with `--save-chunk-images`)

### Custom directories
```bash
python rag_parser.py --input-dir custom_input --output-dir custom_output
```

### Adjust concurrent processing
```bash
# Limit concurrent requests (default: 10)
python rag_parser.py --max-concurrent 5

# Adjust rate limit to avoid API throttling (default: 30 requests/minute)
python rag_parser.py --rate-limit 20

# Combine both settings
python rag_parser.py --max-concurrent 5 --rate-limit 15
```

**Note:** The script uses async/await patterns with `AsyncLandingAIADE` and `aiolimiter` for efficient concurrent processing, following [official LandingAI ADE documentation](https://docs.landing.ai/ade/ade-python#async-parse%3A-processing-multiple-documents-concurrently).

### CSV output modes

**Combined mode (default)** - Creates one CSV with all chunks from all documents:
```bash
# Use default filename (all_chunks.csv)
python rag_parser.py --csv-mode combined

# Specify custom filename
python rag_parser.py --csv-mode combined --csv-name my_research_data.csv
```

**Separate mode** - Creates one CSV per input document:
```bash
python rag_parser.py --csv-mode separate
```

This creates files like:
- `document1_chunks.csv`
- `document2_chunks.csv`
- `document3_chunks.csv`

### Save chunk images (optional)

Optionally save each parsed chunk as an individual PNG image file. This is useful for:
- Visual verification of chunk boundaries
- Creating training datasets for document understanding models
- Building visual search systems
- Debugging parsing results

```bash
# Enable chunk image saving
python rag_parser.py --save-chunk-images

# Combine with other options
python rag_parser.py --save-chunk-images --csv-mode separate
```

**Requirements:** This feature requires `Pillow` and `pymupdf` (included in `requirements.txt`).

**Output structure:** Images are saved as:
```
results_folder/chunk_images/
├── document1/
│   ├── page_0/
│   │   ├── text.{chunk_id}.png
│   │   ├── table.{chunk_id}.png
│   │   └── logo.{chunk_id}.png
│   └── page_1/
│       └── ...
└── document2/
    └── ...
```

**Note:** Following [official LandingAI ADE documentation](https://docs.landing.ai/ade/ade-python#save-parsed-chunks-as-images), each chunk is cropped from the source document using its bounding box coordinates and saved with a descriptive filename: `{chunk_type}.{chunk_id}.png`

### View all options
```bash
python rag_parser.py --help
```
