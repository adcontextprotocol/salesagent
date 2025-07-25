import sqlite3
import json

DB_FILE = "adcp.db"

def init_db():
    """Initializes the database and creates tables with sample data for V2 spec."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute("PRAGMA foreign_keys = ON;")

    # Drop existing tables for a clean slate on each init
    cursor.execute("DROP TABLE IF EXISTS placement_audiences;")
    cursor.execute("DROP TABLE IF EXISTS placement_formats;")
    cursor.execute("DROP TABLE IF EXISTS placements;")
    cursor.execute("DROP TABLE IF EXISTS properties;")
    cursor.execute("DROP TABLE IF EXISTS audiences;")
    cursor.execute("DROP TABLE IF EXISTS creative_formats;")

    # --- Core Tables ---

    cursor.execute("""
    CREATE TABLE creative_formats (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        spec TEXT NOT NULL
    );
    """)

    cursor.execute("""
    CREATE TABLE audiences (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        description TEXT,
        ad_server_targeting TEXT NOT NULL
    );
    """)

    cursor.execute("""
    CREATE TABLE properties (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        description TEXT
    );
    """)

    cursor.execute("""
    CREATE TABLE placements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        property_id INTEGER NOT NULL,
        type TEXT NOT NULL, -- 'custom' or 'catalog'
        delivery_type TEXT NOT NULL, -- 'guaranteed' or 'non_guaranteed'
        base_cpm REAL, -- For guaranteed
        pricing_guidance TEXT, -- JSON for non_guaranteed
        daily_impression_capacity INTEGER,
        FOREIGN KEY (property_id) REFERENCES properties (id)
    );
    """)

    # --- Linking Tables ---

    cursor.execute("""
    CREATE TABLE placement_formats (
        placement_id INTEGER,
        format_id INTEGER,
        PRIMARY KEY (placement_id, format_id),
        FOREIGN KEY (placement_id) REFERENCES placements (id),
        FOREIGN KEY (format_id) REFERENCES creative_formats (id)
    );
    """)

    cursor.execute("""
    CREATE TABLE placement_audiences (
        placement_id INTEGER,
        audience_id INTEGER,
        PRIMARY KEY (placement_id, audience_id),
        FOREIGN KEY (placement_id) REFERENCES placements (id),
        FOREIGN KEY (audience_id) REFERENCES audiences (id)
    );
    """)

    # --- Sample Data ---

    # Creative Formats (OpenRTB style)
    video_spec = {"media_type": "video", "mime": "video/mp4", "w": 1920, "h": 1080, "dur": 30}
    banner_spec = {"media_type": "display", "mime": "image/png", "w": 300, "h": 250}
    cursor.execute("INSERT INTO creative_formats (name, spec) VALUES (?, ?)", ('Standard Video', json.dumps(video_spec)))
    cursor.execute("INSERT INTO creative_formats (name, spec) VALUES (?, ?)", ('Standard Banner', json.dumps(banner_spec)))

    # Audiences
    cat_lovers_targeting = json.dumps([{"gam": {"type": "audience_segment", "id": 12345}}])
    sports_fans_targeting = json.dumps([{"gam": {"type": "audience_segment", "id": 12347}}])
    cursor.execute("INSERT INTO audiences (name, description, ad_server_targeting) VALUES (?, ?, ?)", ('Cat Lovers', 'Users interested in cats.', cat_lovers_targeting))
    cursor.execute("INSERT INTO audiences (name, description, ad_server_targeting) VALUES (?, ?, ?)", ('Sports Fans', 'Users interested in sports.', sports_fans_targeting))

    # Properties
    cursor.execute("INSERT INTO properties (name, description) VALUES (?, ?)", ('Cat World', 'The #1 online destination for cat lovers.'))
    cursor.execute("INSERT INTO properties (name, description) VALUES (?, ?)", ('Sports Yelling', 'Loud opinions about sports.'))

    # Placements
    pricing_guidance = {
        "floor_cpm": 5.0, "suggested_cpm": 7.5,
        "p25": 5.5, "p50": 7.0, "p75": 8.0, "p90": 9.5
    }
    cursor.execute("""
    INSERT INTO placements (name, property_id, type, delivery_type, base_cpm, daily_impression_capacity) 
    VALUES (?, ?, ?, ?, ?, ?)
    """, ('Homepage Banner (Guaranteed)', 1, 'catalog', 'guaranteed', 25.00, 100000))
    
    cursor.execute("""
    INSERT INTO placements (name, property_id, type, delivery_type, pricing_guidance, daily_impression_capacity) 
    VALUES (?, ?, ?, ?, ?, ?)
    """, ('In-Feed Video (Non-Guaranteed)', 2, 'catalog', 'non_guaranteed', json.dumps(pricing_guidance), 500000))

    # Link them together
    cursor.execute("INSERT INTO placement_formats (placement_id, format_id) VALUES (1, 2)") # Banner
    cursor.execute("INSERT INTO placement_audiences (placement_id, audience_id) VALUES (1, 1)") # Cat Lovers

    cursor.execute("INSERT INTO placement_formats (placement_id, format_id) VALUES (2, 1)") # Video
    cursor.execute("INSERT INTO placement_audiences (placement_id, audience_id) VALUES (2, 2)") # Sports Fans

    conn.commit()
    conn.close()
    print("Database initialized successfully for V2 spec.")

if __name__ == '__main__':
    init_db()