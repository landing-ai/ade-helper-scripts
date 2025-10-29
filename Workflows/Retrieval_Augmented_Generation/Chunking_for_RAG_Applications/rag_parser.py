#!/usr/bin/env python3
"""
RAG Document Parser - Batch parsing of documents using LandingAI ADE

This script processes documents concurrently using the LandingAI Agentic Document
Extraction (ADE) library with async/await patterns. It extracts text, markdown,
and chunks from PDFs and images, saving results to organized output folders.

Follows official LandingAI ADE documentation patterns:
https://docs.landing.ai/ade/ade-python

Usage:
    python rag_parser.py
    python rag_parser.py --input-dir custom_input --output-dir custom_output
    python rag_parser.py --max-concurrent 5 --rate-limit 10

Output structure:
    results_folder/
    ├── json/           # Full JSON responses from ADE
    ├── markdown/       # Extracted markdown text
    └── chunks/         # CSV with all document chunks and coordinates
"""

import argparse
import asyncio
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional

import pandas as pd
from aiolimiter import AsyncLimiter
from dotenv import load_dotenv
from landingai_ade import AsyncLandingAIADE
import landingai_ade

# Optional imports for chunk image saving
try:
    from PIL import Image
    import pymupdf
    CHUNK_IMAGES_AVAILABLE = True
except ImportError:
    CHUNK_IMAGES_AVAILABLE = False


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Parse documents using LandingAI ADE and save results to structured folders.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        "--input-dir",
        type=str,
        default="input_folder",
        help="Directory containing input documents (PDF, PNG, JPG, JPEG)"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="results_folder",
        help="Base directory for output files"
    )
    parser.add_argument(
        "--max-concurrent",
        type=int,
        default=10,
        help="Maximum number of concurrent requests"
    )
    parser.add_argument(
        "--rate-limit",
        type=int,
        default=30,
        help="Maximum requests per minute (to avoid rate limiting)"
    )
    parser.add_argument(
        "--csv-mode",
        type=str,
        choices=["combined", "separate"],
        default="combined",
        help="CSV output mode: 'combined' (one CSV for all files) or 'separate' (one CSV per input file)"
    )
    parser.add_argument(
        "--csv-name",
        type=str,
        default="all_chunks.csv",
        help="Name for the output CSV file (only used in 'combined' mode)"
    )
    parser.add_argument(
        "--save-chunk-images",
        action="store_true",
        help="Save individual chunk images as PNG files (requires Pillow and pymupdf)"
    )
    return parser.parse_args()


def setup_output_directories(base_dir: Path, save_chunk_images: bool = False) -> Dict[str, Path]:
    """
    Create output subdirectories if they don't exist.

    Args:
        base_dir: Base output directory path
        save_chunk_images: Whether to create chunk_images directory

    Returns:
        Dictionary mapping output types to their paths
    """
    output_dirs = {
        "json": base_dir / "json",
        "markdown": base_dir / "markdown",
        "chunks": base_dir / "chunks"
    }

    if save_chunk_images:
        output_dirs["chunk_images"] = base_dir / "chunk_images"

    for dir_path in output_dirs.values():
        dir_path.mkdir(parents=True, exist_ok=True)

    return output_dirs


def get_api_key() -> str:
    """
    Retrieve the Vision Agent API key from environment variable.

    Returns:
        str: The API key value

    Raises:
        ValueError: If the VISION_AGENT_API_KEY environment variable is not set
    """
    key = os.environ.get("VISION_AGENT_API_KEY")
    if not key:
        raise ValueError(
            "API key not found. Please set the VISION_AGENT_API_KEY environment variable."
        )
    return key


def collect_input_files(input_dir: Path) -> List[Path]:
    """
    Collect all supported document files from input directory.

    Args:
        input_dir: Directory to scan for documents

    Returns:
        List of file paths with supported extensions
    """
    supported_extensions = {".pdf", ".png", ".jpg", ".jpeg"}
    files = [
        p for p in input_dir.glob("*")
        if p.is_file() and p.suffix.lower() in supported_extensions
    ]
    return sorted(files)


def clean_chunk_text(text: str) -> str:
    """
    Clean chunk text by removing anchor tags and leading/trailing whitespace.

    Args:
        text: Raw chunk text with potential anchor tags

    Returns:
        Cleaned text without anchor tags and extra whitespace
    """
    # Remove anchor tags like <a id='...'></a>
    cleaned = re.sub(r"<a id='[^']*'>\s*</a>", "", text)
    # Strip leading and trailing whitespace
    cleaned = cleaned.strip()
    return cleaned


