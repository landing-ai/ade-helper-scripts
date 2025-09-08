import streamlit as st
import os
import json
from pathlib import Path
from PIL import Image as PILImage
from agentic_doc.parse import parse
from agentic_doc.utils import viz_parsed_document

# ------------------------------------------------------------
# Configure the Streamlit app
# ------------------------------------------------------------
st.set_page_config(page_title="Agentic Document Extraction Sample App", layout="wide")

# ------------------------------------------------------------
# App Title and Logo
# ------------------------------------------------------------
# Display a logo at the top
logo_path = Path("images/LandingAI_Logo.png")
if logo_path.exists():
    st.image(str(logo_path), width=200)
st.title("Agentic Document Extraction App")
"An application that extracts all pages of all documents in a specific directory and makes it easy to 'see' what is happening in real time."

# ------------------------------------------------------------
# Reset Button: Clear session state so user can start over
# ------------------------------------------------------------
if st.button("🔄 Reset App"):
    for key in ["processed_docs", "parsed_results", "original_paths"]:
        if key in st.session_state:
            del st.session_state[key]
    try:
        st.experimental_rerun()
    except AttributeError:
        st.info("Session state cleared. Please refresh the browser (F5) to start over.")
        st.stop()

# ------------------------------------------------------------
# Create four top‐level tabs
# ------------------------------------------------------------
tabs = st.tabs([
    "Document Selection",
    "Extraction Results JSON",
    "Extraction Results Visualizations",
    "About this App"
])


# ------------------------------------------------------------
# Tab 1: Document Selection and Batch Extraction
# ------------------------------------------------------------
with tabs[0]:
    st.header("Document Selection")

    # Let the user type or paste a directory path
    directory = st.text_input("Documents directory path", value=os.getcwd())

    # Only show “Begin Extraction” if the directory actually exists
    if directory and Path(directory).is_dir():
        if st.button("Begin Extraction"):
            base_dir = Path(directory)
            results_base = base_dir / "results"
            groundings_base = base_dir / "groundings"
            results_base.mkdir(parents=True, exist_ok=True)
            groundings_base.mkdir(parents=True, exist_ok=True)

            # 1) Gather all supported files (.pdf/.png/.jpg/.jpeg) in that directory (non‐recursive)
            file_paths = [
                str(p)
                for p in base_dir.iterdir()
                if p.suffix.lower() in [".pdf", ".png", ".jpg", ".jpeg"]
            ]

            total_docs = len(file_paths)
            if total_docs == 0:
                st.warning("No supported documents found in that directory.")
            else:
                st.info(f"Found {total_docs} document(s). Sending them to Agentic Document Extraction…")
                progress_bar = st.progress(0)

                # 2) Batch‐parse all files in a single call to parse(...)
                results = parse(
                    documents=file_paths,
                    result_save_dir=str(results_base),
                    include_marginalia=True,
                    include_metadata_in_markdown=True,
                    grounding_save_dir=str(groundings_base),
                )

                # 3) Now iterate over each returned Result object
                for idx, (result_obj, file_path) in enumerate(zip(results, file_paths)):
                    card_id = Path(file_path).stem

                    # — Initialize session_state dictionaries if not present:
                    if "parsed_results" not in st.session_state:
                        st.session_state["parsed_results"] = {}
                    if "original_paths" not in st.session_state:
                        st.session_state["original_paths"] = {}

                    # — Store the parsed Result object under this card_id:
                    st.session_state["parsed_results"][card_id] = result_obj
                    # — Also store the original file path so Tab 3 knows where to look:
                    st.session_state["original_paths"][card_id] = file_path

                    st.write(f"✔️ Processed {idx+1}/{total_docs}: **{card_id}**")

                    # If you also want to persist Markdown to disk (in addition to JSON), you can do:
                    if result_obj.markdown:
                        md_output = results_base / f"{card_id}.md"
                        with open(md_output, "w") as f_md:
                            f_md.write(result_obj.markdown)

                    # Keep track of processed documents so that Tabs 2 & 3 can display them
                    if "processed_docs" not in st.session_state:
                        st.session_state["processed_docs"] = []
                    st.session_state["processed_docs"].append(card_id)

                    # Update progress
                    progress_bar.progress((idx + 1) / total_docs)

                st.success("✅ Extraction complete! All outputs have been saved in the `results/` and `groundings/` folders.")

