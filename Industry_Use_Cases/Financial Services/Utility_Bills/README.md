# Fast, Accurate Parsing of Utility Bills with LandingAI

This folder contains assets and scripts demonstrating **Agentic Document Extraction (ADE)** on **Utility Bills**. Utility bills are a common proof-of-address document in KYC and onboarding workflows.

Use this workflow to:

- Process PDFs or images of utility bills from many providers.
- Define custom field to extract using a JSON schema.
- Run Agentic Document Extraction on a batch of utility bills and save the results.
- Save the extracted results and visual grounding chunks as structured data.

To learn more visit the [LandingAI Documentation](https://docs.landing.ai/ade/ade-overview).


---

## 🎥 Demo Video

[![Utility Bill Extraction Demo](https://img.youtube.com/vi/_yvlR7-6GBc/0.jpg)](https://youtu.be/_yvlR7-6GBc)


## 📁 Contents

- **utility_bills_executed.ipynb**  
  The notebook that orchestrates the workflow. It has been previously executed so you can see the outputs.

- **input_folder/**  
  Place raw utility bill documents here (PDF, PNG, JPG, JPEG). 9 examples are included 3 JPG and 6 PDF from different electric and gas utiltiies.

- **results_folder/**  
  Processed results (JSON, Markdown and Summary CSV) will be written here after extraction. The outputs from the 9 examples is included.

- **groundings_folder/**  
  Stores grounding files that link extracted fields back to their visual source in the document.

- **utility_bill.json**  
  JSON schema defining the expected fields to extract (e.g., account number, billing address, billing period, amount due, due date).

---

## 🚀 Prerequisites

1. Install the [agentic-doc](https://pypi.org/project/agentic-doc/) library:

   ```bash
   pip install agentic-doc

2. Set your LandingAI Vision Agent API key:

    ``` bash
    export VISION_AGENT_API_KEY="your_api_key_here"
