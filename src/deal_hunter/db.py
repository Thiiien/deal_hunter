import json
import sqlite3
import threading
from pathlib import Path

from .models import Snapshot, VariantInfo

_SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    platform    TEXT    NOT NULL,
    item_key    TEXT    NOT NULL,
    url         TEXT    NOT NULL,
    name        TEXT,
    shop        TEXT,
    category    TEXT    NOT NULL DEFAULT '',
    rating      REAL,
    sold        INTEGER,
    target_price REAL,
    source      TEXT    NOT NULL DEFAULT 'user',
    fail_count  INTEGER NOT NULL DEFAULT 0,
    active      INTEGER NOT NULL DEFAULT 1,
    main_variant_id INTEGER,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE(platform, item_key)
);

CREATE TABLE IF NOT EXISTS price_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id  INTEGER NOT NULL REFERENCES products(id),
    price       REAL    NOT NULL,
    list_price  REAL,
    stock       INTEGER,           -- NULL=unknown, 0=out_of_stock, 1=in_stock
    campaign    TEXT    NOT NULL DEFAULT '',
    voucher_code TEXT   NOT NULL DEFAULT '',
    voucher_discount REAL NOT NULL DEFAULT 0.0,
    final_price REAL,
    ts          TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_ph_product_ts ON price_history(product_id, ts);

CREATE TABLE IF NOT EXISTS campaigns (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    start_date  TEXT    NOT NULL,
    end_date    TEXT    NOT NULL,
    description TEXT
);

