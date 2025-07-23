import sqlite3
import json

DB_FILE = "adcp.db"

def init_db():
    """Initializes the database and creates tables with sample data."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Enable foreign key support
    cursor.execute("PRAGMA foreign_keys = ON;")

    # -- Creative Formats --
    # Storing the detailed spec as a JSON string for flexibility.
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS creative_formats (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        spec TEXT NOT NULL 
    );
    """)

    # -- Audiences --
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS audiences (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        description TEXT
    );
    """)

    # -- Properties --
    # e.g., a website or app
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS properties (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        description TEXT
    );
    """)

    # -- Placements --
    # A specific ad slot on a property
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS placements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        property_id INTEGER NOT NULL,
        base_cpm REAL NOT NULL,
        FOREIGN KEY (property_id) REFERENCES properties (id)
    );
    """)

    # -- Linking Tables (Many-to-Many) --

    # Link placements to the creative formats they support
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS placement_formats (
        placement_id INTEGER,
        format_id INTEGER,
        PRIMARY KEY (placement_id, format_id),
        FOREIGN KEY (placement_id) REFERENCES placements (id),
        FOREIGN KEY (format_id) REFERENCES creative_formats (id)
    );
    """)

    # Link placements to the audiences they can target
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS placement_audiences (
        placement_id INTEGER,
        audience_id INTEGER,
        PRIMARY KEY (placement_id, audience_id),
        FOREIGN KEY (placement_id) REFERENCES placements (id),
        FOREIGN KEY (audience_id) REFERENCES audiences (id)
    );
    """)

    # -- Sample Data --
    # Using INSERT OR IGNORE to prevent errors on subsequent runs
    
    # Creative Formats
    e2e_video_spec = {
        "assets": {
            "video": { "formats": ["mp4", "webm"], "resolutions": [{"width": 1080, "height": 1080, "label": "square"}], "max_file_size_mb": 50, "duration_options": [6, 15]},
            "companion": { "logo": {"size": "300x300", "format": "png"}, "overlay_image": {"size": "1080x1080", "format": "jpg", "optional": True}}
        },
        "description": "An immersive mobile video that scrolls in-feed"
    }
    cursor.execute("INSERT OR IGNORE INTO creative_formats (name, spec) VALUES (?, ?)", 
                   ('E2E mobile video', json.dumps(e2e_video_spec)))

    # Audiences
    cursor.execute("INSERT OR IGNORE INTO audiences (name, description) VALUES (?, ?)", 
                   ('Remarketing', 'Users who have recently visited the advertiser site.'))
    cursor.execute("INSERT OR IGNORE INTO audiences (name, description) VALUES (?, ?)", 
                   ('Premium Sports Fans', 'Users who frequent our premium sports content.'))

    # Properties
    cursor.execute("INSERT OR IGNORE INTO properties (name, description) VALUES (?, ?)", 
                   ('Basketball City Gazette', 'Leading online destination for basketball news.'))
    cursor.execute("INSERT OR IGNORE INTO properties (name, description) VALUES (?, ?)", 
                   ('Yoga for Tall People', 'Niche content site for the vertically gifted yogi.'))

    # Placements
    cursor.execute("INSERT OR IGNORE INTO placements (name, property_id, base_cpm) VALUES (?, ?, ?)", 
                   ('Homepage In-Feed Video', 1, 20.00))
    cursor.execute("INSERT OR IGNORE INTO placements (name, property_id, base_cpm) VALUES (?, ?, ?)", 
                   ('Article Interstitial', 1, 25.00))
    cursor.execute("INSERT OR IGNORE INTO placements (name, property_id, base_cpm) VALUES (?, ?, ?)", 
                   ('Downward Dog In-Feed', 2, 18.00))

    # Link them together
    # Homepage In-Feed on Basketball City supports E2E video and targets Premium Sports Fans
    cursor.execute("INSERT OR IGNORE INTO placement_formats (placement_id, format_id) VALUES (1, 1)")
    cursor.execute("INSERT OR IGNORE INTO placement_audiences (placement_id, audience_id) VALUES (1, 2)")
    
    # Article Interstitial on Basketball City supports E2E video and can be used for Remarketing
    cursor.execute("INSERT OR IGNORE INTO placement_formats (placement_id, format_id) VALUES (2, 1)")
    cursor.execute("INSERT OR IGNORE INTO placement_audiences (placement_id, audience_id) VALUES (2, 1)")

    conn.commit()
    conn.close()
    print("Database initialized successfully.")

if __name__ == '__main__':
    init_db()
