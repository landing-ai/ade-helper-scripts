# ADE LLM Retrieval Workflow

This workflow demonstrates how to use LandingAI's Agentic Document Extraction (ADE) API with OpenAI's LLMs for intelligent document processing, field extraction, and question answering with evaluation.

## Overview

This workflow showcases:
- **Document Parsing**: Extract structured data from PDFs and images using ADE
- **Visual Grounding**: Get bounding boxes and visual crops for every extracted element
- **LLM Field Extraction**: Use OpenAI to extract specific fields from parsed documents
- **RAG Pipeline**: Build a Retrieval-Augmented Generation system with ChromaDB/FAISS
- **Evaluation**: Automated evaluation of extraction quality using LangChain

## Features

### 1. Document Extraction Methods
- **REST API**: Direct HTTP calls to ADE API
- **Python SDK**: Simplified `parse()` function for document processing
- **Visual Grounding**: Automatic generation of grounding images showing bounding boxes

### 2. Multiple Output Formats
- **Markdown**: Human-readable markdown representation
- **Chunks**: Structured JSON with hierarchical document elements
- **Grounding Images**: Visual overlays showing extraction regions

### 3. LLM Integration
- **Field Extraction**: Extract specific fields using OpenAI's GPT models
- **Validation**: Verify document completeness and compliance
- **Q&A**: Answer questions about document content

### 4. Evaluation Pipeline
- **Vector Store**: FAISS-based similarity search for document chunks
- **QA Chain**: LangChain RetrievalQA for question answering
- **Automated Grading**: LLM-based evaluation of answer quality
- **LLM-Generated Evals**: Automatically generate test questions from documents

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

Or install manually:
```bash
pip install agentic-doc python-dotenv openai langchain langchain-community langchain-openai faiss-cpu
```

### 2. Configure API Keys

Copy the example environment file and add your API keys:

```bash
cp .env.example .env
```

Edit `.env` and add your keys:
```env
# LandingAI Vision Agent API Key
VISION_AGENT_API_KEY=your_vision_agent_api_key_here

# OpenAI API Key
OPENAI_API_KEY=your_openai_api_key_here
```

**Getting API Keys:**
- **LandingAI Vision Agent**: https://docs.landing.ai/ade/agentic-api-key
- **OpenAI**: https://platform.openai.com/api-keys

### 3. Run the Notebook

```bash
jupyter notebook Doc_Extraction_Demo_vf.ipynb
```

Or use the streamlined version:
```bash
jupyter notebook ADE_LLM_Retrieval.ipynb
```

## Usage Examples

### Basic Document Parsing

```python
from agentic_doc.parse import parse

# Parse a local file
result = parse("path/to/document.pdf")

# Get the extracted data as markdown
print("Extracted Markdown:")
print(result[0].markdown)

# Get the extracted data as structured chunks
print("Extracted Chunks:")
print(result[0].chunks)
```

### With Visual Grounding

```python
from agentic_doc.parse import parse

# Parse with grounding images saved to disk
result = parse("document.pdf", grounding_save_dir="./groundings")
parsed_doc = result[0]

# Access grounding image paths
for chunk in parsed_doc.chunks:
    for grounding in chunk.grounding:
        if grounding.image_path:
            print(f"Grounding saved to: {grounding.image_path}")
```

### Field Extraction with OpenAI

```python
import openai
from dotenv import load_dotenv
import os

load_dotenv()
client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

markdown_text = parsed_doc.markdown

prompt = f"""
Extract the compliance contact name and email from this document:

{markdown_text}

Return as JSON: {{"name": "", "email": ""}}
"""

response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": prompt}],
    temperature=0.0
)

print(response.choices[0].message.content)
```

### RAG Pipeline with Evaluation

```python
from langchain_core.documents import Document
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain.chains import RetrievalQA

# Convert ADE chunks to LangChain documents
def chunks_to_documents(chunks):
    docs = []
    for chunk in chunks:
        metadata = {
            "chunk_id": chunk.chunk_id,
            "chunk_type": chunk.chunk_type.value,
            "page": chunk.grounding[0].page if chunk.grounding else None
        }
        docs.append(Document(page_content=chunk.text, metadata=metadata))
    return docs

documents = chunks_to_documents(parsed_doc.chunks)

# Create vector store and retriever
embedding_model = OpenAIEmbeddings(api_key=os.getenv("OPENAI_API_KEY"))
vectorstore = FAISS.from_documents(documents, embedding_model)
retriever = vectorstore.as_retriever(search_type="similarity", search_kwargs={"k": 3})

# Create QA chain
llm = ChatOpenAI(api_key=os.getenv("OPENAI_API_KEY"), model="gpt-4o", temperature=0)
qa_chain = RetrievalQA.from_chain_type(llm=llm, retriever=retriever, return_source_documents=True)

# Ask questions
result = qa_chain.invoke({"query": "What is the client's name?"})
print(result["result"])
```

