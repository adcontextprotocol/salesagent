import psycopg2
from psycopg2.extras import DictCursor
import json
import os

# Get database URL from environment
db_url = os.environ.get('DATABASE_URL')

# Connect to database
conn = psycopg2.connect(db_url, cursor_factory=DictCursor)
cursor = conn.cursor()

# Create test products
products = [
    {
        'product_id': 'test_display_300x250',
        'name': 'Display Ad 300x250',
        'formats': json.dumps([{
            'format_id': 'display_300x250',
            'name': 'Medium Rectangle',
            'width': 300,
            'height': 250,
            'type': 'display'
        }]),
        'delivery_type': 'guaranteed',
        'cpm': 10.0,
        'targeting_template': json.dumps({
            'geo_country_any_of': ['US', 'CA'],
            'device_type_any_of': ['desktop', 'mobile']
        })
    },
    {
        'product_id': 'test_video_preroll',
        'name': 'Video Pre-Roll',
        'formats': json.dumps([{
            'format_id': 'video_16x9',
            'name': 'Video 16:9',
            'width': 1920,
            'height': 1080,
            'type': 'video'
        }]),
        'delivery_type': 'guaranteed',
        'cpm': 25.0,
        'targeting_template': json.dumps({
            'geo_country_any_of': ['US'],
            'content_category_any_of': ['sports', 'entertainment']
        })
    }
]

for product in products:
    cursor.execute('''
        INSERT INTO products (tenant_id, product_id, name, formats, delivery_type, cpm, targeting_template, is_fixed_price)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    ''', ('test_publisher', product['product_id'], product['name'], product['formats'], 
          product['delivery_type'], product['cpm'], product['targeting_template'], True))

conn.commit()

print('Products created:')
for product in products:
    print(f"  - {product['name']} (ID: {product['product_id']})")
    print(f"    CPM: ${product['cpm']}")

conn.close()