def extract_chunks_data(
    parse_result: Any,
    document_name: str,
    processed_at: str,
    ade_version: str,
    model_version: str,
    save_chunk_images: bool = False,
    output_base_dir: str = "results_folder"
) -> List[Dict[str, Any]]:
    """
    Extract chunk information from parse result.

    Args:
        parse_result: The ParseResponse object from ADE
        document_name: Name of the source document
        processed_at: ISO format timestamp when document was processed
        ade_version: Version of the landingai-ade library
        model_version: ADE model version used for parsing
        save_chunk_images: Whether chunk images are being saved
        output_base_dir: Base output directory name (default: "results_folder")

    Returns:
        List of dictionaries containing chunk data with sequence and image path info
    """
    chunks_data = []
    document_stem = Path(document_name).stem

    # Get list of chunks for sequence tracking
    chunks_list = parse_result.chunks if hasattr(parse_result, 'chunks') else []

    for idx, chunk in enumerate(chunks_list):
        # Extract grounding box coordinates
        grounding = chunk.grounding if hasattr(chunk, 'grounding') else None
        box = grounding.box if grounding and hasattr(grounding, 'box') else None
        page = grounding.page if grounding and hasattr(grounding, 'page') else None

        # Extract text from markdown
        chunk_content_raw = chunk.markdown if hasattr(chunk, 'markdown') else ''

        # Clean the text by removing anchor tags and whitespace
        chunk_content = clean_chunk_text(chunk_content_raw)

        # Get chunk identifiers
        chunk_id = chunk.id if hasattr(chunk, 'id') else None
        chunk_type = chunk.type if hasattr(chunk, 'type') else None

        # Build chunk image path (relative path including base directory)
        chunk_image_path = None
        if save_chunk_images and chunk_id and chunk_type and page is not None:
            chunk_image_path = f"{output_base_dir}/chunk_images/{document_stem}/page_{page}/{chunk_type}.{chunk_id}.png"

        # Get previous and next chunk IDs for context
        prev_chunk_id = chunks_list[idx - 1].id if idx > 0 and hasattr(chunks_list[idx - 1], 'id') else None
        next_chunk_id = chunks_list[idx + 1].id if idx < len(chunks_list) - 1 and hasattr(chunks_list[idx + 1], 'id') else None

        # Calculate text metrics
        chunk_text_length = len(chunk_content)
        chunk_word_count = len(chunk_content.split()) if chunk_content else 0

        chunks_data.append({
            'DOCUMENT_NAME': document_name,
            'chunk_id': chunk_id,
            'chunk_sequence_number': idx,
            'chunk_type': chunk_type,
            'chunk_content_raw': chunk_content_raw,
            'chunk_content': chunk_content,
            'chunk_text_length': chunk_text_length,
            'chunk_word_count': chunk_word_count,
            'page': page,
            'box_l': box.left if box and hasattr(box, 'left') else None,
            'box_t': box.top if box and hasattr(box, 'top') else None,
            'box_r': box.right if box and hasattr(box, 'right') else None,
            'box_b': box.bottom if box and hasattr(box, 'bottom') else None,
            'prev_chunk_id': prev_chunk_id,
            'next_chunk_id': next_chunk_id,
            'chunk_image_path': chunk_image_path,
            'processed_at': processed_at,
            'ade_version': ade_version,
            'model_version': model_version
        })

    return chunks_data


