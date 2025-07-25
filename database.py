import sqlite3
import json

DB_FILE = "adcp.db"

def init_db():
    """Initializes the database and creates tables with sample data for V2.1 spec."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute("PRAGMA foreign_keys = ON;")

    # Drop existing tables for a clean slate
    cursor.execute("DROP TABLE IF EXISTS placement_audiences;")
    cursor.execute("DROP TABLE IF EXISTS placement_formats;")
    cursor.execute("DROP TABLE IF EXISTS placements;")
    cursor.execute("DROP TABLE IF EXISTS properties;")
    cursor.execute("DROP TABLE IF EXISTS audiences;")
    cursor.execute("DROP TABLE IF EXISTS creative_formats;")

    # --- Core Tables ---

    cursor.execute("""
    CREATE TABLE creative_formats (
        id INTEGER PRIMARY KEY,
        format_id TEXT UNIQUE NOT NULL,
        format_type TEXT NOT NULL,
        spec TEXT NOT NULL
    );
    """)
    cursor.execute("CREATE TABLE audiences (id INTEGER PRIMARY KEY, name TEXT, description TEXT, ad_server_targeting TEXT);")
    cursor.execute("CREATE TABLE properties (id INTEGER PRIMARY KEY, name TEXT, description TEXT);")
    cursor.execute("""
    CREATE TABLE placements (
        id INTEGER PRIMARY KEY, name TEXT, property_id INTEGER, type TEXT, 
        delivery_type TEXT, base_cpm REAL, pricing_guidance TEXT, daily_impression_capacity INTEGER
    );
    """)

    # --- Linking Tables ---
    cursor.execute("CREATE TABLE placement_formats (placement_id INTEGER, format_id INTEGER);")
    cursor.execute("CREATE TABLE placement_audiences (placement_id INTEGER, audience_id INTEGER);")

    # --- Sample Data ---

    # Creative Formats
    std_video_spec = {"media_type": "video", "mime": "video/mp4", "w": 1920, "h": 1080}
    std_banner_spec = {"media_type": "display", "mime": "image/png", "w": 300, "h": 250}
    custom_e2e_spec = {
        "description": "An immersive edge-to-edge mobile video format.",
        "assets": {
            "primary_video": {"type": "video/mp4", "required": True},
            "end_card": {"type": "image/jpeg", "required": True}
        }
    }
    cursor.execute("INSERT INTO creative_formats VALUES (1, 'std_video_1920x1080', 'standard', ?)", [json.dumps(std_video_spec)])
    cursor.execute("INSERT INTO creative_formats VALUES (2, 'std_banner_300x250', 'standard', ?)", [json.dumps(std_banner_spec)])
    cursor.execute("INSERT INTO creative_formats VALUES (3, 'custom_e2e_video', 'custom', ?)", [json.dumps(custom_e2e_spec)])

    # Audiences
    cursor.execute("INSERT INTO audiences VALUES (1, 'Cat Lovers', 'Users interested in cats.', '[{\"gam\": {\"type\": \"audience_segment\", \"id\": 12345}}]')")
    cursor.execute("INSERT INTO audiences VALUES (2, 'Sports Fans', 'Users interested in sports.', '[{\"gam\": {\"type\": \"audience_segment\", \"id\": 12347}}]')")

    # Properties
    cursor.execute("INSERT INTO properties VALUES (1, 'Cat World', 'The #1 online destination for cat lovers.')")
    cursor.execute("INSERT INTO properties VALUES (2, 'Sports Yelling', 'Loud opinions about sports.')")

    # Placements
    pricing = {"floor_cpm": 5.0, "suggested_cpm": 7.5, "p25": 5.5, "p50": 7.0, "p75": 8.0, "p90": 9.5}
    cursor.execute("INSERT INTO placements VALUES (1, 'Homepage Banner (Guaranteed)', 1, 'catalog', 'guaranteed', 25.0, null, 100000)")
    cursor.execute("INSERT INTO placements VALUES (2, 'In-Feed Video (Non-Guaranteed)', 2, 'catalog', 'non_guaranteed', null, ?, 500000)", [json.dumps(pricing)])
    cursor.execute("INSERT INTO placements VALUES (3, 'Custom E2E Video Ad', 1, 'custom', 'guaranteed', 45.0, null, 75000)")

    # Link them together
    cursor.execute("INSERT INTO placement_formats VALUES (1, 2)") # Banner
    cursor.execute("INSERT INTO placement_audiences VALUES (1, 1)") # Cat Lovers

    cursor.execute("INSERT INTO placement_formats VALUES (2, 1)") # Video
    cursor.execute("INSERT INTO placement_audiences VALUES (2, 2)") # Sports Fans
    
    cursor.execute("INSERT INTO placement_formats VALUES (3, 3)") # Custom E2E
    cursor.execute("INSERT INTO placement_audiences VALUES (3, 1)") # Cat Lovers

    conn.commit()
    conn.close()
    print("Database initialized successfully for V2.1 spec.")

if __name__ == '__main__':
    init_db()
