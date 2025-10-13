
from pathlib import Path
from typing import Tuple, Type, Any
import json
import io
import os

# Method 1: Environment variable
def get_api_key() -> str:
    """
    Retrieve the Vision Agent API key from an environment variable.

    This function reads the API key from the VISION_AGENT_API_KEY environment
    variable. Use this method when you prefer to set environment variables
    directly in your shell or deployment environment.

    Returns:
        str: The API key value from the environment variable.

    Raises:
        ValueError: If the VISION_AGENT_API_KEY environment variable is not set.

    Example:
        >>> import os
        >>> os.environ["VISION_AGENT_API_KEY"] = "your-api-key-here"
        >>> api_key = get_api_key()
    """
    key = os.environ.get("VISION_AGENT_API_KEY")
    if not key:
        raise ValueError(
            "API key not found. Please set the VISION_AGENT_API_KEY environment variable."
        )
    return key

# Method 2: From .env file with Pydantic settings
def get_api_key_env() -> str:
    """
    Retrieve the Vision Agent API key from a .env file using Pydantic settings.

    This function reads the API key from a .env file in the current directory
    using Pydantic's BaseSettings. The .env file should contain a line like:
    VISION_AGENT_API_KEY=your-api-key-here

    Use this method when you want to manage configuration through .env files,
    which is useful for local development and keeping secrets out of code.

    Returns:
        str: The API key value from the .env file.

    Raises:
        ValidationError: If the .env file is missing or doesn't contain
                        the required VISION_AGENT_API_KEY field.

    Example:
        >>> # Create a .env file with: VISION_AGENT_API_KEY=your-api-key-here
        >>> api_key = get_api_key_env()

    Note:
        Requires the pydantic-settings package to be installed:
        pip install pydantic-settings
    """
    from pydantic_settings import BaseSettings

    class Settings(BaseSettings):
        vision_agent_api_key: str

        class Config:
            env_file = ".env"

    settings = Settings()
    return settings.vision_agent_api_key

