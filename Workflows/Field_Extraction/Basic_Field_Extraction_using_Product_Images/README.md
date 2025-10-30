# 🏷️ Food Label Extraction with LandingAI ADE

This demo shows how to use **LandingAI's Agentic Document Extraction (ADE)** to extract structured information from food labels using the `landingai-ade` Python library.

## 🌟 Key Features

- **Separate parse() and extract()** - Parse once, extract multiple times with different schemas
- **Complete result preservation** - Save parse JSON, markdown, extract JSON, and summary CSV
- **Structured schemas** - Pydantic models for type-safe field extraction
- **Chunk references** - Traceability showing exactly where each field was found
- **Visual notebook** - View all input images before processing

## 📦 Prerequisites

- Python 3.8+
- LandingAI ADE API key
- Virtual environment (recommended)

## 🚀 Installation

### 1. Set up virtual environment

```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
# On macOS/Linux:
source venv/bin/activate
# On Windows:
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure API key

Create a `.env` file in this directory:

```env
VISION_AGENT_API_KEY=your_api_key_here
```

Get your API key from: https://va.landing.ai/settings/api-key

## 📁 Project Structure

```
Field_Extraction_Demo/
├── food_labels_demo.ipynb          # Main interactive notebook
├── food_label_schema.py            # Pydantic Product schema
├── food_label_utilities.py         # DataFrame utility function
├── requirements.txt                # Python dependencies
├── README.md                       # This file
├── .env                            # API key (not committed)
├── .gitignore                      # Git ignore rules
├── venv/                           # Virtual environment (not committed)
├── input_folder/                   # Sample food label images (6 samples)
└── results_folder/                 # All outputs (generated after running)
    ├── parse/                      # Parse JSON outputs
    ├── markdown/                   # Parse markdown outputs
    ├── extract/                    # Field extraction JSON per image
    └── summary_dataframe.csv       # Final aggregated CSV
```

## 🎯 Usage

### Run the Jupyter Notebook

1. **Open the notebook** in VS Code or Jupyter Lab:
   ```bash
   jupyter lab food_labels_demo.ipynb
   ```

2. **Or open in VS Code** and select the Python interpreter from your venv:
   - Press `Cmd+Shift+P` (Mac) or `Ctrl+Shift+P` (Windows/Linux)
   - Type: "Python: Select Interpreter"
   - Choose: `./venv/bin/python`

3. **Run all cells** sequentially from top to bottom

### Notebook Structure

The notebook is organized into these sections:

1. **Setup & Imports** - Load libraries and authenticate with API key
2. **Define Directories** - Set up input and output folder paths
3. **Collect File Paths** - Find all images to process
4. **View Input Images** - Display thumbnails of all food labels
5. **Single Document Example** - Parse and extract one image step-by-step
6. **Batch Processing** - Parse and extract all images, save results
7. **Create Summary DataFrame** - Aggregate all results into a CSV table
8. **Quick Analysis** - View statistics about extracted products

### Expected Runtime

- Single image: ~8-12 seconds (3-4 seconds parse + 4-5 seconds extract)
- 6 sample images: ~1 minute total
- API credits: ~3-4 credits per image (parsing + extraction)

## 📚 Module Documentation

### `food_label_schema.py`

Defines the `Product` Pydantic model with 27 fields:

**Product Identification:**
- `product_name`, `brand`, `product_type`, `flavor`

**Weight & Serving:**
- `net_weight_oz`, `net_weight_g`, `servings_per_container`, `serving_size`

**Animal Welfare (7 fields):**
- `is_grass_fed`, `is_pasture_raised`, `is_certified_humane`, `is_animal_welfare_certified`
- `no_antibiotics`, `no_hormones`, `no_animal_byproducts`

**Certifications (3 fields):**
- `is_organic`, `is_regenerative`, `is_non_gmo`

**Dietary Claims (7 fields):**
- `is_keto_friendly`, `is_paleo_friendly`, `is_whole30_approved`
- `is_gluten_free`, `is_dairy_free`, `is_lactose_free`, `has_no_added_sugar`

**Other:**
- `is_kosher`, `usda_inspected`

### `food_label_utilities.py`

Contains a single utility function:
- `create_summary_dataframe(extraction_results)` - Converts extraction results to pandas DataFrame with all product fields and chunk reference IDs

## 🔄 Workflow Explained

### 1. Parse Documents
Convert images to structured markdown with grounding information:

```python
from landingai_ade import LandingAIADE
from landingai_ade.types import ParseResponse

client = LandingAIADE(apikey=os.environ.get("VISION_AGENT_API_KEY"))

parse_result: ParseResponse = client.parse(
    document=Path("food_label.jpg"),
    split="page",
    model="dpt-2-latest"
)

# Returns: markdown, chunks, grounding, metadata
print(parse_result.markdown)
print(f"Chunks: {len(parse_result.chunks)}")
```

### 2. Extract Structured Fields
Apply Pydantic schema to markdown:

```python
from landingai_ade.types import ExtractResponse
from landingai_ade.lib import pydantic_to_json_schema
from food_label_schema import Product

# Convert Pydantic model to JSON schema
schema = pydantic_to_json_schema(Product)

extract_result: ExtractResponse = client.extract(
    markdown=parse_result.markdown,
    schema=schema
)

# Returns: structured product data (dict), chunk references, metadata
product = extract_result.extraction  # This is a dictionary
print(f"Product: {product['product_name']}")
print(f"Brand: {product['brand']}")
```

### 3. Explore Results
Access extracted data and metadata:

```python
# Extraction data (dictionary)
product = extract_result.extraction
print(f"Product: {product['product_name']}")
print(f"Brand: {product['brand']}")
print(f"Organic: {product['is_organic']}")

