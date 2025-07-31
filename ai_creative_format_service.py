#!/usr/bin/env python3
"""AI-driven creative format discovery service.

This service discovers and analyzes creative format specifications from:
1. URLs provided by users (publisher spec pages)
2. Standard formats from adcontextprotocol.org
3. Natural language descriptions
"""

import json
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
import aiohttp
from bs4 import BeautifulSoup
import google.generativeai as genai
import os
from urllib.parse import urlparse
import re

from db_config import get_db_connection

logger = logging.getLogger(__name__)

@dataclass
class FormatSpecification:
    """Creative format specification details."""
    format_id: str
    name: str
    type: str  # display, video, audio, native
    description: str
    extends: Optional[str] = None  # Reference to foundational format
    width: Optional[int] = None
    height: Optional[int] = None
    duration_seconds: Optional[int] = None
    max_file_size_kb: Optional[int] = None
    specs: Dict[str, Any] = None
    source_url: Optional[str] = None

class AICreativeFormatService:
    """Service that uses AI to discover and analyze creative formats."""
    
    STANDARD_FORMATS_URL = "https://adcontextprotocol.org/formats.json"
    
    def __init__(self):
        # Initialize Gemini
        api_key = os.environ.get('GEMINI_API_KEY')
        if not api_key:
            raise ValueError("GEMINI_API_KEY environment variable is required")
        
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-2.0-flash')
        
        # Initialize foundational formats manager if available
        try:
            from foundational_formats import FoundationalFormatsManager
            self.formats_manager = FoundationalFormatsManager()
        except ImportError:
            logger.info("Foundational formats not available")
            self.formats_manager = None
        
    async def fetch_standard_formats(self) -> List[FormatSpecification]:
        """Fetch standard formats from adcontextprotocol.org."""
        formats = []
        
        try:
            async with aiohttp.ClientSession() as session:
                # First try the JSON endpoint
                try:
                    async with session.get(self.STANDARD_FORMATS_URL) as response:
                        if response.status == 200:
                            data = await response.json()
                            for fmt in data.get('formats', []):
                                formats.append(FormatSpecification(
                                    format_id=fmt['format_id'],
                                    name=fmt['name'],
                                    type=fmt['type'],
                                    description=fmt.get('description', ''),
                                    width=fmt.get('width'),
                                    height=fmt.get('height'),
                                    duration_seconds=fmt.get('duration_seconds'),
                                    max_file_size_kb=fmt.get('max_file_size_kb'),
                                    specs=fmt.get('specs', {}),
                                    source_url=self.STANDARD_FORMATS_URL
                                ))
                except:
                    # Fallback: scrape the HTML page
                    base_url = "https://adcontextprotocol.org"
                    async with session.get(f"{base_url}/creative-formats") as response:
                        if response.status == 200:
                            html = await response.text()
                            formats.extend(await self._parse_standard_formats_html(html, base_url))
                            
        except Exception as e:
            logger.error(f"Error fetching standard formats: {e}")
            # Return some default standard formats as fallback
            formats = self._get_default_standard_formats()
            
        return formats
    
    def _get_default_standard_formats(self) -> List[FormatSpecification]:
        """Return default standard formats as fallback."""
        return [
            FormatSpecification(
                format_id="display_300x250",
                name="Medium Rectangle",
                type="display",
                description="IAB standard medium rectangle banner",
                width=300,
                height=250,
                max_file_size_kb=200,
                specs={"file_types": ["jpg", "png", "gif", "html5"], "animation": "max 30s"}
            ),
            FormatSpecification(
                format_id="display_728x90",
                name="Leaderboard",
                type="display",
                description="IAB standard leaderboard banner",
                width=728,
                height=90,
                max_file_size_kb=200,
                specs={"file_types": ["jpg", "png", "gif", "html5"], "animation": "max 30s"}
            ),
            FormatSpecification(
                format_id="display_300x600",
                name="Half Page",
                type="display",
                description="IAB standard half page banner",
                width=300,
                height=600,
                max_file_size_kb=300,
                specs={"file_types": ["jpg", "png", "gif", "html5"], "animation": "max 30s"}
            ),
            FormatSpecification(
                format_id="video_instream",
                name="In-Stream Video",
                type="video",
                description="Standard in-stream video ad",
                duration_seconds=30,
                max_file_size_kb=10240,
                specs={"codecs": ["h264", "vp9"], "bitrate": "max 2500kbps", "formats": ["mp4", "webm"]}
            )
        ]
    
    async def discover_formats_from_html(self, html: str, source_url: str = "") -> List[FormatSpecification]:
        """Discover creative format specifications from HTML content."""
        formats = []
        
        try:
            # Extract relevant content from HTML to reduce prompt size
            soup = BeautifulSoup(html, 'html.parser')
            
            # Remove script and style elements
            for script in soup(["script", "style"]):
                script.decompose()
            
            # Extract text content, focusing on relevant sections
            relevant_text = ""
            
            # Look for sections that might contain format specifications
            for tag in soup.find_all(['table', 'div', 'section'], limit=20):
                text = tag.get_text()
                # Only include content that seems relevant to ad formats
                if any(keyword in text.lower() for keyword in 
                       ['format', 'size', 'dimension', 'spec', 'ad', 'banner', 'video', 'creative', 'width', 'height']):
                    relevant_text += text[:500] + "\n"
            
            # Fallback to first part of body text if no relevant sections found
            if not relevant_text.strip():
                body = soup.find('body')
                if body:
                    relevant_text = body.get_text()[:3000]
                else:
                    relevant_text = soup.get_text()[:3000]
            
            # Limit to 3000 chars to avoid token limits
            content_for_ai = relevant_text[:3000]
                    
            # Use AI to extract format information
            foundational_info = ""
            if self.formats_manager:
                foundational_info = """
            For each format, also determine if it extends one of these foundational formats:
            - foundation_immersive_canvas: Premium responsive format for full viewport experiences
            - foundation_product_showcase_carousel: Interactive display with 3-10 products/images
            - foundation_expandable_display: Banner with expandable canvas
            - foundation_scroll_triggered_experience: Mobile-first scroll reveal format
            - foundation_universal_video: Standard video specifications
            
            If the format extends a foundational format, include: "extends": "foundation_format_id"
            """
            
            prompt = f"""
            Analyze this content from a creative specification page and extract all creative format specifications.
            Look for:
            - Ad format names and types (display, video, native, audio)
            - Dimensions (width x height) for display ads
            - Duration limits for video/audio
            - File size limits
            - Accepted file formats (jpg, png, gif, mp4, etc.)
            
            URL: {source_url}
            Content:
            {content_for_ai}
            {foundational_info}
            Return a JSON array of format objects with these fields:
            - name: format name (required)
            - type: "display", "video", "audio", or "native" (required)
            - description: brief description
            - extends: foundational format ID if applicable (optional)
            - width: pixel width (for display formats)
            - height: pixel height (for display formats)
            - duration_seconds: max duration in seconds (for video/audio)
            - max_file_size_kb: max file size in KB
            - specs: object with additional specifications
            
            Return ONLY valid JSON array, no explanation or markdown.
            """
            
            try:
                response = self.model.generate_content(prompt)
                
                # Check if we got a valid response
                if not response or not hasattr(response, 'text') or not response.text:
                    logger.warning(f"Empty response from Gemini for HTML content")
                    raise ValueError("Empty response from AI model")
                
                response_text = response.text.strip()
                
                # Debug logging to see what AI returned
                logger.info(f"AI response for HTML content:")
                logger.info(f"Raw response text: {response_text}")
                
                # Remove markdown code blocks if present
                if response_text.startswith('```json'):
                    response_text = response_text.replace('```json', '').replace('```', '')
                elif response_text.startswith('```'):
                    response_text = response_text.replace('```', '')
                
                response_text = response_text.strip()
                
                if not response_text:
                    logger.warning(f"Empty response text after cleaning for HTML content")
                    raise ValueError("Empty response text after cleaning")
                
                formats_data = json.loads(response_text)
                
                if not isinstance(formats_data, list):
                    logger.warning(f"Expected list but got {type(formats_data)} for HTML content")
                    raise ValueError("Response is not a list")
                
                for fmt in formats_data:
                    if not isinstance(fmt, dict) or not fmt.get('name') or not fmt.get('type'):
                        logger.warning(f"Skipping invalid format entry: {fmt}")
                        continue
                        
                    # Generate format ID
                    if fmt.get('width') and fmt.get('height'):
                        format_id = f"{fmt['type']}_{fmt['width']}x{fmt['height']}"
                    elif fmt.get('duration_seconds'):
                        format_id = f"{fmt['type']}_{fmt['duration_seconds']}s"
                    else:
                        format_id = f"{fmt['type']}_{fmt['name'].lower().replace(' ', '_')}"
                    
                    # If no extends field from AI, try to suggest one
                    extends = fmt.get('extends')
                    if not extends and self.formats_manager:
                        # Create specs dict for suggestion
                        suggest_specs = {
                            'type': fmt['type'],
                            'name': fmt['name']
                        }
                        if 'carousel' in fmt['name'].lower() or 'slideshow' in fmt['name'].lower():
                            suggest_specs['carousel'] = True
                        if 'expandable' in fmt['name'].lower():
                            suggest_specs['expandable'] = True
                        if 'scroll' in fmt['name'].lower():
                            suggest_specs['scroll'] = True
                        if 'edge' in fmt['name'].lower() or 'immersive' in fmt['name'].lower():
                            suggest_specs['responsive'] = True
                            
                        extends = self.formats_manager.suggest_base_format(suggest_specs)
                    
                    formats.append(FormatSpecification(
                        format_id=format_id,
                        name=fmt['name'],
                        type=fmt['type'],
                        description=fmt.get('description', ''),
                        extends=extends,
                        width=fmt.get('width'),
                        height=fmt.get('height'),
                        duration_seconds=fmt.get('duration_seconds'),
                        max_file_size_kb=fmt.get('max_file_size_kb'),
                        specs=fmt.get('specs', {}),
                        source_url=source_url
                    ))
                    
            except (json.JSONDecodeError, ValueError) as e:
                logger.error(f"Failed to parse AI response for HTML content: {e}")
                # Try to extract basic information manually
                formats.extend(self._extract_formats_manually(html, source_url))
            except Exception as e:
                logger.error(f"AI model error for HTML content: {e}")
                # Try to extract basic information manually
                formats.extend(self._extract_formats_manually(html, source_url))
                
        except Exception as e:
            logger.error(f"Error discovering formats from HTML: {e}")
        
        return formats
    
    async def discover_format_from_url(self, url: str) -> List[FormatSpecification]:
        """Discover creative format specifications from a URL."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    html = await response.text()
            
            return await self.discover_formats_from_html(html, url)
                
        except Exception as e:
            logger.error(f"Error fetching URL {url}: {e}")
        
        return []
    
    def _extract_formats_manually(self, html: str, url: str) -> List[FormatSpecification]:
        """Manually extract format information as fallback."""
        formats = []
        soup = BeautifulSoup(html, 'html.parser')
        
        # Look for common patterns
        # Pattern 1: Tables with format specifications
        tables = soup.find_all('table')
        for table in tables:
            # Check if table contains format info
            headers = [th.text.lower() for th in table.find_all('th')]
            if any(word in ' '.join(headers) for word in ['size', 'dimension', 'format', 'spec']):
                for row in table.find_all('tr')[1:]:  # Skip header
                    cells = row.find_all(['td', 'th'])
                    if len(cells) >= 2:
                        # Try to extract format info
                        text = ' '.join(cell.text for cell in cells)
                        # Look for dimensions
                        dim_match = re.search(r'(\d{2,4})\s*x\s*(\d{2,4})', text)
                        if dim_match:
                            width, height = int(dim_match.group(1)), int(dim_match.group(2))
                            name = cells[0].text.strip() if cells[0].text else f"{width}x{height}"
                            formats.append(FormatSpecification(
                                format_id=f"display_{width}x{height}",
                                name=name,
                                type="display",
                                description=f"Display ad {width}x{height}",
                                width=width,
                                height=height,
                                specs={},
                                source_url=url
                            ))
        
        # Pattern 2: Lists with format specifications
        for ul in soup.find_all(['ul', 'ol']):
            for li in ul.find_all('li'):
                text = li.text
                dim_match = re.search(r'(\d{2,4})\s*x\s*(\d{2,4})', text)
                if dim_match:
                    width, height = int(dim_match.group(1)), int(dim_match.group(2))
                    # Extract format name if present
                    name_match = re.search(r'^([^:]+):', text)
                    name = name_match.group(1).strip() if name_match else f"{width}x{height}"
                    formats.append(FormatSpecification(
                        format_id=f"display_{width}x{height}",
                        name=name,
                        type="display",
                        description=text[:200],
                        width=width,
                        height=height,
                        specs={},
                        source_url=url
                    ))
        
        return formats
    
    async def _parse_standard_formats_html(self, html: str, base_url: str) -> List[FormatSpecification]:
        """Parse standard formats from HTML page."""
        formats = []
        soup = BeautifulSoup(html, 'html.parser')
        
        # Use AI to parse the page structure
        prompt = f"""
        Parse this HTML from the AdContext Protocol creative formats page.
        Extract all standard creative format specifications.
        
        HTML (first 5000 chars):
        {html[:5000]}
        
        Return JSON array with format specifications as described previously.
        Focus on IAB standard formats and commonly used sizes.
        """
        
        try:
            response = self.model.generate_content(prompt)
            
            # Debug logging to see what AI returned
            logger.info(f"AI response for standard formats HTML:")
            logger.info(f"Raw response text: {response.text}")
            
            formats_data = json.loads(response.text)
            
            for fmt in formats_data:
                if fmt.get('width') and fmt.get('height'):
                    format_id = f"display_{fmt['width']}x{fmt['height']}"
                elif fmt.get('duration_seconds'):
                    format_id = f"{fmt['type']}_{fmt.get('name', '').lower().replace(' ', '_')}"
                else:
                    format_id = f"{fmt['type']}_{fmt.get('name', '').lower().replace(' ', '_')}"
                
                formats.append(FormatSpecification(
                    format_id=format_id,
                    name=fmt['name'],
                    type=fmt['type'],
                    description=fmt.get('description', ''),
                    width=fmt.get('width'),
                    height=fmt.get('height'),
                    duration_seconds=fmt.get('duration_seconds'),
                    max_file_size_kb=fmt.get('max_file_size_kb'),
                    specs=fmt.get('specs', {}),
                    source_url=f"{base_url}/creative-formats"
                ))
                
        except Exception as e:
            logger.error(f"Error parsing standard formats HTML: {e}")
            
        return formats
    
    async def analyze_format_description(
        self,
        name: str,
        description: str,
        type_hint: Optional[str] = None
    ) -> FormatSpecification:
        """Analyze a natural language description to create a format specification."""
        
        prompt = f"""
        Create a creative format specification from this description:
        
        Name: {name}
        Description: {description}
        Type hint: {type_hint or 'auto-detect'}
        
        Analyze the description and determine:
        1. Type (display, video, audio, or native)
        2. Dimensions if applicable
        3. Duration if applicable
        4. File size limits
        5. Technical specifications
        
        Common patterns:
        - "banner" usually means display
        - Dimensions like "300x250" indicate display format
        - Duration mentions indicate video/audio
        - "native" or "sponsored content" indicate native format
        
        Return a JSON object with:
        - type: "display", "video", "audio", or "native"
        - description: enhanced description
        - width/height: for display formats
        - duration_seconds: for video/audio
        - max_file_size_kb: reasonable limit based on format
        - specs: technical specifications object
        
        Return ONLY valid JSON, no explanation.
        """
        
        response = self.model.generate_content(prompt)
        
        # Check if we got a valid response
        if not response or not hasattr(response, 'text') or not response.text:
            logger.warning(f"Empty response from Gemini for format description '{name}'")
            raise ValueError("Empty response from AI model")
        
        response_text = response.text.strip()
        
        # Debug logging to see what AI returned
        logger.info(f"AI response for format description '{name}':")
        logger.info(f"Raw response text: {response_text}")
        
        # Remove markdown code blocks if present
        if response_text.startswith('```json'):
            response_text = response_text.replace('```json', '').replace('```', '')
        elif response_text.startswith('```'):
            response_text = response_text.replace('```', '')
        
        response_text = response_text.strip()
        
        if not response_text:
            logger.warning(f"Empty response text after cleaning for format description '{name}'")
            raise ValueError("Empty response text after cleaning")
        
        try:
            data = json.loads(response_text)
            
            # Generate format ID
            if data.get('width') and data.get('height'):
                format_id = f"{data['type']}_{data['width']}x{data['height']}"
            elif data.get('duration_seconds'):
                format_id = f"{data['type']}_{name.lower().replace(' ', '_')}"
            else:
                format_id = f"{data['type']}_{name.lower().replace(' ', '_')}"
            
            return FormatSpecification(
                format_id=format_id,
                name=name,
                type=data['type'],
                description=data.get('description', description),
                width=data.get('width'),
                height=data.get('height'),
                duration_seconds=data.get('duration_seconds'),
                max_file_size_kb=data.get('max_file_size_kb'),
                specs=data.get('specs', {})
            )
            
        except Exception as e:
            logger.error(f"Error analyzing format description: {e}")
            # Return a basic format
            return FormatSpecification(
                format_id=f"custom_{name.lower().replace(' ', '_')}",
                name=name,
                type=type_hint or "display",
                description=description,
                specs={}
            )

async def discover_creative_format(
    tenant_id: Optional[str],
    name: str,
    description: Optional[str] = None,
    url: Optional[str] = None,
    type_hint: Optional[str] = None
) -> Dict[str, Any]:
    """Main entry point for discovering creative formats."""
    
    service = AICreativeFormatService()
    
    if url:
        # Discover from URL
        formats = await service.discover_format_from_url(url)
        if formats:
            # Return the first/best match
            fmt = formats[0]
        else:
            # Fallback to description analysis
            fmt = await service.analyze_format_description(name, description or "", type_hint)
    else:
        # Analyze description
        fmt = await service.analyze_format_description(name, description or "", type_hint)
    
    # Convert to dict for storage
    return {
        "format_id": fmt.format_id,
        "tenant_id": tenant_id,
        "name": fmt.name,
        "type": fmt.type,
        "description": fmt.description,
        "width": fmt.width,
        "height": fmt.height,
        "duration_seconds": fmt.duration_seconds,
        "max_file_size_kb": fmt.max_file_size_kb,
        "specs": json.dumps(fmt.specs or {}),
        "is_standard": False,  # Custom formats are not standard
        "source_url": fmt.source_url
    }

async def sync_standard_formats():
    """Sync standard formats from adcontextprotocol.org to database."""
    service = AICreativeFormatService()
    formats = await service.fetch_standard_formats()
    
    conn = get_db_connection()
    
    for fmt in formats:
        try:
            # Check if format already exists
            cursor = conn.execute(
                "SELECT format_id FROM creative_formats WHERE format_id = ?",
                (fmt.format_id,)
            )
            
            if not cursor.fetchone():
                # Insert new format
                conn.execute("""
                    INSERT INTO creative_formats (
                        format_id, tenant_id, name, type, description,
                        width, height, duration_seconds, max_file_size_kb,
                        specs, is_standard, extends, source_url
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    fmt.format_id,
                    None,  # Standard formats have no tenant
                    fmt.name,
                    fmt.type,
                    fmt.description,
                    fmt.width,
                    fmt.height,
                    fmt.duration_seconds,
                    fmt.max_file_size_kb,
                    json.dumps(fmt.specs or {}),
                    True,  # is_standard
                    fmt.extends,
                    fmt.source_url
                ))
                
        except Exception as e:
            logger.error(f"Error syncing format {fmt.format_id}: {e}")
    
    conn.connection.commit()
    conn.close()
    
    return len(formats)