def save_parse_results(results: Any, output_dir: str = "./ade_results") -> None:
    """
    Save ADE parse results to disk.

    This function serializes a parse result object (such as the output from
    LandingAI's Agentic Document Extraction) into a JSON file and saves it to 
    the specified directory. The filename is derived from `results.metadata.filename`
    when available.

    Args:
        results: The ADE parse results object returned by the parse() call.
                 Must have `metadata.filename` and `model_dump()` attributes.
        output_dir (str, optional): Directory where the JSON file will be saved.
                                   Defaults to "./ade_results".

    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Use the filename embedded in the metadata
    parse_filename = getattr(getattr(results, "metadata", {}), "filename", "unknown_filename")
    base_filename = f"parse_{Path(parse_filename).stem}"

    # Dump results as JSON
    if hasattr(results, "model_dump"):
        results_json = json.dumps(results.model_dump(), indent=2, default=str)
    else:
        # fallback if it's a plain dict-like object
        results_json = json.dumps(results, indent=2, default=str)

    json_path = output_path / f"{base_filename}.json"

    with open(json_path, "w", encoding="utf-8") as f:
        f.write(results_json)

    print(f"Parse results saved to: {json_path}")

def parse_and_save(document_path: str | Path, client: Any, output_dir: str = "./ade_results") -> Any:
    """
    Parse a document using LandingAI ADE and save the full result as JSON.

    This function takes a document filepath, sends it to the ADE parse API,
    and saves the complete parse result to disk. The JSON filename will match
    the original document filename.

    Args:
        document_path (str or Path): Path to the document file to parse.
                                     Supported formats: .pdf, .png, .jpg, .jpeg
        client (LandingAIADE): An initialized LandingAI ADE client instance.
        output_dir (str, optional): Directory where the JSON file will be saved.
                                   Defaults to "./ade_results".

    Returns:
        ParseResponse: The full parse result object from the ADE API.

    Raises:
        FileNotFoundError: If the document file does not exist.
        Exception: Any exceptions from the parse operation are propagated.

    Example:
        >>> from landingai_ade import LandingAIADE
        >>> from utilities import parse_and_save
        >>>
        >>> client = LandingAIADE(apikey="your-api-key")
        >>> result = parse_and_save("invoice.pdf", client, output_dir="./results")
        >>> print(f"Parsed {len(result.chunks)} chunks")
    """
    # Convert to Path object
    doc_path = Path(document_path)

    # Validate file exists
    if not doc_path.exists():
        raise FileNotFoundError(f"Document not found: {document_path}")

    # Parse the document
    parse_result = client.parse(document=doc_path)

    # Save the results using existing function
    save_parse_results(parse_result, output_dir=output_dir)

    return parse_result

def parse_extract_save(document_path: str | Path, client: Any, schema_class: Type[Any], output_dir: str = "./ade_results") -> Tuple[Any, Any]:
    """
    Parse a document, extract structured data using a Pydantic schema, and save both results as JSON.

    This function performs a complete ADE workflow:
    1. Parses the document to extract markdown and chunks
    2. Saves the parse result as parse_{filename}.json
    3. Extracts structured data using the provided Pydantic schema
    4. Saves the extraction result as extract_{filename}.json

    Args:
        document_path (str or Path): Path to the document file to parse.
                                     Supported formats: .pdf, .png, .jpg, .jpeg
        client (LandingAIADE): An initialized LandingAI ADE client instance.
        schema_class (BaseModel): A Pydantic model class defining the extraction schema.
        output_dir (str, optional): Directory where JSON files will be saved.
                                   Defaults to "./ade_results".

    Returns:
        tuple: (parse_result, extract_result) - Both result objects from the API.

    Raises:
        FileNotFoundError: If the document file does not exist.
        Exception: Any exceptions from parse or extract operations are propagated.

    Example:
        >>> from landingai_ade import LandingAIADE
        >>> from utilities import parse_extract_save
        >>> from invoice_schema import InvoiceExtractionSchema
        >>>
        >>> client = LandingAIADE(apikey="your-api-key")
        >>> parse_result, extract_result = parse_extract_save(
        ...     "my_doc.pdf",
        ...     client,
        ...     InvoiceExtractionSchema,
        ...     output_dir="./results"
        ... )
        >>> # Results saved as: parse_my_doc.json and extract_my_doc.json
        >>> print(f"Extracted: {extract_result.extraction}")
    """
    from landingai_ade.lib import pydantic_to_json_schema

    # Convert to Path object
    doc_path = Path(document_path)

    # Validate file exists
    if not doc_path.exists():
        raise FileNotFoundError(f"Document not found: {document_path}")

    # Create output directory
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Extract base filename without extension
    base_filename = doc_path.stem

    # STEP 1: Parse the document
    parse_result = client.parse(document=doc_path)

    # Save parse result
    parse_json_path = output_path / f"parse_{base_filename}.json"
    if hasattr(parse_result, "model_dump"):
        parse_json = json.dumps(parse_result.model_dump(), indent=2, default=str)
    else:
        parse_json = json.dumps(parse_result, indent=2, default=str)

    with open(parse_json_path, "w", encoding="utf-8") as f:
        f.write(parse_json)
    print(f"Parse results saved to: {parse_json_path}")

    # STEP 2: Extract structured data using the schema
    # Convert Pydantic schema to JSON schema
    json_schema = pydantic_to_json_schema(schema_class)

    # Call extract with markdown from parse result
    extract_result = client.extract(
        schema=json_schema,
        markdown=io.BytesIO(parse_result.markdown.encode("utf-8"))
    )

    # Save extract result
    extract_json_path = output_path / f"extract_{base_filename}.json"
    if hasattr(extract_result, "model_dump"):
        extract_json = json.dumps(extract_result.model_dump(), indent=2, default=str)
    else:
        extract_json = json.dumps(extract_result, indent=2, default=str)

    with open(extract_json_path, "w", encoding="utf-8") as f:
        f.write(extract_json)
    print(f"Extract results saved to: {extract_json_path}")

    return parse_result, extract_result

