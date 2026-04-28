"""
Utility functions for ADE document processing and visualization.
This module contains helper functions to keep the main notebook clean and focused.
"""

import os
import json
import shutil
from pathlib import Path
from PIL import Image, ImageDraw
import pymupdf
from IPython.display import HTML, display
import base64
from io import BytesIO


# Define color scheme for different chunk types
CHUNK_TYPE_COLORS = {
    "chunkText": (40, 167, 69),        # Green
    "chunkTable": (0, 123, 255),       # Blue
    "chunkMarginalia": (111, 66, 193), # Purple
    "chunkFigure": (255, 0, 255),      # Magenta
    "chunkLogo": (144, 238, 144),      # Light green
    "chunkCard": (255, 165, 0),        # Orange
    "chunkAttestation": (0, 255, 255), # Cyan
    "chunkScanCode": (255, 193, 7),    # Yellow
    "chunkForm": (220, 20, 60),        # Red
    "tableCell": (173, 216, 230),      # Light blue
    "table": (70, 130, 180),           # Steel blue
}


def cleanup_results_folders():
    """Remove and recreate results folders to avoid duplicates. Keep cache intact."""
    folders = ["results", "results_extracted"]
    for folder in folders:
        if Path(folder).exists():
            shutil.rmtree(folder)
        Path(folder).mkdir(exist_ok=True)

    # Ensure cache folder exists but don't delete it
    Path("cache").mkdir(exist_ok=True)
    print("✓ Results folders cleaned and ready")


def save_to_cache(filename, data):
    """Save API results to cache for offline fallback."""
    cache_dir = Path("cache")
    cache_dir.mkdir(exist_ok=True)
    cache_file = cache_dir / f"{filename}.json"

    # Convert data to JSON-serializable format
    if hasattr(data, 'model_dump'):
        data = data.model_dump()

    # Special handling for page_classifications to extract markdown properly
    if filename == "page_classifications" and isinstance(data, list):
        clean_data = []
        for item in data:
            clean_item = {
                "page": item.get("page"),
                "doc_type": item.get("doc_type"),
                "split": item.get("split") if isinstance(item.get("split"), dict) else {}
            }
            clean_data.append(clean_item)
        data = clean_data

    with open(cache_file, 'w') as f:
        json.dump(data, f, indent=2, default=str)


def load_from_cache(filename):
    """Load results from cache if available."""
    cache_file = Path("cache") / f"{filename}.json"
    if cache_file.exists():
        with open(cache_file, 'r') as f:
            return json.load(f)
    return None


def save_parse_result_for_viz(parse_result, filename="parse_result_viz.pkl"):
    """Save parse_result with grounding data using pickle for visualization."""
    import pickle
    cache_dir = Path("cache")
    cache_dir.mkdir(exist_ok=True)
    cache_file = cache_dir / filename

    with open(cache_file, 'wb') as f:
        pickle.dump(parse_result, f)


def load_parse_result_for_viz(filename="parse_result_viz.pkl"):
    """Load parse_result with grounding data from pickle."""
    import pickle
    cache_file = Path("cache") / filename
    if cache_file.exists():
        with open(cache_file, 'rb') as f:
            return pickle.load(f)
    return None


def create_scrollable_pdf_viewer(pdf_path, max_height="600px"):
    """
    Create an interactive scrollable HTML viewer for a PDF.

    Args:
        pdf_path: Path to the PDF file
        max_height: Maximum height of the scrollable container

    Returns:
        IPython HTML object for display
    """
    pdf = pymupdf.open(pdf_path)

    html_content = f"""
    <div style="max-height: {max_height}; overflow-y: scroll; border: 2px solid #ccc; padding: 10px;">
    """

    for page_num in range(len(pdf)):
        pix = pdf[page_num].get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5))
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

        buffered = BytesIO()
        img.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode()

        html_content += f"""
        <div style="margin-bottom: 20px;">
            <h4 style="color: #333;">Page {page_num + 1}</h4>
            <img src="data:image/png;base64,{img_str}" style="max-width: 100%; border: 1px solid #ddd;">
        </div>
        """

    html_content += "</div>"
    pdf.close()

    return HTML(html_content)


