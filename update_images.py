import sqlite3, csv, re

def parse_price(raw):
    cleaned = re.sub(r'[^\d.]', '', raw.strip())
    try: return float(cleaned)
    except: return 0.0

db = sqlite3.connect('ecommerce.db')
db.row_factory = sqlite3.Row

name_map = {}
for r in db.execute('SELECT product_id, name FROM products').fetchall():
    name_map[r['name'].strip().lower()] = r['product_id']

updated = 0
with open('data/amazon.csv', newline='', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        name = row.get('product_name', '').strip()
        img  = row.get('img_link', '').strip()
        if not img or not name:
            continue
        pid = name_map.get(name.lower())
        if pid:
            db.execute(
                'UPDATE products SET image=? WHERE product_id=? AND (image IS NULL OR image="")',
                (img, pid)
            )
            updated += 1

db.commit()
print('Updated', updated, 'product images')
db.close()
