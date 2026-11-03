import sys
import io
import sqlite3

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

conn = sqlite3.connect('data/deals.db')
conn.row_factory = sqlite3.Row
rows = conn.execute('''
    SELECT p.id, p.platform, p.source, p.url, p.name, p.target_price, p.main_variant_id,
           ph.price, ph.list_price, ph.final_price, ph.stock, ph.ts 
    FROM products p 
    LEFT JOIN price_history ph ON ph.id = (
        SELECT id FROM price_history WHERE product_id = p.id ORDER BY id DESC LIMIT 1
    )
    WHERE p.active = 1 AND (p.source = 'user' OR p.target_price IS NOT NULL)
    ORDER BY p.id DESC

''').fetchall()

for r in rows:
    name = (r['name'] or '')[:40]
    url = (r['url'] or '')
    print(f"#{r['id']} [{r['platform']}|{r['source']}] price={r['price']} (list={r['list_price']}, final={r['final_price']}, stock={r['stock']}) target={r['target_price']} main_var={r['main_variant_id']} | {name} | {url}")

