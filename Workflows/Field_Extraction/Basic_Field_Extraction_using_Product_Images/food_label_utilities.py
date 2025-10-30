"""
Food Label Utilities - Domain-specific helper functions for food label extraction

This module provides utilities for converting extraction results to pandas DataFrames.
"""

import pandas as pd
from typing import List, Tuple, Any


def create_summary_dataframe(extraction_results: List[Tuple[Any, Any, str]]) -> pd.DataFrame:
    """
    Convert a list of extraction results to a pandas DataFrame.

    Args:
        extraction_results: List of tuples containing (parse_result, extract_result, document_name)

    Returns:
        DataFrame with extracted product fields and metadata
    """
    records = []

    for parse_result, extract_result, doc_name in extraction_results:
        # Access the extraction data (returns dictionaries in new library)
        product = extract_result.extraction
        meta = extract_result.extraction_metadata

        # Build a dictionary with all product fields
        product_dict = {
            "document_name": doc_name,
            "product_name": product['product_name'],
            "product_name_chunks": str(meta['product_name'].get('references', [])),
            "brand": product['brand'],
            "brand_chunks": str(meta['brand'].get('references', [])),
            "net_weight_oz": product['net_weight_oz'],
            "net_weight_oz_chunks": str(meta['net_weight_oz'].get('references', [])),
            "net_weight_g": product['net_weight_g'],
            "servings_per_container": product['servings_per_container'],
            "serving_size": product['serving_size'],
            "product_type": product['product_type'],
            "flavor": product['flavor'],
            "is_grass_fed": product['is_grass_fed'],
            "is_organic": product['is_organic'],
            "is_keto_friendly": product['is_keto_friendly'],
            "is_paleo_friendly": product['is_paleo_friendly'],
            "is_kosher": product['is_kosher'],
            "is_regenerative": product['is_regenerative'],
            "is_certified_humane": product['is_certified_humane'],
            "is_animal_welfare_certified": product['is_animal_welfare_certified'],
            "is_pasture_raised": product['is_pasture_raised'],
            "is_non_gmo": product['is_non_gmo'],
            "is_gluten_free": product['is_gluten_free'],
            "is_dairy_free": product['is_dairy_free'],
            "is_lactose_free": product['is_lactose_free'],
            "is_whole30_approved": product['is_whole30_approved'],
            "has_no_added_sugar": product['has_no_added_sugar'],
            "no_antibiotics": product['no_antibiotics'],
            "no_hormones": product['no_hormones'],
            "no_animal_byproducts": product['no_animal_byproducts'],
            "usda_inspected": product['usda_inspected'],
            "usda_inspected_chunks": str(meta['usda_inspected'].get('references', [])),
        }

        records.append(product_dict)

    # Create DataFrame
    df = pd.DataFrame(records)
    return df
