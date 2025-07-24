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
        "assets": { "video": { "formats": ["mp4", "webm"], "resolutions": [{"width": 1080, "height": 1080, "label": "square"}], "max_file_size_mb": 50, "duration_options": [6, 15]}, "companion": { "logo": {"size": "300x300", "format": "png"}, "overlay_image": {"size": "1080x1080", "format": "jpg", "optional": True}}},
        "description": "An immersive mobile video that scrolls in-feed"
    }
    banner_spec = {
        "assets": {"image": {"sizes": ["300x250", "728x90"], "format": "png"}},
        "description": "A standard display banner ad."
    }
    cursor.execute("INSERT OR IGNORE INTO creative_formats (name, spec) VALUES (?, ?)", ('E2E mobile video', json.dumps(e2e_video_spec)))
    cursor.execute("INSERT OR IGNORE INTO creative_formats (name, spec) VALUES (?, ?)", ('Standard Banner', json.dumps(banner_spec)))

    # Audiences
    cursor.execute("INSERT OR IGNORE INTO audiences (name, description) VALUES (?, ?)", ('Cat Lovers', 'Users who own cats or show strong interest in cat-related content.'))
    cursor.execute("INSERT OR IGNORE INTO audiences (name, description) VALUES (?, ?)", ('Dog Lovers', 'Users who own dogs or show strong interest in dog-related content.'))
    cursor.execute("INSERT OR IGNORE INTO audiences (name, description) VALUES (?, ?)", ('High-Income Earners', 'Users in the top 20% of household income.'))
    cursor.execute("INSERT OR IGNORE INTO audiences (name, description) VALUES (?, ?)", ('Sports Fans', 'Users who frequent sports content.'))


    # Properties
    cursor.execute("INSERT OR IGNORE INTO properties (name, description) VALUES (?, ?)", ('Cat World', 'The #1 online destination for cat lovers.'))
    cursor.execute("INSERT OR IGNORE INTO properties (name, description) VALUES (?, ?)", ('Dog Weekly', 'Your weekly source for everything dog-related.'))
    cursor.execute("INSERT OR IGNORE INTO properties (name, description) VALUES (?, ?)", ('The Finance Times', 'Global news and analysis for business leaders.'))
    cursor.execute("INSERT OR IGNORE INTO properties (name, description) VALUES (?, ?)", ('Sports Yelling', 'Loud opinions about sports.'))


    # Placements
    cursor.execute("INSERT OR IGNORE INTO placements (name, property_id, base_cpm) VALUES (?, ?, ?)", ('Homepage Banner', 1, 25.00)) # Cat World
    cursor.execute("INSERT OR IGNORE INTO placements (name, property_id, base_cpm) VALUES (?, ?, ?)", ('Article In-Feed Video', 1, 35.00)) # Cat World
    cursor.execute("INSERT OR IGNORE INTO placements (name, property_id, base_cpm) VALUES (?, ?, ?)", ('Homepage Banner', 2, 22.00)) # Dog Weekly
    cursor.execute("INSERT OR IGNORE INTO placements (name, property_id, base_cpm) VALUES (?, ?, ?)", ('Homepage Leaderboard', 3, 45.00)) # Finance Times
    cursor.execute("INSERT OR IGNORE INTO placements (name, property_id, base_cpm) VALUES (?, ?, ?)", ('Homepage Video', 4, 30.00)) # Sports Yelling

    # Link them together
    # Cat World (Property ID 1)
    # Placement ID 1 ('Homepage Banner') supports Banner (Format ID 2) and targets Cat Lovers (Audience ID 1)
    cursor.execute("INSERT OR IGNORE INTO placement_formats (placement_id, format_id) VALUES (1, 2)")
    cursor.execute("INSERT OR IGNORE INTO placement_audiences (placement_id, audience_id) VALUES (1, 1)")
    # Placement ID 2 ('Article In-Feed Video') supports Video (Format ID 1) and targets Cat Lovers (Audience ID 1)
    cursor.execute("INSERT OR IGNORE INTO placement_formats (placement_id, format_id) VALUES (2, 1)")
    cursor.execute("INSERT OR IGNORE INTO placement_audiences (placement_id, audience_id) VALUES (2, 1)")
    
    # Dog Weekly (Property ID 2)
    # Placement ID 3 ('Homepage Banner') supports Banner (Format ID 2) and targets Dog Lovers (Audience ID 2)
    cursor.execute("INSERT OR IGNORE INTO placement_formats (placement_id, format_id) VALUES (3, 2)")
    cursor.execute("INSERT OR IGNORE INTO placement_audiences (placement_id, audience_id) VALUES (3, 2)")

    # The Finance Times (Property ID 3)
    # Placement ID 4 ('Homepage Leaderboard') supports Banner (Format ID 2) and targets High-Income (Audience ID 3)
    cursor.execute("INSERT OR IGNORE INTO placement_formats (placement_id, format_id) VALUES (4, 2)")
    cursor.execute("INSERT OR IGNORE INTO placement_audiences (placement_id, audience_id) VALUES (4, 3)")

    # Sports Yelling (Property ID 4)
    # Placement ID 5 ('Homepage Video') supports Video (Format ID 1) and targets Sports Fans (Audience ID 4)
    cursor.execute("INSERT OR IGNORE INTO placement_formats (placement_id, format_id) VALUES (5, 1)")
    cursor.execute("INSERT OR IGNORE INTO placement_audiences (placement_id, audience_id) VALUES (5, 4)")

    conn.commit()
    conn.close()
    print("Database initialized successfully.")

if __name__ == '__main__':
    init_db()