def group_pages_by_document_type(page_classifications):
    """
    Group consecutive pages of the same type into logical documents.

    Args:
        page_classifications: List of dicts with page, doc_type, and split info

    Returns:
        Dictionary of split documents with metadata
    """
    split_documents = {}
    current_doc_type = None
    current_pages = []
    current_splits = []
    doc_counter = 1

    for classification in page_classifications:
        page_idx = classification["page"]
        doc_type = classification["doc_type"]
        split = classification["split"]

        if doc_type != current_doc_type:
            if current_doc_type is not None:
                doc_name = f"{current_doc_type}_{doc_counter}"
                # Handle both object and dict formats
                if current_splits:
                    first_split = current_splits[0]
                    if hasattr(first_split, 'markdown'):
                        # From API - split is an object
                        combined_markdown = "\n\n".join([s.markdown for s in current_splits])
                    elif isinstance(first_split, dict) and 'markdown' in first_split:
                        # From cache - split is a dict
                        combined_markdown = "\n\n".join([s['markdown'] for s in current_splits])
                    else:
                        combined_markdown = ""
                else:
                    combined_markdown = ""

                split_documents[doc_name] = {
                    "doc_type": current_doc_type,
                    "pages": current_pages,
                    "markdown": combined_markdown,
                    "splits": current_splits
                }
                doc_counter += 1

            current_doc_type = doc_type
            current_pages = [page_idx]
            current_splits = [split]
        else:
            current_pages.append(page_idx)
            current_splits.append(split)

    # Save the last group
    if current_doc_type is not None:
        doc_name = f"{current_doc_type}_{doc_counter}"
        # Handle both object and dict formats
        if current_splits:
            first_split = current_splits[0]
            if hasattr(first_split, 'markdown'):
                # From API - split is an object
                combined_markdown = "\n\n".join([s.markdown for s in current_splits])
            elif isinstance(first_split, dict) and 'markdown' in first_split:
                # From cache - split is a dict
                combined_markdown = "\n\n".join([s['markdown'] for s in current_splits])
            else:
                combined_markdown = ""
        else:
            combined_markdown = ""

        split_documents[doc_name] = {
            "doc_type": current_doc_type,
            "pages": current_pages,
            "markdown": combined_markdown,
            "splits": current_splits
        }

    return split_documents


def draw_bounding_boxes_for_split(groundings, document_path, page_numbers, base_path="."):
    """
    Draw bounding boxes on specific pages of a document to visualize parsed chunks.

    Args:
        groundings: Dictionary of grounding objects with chunk locations
        document_path: Path to the original merged document
        page_numbers: List of page numbers to visualize (0-indexed)
        base_path: Directory to save annotated images
    """
    def create_annotated_image(image, groundings, page_num=0):
        annotated_img = image.copy()
        draw = ImageDraw.Draw(annotated_img)
        img_width, img_height = image.size
        groundings_found = 0

        for gid, grounding in groundings.items():
            if grounding.page != page_num:
                continue

            groundings_found += 1
            box = grounding.box

            left, top, right, bottom = box.left, box.top, box.right, box.bottom
            x1 = int(left * img_width)
            y1 = int(top * img_height)
            x2 = int(right * img_width)
            y2 = int(bottom * img_height)

            color = CHUNK_TYPE_COLORS.get(grounding.type, (128, 128, 128))
            draw.rectangle([x1, y1, x2, y2], outline=color, width=3)

            label = f"{grounding.type}:{gid}"
            label_y = max(0, y1 - 20)
            draw.rectangle([x1, label_y, x1 + len(label) * 8, y1], fill=color)
            draw.text((x1 + 2, label_y + 2), label, fill=(255, 255, 255))

        if groundings_found == 0:
            return None
        return annotated_img

    if document_path.suffix.lower() == '.pdf':
        pdf = pymupdf.open(document_path)

        for page_num in page_numbers:
            page = pdf[page_num]
            pix = page.get_pixmap(matrix=pymupdf.Matrix(2, 2))
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

            annotated_img = create_annotated_image(img, groundings, page_num)
            if annotated_img is not None:
                annotated_path = f"{base_path}/page_{page_num + 1}_annotated.png"
                annotated_img.save(annotated_path)

        pdf.close()

    return True


def create_cropped_chunk_images(parse_result, extraction_metadata, document_path, first_page, doc_name):
    """
    Create cropped images of individual chunks and full page with chunks outlined.

    Returns dict mapping field_name -> {"crop": Image, "outlined": Image}
    """
    pdf = pymupdf.open(document_path)
    page = pdf[first_page]
    pix = page.get_pixmap(matrix=pymupdf.Matrix(2, 2))
    full_page_img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    pdf.close()

    img_width, img_height = full_page_img.size
    field_images = {}

    for field_name, metadata in extraction_metadata.items():
        # Get the first chunk reference
        chunk_id = metadata['references'][0]

        if chunk_id not in parse_result.grounding:
            continue

        grounding = parse_result.grounding[chunk_id]

        # Only process if it's on the first page
        if grounding.page != first_page:
            continue

        box = grounding.box
        left, top, right, bottom = box.left, box.top, box.right, box.bottom

        # Convert normalized coordinates to pixels
        x1 = int(left * img_width)
        y1 = int(top * img_height)
        x2 = int(right * img_width)
        y2 = int(bottom * img_height)

        # Add padding for better visibility
        padding = 10
        x1_crop = max(0, x1 - padding)
        y1_crop = max(0, y1 - padding)
        x2_crop = min(img_width, x2 + padding)
        y2_crop = min(img_height, y2 + padding)

        # Create cropped image
        cropped = full_page_img.crop((x1_crop, y1_crop, x2_crop, y2_crop))

        # Create outlined version (full page with just this chunk highlighted)
        outlined = full_page_img.copy()
        draw = ImageDraw.Draw(outlined)
        color = (231, 76, 60)  # Red
        draw.rectangle([x1, y1, x2, y2], outline=color, width=5)

        # Add label
        label = field_name
        label_y = max(0, y1 - 25)
        draw.rectangle([x1, label_y, x1 + len(label) * 10, y1], fill=color)
        draw.text((x1 + 5, label_y + 5), label, fill=(255, 255, 255))

        field_images[field_name] = {
            "crop": cropped,
            "outlined": outlined
        }

    return field_images