## Files

- **`Doc_Extraction_Demo_vf.ipynb`**: Full-featured demo with evaluation pipeline
- **`ADE_LLM_Retrieval.ipynb`**: Streamlined version of the workflow
- **`.env.example`**: Template for environment variables
- **`requirements.txt`**: Python dependencies
- **`KYC_EXAMPLE_DOC.pdf`**: Sample KYC document for testing

## Output Structure

### Parsed Document Structure

```python
ParsedDocument(
    markdown: str,              # Full document as markdown
    chunks: List[Chunk],        # Structured chunks
    metadata: Dict              # Document metadata
)
```

### Chunk Structure

```python
Chunk(
    text: str,                  # Chunk text content
    chunk_type: ChunkType,      # Type: title, text, table, figure, etc.
    chunk_id: str,              # Unique chunk identifier
    grounding: List[ChunkGrounding]  # Visual grounding with bounding boxes
)
```

### Grounding Structure

```python
ChunkGrounding(
    page: int,                  # Page number (0-indexed)
    box: ChunkGroundingBox,     # Bounding box coordinates (normalized 0-1)
    image_path: Path            # Path to grounding image (if saved)
)
```

## Example Use Cases

### 1. KYC Document Processing
- Extract client information (name, address, registration numbers)
- Validate required attachments
- Extract compliance contact details
- Verify ownership structures

### 2. Financial Document Analysis
- Parse financial statements and tables
- Extract revenue, net income, and employee data
- Analyze year-over-year growth metrics
- Chart and visualization extraction

### 3. Compliance Verification
- Check for missing required documents
- Validate form completeness
- Extract signatures and dates
- Verify regulatory information

### 4. Question Answering
- Build searchable document database
- Answer specific questions about document content
- Generate document summaries
- Create automated evaluation pipelines

## Evaluation Metrics

The workflow includes automated evaluation:
- **Correctness**: LLM-based grading of answer accuracy
- **Ground Truth Comparison**: Compare predictions against expected answers
- **Coverage**: Measure retrieval quality across document chunks
- **Auto-Generated Tests**: Use LLMs to generate evaluation questions

Example evaluation results:
```
Q1: What is the client's name?
Prediction: The client's name is Acme Global Holdings Ltd.
Ground Truth: Acme Global Holdings Ltd.
Grade: CORRECT ✓

Q2: What is the email address for compliance contact?
Prediction: The email address for the compliance contact is compliance@acmeglobal.com.
Ground Truth: compliance@acmeglobal.com
Grade: CORRECT ✓
```

## Visualization

The workflow generates multiple visualization types:

### 1. Grounding Overlays
Visual overlays showing bounding boxes for each extracted chunk with labels.

### 2. Markdown Preview
Human-readable markdown representation of the entire document.

### 3. Structured JSON
Hierarchical JSON representation with chunk types and metadata.

## Troubleshooting

### API Key Not Set Error
```
ValueError: API key is not set. Please provide a valid API key.
```
**Solution**: Ensure your `.env` file exists and contains valid API keys.

### Missing Dependencies
```
ModuleNotFoundError: No module named 'agentic_doc'
```
**Solution**: Install dependencies with `pip install -r requirements.txt`

### File Not Found
```
FileNotFoundError: [Errno 2] No such file or directory: './KYC_EXAMPLE_DOC.pdf'
```
**Solution**: Ensure you're running the notebook from the correct directory.

## Resources

- **ADE Documentation**: https://docs.landing.ai/ade/ade-overview
- **Visual Playground**: https://va.landing.ai/demo/doc-extraction
- **API Reference**: https://docs.landing.ai/ade/ade-api-reference
- **GitHub**: https://github.com/landing-ai/agentic-doc
- **Support**: https://docs.landing.ai/ade/ade-support

## License

This example is provided by LandingAI for demonstration purposes.

## Contributing

For issues or questions, please refer to the main repository's issue tracker.