import sqlite3
import json
import os

DB_FILE = "adcp.db"

def init_db():
    """Initializes the database with principals (including access tokens) and products."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Check if we're in production mode
    is_production = os.environ.get('PRODUCTION') == 'true'
    
    cursor.execute("DROP TABLE IF EXISTS products;")
    cursor.execute("DROP TABLE IF EXISTS principals;")

    # --- Principals Table with access_token ---
    cursor.execute("""
    CREATE TABLE principals (
        principal_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        platform_mappings TEXT NOT NULL,
        access_token TEXT NOT NULL UNIQUE
    );
    """)

    # --- Products Table ---
    cursor.execute("""
    CREATE TABLE products (
        product_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        description TEXT NOT NULL,
        formats TEXT NOT NULL,
        targeting_template TEXT NOT NULL,
        delivery_type TEXT NOT NULL,
        is_fixed_price BOOLEAN NOT NULL,
        cpm REAL,
        price_guidance TEXT,
        is_custom BOOLEAN DEFAULT 0
    );
    """)

    # Only insert sample data if not in production
    if not is_production:
        principals_data = [
            {
                "principal_id": "purina",
                "name": "Purina Pet Foods",
                "platform_mappings": {
                    "gam_advertiser_id": 12345,
                    "kevel_advertiser_id": "purina-pet-foods",
                    "triton_advertiser_id": "ADV-PUR-001",
                    "mock_advertiser_id": "mock-purina"
                },
                "access_token": "purina_secret_token_abc123"
            },
            {
                "principal_id": "acme_corp",
                "name": "Acme Corporation",
                "platform_mappings": {
                    "gam_advertiser_id": 67890,
                    "kevel_advertiser_id": "acme-corporation",
                    "triton_advertiser_id": "ADV-ACM-002",
                    "mock_advertiser_id": "mock-acme"
                },
                "access_token": "acme_secret_token_xyz789"
            }
        ]
        
        for p in principals_data:
            cursor.execute("INSERT INTO principals VALUES (?, ?, ?, ?)",
                           (p["principal_id"], p["name"], json.dumps(p["platform_mappings"]), p["access_token"]))

        products_data = [
            {
                "product_id": "prod_video_guaranteed_sports",
                "name": "Sports Video - Guaranteed",
                "description": "Premium sports content video inventory with guaranteed delivery",
                "formats": [
                    {
                        "format_id": "fmt_video_30s",
                        "name": "30-second Video",
                        "type": "video",
                        "description": "Standard 30-second video ad",
                        "specs": {
                            "duration_seconds": 30,
                            "placement": "instream",
                            "resolution": "1920x1080",
                            "bitrate": "2500kbps"
                        },
                        "delivery_options": {
                            "vast": {
                                "versions": ["2.0", "3.0", "4.0"]
                            }
                        }
                    }
                ],
                "targeting_template": {
                    "content_categories_include": ["sports"],
                    "geography": ["USA"]
                },
                "delivery_type": "guaranteed",
                "is_fixed_price": False,
                "cpm": None,
                "price_guidance": {
                    "floor": 35.0,
                    "p25": 40.0,
                    "p50": 45.0,
                    "p75": 50.0,
                    "p90": 60.0
                },
                "is_custom": False
            },
            {
                "product_id": "prod_audio_podcast_tech",
                "name": "Tech Podcast Audio - Non-Guaranteed",
                "description": "Technology-focused podcast inventory with flexible delivery",
                "formats": [
                    {
                        "format_id": "fmt_audio_30s",
                        "name": "30-second Audio",
                        "type": "audio",
                        "description": "Standard 30-second audio ad for podcasts",
                        "specs": {
                            "duration_seconds": 30,
                            "placement": "podcast",
                            "format": "mp3",
                            "bitrate": "128kbps"
                        },
                        "delivery_options": {
                            "hosted": {
                                "delivery_method": "dynamic_insertion"
                            }
                        }
                    }
                ],
                "targeting_template": {
                    "content_categories_include": ["technology", "business"],
                    "geography": ["USA", "CAN"]
                },
                "delivery_type": "non_guaranteed",
                "is_fixed_price": True,
                "cpm": 25.0,
                "price_guidance": None,
                "is_custom": False
            }
        ]

        for p in products_data:
            cursor.execute("""
                INSERT INTO products VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                p["product_id"],
                p["name"],
                p["description"],
                json.dumps(p["formats"]),
                json.dumps(p["targeting_template"]),
                p["delivery_type"],
                p["is_fixed_price"],
                p.get("cpm"),
                json.dumps(p["price_guidance"]) if p.get("price_guidance") else None,
                p["is_custom"]
            ))
        
        print("Database initialized with sample data.")
    else:
        print("Database initialized (production mode - no sample data).")

    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()