def visualize_extractions_side_by_side(final_extractions, parse_result, merged_document):
    """
    Create side-by-side visualization showing cropped chunks and outlined full pages.

    Args:
        final_extractions: Dictionary containing extraction results and metadata
        parse_result: ParseResponse object with grounding data
        merged_document: Path to the merged PDF document
    """
    print("📊 Extracted Field Visualizations with Side-by-Side Comparison\n")

    for doc_name, extraction in final_extractions.items():
        print(f"\n{'='*80}")
        print(f"Document: {doc_name}")
        print(f"Type: {extraction['doc_type']}")
        print(f"{'='*80}\n")

        print("📋 Extracted Fields:")
        for field_name, field_value in extraction['extraction'].items():
            print(f"  • {field_name}: {field_value}")
        print()

        first_page = extraction['pages'][0]

        # Create cropped and outlined images for each field
        field_images = create_cropped_chunk_images(
            parse_result,
            extraction['extraction_metadata'],
            merged_document,
            first_page,
            doc_name
        )

        # Display each field with side-by-side comparison
        for field_name, images in field_images.items():
            html_parts = [f'<div style="margin-bottom: 30px;"><h3 style="color: #2c3e50;">Field: {field_name}</h3>']
            html_parts.append('<div style="display: flex; gap: 20px;">')

            # Left side: Cropped chunk image
            buffered = BytesIO()
            images["crop"].save(buffered, format="PNG")
            img_str = base64.b64encode(buffered.getvalue()).decode()

            html_parts.append(f'''
            <div style="flex: 1;">
                <h4 style="text-align: center; color: #e74c3c;">🔍 Cropped Chunk</h4>
                <img src="data:image/png;base64,{img_str}" style="width: 100%; border: 2px solid #e74c3c;">
                <p style="text-align: center; color: #555; font-size: 12px;">Extracted region close-up</p>
            </div>
            ''')

            # Right side: Full page with chunk outlined
            buffered = BytesIO()
            images["outlined"].save(buffered, format="PNG")
            img_str = base64.b64encode(buffered.getvalue()).decode()

            html_parts.append(f'''
            <div style="flex: 1;">
                <h4 style="text-align: center; color: #3498db;">📄 Context View</h4>
                <img src="data:image/png;base64,{img_str}" style="width: 100%; border: 2px solid #3498db;">
                <p style="text-align: center; color: #555; font-size: 12px;">Field location on full page</p>
            </div>
            ''')

            html_parts.append('</div></div>')
            display(HTML(''.join(html_parts)))

        print("\n🔍 Extraction Metadata (Source Chunks):")
        for field_name, metadata in extraction['extraction_metadata'].items():
            chunk_refs = ', '.join(metadata['references'])
            print(f"  • {field_name}: chunk IDs [{chunk_refs}]")
        print("\n")

    print("\n✅ Visualization complete!")


def print_classification_summary(page_classifications):
    """Print a formatted summary of page classifications."""
    print(f"\n=== Classification Summary ===")
    for classification in page_classifications:
        print(f"Page {classification['page'] + 1}: {classification['doc_type']}")


def print_split_summary(split_documents):
    """Print a formatted summary of split documents."""
    print("\n=== Document Split Summary ===")
    for doc_name, doc_info in split_documents.items():
        print(f"{doc_name}:")
        print(f"  Type: {doc_info['doc_type']}")
        print(f"  Pages: {min(doc_info['pages']) + 1}-{max(doc_info['pages']) + 1}")
        print(f"  Total pages: {len(doc_info['pages'])}")


def print_extraction_summary(document_extractions):
    """Print a formatted summary of all extractions."""
    print("\n=== All Extractions Complete ===")
    for doc_name, extraction in document_extractions.items():
        print(f"\n{doc_name}:")
        print(f"  Type: {extraction['doc_type']}")
        print(f"  Pages: {extraction['pages']}")
        print(f"  Data: {extraction['extraction']}")
