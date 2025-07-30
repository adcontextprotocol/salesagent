"""Populate creative_formats table with standard IAB formats."""

import json
from typing import Dict, Any
from db_config import get_db_connection

# Standard IAB display formats
STANDARD_DISPLAY_FORMATS = [
    {
        "format_id": "display_300x250",
        "name": "Medium Rectangle",
        "type": "display",
        "description": "Most popular display ad size, suitable for both desktop and mobile",
        "width": 300,
        "height": 250,
        "max_file_size_kb": 200,
        "specs": {
            "file_types": ["jpg", "png", "gif", "html5"],
            "animation_length_seconds": 30,
            "polite_load_kb": 300
        }
    },
    {
        "format_id": "display_728x90",
        "name": "Leaderboard",
        "type": "display",
        "description": "Traditional banner format for desktop headers",
        "width": 728,
        "height": 90,
        "max_file_size_kb": 200,
        "specs": {
            "file_types": ["jpg", "png", "gif", "html5"],
            "animation_length_seconds": 30,
            "polite_load_kb": 300
        }
    },
    {
        "format_id": "display_320x50",
        "name": "Mobile Banner",
        "type": "display",
        "description": "Standard mobile banner",
        "width": 320,
        "height": 50,
        "max_file_size_kb": 150,
        "specs": {
            "file_types": ["jpg", "png", "gif", "html5"],
            "animation_length_seconds": 30,
            "polite_load_kb": 200
        }
    },
    {
        "format_id": "display_300x600",
        "name": "Half Page",
        "type": "display",
        "description": "High-impact format for desktop sidebars",
        "width": 300,
        "height": 600,
        "max_file_size_kb": 250,
        "specs": {
            "file_types": ["jpg", "png", "gif", "html5"],
            "animation_length_seconds": 30,
            "polite_load_kb": 400
        }
    },
    {
        "format_id": "display_970x250",
        "name": "Billboard",
        "type": "display",
        "description": "Premium large format for desktop headers",
        "width": 970,
        "height": 250,
        "max_file_size_kb": 300,
        "specs": {
            "file_types": ["jpg", "png", "gif", "html5"],
            "animation_length_seconds": 30,
            "polite_load_kb": 500
        }
    },
    {
        "format_id": "display_160x600",
        "name": "Wide Skyscraper",
        "type": "display",
        "description": "Vertical format for desktop sidebars",
        "width": 160,
        "height": 600,
        "max_file_size_kb": 200,
        "specs": {
            "file_types": ["jpg", "png", "gif", "html5"],
            "animation_length_seconds": 30,
            "polite_load_kb": 300
        }
    }
]

# Standard video formats
STANDARD_VIDEO_FORMATS = [
    {
        "format_id": "video_instream_15s",
        "name": "In-Stream Video (15s)",
        "type": "video",
        "description": "Standard pre-roll/mid-roll video ad",
        "duration_seconds": 15,
        "max_file_size_kb": 10240,  # 10MB
        "specs": {
            "aspect_ratios": ["16:9", "4:3", "1:1"],
            "min_resolution": "640x360",
            "codecs": ["H.264", "VP8", "VP9"],
            "container_formats": ["MP4", "WebM"],
            "min_bitrate_kbps": 500,
            "max_bitrate_kbps": 5000,
            "vpaid_support": True,
            "skip_button_seconds": 5
        }
    },
    {
        "format_id": "video_instream_30s",
        "name": "In-Stream Video (30s)",
        "type": "video",
        "description": "Extended pre-roll/mid-roll video ad",
        "duration_seconds": 30,
        "max_file_size_kb": 20480,  # 20MB
        "specs": {
            "aspect_ratios": ["16:9", "4:3", "1:1"],
            "min_resolution": "640x360",
            "codecs": ["H.264", "VP8", "VP9"],
            "container_formats": ["MP4", "WebM"],
            "min_bitrate_kbps": 500,
            "max_bitrate_kbps": 5000,
            "vpaid_support": True,
            "skip_button_seconds": 5
        }
    },
    {
        "format_id": "video_outstream",
        "name": "Out-Stream Video",
        "type": "video",
        "description": "Video ad that plays in content feed",
        "duration_seconds": 30,
        "max_file_size_kb": 15360,  # 15MB
        "specs": {
            "aspect_ratios": ["16:9", "1:1"],
            "min_resolution": "640x360",
            "codecs": ["H.264", "VP8", "VP9"],
            "container_formats": ["MP4", "WebM"],
            "min_bitrate_kbps": 500,
            "max_bitrate_kbps": 3000,
            "autoplay": "muted",
            "viewability_threshold": 50
        }
    }
]

# Standard native formats
STANDARD_NATIVE_FORMATS = [
    {
        "format_id": "native_content_feed",
        "name": "Native Content Feed",
        "type": "native",
        "description": "Native ad for content feeds",
        "specs": {
            "required_assets": [
                {"name": "headline", "max_length": 90},
                {"name": "description", "max_length": 140},
                {"name": "main_image", "dimensions": "1200x627", "aspect_ratio": "1.91:1"},
                {"name": "logo", "dimensions": "128x128", "aspect_ratio": "1:1"},
                {"name": "cta_text", "max_length": 15}
            ],
            "optional_assets": [
                {"name": "video", "max_duration_seconds": 30},
                {"name": "rating", "scale": "0-5"},
                {"name": "price", "format": "currency"}
            ]
        }
    }
]

def populate_creative_formats():
    """Populate the creative_formats table with standard IAB formats."""
    
    all_formats = STANDARD_DISPLAY_FORMATS + STANDARD_VIDEO_FORMATS + STANDARD_NATIVE_FORMATS
    
    conn = get_db_connection()
    
    for fmt in all_formats:
        # Check if format already exists
        cursor = conn.execute(
            "SELECT format_id FROM creative_formats WHERE format_id = ?",
            (fmt["format_id"],)
        )
        existing = cursor.fetchone()
        
        if existing:
            print(f"Format {fmt['format_id']} already exists, skipping...")
            continue
        
        # Insert format
        specs_json = json.dumps(fmt["specs"])
        
        conn.execute(
            """
            INSERT INTO creative_formats (
                format_id, name, type, description, 
                width, height, duration_seconds, max_file_size_kb,
                specs, is_standard
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                fmt["format_id"],
                fmt["name"], 
                fmt["type"],
                fmt["description"],
                fmt.get("width"),
                fmt.get("height"),
                fmt.get("duration_seconds"),
                fmt.get("max_file_size_kb"),
                specs_json,
                1  # is_standard (SQLite uses 1 for True)
            )
        )
        print(f"Added format: {fmt['name']} ({fmt['format_id']})")
    
    conn.connection.commit()
    conn.close()
    
    print("\nCreative formats population complete!")

if __name__ == "__main__":
    populate_creative_formats()