# ------------------------------------------------------------
# Tab 2: Display Extraction Results (JSON)
# ------------------------------------------------------------
with tabs[1]:
    st.header("Extraction Results (JSON)")

    if "processed_docs" not in st.session_state or not st.session_state["processed_docs"]:
        st.info("No extraction results available yet. Please run extraction on Tab 1.")
    else:
        doc_ids = st.session_state["processed_docs"]
        sub_tabs = st.tabs([f"{doc_id}" for doc_id in doc_ids])

        for idx, doc_id in enumerate(doc_ids):
            with sub_tabs[idx]:
                st.subheader(f"Document: {doc_id}")

                result_dir = Path(directory) / "results"

                # Look for any JSON file that starts with `<doc_id>_` and ends in `.json`
                matches = sorted(result_dir.glob(f"{doc_id}_*.json"))

                if matches:
                    # If there are multiple timestamped outputs, pick the last one
                    latest_json_path = matches[-1]
                    st.markdown(f"**Showing:** `{latest_json_path.name}`")
                    with open(latest_json_path, "r") as f_json:
                        st.json(json.load(f_json))
                else:
                    st.warning("No JSON result file found for this document.")

# ------------------------------------------------------------
# Tab 3: Display Extraction Results (Visualizations)
# ------------------------------------------------------------
with tabs[2]:
    st.header("Extraction Results (Visualizations)")

    # Check that Tab 1 has already populated processed_docs, parsed_results, and original_paths
    if (
        "processed_docs" not in st.session_state
        or not st.session_state["processed_docs"]
    ):
        st.info("No extraction results available yet. Please run extraction on Tab 1.")
    else:
        doc_ids = st.session_state["processed_docs"]

        # Create one subtab per document (just like Tab 2 does for JSON)
        sub_tabs = st.tabs([f"{doc_id}" for doc_id in doc_ids])

        for idx, doc_id in enumerate(doc_ids):
            with sub_tabs[idx]:
                st.subheader(f"Document: {doc_id}")

                # 1) Retrieve the original file path and parsed Result object
                doc_path = st.session_state["original_paths"].get(doc_id)
                parsed_doc = st.session_state["parsed_results"].get(doc_id)

                if doc_path is None or parsed_doc is None:
                    st.warning(
                        "Could not find either the original path or parsed result for this document."
                    )
                    continue

                # 2) Create (or reuse) a “visualizations/<doc_id>” folder
                viz_base = Path(doc_path).parent / "visualizations" / doc_id
                viz_base.mkdir(parents=True, exist_ok=True)

                # 3) Call viz_parsed_document()
                try:
                    image_paths = viz_parsed_document(
                        doc_path,
                        parsed_doc,
                        output_dir=str(viz_base),
                    )
                except Exception as e:
                    st.error(f"Error while visualizing '{doc_id}': {e}")
                    continue

                # 4) Display the results
                if not image_paths:
                    st.warning("No visualization images were created for this document.")
                else:
                    st.caption(f"{len(image_paths)} page‐level visualization(s) created.")

                    for page_idx, item in enumerate(image_paths, start=1):
                        # If viz_parsed_document returned a PIL.Image, display directly
                        if isinstance(item, PILImage.Image):
                            st.image(
                                item,
                                caption=f"Page {page_idx}",
                                use_container_width=True,
                            )
                        else:
                            # Otherwise assume it’s a file path to a saved PNG
                            p = Path(item)
                            st.image(
                                str(p),
                                caption=p.name,
                                use_container_width=True,
                            )

# ------------------------------------------------------------
# Tab 4: About this App
# ------------------------------------------------------------
with tabs[3]:
    st.header("About this App")
    st.markdown("""
**Agentic Document Extraction App**  
Version: 1.0.0  

This Streamlit application enables you to **batch‐parse** local documents (PDF, PNG, JPG, JPEG) using LandingAI’s Agentic Document Extraction API. 

**How to Use**  
1. **Select a Folder**  
   - Enter or browse to the directory containing your documents.  
   - Click **Begin Extraction** to send all supported files in that folder to the Agentic Document Extraction service.  

2. **View JSON Results**  
   - Click on the **Extraction Results JSON** tab to see the structured JSON output for each document.  
   - Each document has its own subtab, showing the most recently generated JSON.  

3. **View Visualizations**  
   - Click on the **Extraction Results Visualizations** tab to see page‐level bounding‐box images overlaid on each original document page.  
   - Each document has its own subtab with one image per page.  

4. **Reset & Rerun**  
   - Use the **🔄 Reset App** button at the top to clear all outputs and start fresh on a different folder.  

---

**Try Agentic Document Extraction**  
You can try Agentic Document Extraction for free at [va.landing.ai](http://va.landing.ai).  

**API Documentation**  
Full API docs are available at [docs.landing.ai/ade](https://docs.landing.ai/ade).  

---
                
**Dependencies**  
- Python 3.9+  
- Streamlit  
- agentic_doc (Agentic Document Extraction SDK)  
- Pillow (for image handling)  

**Developed By**  
Andrea Kropp, Machine Learning Engineer  

**License & Attribution**  
This application leverages the Agentic Document Extraction SDK from LandingAI. Please refer to the LandingAI documentation for detailed API usage guidelines and terms of service. 
                 
    """)