CREATE TABLE IF NOT EXISTS alerts (
    product_id  INTEGER PRIMARY KEY REFERENCES products(id),
    last_price  REAL    NOT NULL,
    sent_at     TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS scan_log (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    ts    TEXT    NOT NULL DEFAULT (datetime('now')),
    ok    INTEGER NOT NULL DEFAULT 0,
    fail  INTEGER NOT NULL DEFAULT 0,
    msg   TEXT
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS keywords (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword         TEXT    NOT NULL,
    platform        TEXT    NOT NULL DEFAULT '',
    active          INTEGER NOT NULL DEFAULT 1,
    origin_filter   TEXT    NOT NULL DEFAULT 'vn',
    ship_filter     TEXT    NOT NULL DEFAULT 'vn',
    shop_filter     TEXT    NOT NULL DEFAULT 'any',
    services_filter TEXT    NOT NULL DEFAULT '',
    filters_json    TEXT    NOT NULL DEFAULT '{}',
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    last_run        TEXT,
    last_scanned    INTEGER NOT NULL DEFAULT 0,
    last_matched    INTEGER NOT NULL DEFAULT 0,
    last_msg        TEXT,
    UNIQUE(keyword, platform)
);

CREATE TABLE IF NOT EXISTS keyword_products (
    keyword_id  INTEGER NOT NULL REFERENCES keywords(id) ON DELETE CASCADE,
    product_id  INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    verified    INTEGER NOT NULL DEFAULT 1,
    matched_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY(keyword_id, product_id)
);

CREATE TABLE IF NOT EXISTS rejected_items (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    platform    TEXT    NOT NULL,
    item_key    TEXT    NOT NULL,
    keyword_id  INTEGER NOT NULL REFERENCES keywords(id) ON DELETE CASCADE,
    reason      TEXT    NOT NULL DEFAULT '',
    ts          TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE(platform, item_key, keyword_id)
);

CREATE TABLE IF NOT EXISTS variants (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id  INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    variant_key TEXT    NOT NULL,
    name        TEXT    NOT NULL,
    attrs       TEXT    NOT NULL DEFAULT '{}',
    active      INTEGER NOT NULL DEFAULT 1,
    first_seen  TEXT    NOT NULL DEFAULT (datetime('now')),
    last_seen   TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE(product_id, variant_key)
);
CREATE INDEX IF NOT EXISTS idx_variants_product ON variants(product_id, active);

CREATE TABLE IF NOT EXISTS variant_history (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    variant_id   INTEGER NOT NULL REFERENCES variants(id) ON DELETE CASCADE,
    price        REAL,
    list_price   REAL,
    stock_state  TEXT    NOT NULL DEFAULT 'unknown',
    stock_qty    INTEGER,
    stock_source TEXT    NOT NULL DEFAULT '',
    source       TEXT    NOT NULL DEFAULT 'browser',
    ts           TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_vh_variant_ts ON variant_history(variant_id, ts);

CREATE TABLE IF NOT EXISTS fallback_rules (
    product_id          INTEGER PRIMARY KEY REFERENCES products(id) ON DELETE CASCADE,
    enabled             INTEGER NOT NULL DEFAULT 1,
    mode                TEXT    NOT NULL DEFAULT 'any',
    key_attrs           TEXT    NOT NULL DEFAULT '[]',
    selected_variants   TEXT    NOT NULL DEFAULT '[]',
    price_ceiling_pct   REAL    NOT NULL DEFAULT 20.0,
    max_price           REAL
);

CREATE TABLE IF NOT EXISTS fallback_events (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id         INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    main_variant_id    INTEGER REFERENCES variants(id),
    chosen_variant_id  INTEGER REFERENCES variants(id),
    state              TEXT    NOT NULL DEFAULT 'active',
    effective_price    REAL,
    reason             TEXT    NOT NULL DEFAULT '',
    created_at         TEXT    NOT NULL DEFAULT (datetime('now')),
    notified_at        TEXT,
    resolved_at        TEXT,
    outcome            TEXT    NOT NULL DEFAULT ''
);
"""


class DB:
    def __init__(self, path: str):
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        with self._lock:
            self.conn.executescript(_SCHEMA)
            self._migrate()

    def _migrate(self):
        with self._lock:
            # Ensure category and target_price columns in products
            cols_p = [r[1] for r in self.conn.execute("PRAGMA table_info(products)").fetchall()]
            if "category" not in cols_p:
                self.conn.execute("ALTER TABLE products ADD COLUMN category TEXT NOT NULL DEFAULT ''")
            if "target_price" not in cols_p:
                self.conn.execute("ALTER TABLE products ADD COLUMN target_price REAL")
            if "source" not in cols_p:
                self.conn.execute("ALTER TABLE products ADD COLUMN source TEXT NOT NULL DEFAULT 'user'")
            if "origin" not in cols_p:
                self.conn.execute("ALTER TABLE products ADD COLUMN origin TEXT NOT NULL DEFAULT ''")
            if "shop_country" not in cols_p:
                self.conn.execute("ALTER TABLE products ADD COLUMN shop_country TEXT NOT NULL DEFAULT ''")
            if "ships_from" not in cols_p:
                self.conn.execute("ALTER TABLE products ADD COLUMN ships_from TEXT NOT NULL DEFAULT ''")
            if "services" not in cols_p:
                self.conn.execute("ALTER TABLE products ADD COLUMN services TEXT NOT NULL DEFAULT ''")
            if "verified" not in cols_p:
                self.conn.execute("ALTER TABLE products ADD COLUMN verified INTEGER NOT NULL DEFAULT 1")
            if "fail_count" not in cols_p:
                self.conn.execute("ALTER TABLE products ADD COLUMN fail_count INTEGER NOT NULL DEFAULT 0")
            if "main_variant_id" not in cols_p:
                self.conn.execute("ALTER TABLE products ADD COLUMN main_variant_id INTEGER REFERENCES variants(id)")

            # Ensure campaign and voucher columns in price_history
            cols_ph = [r[1] for r in self.conn.execute("PRAGMA table_info(price_history)").fetchall()]
            if "campaign" not in cols_ph:
                self.conn.execute("ALTER TABLE price_history ADD COLUMN campaign TEXT NOT NULL DEFAULT ''")
            if "voucher_code" not in cols_ph:
                self.conn.execute("ALTER TABLE price_history ADD COLUMN voucher_code TEXT NOT NULL DEFAULT ''")
            if "voucher_discount" not in cols_ph:
                self.conn.execute("ALTER TABLE price_history ADD COLUMN voucher_discount REAL NOT NULL DEFAULT 0.0")
            if "final_price" not in cols_ph:
                self.conn.execute("ALTER TABLE price_history ADD COLUMN final_price REAL")

            self.conn.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS price_anomalies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_id INTEGER NOT NULL,
                    platform TEXT NOT NULL,
                    item_key TEXT NOT NULL,
                    name TEXT NOT NULL,
                    url TEXT NOT NULL,
                    price REAL NOT NULL,
                    baseline REAL NOT NULL,
                    baseline_type TEXT NOT NULL,
                    discount REAL NOT NULL,
                    stage TEXT NOT NULL DEFAULT 'confirming',
                    reject_reason TEXT,
                    admin_message_id INTEGER,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    confirmed_at TEXT,
                    resolved_at TEXT,
                    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
                )
            """)
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS keywords (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    keyword         TEXT    NOT NULL,
                    platform        TEXT    NOT NULL DEFAULT '',
                    active          INTEGER NOT NULL DEFAULT 1,
                    origin_filter   TEXT    NOT NULL DEFAULT 'vn',
                    ship_filter     TEXT    NOT NULL DEFAULT 'vn',
                    shop_filter     TEXT    NOT NULL DEFAULT 'any',
                    services_filter TEXT    NOT NULL DEFAULT '',
                    filters_json    TEXT    NOT NULL DEFAULT '{}',
                    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
                    last_run        TEXT,
                    last_scanned    INTEGER NOT NULL DEFAULT 0,
                    last_matched    INTEGER NOT NULL DEFAULT 0,
                    last_msg        TEXT,
                    UNIQUE(keyword, platform)
                )
            """)
            cols_k = [r[1] for r in self.conn.execute("PRAGMA table_info(keywords)").fetchall()]
            if "filters_json" not in cols_k:
                self.conn.execute("ALTER TABLE keywords ADD COLUMN filters_json TEXT NOT NULL DEFAULT '{}'")
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS keyword_products (
                    keyword_id  INTEGER NOT NULL REFERENCES keywords(id) ON DELETE CASCADE,
                    product_id  INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
                    verified    INTEGER NOT NULL DEFAULT 1,
                    matched_at  TEXT    NOT NULL DEFAULT (datetime('now')),
                    PRIMARY KEY(keyword_id, product_id)
                )
            """)
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS rejected_items (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    platform    TEXT    NOT NULL,
                    item_key    TEXT    NOT NULL,
                    keyword_id  INTEGER NOT NULL REFERENCES keywords(id) ON DELETE CASCADE,
                    reason      TEXT    NOT NULL DEFAULT '',
                    ts          TEXT    NOT NULL DEFAULT (datetime('now')),
                    UNIQUE(platform, item_key, keyword_id)
                )
            """)
            # Fix existing keyword products mistakenly set as 'user' source
            self.conn.execute("UPDATE products SET source='keyword' WHERE source='user' AND id IN (SELECT product_id FROM keyword_products)")

            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS variants (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_id  INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
                    variant_key TEXT    NOT NULL,
                    name        TEXT    NOT NULL,
                    attrs       TEXT    NOT NULL DEFAULT '{}',
                    active      INTEGER NOT NULL DEFAULT 1,
                    first_seen  TEXT    NOT NULL DEFAULT (datetime('now')),
                    last_seen   TEXT    NOT NULL DEFAULT (datetime('now')),
                    UNIQUE(product_id, variant_key)
                )
            """)
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_variants_product ON variants(product_id, active)")

            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS variant_history (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    variant_id   INTEGER NOT NULL REFERENCES variants(id) ON DELETE CASCADE,
                    price        REAL,
                    list_price   REAL,
                    stock_state  TEXT    NOT NULL DEFAULT 'unknown',
                    stock_qty    INTEGER,
                    stock_source TEXT    NOT NULL DEFAULT '',
                    source       TEXT    NOT NULL DEFAULT 'browser',
                    ts           TEXT    NOT NULL DEFAULT (datetime('now'))
                )
            """)
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_vh_variant_ts ON variant_history(variant_id, ts)")

            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS fallback_rules (
                    product_id          INTEGER PRIMARY KEY REFERENCES products(id) ON DELETE CASCADE,
                    enabled             INTEGER NOT NULL DEFAULT 1,
                    mode                TEXT    NOT NULL DEFAULT 'any',
                    key_attrs           TEXT    NOT NULL DEFAULT '[]',
                    selected_variants   TEXT    NOT NULL DEFAULT '[]',
                    price_ceiling_pct   REAL    NOT NULL DEFAULT 20.0,
                    max_price           REAL
                )
            """)

            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS fallback_events (
                    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_id         INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
                    main_variant_id    INTEGER REFERENCES variants(id),
                    chosen_variant_id  INTEGER REFERENCES variants(id),
                    state              TEXT    NOT NULL DEFAULT 'active',
                    effective_price    REAL,
                    reason             TEXT    NOT NULL DEFAULT '',
                    created_at         TEXT    NOT NULL DEFAULT (datetime('now')),
                    notified_at        TEXT,
                    resolved_at        TEXT,
                    outcome            TEXT    NOT NULL DEFAULT ''
                )
            """)
            # Canonicalize all stored product URLs
            from .adapters.playwright import canonicalize_url
            for row in self.conn.execute("SELECT id, url FROM products WHERE url IS NOT NULL").fetchall():
                pid, u = row[0], row[1]
                cu = canonicalize_url(u)
                if cu != u:
                    self.conn.execute("UPDATE products SET url = ? WHERE id = ?", (cu, pid))

            self.conn.commit()

    # ── Products ────────────────────────────────────────────────────────────

    def add_product_url(self, url: str, platform: str, item_key: str, source: str = "user") -> int:
        """Add or reactivate a product. Returns its id."""
        with self._lock:
            cur = self.conn.execute(
                """INSERT INTO products(platform, item_key, url, source)
                   VALUES(?, ?, ?, ?)
                   ON CONFLICT(platform, item_key) DO UPDATE SET
                       url=excluded.url,
                       active=1,
                       fail_count=0,
                       source=CASE WHEN excluded.source='user' THEN 'user' ELSE products.source END
                   RETURNING id""",
                (platform, item_key, url, source),
            )
            row = cur.fetchone()
            self.conn.commit()
            return row[0]

    def upsert_product_meta(self, snapshot: Snapshot, source: str = "keyword") -> int:
        """Insert or update product metadata from a fresh snapshot. Returns id."""
        category = getattr(snapshot, "category", "") or ""
        origin = getattr(snapshot, "origin", "") or ""
        shop_country = getattr(snapshot, "shop_country", "") or ""
        ships_from = getattr(snapshot, "ships_from", "") or ""
        services = getattr(snapshot, "services", "") or ""
        if isinstance(services, list):
            services = ",".join(services)
        verified = getattr(snapshot, "verified", 1)
        with self._lock:
            cur = self.conn.execute(
                """INSERT INTO products(platform, item_key, url, name, shop, category, rating, sold, origin, shop_country, ships_from, services, verified, source)
                   VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(platform, item_key) DO UPDATE SET
                     url=excluded.url, name=excluded.name, shop=excluded.shop,
                     category=CASE WHEN excluded.category != '' THEN excluded.category ELSE products.category END,
                     rating=excluded.rating, sold=excluded.sold,
                     origin=CASE WHEN excluded.origin != '' THEN excluded.origin ELSE products.origin END,
                     shop_country=CASE WHEN excluded.shop_country != '' THEN excluded.shop_country ELSE products.shop_country END,
                     ships_from=CASE WHEN excluded.ships_from != '' THEN excluded.ships_from ELSE products.ships_from END,
                     services=CASE WHEN excluded.services != '' THEN excluded.services ELSE products.services END,
                     verified=excluded.verified,
                     source=CASE WHEN products.source='user' THEN 'user' WHEN excluded.source='user' THEN 'user' ELSE excluded.source END
                   RETURNING id""",
                (snapshot.platform, snapshot.item_key, snapshot.url,
                 snapshot.name, snapshot.shop, category, snapshot.rating, snapshot.sold,
                 origin, shop_country, ships_from, services, verified, source),
            )
            row = cur.fetchone()
            self.conn.commit()
            return row[0]

    def update_product_from_snapshot(self, product_id: int, snapshot: Snapshot) -> int:
        """Update existing product with metadata and canonical key/URL from snapshot.
        If canonical key matches an existing record, handles merge safely. Returns target product_id.
        """
        category = getattr(snapshot, "category", "") or ""
        origin = getattr(snapshot, "origin", "") or ""
        shop_country = getattr(snapshot, "shop_country", "") or ""
        ships_from = getattr(snapshot, "ships_from", "") or ""
        services = getattr(snapshot, "services", "") or ""
        if isinstance(services, list):
            services = ",".join(services)
        verified = getattr(snapshot, "verified", 1)
        with self._lock:
            existing = self.conn.execute(
                "SELECT id FROM products WHERE platform = ? AND item_key = ?",
                (snapshot.platform, snapshot.item_key),
            ).fetchone()

            if existing and existing["id"] != product_id:
                target_id = existing["id"]
                self.conn.execute(
                    "UPDATE price_history SET product_id = ? WHERE product_id = ?",
                    (target_id, product_id),
                )
                self.conn.execute("DELETE FROM products WHERE id = ?", (product_id,))
                cur_id = target_id
            else:
                cur_id = product_id

            self.conn.execute(
                """UPDATE products
                   SET item_key = ?, url = ?, name = COALESCE(NULLIF(?, ''), name),
                       shop = COALESCE(NULLIF(?, ''), shop),
                       category = CASE WHEN ? != '' THEN ? ELSE category END,
                       rating = COALESCE(?, rating),
                       sold = COALESCE(?, sold),
                       origin = CASE WHEN ? != '' THEN ? ELSE origin END,
                       shop_country = CASE WHEN ? != '' THEN ? ELSE shop_country END,
                       ships_from = CASE WHEN ? != '' THEN ? ELSE ships_from END,
                       services = CASE WHEN ? != '' THEN ? ELSE services END,
                       verified = COALESCE(?, verified),
                       fail_count = 0
                   WHERE id = ?""",
                (
                    snapshot.item_key,
                    snapshot.url,
                    snapshot.name,
                    snapshot.shop,
                    category,
                    category,
                    snapshot.rating,
                    snapshot.sold,
                    origin,
                    origin,
                    shop_country,
                    shop_country,
                    ships_from,
                    ships_from,
                    services,
                    services,
                    verified,
                    cur_id,
                ),
            )
            self.conn.commit()
            return cur_id

    def increment_product_fail_count(self, product_id: int) -> int:
        with self._lock:
            row = self.conn.execute("SELECT fail_count FROM products WHERE id=?", (product_id,)).fetchone()
            new_count = (row["fail_count"] if row else 0) + 1
            self.conn.execute("UPDATE products SET fail_count=? WHERE id=?", (new_count, product_id))
            self.conn.commit()
            return new_count

    def reset_product_fail_count(self, product_id: int):
        with self._lock:
            self.conn.execute("UPDATE products SET fail_count=0 WHERE id=?", (product_id,))
            self.conn.commit()

    def get_active_products(self) -> list[sqlite3.Row]:
        with self._lock:
            return self.conn.execute(
                "SELECT * FROM products WHERE active=1 ORDER BY platform, CASE WHEN source='user' THEN 0 ELSE 1 END, id"
            ).fetchall()

    def get_active_tracked_products(self) -> list[sqlite3.Row]:
        with self._lock:
            return self.conn.execute(
                "SELECT * FROM products WHERE active=1 AND source='user' ORDER BY platform, id"
            ).fetchall()

    def get_tracked_products_with_latest_price(self) -> list[sqlite3.Row]:
        """Return user-tracked products (source='user', active=1) joined with latest price snapshot."""
        with self._lock:
            return self.conn.execute("""
                SELECT p.*,
                       ph.price            AS current_price,
                       ph.list_price       AS current_list_price,
                       ph.stock            AS current_stock,
                       ph.campaign         AS current_campaign,
                       ph.voucher_code     AS current_voucher_code,
                       ph.voucher_discount AS current_voucher_discount,
                       ph.final_price      AS current_final_price,
                       ph.ts               AS last_scanned
                FROM products p
                LEFT JOIN price_history ph ON ph.id = (
                    SELECT id FROM price_history
                    WHERE product_id = p.id
                    ORDER BY ts DESC LIMIT 1
                )
                WHERE p.active = 1 AND p.source = 'user'
                ORDER BY p.id DESC
            """).fetchall()

    def get_products_with_latest_price(self, include_inactive: bool = False) -> list[sqlite3.Row]:
        """For dashboard: products joined with their most recent price snapshot."""
        where_sql = "" if include_inactive else "WHERE p.active = 1"
        with self._lock:
            return self.conn.execute(f"""
                SELECT p.*,
                       ph.price            AS current_price,
                       ph.list_price       AS current_list_price,
                       ph.stock            AS current_stock,
                       ph.campaign         AS current_campaign,
                       ph.voucher_code     AS current_voucher_code,
                       ph.voucher_discount AS current_voucher_discount,
                       ph.final_price      AS current_final_price,
                       ph.ts               AS last_scanned,
                       COALESCE(
                           v.name,
                           (SELECT v2.name FROM variants v2
                            JOIN variant_history vh ON vh.variant_id = v2.id
                            WHERE v2.product_id = p.id AND vh.stock_state = 'in' AND vh.price = ph.price
                            ORDER BY vh.ts DESC LIMIT 1),
                           (SELECT v3.name FROM variants v3
                            JOIN variant_history vh2 ON vh2.variant_id = v3.id
                            WHERE v3.product_id = p.id
                            ORDER BY vh2.ts DESC, vh2.price ASC LIMIT 1)
                       ) AS active_variant_name,
                       (SELECT COUNT(*) FROM variants v_cnt WHERE v_cnt.product_id = p.id AND v_cnt.active = 1) AS variants_count
                FROM products p
                LEFT JOIN price_history ph ON ph.id = (
                    SELECT id FROM price_history
                    WHERE product_id = p.id
                    ORDER BY ts DESC LIMIT 1
                )
                LEFT JOIN variants v ON v.id = p.main_variant_id
                {where_sql}
                ORDER BY p.id DESC
            """).fetchall()

    # ── Price history ────────────────────────────────────────────────────────

    def save_snapshot(self, product_id: int, snapshot: Snapshot, campaign: str = ""):
        stock_int = None if snapshot.stock is None else int(snapshot.stock)
        v_code = getattr(snapshot, "voucher_code", "") or ""
        v_disc = getattr(snapshot, "voucher_discount", 0.0) or 0.0
        f_price = getattr(snapshot, "final_price", None)
        if f_price is None:
            f_price = snapshot.price
        with self._lock:
            self.conn.execute(
                """INSERT INTO price_history(product_id, price, list_price, stock, campaign, voucher_code, voucher_discount, final_price)
                   VALUES(?,?,?,?,?,?,?,?)""",
                (product_id, snapshot.price, snapshot.list_price, stock_int, campaign, v_code, v_disc, f_price),
            )
            self.conn.commit()

        # Upsert variants if present in snapshot
        if getattr(snapshot, "variants", None):
            self.upsert_variants(
                product_id,
                snapshot.variants,
                initial_sku_key=getattr(snapshot, "sku_from_url", None),
            )

    def upsert_variants(
        self,
        product_id: int,
        variants: list[VariantInfo],
        initial_sku_key: str | None = None,
        source: str = "browser",
    ):
        """
        Upsert variants for a product and record variant_history with delta tracking.
        If product has no main_variant_id, auto-assign based on initial_sku_key or lowest in-stock variant.
        """
        if not variants:
            return

        with self._lock:
            prod = self.conn.execute(
                "SELECT main_variant_id FROM products WHERE id=?", (product_id,)
            ).fetchone()
            current_main_id = prod["main_variant_id"] if prod and "main_variant_id" in prod.keys() else None

            target_main_id = current_main_id
            best_in_stock_id = None
            best_in_stock_price = float("inf")

            for v in variants:
                attrs_json = json.dumps(v.attrs, ensure_ascii=False) if v.attrs else "{}"
                cur = self.conn.execute(
                    """INSERT INTO variants(product_id, variant_key, name, attrs, active, last_seen)
                       VALUES(?, ?, ?, ?, 1, datetime('now'))
                       ON CONFLICT(product_id, variant_key) DO UPDATE SET
                           name=excluded.name,
                           attrs=CASE WHEN excluded.attrs != '{}' THEN excluded.attrs ELSE variants.attrs END,
                           active=1,
                           last_seen=datetime('now')
                       RETURNING id""",
                    (product_id, str(v.variant_key), v.name, attrs_json),
                )
                var_row = cur.fetchone()
                var_id = var_row[0]

                # Delta tracking for variant_history
                last_hist = self.conn.execute(
                    """SELECT price, list_price, stock_state FROM variant_history
                       WHERE variant_id=? ORDER BY ts DESC LIMIT 1""",
                    (var_id,),
                ).fetchone()

                needs_insert = False
                if not last_hist:
                    needs_insert = True
                else:
                    if (
                        last_hist["price"] != v.price
                        or last_hist["list_price"] != v.list_price
                        or last_hist["stock_state"] != v.stock_state
                    ):
                        needs_insert = True

                if needs_insert:
                    self.conn.execute(
                        """INSERT INTO variant_history(variant_id, price, list_price, stock_state, stock_qty, stock_source, source)
                           VALUES(?, ?, ?, ?, ?, ?, ?)""",
                        (
                            var_id,
                            v.price,
                            v.list_price,
                            v.stock_state,
                            v.stock_qty,
                            v.stock_source,
                            source,
                        ),
                    )

                if initial_sku_key and str(v.variant_key) == str(initial_sku_key):
                    target_main_id = var_id
                elif (
                    v.stock_state == "in"
                    and v.price is not None
                    and v.price > 0
                    and v.price < best_in_stock_price
                ):
                    best_in_stock_price = v.price
                    best_in_stock_id = var_id

            # Assign main_variant_id if not currently set
            if not current_main_id:
                final_main_id = target_main_id or best_in_stock_id
                if final_main_id:
                    self.conn.execute(
                        "UPDATE products SET main_variant_id=? WHERE id=?",
                        (final_main_id, product_id),
                    )

            # Ensure default fallback_rules row exists
            self.conn.execute(
                """INSERT INTO fallback_rules(product_id, enabled, mode, price_ceiling_pct)
                   VALUES(?, 1, 'any', 20.0)
                   ON CONFLICT(product_id) DO NOTHING""",
                (product_id,),
            )

            self.conn.commit()

    def get_product_variants(self, product_id: int) -> list[sqlite3.Row]:
        """Return all active variants for a product with latest price and stock status."""
        with self._lock:
            return self.conn.execute(
                """SELECT v.*,
                          vh.price,
                          vh.list_price,
                          vh.stock_state,
                          vh.stock_qty,
                          vh.stock_source,
                          vh.ts as last_updated
                   FROM variants v
                   LEFT JOIN variant_history vh ON vh.id = (
                       SELECT id FROM variant_history WHERE variant_id = v.id ORDER BY ts DESC LIMIT 1
                   )
                   WHERE v.product_id = ? AND v.active = 1
                   ORDER BY v.id ASC""",
                (product_id,),
            ).fetchall()

    def get_variant(self, variant_id: int) -> sqlite3.Row | None:
        with self._lock:
            return self.conn.execute(
                "SELECT * FROM variants WHERE id=?", (variant_id,)
            ).fetchone()

    def set_main_variant(self, product_id: int, variant_id: int):
        with self._lock:
            self.conn.execute(
                "UPDATE products SET main_variant_id=? WHERE id=?",
                (variant_id, product_id),
            )
            self.conn.commit()

    def get_fallback_rule(self, product_id: int) -> sqlite3.Row | None:
        with self._lock:
            return self.conn.execute(
                "SELECT * FROM fallback_rules WHERE product_id=?", (product_id,)
            ).fetchone()

    def get_active_fallback_event(self, product_id: int) -> sqlite3.Row | None:
        with self._lock:
            return self.conn.execute(
                """SELECT * FROM fallback_events
                   WHERE product_id = ? AND state IN ('suspect_out', 'active')
                   ORDER BY id DESC LIMIT 1""",
                (product_id,),
            ).fetchone()

    def evaluate_variant_state(self, product_id: int) -> dict:
        """
        Evaluate stock state machine for product's main variant and fallback logic:
        - CÒN HÀNG -> In stock (resolves any active fallback events)
        - NGHI HẾT (suspect_out) -> First detection of out of stock (triggers fast verification scan)
        - HẾT HÀNG (active) -> Confirmed out of stock (evaluates and applies fallback variant)
        """
        from .detector import is_accessory_or_fake

        with self._lock:
            prod = self.conn.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
            if not prod:
                return {"action": "none"}

            main_vid = prod["main_variant_id"] if "main_variant_id" in prod.keys() else None
            if not main_vid:
                return {"action": "none"}

            # Fetch all active variants with their latest state
            variants = self.conn.execute(
                """SELECT v.*, vh.price, vh.list_price, vh.stock_state, vh.stock_qty
                   FROM variants v
                   LEFT JOIN variant_history vh ON vh.id = (
                       SELECT id FROM variant_history WHERE variant_id = v.id ORDER BY ts DESC LIMIT 1
                   )
                   WHERE v.product_id = ? AND v.active = 1""",
                (product_id,),
            ).fetchall()

            if not variants:
                return {"action": "none"}

            main_var = next((v for v in variants if v["id"] == main_vid), None)
            if not main_var:
                return {"action": "none"}

            active_event = self.conn.execute(
                """SELECT * FROM fallback_events
                   WHERE product_id = ? AND state IN ('suspect_out', 'active')
                   ORDER BY id DESC LIMIT 1""",
                (product_id,),
            ).fetchone()

            # Case A: Main variant is IN STOCK
            if main_var["stock_state"] == "in":
                if active_event:
                    outcome = "false_alarm" if active_event["state"] == "suspect_out" else "main_restocked"
                    self.conn.execute(
                        """UPDATE fallback_events
                           SET state = 'resolved', resolved_at = datetime('now'), outcome = ?
                           WHERE id = ?""",
                        (outcome, active_event["id"]),
                    )
                    self.conn.commit()
                    return {"action": "resolved", "outcome": outcome, "main_variant_id": main_vid}
                return {"action": "in_stock", "main_variant_id": main_vid}

            # Case B: Main variant is OUT OF STOCK (or unknown)
            if main_var["stock_state"] in ("out", "unknown"):
                # B.1: First time detected out of stock -> suspect_out (Fast scan trigger)
                if not active_event:
                    self.conn.execute(
                        """INSERT INTO fallback_events(product_id, main_variant_id, state, reason, created_at)
                           VALUES(?, ?, 'suspect_out', 'Nghi hết hàng (lần 1) - chờ quét xác minh', datetime('now'))""",
                        (product_id, main_vid),
                    )
                    self.conn.commit()
                    return {"action": "suspect_out", "product_id": product_id, "main_variant_id": main_vid}

                # B.2: Second time (confirmed out of stock) -> select/verify fallback variant
                rule = self.conn.execute(
                    "SELECT * FROM fallback_rules WHERE product_id=?", (product_id,)
                ).fetchone()
                ceiling_pct = float(rule["price_ceiling_pct"]) if rule and "price_ceiling_pct" in rule.keys() else 20.0
                enabled = int(rule["enabled"]) if rule and "enabled" in rule.keys() else 1

                if not enabled:
                    if active_event["state"] != "active":
                        self.conn.execute(
                            "UPDATE fallback_events SET state='active', reason='Thay thế bị tắt bởi quy tắc' WHERE id=?",
                            (active_event["id"],),
                        )
                        self.conn.commit()
                    return {"action": "disabled"}

                # Reference price for main variant
                ref_row = self.conn.execute(
                    """SELECT price FROM variant_history
                       WHERE variant_id = ? AND price IS NOT NULL AND price > 0
                       ORDER BY ts DESC LIMIT 1""",
                    (main_vid,),
                ).fetchone()
                ref_price = ref_row["price"] if ref_row else (main_var["price"] or 0.0)
                price_ceiling = ref_price * (1.0 + ceiling_pct / 100.0) if ref_price > 0 else float("inf")

                candidates = []
                for v in variants:
                    if v["id"] == main_vid:
                        continue
                    if v["stock_state"] != "in":
                        continue
                    p_val = v["price"]
                    if not p_val or p_val <= 0:
                        continue
                    if p_val > price_ceiling:
                        continue
                    if is_accessory_or_fake(v["name"] or "", price=p_val, baseline=ref_price):
                        continue
                    candidates.append(v)

                if candidates:
                    best_v = min(candidates, key=lambda c: c["price"])
                    self.conn.execute(
                        """UPDATE fallback_events
                           SET state = 'active',
                               chosen_variant_id = ?,
                               effective_price = ?,
                               reason = ?
                           WHERE id = ?""",
                        (
                            best_v["id"],
                            best_v["price"],
                            f"Tạm thay: {best_v['name']} ({best_v['price']:,.0f}₫)",
                            active_event["id"],
                        ),
                    )
                    # Sync latest price_history row so dashboard & alerts reflect in-stock price
                    latest_ph = self.conn.execute(
                        "SELECT id FROM price_history WHERE product_id=? ORDER BY ts DESC LIMIT 1",
                        (product_id,),
                    ).fetchone()
                    if latest_ph:
                        self.conn.execute(
                            "UPDATE price_history SET price=?, final_price=?, stock=1 WHERE id=?",
                            (best_v["price"], best_v["price"], latest_ph["id"]),
                        )
                    self.conn.commit()
                    return {
                        "action": "fallback_applied",
                        "product_id": product_id,
                        "chosen_variant_id": best_v["id"],
                        "chosen_variant_name": best_v["name"],
                        "price": best_v["price"],
                    }
                else:
                    self.conn.execute(
                        """UPDATE fallback_events
                           SET state = 'active', chosen_variant_id = NULL, reason = 'Không có biến thể thay thế hợp lệ còn hàng'
                           WHERE id = ?""",
                        (active_event["id"],),
                    )
                    self.conn.commit()
                    return {"action": "no_candidates", "product_id": product_id}

            return {"action": "none"}


    def get_latest_price(self, product_id: int) -> float | None:
        with self._lock:
            row = self.conn.execute(
                "SELECT price FROM price_history WHERE product_id=? AND price > 0 ORDER BY ts DESC LIMIT 1",
                (product_id,),
            ).fetchone()
            return row["price"] if row else None

    def get_price_history_30d(self, product_id: int, exclude_latest: bool = False) -> list[float]:
        """Return prices from the last 30 days, newest first.

        exclude_latest=True: skip the most-recently inserted row (i.e. the one
        just saved in this scan cycle) so detector compares against prior history.
        """
        with self._lock:
            rows = self.conn.execute(
                """SELECT COALESCE(final_price, price) FROM price_history
                   WHERE product_id=? AND price > 0 AND ts >= datetime('now', '-30 days')
                   ORDER BY ts DESC""",
                (product_id,),
            ).fetchall()
            prices = [r[0] for r in rows if r[0] is not None]
            return prices[1:] if exclude_latest and prices else prices

    def get_price_history_for_chart(self, product_id: int) -> list[dict]:
        with self._lock:
            rows = self.conn.execute(
                """SELECT ts, price, list_price, campaign FROM price_history
                   WHERE product_id=?
                   ORDER BY ts ASC""",
                (product_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_active_campaign_name(self, dt=None) -> str | None:
        """Find active custom campaign in campaigns table."""
        now_str = dt.strftime("%Y-%m-%d %H:%M:%S") if dt else "datetime('now')"
        with self._lock:
            row = self.conn.execute(
                "SELECT name FROM campaigns WHERE ? BETWEEN start_date AND end_date LIMIT 1",
                (now_str,),
            ).fetchone()
            return row[0] if row else None

    # ── Alerts ───────────────────────────────────────────────────────────────

    def get_alert(self, product_id: int) -> sqlite3.Row | None:
        with self._lock:
            return self.conn.execute(
                "SELECT last_price, sent_at FROM alerts WHERE product_id=?",
                (product_id,),
            ).fetchone()

    def clear_alert(self, product_id: int):
        with self._lock:
            self.conn.execute("DELETE FROM alerts WHERE product_id=?", (product_id,))
            self.conn.commit()

    def upsert_alert(self, product_id: int, price: float):
        with self._lock:
            self.conn.execute(
                """INSERT INTO alerts(product_id, last_price, sent_at)
                   VALUES(?, ?, datetime('now'))
                   ON CONFLICT(product_id) DO UPDATE SET
                     last_price=excluded.last_price, sent_at=excluded.sent_at""",
                (product_id, price),
            )
            self.conn.commit()

    # ── Scan log ─────────────────────────────────────────────────────────────

    def log_scan(self, ok: int, fail: int, msg: str | None = None):
        with self._lock:
            self.conn.execute(
                "INSERT INTO scan_log(ok, fail, msg) VALUES(?,?,?)", (ok, fail, msg)
            )
            self.conn.commit()

    def get_last_scan(self) -> sqlite3.Row | None:
        with self._lock:
            return self.conn.execute(
                "SELECT * FROM scan_log ORDER BY ts DESC LIMIT 1"
            ).fetchone()

    def set_target_price(self, product_id: int, target_price: float | None):
        """Set or clear desired target price for a product."""
        with self._lock:
            self.conn.execute(
                "UPDATE products SET target_price=? WHERE id=?",
                (target_price, product_id),
            )
            self.conn.execute("DELETE FROM alerts WHERE product_id=?", (product_id,))
            self.conn.commit()

    def get_product(self, product_id: int) -> sqlite3.Row | None:
        with self._lock:
            return self.conn.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()

    def get_product_by_ref(self, ref: str | int) -> sqlite3.Row | None:
        """Find product by id or url/item_key."""
        if ref is None:
            return None
        with self._lock:
            if isinstance(ref, int) or (isinstance(ref, str) and ref.strip().isdigit()):
                return self.conn.execute("SELECT * FROM products WHERE id=?", (int(ref),)).fetchone()
            if isinstance(ref, str):
                s = ref.strip()
                # 1. Direct url match
                row = self.conn.execute("SELECT * FROM products WHERE url=?", (s,)).fetchone()
                if row:
                    return row
                # 2. Clean url match (without query params)
                clean_url = s.split("?")[0]
                row = self.conn.execute("SELECT * FROM products WHERE url=?", (clean_url,)).fetchone()
                if row:
                    return row
                # 3. Match by platform + item_key
                if "shopee.vn" in s or "lazada.vn" in s:
                    try:
                        from .adapters.base import BaseAdapter
                        platform = BaseAdapter.parse_platform(s)
                        item_key = BaseAdapter.parse_item_key(s)
                        return self.conn.execute(
                            "SELECT * FROM products WHERE platform=? AND item_key=?", (platform, item_key)
                        ).fetchone()
                    except Exception:
                        pass
            return None

    def delete_product(self, product_id: int):
        """Remove a product and its history from active tracking."""
        self.delete_products([product_id])

    def delete_products(self, product_ids: list[int]):
        """Remove multiple products and their history from active tracking."""
        if not product_ids:
            return
        with self._lock:
            placeholders = ",".join("?" for _ in product_ids)
            # foreign keys are not enforced in this connection: delete children explicitly
            self.conn.execute(f"DELETE FROM variant_history WHERE variant_id IN (SELECT id FROM variants WHERE product_id IN ({placeholders}))", product_ids)
            for table in ("price_history", "alerts", "variants", "fallback_rules", "fallback_events", "price_anomalies", "keyword_products"):
                self.conn.execute(f"DELETE FROM {table} WHERE product_id IN ({placeholders})", product_ids)
            self.conn.execute(f"DELETE FROM products WHERE id IN ({placeholders})", product_ids)
            self.conn.commit()

    def purge_junk_flash_sales(self, min_price: float) -> int:
        """Permanently delete flash sale products whose list_price and price are below min_price.
        Safely preserves user-tracked products (source='user'). Returns count of deleted products."""
        with self._lock:
            cur = self.conn.execute("""
                SELECT p.id FROM products p
                LEFT JOIN price_history ph ON ph.id = (
                    SELECT id FROM price_history
                    WHERE product_id = p.id
                    ORDER BY ts DESC LIMIT 1
                )
                WHERE p.source = 'flash_sale'
                  AND MAX(COALESCE(ph.list_price, 0), COALESCE(ph.price, 0)) < ?
            """, (min_price,))
            pids = [row[0] for row in cur.fetchall()]
        if pids:
            self.delete_products(pids)
        return len(pids)

    def get_setting(self, key: str, default: str = "") -> str:
        with self._lock:
            row = self.conn.execute(
                "SELECT value FROM settings WHERE key=?", (key,)
            ).fetchone()
            return row[0] if row else default

    def set_setting(self, key: str, value: str):
        with self._lock:
            self.conn.execute(
                "INSERT INTO settings(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, str(value)),
            )
            self.conn.commit()

    # ── Price Anomalies (Lỗi giá) ──────────────────────────────────────────

    def create_anomaly(
        self,
        product_id: int,
        platform: str,
        item_key: str,
        name: str,
        url: str,
        price: float,
        baseline: float,
        baseline_type: str,
        discount: float,
        stage: str = "confirming",
        admin_message_id: int | None = None,
    ) -> int:
        with self._lock:
            cur = self.conn.execute(
                """INSERT INTO price_anomalies(
                    product_id, platform, item_key, name, url, price, baseline, baseline_type, discount, stage, admin_message_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (product_id, platform, item_key, name, url, price, baseline, baseline_type, discount, stage, admin_message_id),
            )
            self.conn.commit()
            return cur.lastrowid

    def get_anomaly(self, anomaly_id: int) -> sqlite3.Row | None:
        with self._lock:
            return self.conn.execute("SELECT * FROM price_anomalies WHERE id = ?", (anomaly_id,)).fetchone()

    def get_recent_anomaly_for_product(self, product_id: int, hours: int = 4) -> sqlite3.Row | None:
        """Find recent anomaly to avoid spamming the same product repeatedly."""
        with self._lock:
            return self.conn.execute(
                """SELECT * FROM price_anomalies
                   WHERE product_id = ? AND created_at >= datetime('now', ?)
                   ORDER BY id DESC LIMIT 1""",
                (product_id, f"-{hours} hours"),
            ).fetchone()

    def get_anomalies(self, limit: int = 50) -> list[sqlite3.Row]:
        with self._lock:
            return self.conn.execute(
                "SELECT * FROM price_anomalies ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()

    def update_anomaly_stage(self, anomaly_id: int, stage: str, reject_reason: str | None = None):
        with self._lock:
            now_col = "confirmed_at = datetime('now')" if stage == "confirmed" else "resolved_at = datetime('now')"
            self.conn.execute(
                f"""UPDATE price_anomalies
                    SET stage = ?, reject_reason = COALESCE(?, reject_reason), {now_col}
                    WHERE id = ?""",
                (stage, reject_reason, anomaly_id),
            )
            self.conn.commit()

    def update_anomaly_message_id(self, anomaly_id: int, message_id: int):
        with self._lock:
            self.conn.execute(
                "UPDATE price_anomalies SET admin_message_id = ? WHERE id = ?",
                (message_id, anomaly_id),
            )
            self.conn.commit()

    # ── Keywords & Keyword Tracking ──────────────────────────────────────────

    def add_or_update_keyword(
        self,
        keyword: str,
        platform: str | dict = "",
        origin_filter: str = "vn",
        ship_filter: str = "vn",
        shop_filter: str = "any",
        services_filter: str = "",
        filters_json: str = "{}",
    ) -> int:
        if isinstance(platform, dict):
            f = platform
            platform = str(f.get("platform", "all") or "all")
            origin_filter = f.get("origin_filter", origin_filter)
            ship_filter = f.get("ship_filter", ship_filter)
            shop_filter = f.get("shop_filter", shop_filter)
            svcs = f.get("services", services_filter)
            services_filter = ",".join(svcs) if isinstance(svcs, list) else str(svcs or "")
            filters_json = json.dumps(f)
        elif not filters_json or filters_json == "{}":
            svcs_list = [s.strip() for s in services_filter.split(",") if s.strip()] if services_filter else []
            filters_json = json.dumps({
                "origin_filter": origin_filter,
                "ship_filter": ship_filter,
                "shop_filter": shop_filter,
                "services": svcs_list,
                "platform": platform,
            })

        with self._lock:
            existing = self.conn.execute(
                "SELECT id, origin_filter, ship_filter, shop_filter, services_filter, filters_json FROM keywords WHERE keyword = ? AND platform = ?",
                (keyword.strip(), platform.strip()),
            ).fetchone()

            if existing:
                kid = existing["id"]
                if (
                    existing["origin_filter"] != origin_filter
                    or existing["ship_filter"] != ship_filter
                    or existing["shop_filter"] != shop_filter
                    or existing["services_filter"] != services_filter
                ):
                    self.clear_rejected_items(kid)

                self.conn.execute(
                    """UPDATE keywords
                       SET origin_filter = ?, ship_filter = ?, shop_filter = ?, services_filter = ?, filters_json = ?, active = 1
                       WHERE id = ?""",
                    (origin_filter, ship_filter, shop_filter, services_filter, filters_json, kid),
                )
                self.conn.commit()
                return kid

            cur = self.conn.execute(
                """INSERT INTO keywords(keyword, platform, origin_filter, ship_filter, shop_filter, services_filter, filters_json)
                   VALUES(?, ?, ?, ?, ?, ?, ?)
                   RETURNING id""",
                (keyword.strip(), platform.strip(), origin_filter, ship_filter, shop_filter, services_filter, filters_json),
            )
            row = cur.fetchone()
            self.conn.commit()
            return row[0]

    def get_keyword(self, keyword_id: int) -> dict | None:
        with self._lock:
            row = self.conn.execute("SELECT * FROM keywords WHERE id = ?", (keyword_id,)).fetchone()
            return dict(row) if row else None

    def get_keywords(self, active_only: bool = False) -> list[dict]:
        with self._lock:
            sql = """
                SELECT k.*, COUNT(kp.product_id) AS product_count
                FROM keywords k
                LEFT JOIN keyword_products kp ON k.id = kp.keyword_id
            """
            if active_only:
                sql += " WHERE k.active = 1 "
            sql += " GROUP BY k.id ORDER BY k.id DESC"
            rows = self.conn.execute(sql).fetchall()
            results = []
            for r in rows:
                d = dict(r)
                if not d.get("filters_json") or d["filters_json"] == "{}":
                    svcs = [s.strip() for s in (d.get("services_filter") or "").split(",") if s.strip()]
                    d["filters_json"] = json.dumps({
                        "origin_filter": d.get("origin_filter", "vn"),
                        "ship_filter": d.get("ship_filter", "vn"),
                        "shop_filter": d.get("shop_filter", "any"),
                        "services": svcs,
                        "platform": d.get("platform", "all"),
                    })
                results.append(d)
            return results

    def delete_keyword(self, keyword_id: int) -> bool:
        with self._lock:
            cur = self.conn.execute("DELETE FROM keywords WHERE id = ?", (keyword_id,))
            self.conn.commit()
            return cur.rowcount > 0

    def set_keyword_active(self, keyword_id: int, active: bool):
        with self._lock:
            self.conn.execute("UPDATE keywords SET active = ? WHERE id = ?", (1 if active else 0, keyword_id))
            self.conn.commit()

    def update_keyword_stats(self, keyword_id: int, scanned: int, matched: int, msg: str = ""):
        with self._lock:
            self.conn.execute(
                """UPDATE keywords
                   SET last_run = datetime('now'), last_scanned = ?, last_matched = ?, last_msg = ?
                   WHERE id = ?""",
                (scanned, matched, msg, keyword_id),
            )
            self.conn.commit()

    def link_keyword_product(self, keyword_id: int, product_id: int, verified: int = 1):
        with self._lock:
            self.conn.execute(
                """INSERT INTO keyword_products(keyword_id, product_id, verified)
                   VALUES(?, ?, ?)
                   ON CONFLICT(keyword_id, product_id) DO UPDATE SET verified = excluded.verified, matched_at = datetime('now')""",
                (keyword_id, product_id, verified),
            )
            self.conn.commit()

    def get_keyword_products(self, keyword_id: int | None = None) -> list[dict]:
        with self._lock:
            sql = """
                SELECT p.*, kp.keyword_id, kp.verified AS match_verified, kp.matched_at,
                       k.keyword AS keyword_name,
                       ph.price AS current_price,
                       ph.list_price AS current_list_price,
                       ph.final_price AS current_final_price,
                       ph.voucher_code AS current_voucher_code,
                       ph.voucher_discount AS current_voucher_discount
                FROM keyword_products kp
                JOIN products p ON kp.product_id = p.id
                JOIN keywords k ON kp.keyword_id = k.id
                LEFT JOIN price_history ph ON ph.id = (
                    SELECT id FROM price_history
                    WHERE product_id = p.id
                    ORDER BY ts DESC LIMIT 1
                )
            """
            params = []
            if keyword_id is not None:
                sql += " WHERE kp.keyword_id = ?"
                params.append(keyword_id)
            sql += " ORDER BY kp.matched_at DESC"
            rows = self.conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]

    def is_item_rejected(self, platform: str, item_key: str, keyword_id: int, max_age_days: int = 7) -> bool:
        with self._lock:
            row = self.conn.execute(
                """SELECT id FROM rejected_items
                   WHERE platform = ? AND item_key = ? AND keyword_id = ?
                     AND ts >= datetime('now', ?)""",
                (platform, item_key, keyword_id, f"-{max_age_days} days"),
            ).fetchone()
            return row is not None

    def record_rejected_item(self, platform: str, item_key: str, keyword_id: int, reason: str = ""):
        with self._lock:
            self.conn.execute(
                """INSERT INTO rejected_items(platform, item_key, keyword_id, reason, ts)
                   VALUES(?, ?, ?, ?, datetime('now'))
                   ON CONFLICT(platform, item_key, keyword_id) DO UPDATE SET
                       reason = excluded.reason, ts = datetime('now')""",
                (platform, item_key, keyword_id, reason),
            )
            self.conn.commit()

    def clear_rejected_items(self, keyword_id: int):
        with self._lock:
            self.conn.execute("DELETE FROM rejected_items WHERE keyword_id = ?", (keyword_id,))
            self.conn.commit()

    # ─────────────────────────────────────────────────────────────────────────

    def close(self):
        with self._lock:
            self.conn.close()
