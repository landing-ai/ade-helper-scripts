# Word-Level Grounding Demo

This workflow demonstrates **word-level grounding** for extracted fields using LandingAI's Agentic Document Extraction (ADE). Unlike standard chunk-level grounding, this demo shows how to pinpoint the exact words in a document that correspond to extracted field values.

## Overview

When ADE extracts a field value (e.g., "8%"), it provides chunk-level grounding that shows which document chunks contain the information. This demo takes it one step further by using OCR to identify the precise word-level locations within those chunks.

### What This Demo Shows

- **Parse**: Extract document structure, markdown, and chunk-level grounding from a PDF
- **Extract**: Extract specific fields using a Pydantic schema
- **Word-Level Grounding**: Use OCR (Tesseract) to find exact word positions within identified chunks
- **Visualization**: Highlight matched words with a "highlighter" effect showing confidence levels

## Use Case

This is particularly useful for:
- **Auditability**: Show users exactly where extracted values came from at word level
- **Quality Assurance**: Verify extraction accuracy by visualizing source locations
- **Compliance**: Provide detailed traceability for regulated industries
- **Debugging**: Understand why certain values were extracted

## Setup

### Installation

```bash
pip install landingai-ade python-dotenv pillow pymupdf matplotlib pytesseract
```

### Tesseract OCR

This demo requires Tesseract OCR to be installed on your system:

**macOS:**
```bash
brew install tesseract
```

**Ubuntu/Debian:**
```bash
sudo apt-get install tesseract-ocr
```

**Windows:**
Download installer from: https://github.com/UB-Mannheim/tesseract/wiki

### API Key

Set your LandingAI API key in a `.env` file:
```
VISION_AGENT_API_KEY=your_api_key_here
ADE_MODEL=dpt-2-latest
```

## How It Works

### 1. Parse Document

First, the document is parsed to extract:
- **Markdown representation**: Text content of the document
- **Chunks**: Structural elements (text blocks, tables, figures, etc.)
- **Grounding data**: Bounding box coordinates for each chunk

```python
parse_response = client.parse(
    document=pdf_path,
    model="dpt-2-latest"
)
```

### 2. Extract Field

Define a schema for the field you want to extract:

```python
schema_dict = {
    "type": "object",
    "properties": {
        "remaining_human_genome": {
            "type": "string",
            "description": "The percentage of the human genome that was left unfinished..."
        }
    },
    "required": ["remaining_human_genome"]
}
```

Extract from the parsed markdown:

```python
extract_response = client.extract(
    schema=json.dumps(schema_dict),
    markdown=markdown_path
)
```

### 3. Get Chunk References

The extraction response includes `extraction_metadata` with chunk references:

```python
chunk_ids = extract_response.extraction_metadata['remaining_human_genome']['references']
```

These chunk IDs tell you which chunks contain the extracted value.

### 4. Word-Level OCR

For each referenced chunk:
1. Get the chunk's bounding box from grounding data
2. Crop the page image to that chunk
3. Run OCR on the cropped region
4. Fuzzy match OCR results against the extracted value
5. Record word-level positions for matches

```python
ocr_data = pytesseract.image_to_data(chunk_img, output_type=pytesseract.Output.DICT)
```

### 5. Visualize Results

Highlight matched words with a "highlighter pen" effect:
- **Bright yellow** (120 opacity): Exact matches (>90% similarity)
- **Orange** (100 opacity): Good matches (70-90% similarity)
- **Light yellow** (80 opacity): Partial matches (50-70% similarity)

Red badges show similarity percentages for high-confidence matches.

## Output Files

The demo generates several output files:

- `parsed_output.md`: Markdown representation of the document
- `grounding_data.json`: Chunk-level grounding data (bounding boxes, pages, types)
- `output_visualizations/page_0_annotated.png`: Visualization with highlighted words
- `output_visualizations/extraction_results.json`: Detailed match data including coordinates

## Example Result

For the demo PDF (genomics research paper), extracting the field:
- **Field**: `remaining_human_genome`
- **Extracted Value**: "8%"
- **Found**: 1 exact match with 100% similarity
- **Location**: Page 0, within identified chunk(s)

The visualization shows "8%" highlighted in yellow on the original document.

## Customization

### Adjust OCR Confidence Threshold

In the OCR processing section, adjust the confidence filter:

```python
if conf < 30:  # Change this threshold (0-100)
    continue
```

### Modify Fuzzy Matching

Adjust similarity requirements:

```python
if similarity > 0.5:  # Change this threshold (0.0-1.0)
    # Process match
```

### Change Highlighter Colors

Modify the color definitions in the visualization section:

```python
if similarity > 0.9:
    color = (255, 255, 0, 120)  # (R, G, B, Alpha)
```

## Limitations

- **OCR Accuracy**: Tesseract OCR may not work well on low-quality scans or complex layouts
- **Performance**: OCR processing adds significant overhead compared to chunk-level grounding
- **Multi-word Values**: Fuzzy matching works best for short values (1-3 words)
- **Language Support**: Default configuration uses English; other languages require Tesseract language packs

## When to Use Word-Level Grounding

**Use this approach when:**
- You need precise provenance for compliance/audit trails
- Field values are short (numbers, dates, single words)
- Document quality is good enough for OCR
- You're building explainable AI systems

**Stick with chunk-level grounding when:**
- Performance is critical (OCR is slow)
- Field values span multiple lines or sections
- Document quality is poor (handwritten, faded, etc.)
- Chunk-level context is sufficient for your use case

## Further Reading

- [ADE Documentation](https://docs.landing.ai/ade/ade-overview)
- [ADE Parse API](https://docs.landing.ai/ade/ade-parse)
- [ADE Extract API](https://docs.landing.ai/ade/ade-extract)
- [Tesseract OCR Documentation](https://tesseract-ocr.github.io/)

## Troubleshooting

**"Tesseract not found" error:**
- Ensure Tesseract is installed and in your system PATH
- On macOS with Homebrew: `brew install tesseract`

**Low OCR accuracy:**
- Try increasing image resolution: `pymupdf.Matrix(3, 3)` instead of `(2, 2)`
- Preprocess images (convert to grayscale, increase contrast)
- Use Tesseract's PSM modes for specific layouts

**No matches found:**
- Check `extraction_metadata` to ensure chunk references are present
- Lower the similarity threshold in fuzzy matching
- Verify the extracted value matches what's visually in the document