def save_chunks_as_images(
    parse_result: Any,
    document_path: Path,
    output_base_dir: Path
) -> Optional[Path]:
    """
    Save individual parsed chunks as PNG image files.

    Following official LandingAI ADE documentation:
    https://docs.landing.ai/ade/ade-python#save-parsed-chunks-as-images

    Args:
        parse_result: The ParseResponse object from ADE
        document_path: Path to the source document
        output_base_dir: Base directory for chunk images (chunk_images folder)

    Returns:
        Path to the created document directory, or None if failed
    """
    if not CHUNK_IMAGES_AVAILABLE:
        print(f"⚠️  Warning: Cannot save chunk images. Install: pip install Pillow pymupdf")
        return None

    try:
        document_name = document_path.stem
        document_dir = output_base_dir / document_name

        def save_page_chunks(image: Image.Image, chunks: List[Any], page_num: int) -> None:
            """Save all chunks for a specific page."""
            img_width, img_height = image.size
            page_dir = document_dir / f"page_{page_num}"
            page_dir.mkdir(parents=True, exist_ok=True)

            for chunk in chunks:
                if not hasattr(chunk, 'grounding') or chunk.grounding.page != page_num:
                    continue

                box = chunk.grounding.box
                x1 = int(box.left * img_width)
                y1 = int(box.top * img_height)
                x2 = int(box.right * img_width)
                y2 = int(box.bottom * img_height)

                # Crop and save chunk image
                chunk_img = image.crop((x1, y1, x2, y2))
                filename = f"{chunk.type}.{chunk.id}.png"
                output_path = page_dir / filename
                chunk_img.save(output_path)

        # Handle PDFs vs images differently
        if document_path.suffix.lower() == '.pdf':
            pdf = pymupdf.open(document_path)
            for page_num in range(len(pdf)):
                page = pdf[page_num]
                pix = page.get_pixmap(matrix=pymupdf.Matrix(2, 2))
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                save_page_chunks(img, parse_result.chunks, page_num)
            pdf.close()
        else:
            # Handle image files (PNG, JPG, JPEG)
            img = Image.open(document_path)
            if img.mode != "RGB":
                img = img.convert("RGB")
            save_page_chunks(img, parse_result.chunks, 0)

        return document_dir

    except Exception as e:
        print(f"⚠️  Warning: Failed to save chunk images for {document_path.name}: {e}")
        return None


async def process_document(
    file_path: Path,
    client: AsyncLandingAIADE,
    output_dirs: Dict[str, Path],
    ade_version: str,
    rate_limiter: AsyncLimiter,
    save_chunk_images: bool = False
) -> Optional[Dict[str, Any]]:
    """
    Process a single document asynchronously: parse, save JSON, save markdown, extract chunks.

    Args:
        file_path: Path to the document file
        client: Initialized async LandingAI ADE client
        output_dirs: Dictionary of output directory paths
        ade_version: Version of the landingai-ade library
        rate_limiter: AsyncLimiter for rate limiting requests
        save_chunk_images: Whether to save individual chunk images

    Returns:
        Dictionary with 'chunks_data' and 'file_path' if successful, None if failed
    """
    try:
        # Respect rate limit
        async with rate_limiter:
            # Capture processing timestamp
            processed_at = datetime.now(timezone.utc).isoformat()

            # Parse the document (async)
            parse_result = await client.parse(document=file_path)

            document_name = file_path.name
            base_filename = file_path.stem

            # Get model version from metadata
            model_version = getattr(parse_result.metadata, 'version', 'unknown') if hasattr(parse_result, 'metadata') else 'unknown'

            # Save full JSON response
            json_path = output_dirs["json"] / f"{base_filename}.json"
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(parse_result.model_dump(), f, indent=2, default=str)

            # Save markdown
            markdown_path = output_dirs["markdown"] / f"{base_filename}.md"
            with open(markdown_path, "w", encoding="utf-8") as f:
                f.write(parse_result.markdown)

            # Extract chunks data with additional metadata
            # Get base output directory name for image paths
            output_base_dir = output_dirs["chunks"].parent.name
            chunks_data = extract_chunks_data(
                parse_result,
                document_name,
                processed_at,
                ade_version,
                model_version,
                save_chunk_images,
                output_base_dir
            )

            # Optionally save chunk images
            if save_chunk_images and "chunk_images" in output_dirs:
                save_chunks_as_images(
                    parse_result,
                    file_path,
                    output_dirs["chunk_images"]
                )

            return {
                'chunks_data': chunks_data,
                'file_path': file_path,
                'success': True
            }

    except Exception as e:
        print(f"\n❌ Failed to process {file_path.name}: {e}")
        return {
            'chunks_data': None,
            'file_path': file_path,
            'success': False
        }


