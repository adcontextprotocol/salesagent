import sqlite3
import json

DB_FILE = "adcp.db"

def init_db():
    """Initializes the database with V2.3 data, including advanced pricing models."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS products;")
    cursor.execute("""
    CREATE TABLE products (
        product_id TEXT PRIMARY KEY, name TEXT, description TEXT, formats TEXT,
        targeting_template TEXT, delivery_type TEXT, is_fixed_price INTEGER,
        cpm REAL, price_guidance TEXT, is_custom INTEGER, expires_at TEXT
    );
    """)

    products_data = [
        {
            "product_id": "prod_video_guaranteed_sports",
            "name": "Premium In-Stream Video (Sports, Guaranteed)",
            "description": "Guaranteed delivery on premium sports content.",
            "formats": [{
                "format_id": "video_standard_1080p", "name": "Standard HD Video", "type": "video",
                "description": "Standard 1080p video ad", "specs": {}, "delivery_options": {}
            }],
            "targeting_template": {"geography": ["USA"], "content_categories_include": ["sports"]},
            "delivery_type": "guaranteed",
            "is_fixed_price": True,
            "cpm": 45.00,
            "price_guidance": None
        },
        {
            "product_id": "prod_display_nonguaranteed_news",
            "name": "Run-of-Network Display Banner (News, Non-Guaranteed)",
            "description": "Non-guaranteed, auction-based delivery on news sites.",
            "formats": [{
                "format_id": "display_banner_300x250", "name": "Standard Banner", "type": "display",
                "description": "A 300x250 display banner.", "specs": {}, "delivery_options": {}
            }],
            "targeting_template": {"content_categories_include": ["news", "politics"]},
            "delivery_type": "non_guaranteed",
            "is_fixed_price": False,
            "cpm": None,
            "price_guidance": {
                "floor": 10.00, "p25": 12.50, "p50": 15.00, "p75": 18.00, "p90": 22.00
            }
        }
    ]

    for product in products_data:
        cursor.execute(
            "INSERT INTO products VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                product["product_id"], product["name"], product["description"],
                json.dumps(product["formats"]), json.dumps(product["targeting_template"]),
                product["delivery_type"], product["is_fixed_price"], product["cpm"],
                json.dumps(product["price_guidance"]), False, None
            )
        )

    conn.commit()
    conn.close()
    print("Database initialized with advanced pricing models.")

if __name__ == '__main__':
    init_db()