# See where data was found (chunk reference IDs)
meta = extract_result.extraction_metadata
print(f"Product name from chunks: {meta['product_name']['references']}")
```

### 4. Save Results
Save parse and extract results to disk:

```python
import json

# Save parse result
with open("results_folder/parse/my_document.json", 'w') as f:
    json.dump(parse_result.model_dump(), f, indent=2, ensure_ascii=False)

# Save markdown
with open("results_folder/markdown/my_document.md", 'w') as f:
    f.write(parse_result.markdown)

# Save extraction result
with open("results_folder/extract/my_document.json", 'w') as f:
    json.dump(extract_result.model_dump(), f, indent=2, ensure_ascii=False)
```

### 5. Create Summary Table
Aggregate results into a DataFrame:

```python
from food_label_utilities import create_summary_dataframe

# Convert list of results to DataFrame
# Format: [(parse_result, extract_result, document_name), ...]
extraction_results = [
    (parse_result, extract_result, "my_document")
]

df = create_summary_dataframe(extraction_results)

# Save to CSV
df.to_csv("results_folder/summary_dataframe.csv", index=False)
print(f"Created CSV with {len(df)} rows and {len(df.columns)} columns")
```

## 📊 Output Files

After running the notebook, you'll have:

| Location | Content | Purpose |
|----------|---------|---------|
| `results_folder/parse/*.json` | Full parse responses | Complete parsing data, reusable for multiple extractions |
| `results_folder/markdown/*.md` | Document markdown | Human-readable text, can be re-extracted without re-parsing |
| `results_folder/extract/*.json` | Field extraction results | Structured data per document with chunk references |
| `results_folder/summary_dataframe.csv` | Aggregated summary | All products in a single table for analysis |

## 🎨 Customization

### Modify the Schema

Edit `food_label_schema.py` to add/remove fields:

```python
from pydantic import BaseModel, Field

class Product(BaseModel):
    # Add new field
    calories_per_serving: int = Field(
        description="Calories per serving from Nutrition Facts"
    )

    # Add new certification
    is_fair_trade: bool = Field(
        description="True if Fair Trade certified"
    )

    # ... existing fields ...
```

After modifying the schema:
1. Update `food_label_utilities.py` to include new fields in the DataFrame
2. Re-run the notebook to extract with the updated schema

### Create Additional Schemas

You can create multiple schemas and extract different fields from the same parsed documents:

```python
class NutritionFacts(BaseModel):
    calories: int = Field(description="Calories per serving")
    total_fat_g: float = Field(description="Total fat in grams")
    sodium_mg: int = Field(description="Sodium in milligrams")
    protein_g: float = Field(description="Protein in grams")

# Parse once
parse_result = client.parse(
    document=image_path,
    split="page",
    model="dpt-2-latest"
)

# Extract with different schemas
product_schema = pydantic_to_json_schema(Product)
nutrition_schema = pydantic_to_json_schema(NutritionFacts)

product_data = client.extract(markdown=parse_result.markdown, schema=product_schema)
nutrition_data = client.extract(markdown=parse_result.markdown, schema=nutrition_schema)
```

### Process Your Own Images

Replace the contents of `input_folder/` with your own food label images:

1. Supported formats: `.jpg`, `.jpeg`, `.png`, `.pdf`
2. Best quality: Clear, well-lit images with readable text
3. The notebook will automatically process all files in `input_folder/`

## ⚡ Performance Tips

- **Reuse parse results**: Save parse JSON and markdown, then extract multiple times with different schemas without re-parsing
- **Sequential processing**: The notebook processes documents one at a time for reliability and easy debugging
- **Batch processing**: For large datasets (100+ documents), consider processing in batches of 20-50 at a time
- **API credits**: Each parse costs ~3 credits, each extract costs ~0.9 credits (costs may vary)

## 🐛 Troubleshooting

### API Key Issues
```
Error: API key is invalid
```
**Solution**: Check your `.env` file has the correct `VISION_AGENT_API_KEY`

### Import Errors
```
ModuleNotFoundError: No module named 'landingai_ade'
```
**Solution**:
1. Activate venv: `source venv/bin/activate`
2. Install dependencies: `pip install -r requirements.txt`

### Empty or Incorrect Extractions

If fields are empty or incorrectly extracted:

1. **Check the markdown**: View the parse result markdown to ensure the text was correctly extracted
2. **Improve field descriptions**: Make schema field descriptions more specific and clear
3. **Document quality**: Ensure images are not blurry, have good lighting, and text is readable
4. **Test iteratively**: Extract one image at a time to debug issues

### Kernel Not Found (VS Code)

If you can't find the kernel in VS Code:
1. Open notebook in VS Code
2. Press `Cmd+Shift+P` → "Python: Select Interpreter"
3. Choose: `./venv/bin/python`
4. Reload the window if needed

## 📚 Additional Resources

- **ADE Documentation**: https://docs.landing.ai/ade/ade-overview
- **ADE Python Library**: https://docs.landing.ai/ade/ade-python
- **API Reference**: https://docs.landing.ai/ade/ade-parse-docs
- **Pydantic Documentation**: https://docs.pydantic.dev/
- **Supported File Types**: https://docs.landing.ai/ade/ade-file-types

## 🤝 Support

For questions or issues:
- **Documentation**: https://docs.landing.ai
- **API Support**: Contact your LandingAI representative

---

**Last Updated**: October 2025
**ADE Library Version**: 0.20.0+
**Python Version**: 3.8+