async def process_all_documents(
    file_paths: List[Path],
    client: AsyncLandingAIADE,
    output_dirs: Dict[str, Path],
    ade_version: str,
    rate_limiter: AsyncLimiter,
    csv_mode: str,
    save_chunk_images: bool = False
) -> tuple[List[Dict[str, Any]], int]:
    """
    Process all documents concurrently with progress tracking.

    Args:
        file_paths: List of file paths to process
        client: Initialized async LandingAI ADE client
        output_dirs: Dictionary of output directory paths
        ade_version: Version of the landingai-ade library
        rate_limiter: AsyncLimiter for rate limiting
        csv_mode: CSV output mode ('combined' or 'separate')
        save_chunk_images: Whether to save individual chunk images

    Returns:
        Tuple of (all_chunks_data, successful_count)
    """
    print(f"🚀 Starting async processing of {len(file_paths)} documents...\n")

    # Create tasks for all documents
    tasks = [
        process_document(path, client, output_dirs, ade_version, rate_limiter, save_chunk_images)
        for path in file_paths
    ]

    # Process all documents concurrently
    results = await asyncio.gather(*tasks)

    # Collect results
    all_chunks = []
    successful_count = 0

    for result in results:
        if result and result['success']:
            successful_count += 1
            chunks_data = result['chunks_data']
            file_path = result['file_path']

            if csv_mode == "separate" and chunks_data:
                # Save individual CSV for this document
                chunks_df = pd.DataFrame(chunks_data)
                csv_filename = f"{file_path.stem}_chunks.csv"
                csv_path = output_dirs["chunks"] / csv_filename
                chunks_df.to_csv(csv_path, index=False)
            elif csv_mode == "combined" and chunks_data:
                # Combined mode: accumulate all chunks
                all_chunks.extend(chunks_data)

            # Print progress
            print(f"✅ Processed: {file_path.name} ({len(chunks_data) if chunks_data else 0} chunks)")

    return all_chunks, successful_count


async def main_async(args: argparse.Namespace) -> None:
    """Main async execution function."""
    # Resolve paths
    script_dir = Path(__file__).parent
    input_dir = script_dir / args.input_dir
    output_base = script_dir / args.output_dir

    # Validate input directory
    if not input_dir.exists():
        print(f"❌ Error: Input directory not found: {input_dir}")
        return

    # Setup output directories
    output_dirs = setup_output_directories(output_base, args.save_chunk_images)
    print(f"📁 Input directory: {input_dir}")
    print(f"📁 Output directory: {output_base}")
    print(f"   ├── json/")
    print(f"   ├── markdown/")
    print(f"   ├── chunks/")
    if args.save_chunk_images:
        print(f"   └── chunk_images/")
    print()

    # Initialize async ADE client
    try:
        api_key = get_api_key()
        client = AsyncLandingAIADE(apikey=api_key)
        ade_version = landingai_ade.__version__
        print("✅ LandingAI async ADE client initialized")
        print(f"   Library version: {ade_version}")
    except ValueError as e:
        print(f"❌ Error: {e}")
        return

    # Collect input files
    file_paths = collect_input_files(input_dir)
    if not file_paths:
        print(f"⚠️  No supported documents found in {input_dir}")
        print("   Supported formats: .pdf, .png, .jpg, .jpeg")
        return

    print(f"📄 Found {len(file_paths)} documents to process")
    print(f"⚙️  Max concurrent requests: {args.max_concurrent}")
    print(f"⏱️  Rate limit: {args.rate_limit} requests/minute")
    print(f"📊 CSV mode: {args.csv_mode}")
    if args.csv_mode == "combined":
        print(f"📁 Output CSV: {args.csv_name}")
    if args.save_chunk_images:
        if CHUNK_IMAGES_AVAILABLE:
            print(f"🖼️  Chunk images: Enabled")
        else:
            print(f"⚠️  Chunk images: Disabled (install Pillow and pymupdf)")
    print()

    # Create rate limiter (requests per minute)
    rate_limiter = AsyncLimiter(args.rate_limit, 60)

    # Process all documents concurrently
    all_chunks, successful_count = await process_all_documents(
        file_paths,
        client,
        output_dirs,
        ade_version,
        rate_limiter,
        args.csv_mode,
        args.save_chunk_images
    )

    # For combined mode, save single CSV with all chunks
    if args.csv_mode == "combined" and all_chunks:
        chunks_df = pd.DataFrame(all_chunks)
        chunks_csv_path = output_dirs["chunks"] / args.csv_name
        chunks_df.to_csv(chunks_csv_path, index=False)
        print(f"\n💾 Saved combined chunks CSV: {chunks_csv_path}")
        print(f"   Total chunks: {len(chunks_df)}")
    elif args.csv_mode == "separate":
        print(f"\n💾 Saved {successful_count} separate CSV files to: {output_dirs['chunks']}")
        print(f"   Format: <filename>_chunks.csv")

    # Print summary
    print(f"\n{'='*60}")
    print(f"✅ Processing complete!")
    print(f"   Successful: {successful_count}/{len(file_paths)} documents")
    print(f"   Failed: {len(file_paths) - successful_count}/{len(file_paths)} documents")
    print(f"{'='*60}")


def main():
    """Main entry point."""
    # Load environment variables from .env file
    load_dotenv()

    # Parse command-line arguments
    args = parse_arguments()

    # Run async main function
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
