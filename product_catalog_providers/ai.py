"""AI-powered product catalog provider using Gemini for intelligent matching."""

import os
import json
import google.generativeai as genai
from typing import List, Dict, Any, Optional
from .base import ProductCatalogProvider
from schemas import Product
from db_config import get_db_connection


class AIProductCatalog(ProductCatalogProvider):
    """
    AI-powered product catalog that uses Gemini to intelligently match
    products to briefs, simulating a RAG-like system.
    
    This provider:
    1. Fetches all available products from the database
    2. Uses Gemini to analyze the brief and rank/filter products
    3. Returns the most relevant products based on the AI's analysis
    
    Configuration:
        model: Gemini model to use (default: "gemini-1.5-flash")
        max_products: Maximum number of products to return (default: 5)
        temperature: Model temperature for creativity (default: 0.3)
        include_reasoning: Include AI reasoning in response (default: false)
    """
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.model_name = config.get('model', 'gemini-1.5-flash')
        self.max_products = config.get('max_products', 5)
        self.temperature = config.get('temperature', 0.3)
        self.include_reasoning = config.get('include_reasoning', False)
        
        # Initialize Gemini
        api_key = os.environ.get('GEMINI_API_KEY')
        if not api_key:
            raise ValueError("GEMINI_API_KEY environment variable is required for AI product catalog")
        
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(self.model_name)
    
    async def get_products(
        self,
        brief: str,
        tenant_id: str,
        principal_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> List[Product]:
        """
        Use AI to match products to the brief.
        """
        # First, get all available products from the database
        all_products = await self._get_all_products(tenant_id)
        
        if not all_products:
            return []
        
        # Prepare the prompt for Gemini
        prompt = self._build_prompt(brief, all_products, context)
        
        # Get AI recommendation
        response = self.model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=self.temperature,
                response_mime_type="application/json",
            )
        )
        
        # Parse the AI response
        try:
            ai_result = json.loads(response.text)
            recommended_ids = ai_result.get('recommended_product_ids', [])
            
            # Filter and reorder products based on AI recommendation
            product_map = {p.product_id: p for p in all_products}
            recommended_products = []
            
            for product_id in recommended_ids[:self.max_products]:
                if product_id in product_map:
                    product = product_map[product_id]
                    # Optionally add AI reasoning as metadata
                    if self.include_reasoning and product_id in ai_result.get('reasoning', {}):
                        # Note: We'd need to extend Product schema to include metadata
                        pass
                    recommended_products.append(product)
            
            return recommended_products
            
        except json.JSONDecodeError:
            # Fallback to returning all products if AI fails
            return all_products[:self.max_products]
    
    async def _get_all_products(self, tenant_id: str) -> List[Product]:
        """Fetch all products from the database."""
        conn = get_db_connection()
        cursor = conn.execute(
            "SELECT * FROM products WHERE tenant_id = ?",
            (tenant_id,)
        )
        rows = cursor.fetchall()
        conn.close()
        
        products = []
        for row in rows:
            # Convert Row object to dictionary
            product_data = {column: row[column] for column in row.keys()}
            product_data.pop('tenant_id', None)
            product_data['formats'] = json.loads(product_data['formats'])
            product_data['targeting_template'] = json.loads(product_data['targeting_template'])
            if product_data.get('price_guidance'):
                product_data['price_guidance'] = json.loads(product_data['price_guidance'])
            products.append(Product(**product_data))
        
        return products
    
    def _build_prompt(self, brief: str, products: List[Product], context: Optional[Dict[str, Any]]) -> str:
        """Build the prompt for Gemini."""
        products_json = []
        for p in products:
            products_json.append({
                'product_id': p.product_id,
                'name': p.name,
                'description': p.description,
                'formats': [f.name for f in p.formats],
                'targeting': p.targeting_template.model_dump(exclude_none=True),
                'delivery_type': p.delivery_type,
                'is_fixed_price': p.is_fixed_price,
                'cpm': p.cpm,
                'price_guidance': p.price_guidance.model_dump() if p.price_guidance else None
            })
        
        prompt = f"""You are an intelligent product catalog system for a digital advertising platform.

Given an advertising brief, analyze and recommend the most suitable products.

BRIEF:
{brief}

AVAILABLE PRODUCTS:
{json.dumps(products_json, indent=2)}

{f"ADDITIONAL CONTEXT: {json.dumps(context)}" if context else ""}

Analyze the brief and recommend products that best match the advertiser's needs.
Consider:
- Target audience alignment
- Budget constraints (if mentioned)
- Campaign objectives
- Geographic requirements
- Format preferences
- Delivery requirements (guaranteed vs non-guaranteed)

Return a JSON object with:
{{
  "recommended_product_ids": ["product_id1", "product_id2", ...],
  "reasoning": {{
    "product_id1": "Brief explanation why this product matches",
    "product_id2": "Brief explanation why this product matches"
  }}
}}

Order products by relevance (most relevant first).
"""
        return prompt