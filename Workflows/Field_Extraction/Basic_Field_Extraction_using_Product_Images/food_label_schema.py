"""
Food Label Schema - Pydantic model for extracting product information from food labels

This schema defines the structure for extracting:
- Product identification (name, brand, type, flavor)
- Weight and serving information
- Certifications and claims (organic, non-GMO, grass-fed, etc.)
"""

from pydantic import BaseModel, Field


class Product(BaseModel):
    """Schema for extracting structured product information from food labels."""

    # Product Identification
    product_name: str = Field(
        description="The full name of the product excluding the brand name as it appears on the packaging."
    )
    brand: str = Field(
        description="The brand or company name."
    )
    product_type: str = Field(
        description="General category of the product (e.g., 'yogurt', 'hot dogs', 'supplement', 'beef sticks')."
    )
    flavor: str = Field(
        description="The flavor of the product if applicable, such as 'creamy vanilla' or 'original'. Return empty field if not found or not applicable."
    )

    # Weight and Serving Information
    net_weight_oz: float = Field(
        description="The net weight of the product in ounces, as labeled (e.g., 'NET WT 8 OZ'). Return empty field if not found."
    )
    net_weight_g: float = Field(
        description="The net weight of the product in grams, often shown in parentheses next to ounces (e.g., '330 g'). Return empty field if not found."
    )
    servings_per_container: int = Field(
        description="The total number of servings per container, usually listed in the Nutrition Facts panel. Return empty field if not found."
    )
    serving_size: str = Field(
        description="The serving size as printed on the package, such as '1 stick (45g)' or '1 scoop (10g)'. Return empty field if not found."
    )

    # Animal Welfare and Sourcing Claims
    is_grass_fed: bool = Field(
        description="True if the label mentions 'Grass-Fed' or 'Grass Fed'."
    )
    is_pasture_raised: bool = Field(
        description="True if the label claims the animals were 'Pasture Raised' or 'Pasture-Raised'."
    )
    is_certified_humane: bool = Field(
        description="True if the label features the 'Certified Humane' logo or wording."
    )
    is_animal_welfare_certified: bool = Field(
        description="True if the product is 'Animal Welfare Certified' or meets GAP (Global Animal Partnership) standards."
    )
    no_antibiotics: bool = Field(
        description="True if the label claims 'No Antibiotics' or 'Raised without antibiotics' or similar language."
    )
    no_hormones: bool = Field(
        description="True if the product claims 'No Hormones' or 'No added hormones' or 'Not treated with rBST' or similar language."
    )
    no_animal_byproducts: bool = Field(
        description="True if it states animals were not fed animal by-products."
    )

    # Organic and Environmental Certifications
    is_organic: bool = Field(
        description="True if the label mentions 'Organic' or includes the 'USDA Organic' seal."
    )
    is_regenerative: bool = Field(
        description="True if the label includes terms like 'Regeneratively Sourced' or 'Certified Regenerative' or 'Regenerative Organic'."
    )
    is_non_gmo: bool = Field(
        description="True if the product is labeled 'Non-GMO' or has the 'Non-GMO Project Verified' seal."
    )

    # Dietary and Lifestyle Claims
    is_keto_friendly: bool = Field(
        description="True if the label mentions 'Keto' or 'Ketogenic' diets or similar."
    )
    is_paleo_friendly: bool = Field(
        description="True if the label mentions 'Paleo' or 'Paleolithic' diets or similar."
    )
    is_whole30_approved: bool = Field(
        description="True if the product is labeled as 'Whole30 Approved'."
    )

    # Allergen and Dietary Restriction Claims
    is_gluten_free: bool = Field(
        description="True if the product is labeled 'Gluten-Free' or certified gluten-free."
    )
    is_dairy_free: bool = Field(
        description="True if the product states 'Dairy-Free' or 'No Dairy'."
    )
    is_lactose_free: bool = Field(
        description="True if the product explicitly states 'Lactose-Free' or 'No Lactose'."
    )
    has_no_added_sugar: bool = Field(
        description="True if the packaging says 'No Added Sugar' or 'Zero Sugar' or 'Unsweetened' or similar."
    )

    # Religious and Cultural Certifications
    is_kosher: bool = Field(
        description="True if the label mentions 'Kosher' or includes a kosher certification symbol."
    )

    # Government Inspection
    usda_inspected: bool = Field(
        description="True if the USDA inspection seal or 'USDA Inspected' text is present on the packaging."
    )
