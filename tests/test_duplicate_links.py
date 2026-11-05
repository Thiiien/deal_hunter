"""Duplicate links: one Lazada listing is one product whatever the link form; re-adding says so (glossary: Canonical Link & Merge)."""
from deal_hunter.config import Config
from deal_hunter.db import DB
from deal_hunter.models import Snapshot
from deal_hunter.web import create_app


def _snap(price, item_key, url, name="Bàn phím AULA"):
    return Snapshot(platform="lazada", item_key=item_key, url=url, name=name, shop="AULA", price=price, list_price=None, stock=True)


def test_startup_merge_folds_variant_keyed_rows_into_the_user_row():
    db = DB(":memory:")
    old = db.upsert_product_meta(_snap(700_000.0, "13445776195.117548710186", "https://www.lazada.vn/products/aula-i13445776195-s117548710186.html"), source="flash_sale")
    db.save_snapshot(old, _snap(700_000.0, "13445776195.117548710186", "x"))
    db.save_snapshot(old, _snap(650_000.0, "13445776195.117548710186", "x"))
    new = db.add_product_url("https://www.lazada.vn/products/pdp-i13445776195.html", "lazada", "13445776195", source="user")
    db.set_target_price(new, 600_000.0)
    db.save_snapshot(new, _snap(640_000.0, "13445776195", "x"))
    lone = db.upsert_product_meta(_snap(1.0, "999.1", "https://www.lazada.vn/products/other-i999-s1.html"), source="keyword")
    db._merge_lazada_variant_keys()
    keys = {r["id"]: r for r in db.conn.execute("SELECT * FROM products WHERE platform='lazada'").fetchall()}
    # the user-tracked row keeps its id (it is the one quoted in Telegram); the older discovery row folds into it
    assert set(keys) == {new, lone} and keys[new]["item_key"] == "13445776195" and keys[lone]["item_key"] == "999"
    assert keys[new]["source"] == "user" and keys[new]["active"] == 1 and keys[new]["target_price"] == 600_000.0
    assert db.conn.execute("SELECT COUNT(*) FROM price_history WHERE product_id=?", (new,)).fetchone()[0] == 3
    assert db.conn.execute("SELECT COUNT(*) FROM price_history WHERE product_id=?", (old,)).fetchone()[0] == 0
    db._merge_lazada_variant_keys()  # idempotent
    assert db.conn.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 2


def test_adding_the_same_listing_twice_reports_existing_and_overrides_target():
    db = DB(":memory:")
    client = create_app(Config(db_path=":memory:", fetch_mode="mock"), db, None).test_client()
    first = client.post("/api/products", json={"url": "https://www.lazada.vn/products/aula-i13445776195-s117548710186.html", "target_price": 600000}).get_json()
    assert first["existing"] is False and first["item_key"] == "13445776195" and first["target_price"] == 600000.0
    again = client.post("/api/products", json={"url": "https://www.lazada.vn/products/pdp-i13445776195.html?spm=x"}).get_json()
    assert again["existing"] is True and again["id"] == first["id"] and again["target_price"] == 600000.0  # kept
    third = client.post("/api/products", json={"url": "https://www.lazada.vn/products/pdp-i13445776195.html", "target_price": 550000}).get_json()
    assert third["existing"] is True and third["target_price"] == 550000.0  # new price overrides
    assert db.conn.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 1
