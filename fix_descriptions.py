import csv
from database import get_db

db = get_db()
updated = 0
with open('data/amazon.csv', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        desc = row.get('about_product', '').strip()
        name = row.get('product_name', '').strip()
        if not desc or not name:
            continue
        db.execute('UPDATE products SET description=? WHERE name=?', (desc, name))
        updated += db.execute('SELECT changes()').fetchone()[0]

db.commit()
db.close()
print(f'Updated {updated} product descriptions')
