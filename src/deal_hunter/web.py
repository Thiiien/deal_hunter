import html
import re
import json
import logging
import threading
from pathlib import Path

from flask import Flask, jsonify, request, send_file

from .config import Config
from .db import DB
from .detector import detect
from .login import check_session_valid, interactive_login
from .models import DealStatus
from .scanner import Scanner

log = logging.getLogger(__name__)

# Shared login state — only one login attempt at a time
_login_state: dict = {"running": False, "result": None}  # result: True/False/None

_DASHBOARD = Path(__file__).parent.parent.parent / "templates" / "dashboard.html"


def create_app(config: Config, db: DB, scanner: Scanner) -> Flask:
    app = Flask(__name__)
    app.config["JSON_SORT_KEYS"] = False

    # ── Pages ────────────────────────────────────────────────────────────────

    @app.get("/")
    def index():
        return send_file(_DASHBOARD)

    # ── API ──────────────────────────────────────────────────────────────────

    @app.get("/api/summary")
    def api_summary():
        from .campaign import get_active_campaign
        last = db.get_last_scan()
        products = db.get_products_with_latest_price(include_inactive=True)
        user_products = [p for p in products if dict(p).get("source", "user") == "user"]
        deal_count = sum(
            1 for p in user_products
            if _quick_detect(db, p, config) == DealStatus.REAL_DEAL
        )
        shopee_count = sum(1 for p in user_products if p["platform"] == "shopee")
        lazada_count = sum(1 for p in user_products if p["platform"] == "lazada")
        return jsonify({
            "total_products": len(user_products),
            "shopee_count": shopee_count,
            "lazada_count": lazada_count,
            "deal_count": deal_count,
            "active_campaign": get_active_campaign(db),
            "last_scan": dict(last) if last else None,
            "scan_interval_min": config.scan_interval_min,
            "keyword_interval_min": getattr(config, "keyword_interval_min", 180),
            "megasale_interval_min": getattr(config, "megasale_interval_min", 60),
            "price_error_interval_min": getattr(config, "price_error_interval_min", 60),
            "tmall_interval_min": getattr(config, "tmall_interval_min", 120),
            "tmall_scan_enabled": getattr(config, "tmall_scan_enabled", True),
            "tmall_min_price": getattr(config, "tmall_min_price", 100000.0),
            "tmall_max_price": getattr(config, "tmall_max_price", 20000000.0),
        })


    @app.get("/api/products")
    def api_products():
        rows = db.get_products_with_latest_price(include_inactive=True)
        result = []
        for p in rows:
            d = dict(p)
            d["name"] = html.escape(d.get("name") or "")
            detection = _quick_detect_full(db, p, config)
            status = detection.status if detection else None
            d["deal_status"] = status.value if status else None

            # Category extraction
            cat = d.get("category") or ""
            d["top_category"] = cat.split(" > ")[0].strip() if cat else "Khác"

            # Discount calculation
            disc_hist = detection.disc_hist if detection else None
            disc_list = detection.disc_list if detection else None
            eff_disc = 0
            if disc_hist is not None and disc_hist > 0:
                eff_disc = round(disc_hist * 100)
            elif d.get("current_price") and d.get("current_list_price") and d["current_price"] < d["current_list_price"]:
                eff_disc = round((1 - d["current_price"] / d["current_list_price"]) * 100)
            d["discount_percent"] = eff_disc

            # Deep deal detection for Mega Sale
            is_deep = False
            base_val = max(d.get("current_list_price") or 0.0, d.get("current_price") or 0.0)
            if base_val >= config.deal_min_original_price:
                if status == DealStatus.REAL_DEAL:
                    is_deep = True
                elif disc_hist is not None and disc_hist >= 0.20:
                    is_deep = True
                elif d.get("current_campaign") and disc_list is not None and disc_list >= 0.30:
                    is_deep = True
                elif d.get("current_price") and d.get("current_list_price") and (1 - d["current_price"] / d["current_list_price"]) >= 0.30:
                    is_deep = True
                elif d.get("target_price") and d.get("current_price") and d["current_price"] <= d["target_price"]:
                    is_deep = True
            d["is_deep_deal"] = is_deep
            d["source"] = d.get("source") or "user"
            d["is_out_of_stock"] = (d.get("current_stock") == 0)

            # Skip junk flash sale items with baseline < deal_min_original_price
            if d["source"] == "flash_sale" and base_val < config.deal_min_original_price:
                continue

            # Enforce TMALL category and price range filter for real-time display
            if d["source"] == "lazada_tmall":
                tm_price = d.get("current_price") or 0.0
                tm_min = getattr(config, "tmall_min_price", 100000.0)
                tm_max = getattr(config, "tmall_max_price", 20000000.0)
                if tm_price < tm_min or tm_price > tm_max:
                    continue
                if d.get("category") not in ("Thiết Bị Điện Tử", "Phụ Kiện Điện Tử"):
                    continue

            # Variant extraction and clean product name (ADR 0061)
            var_count = d.get("variants_count") or 0
            var_name = (d.get("active_variant_name") or "").strip()
            raw_title = d.get("name") or ""

            if (not var_name or var_name.startswith("Phân loại ")) and "(" in raw_title and raw_title.endswith(")"):
                m = re.search(r"\(([^()]+)\)$", raw_title)
                if m and var_count > 1:
                    var_name = m.group(1).strip()

            clean_title = raw_title
            if var_count > 1 and var_name:
                if f"({var_name})" in clean_title:
                    clean_title = clean_title.replace(f"({var_name})", "").strip()
                elif "(" in clean_title and clean_title.endswith(")"):
                    clean_title = re.sub(r"\s*\([^()]+\)$", "", clean_title).strip()

            d["clean_name"] = clean_title
            d["variant_name"] = html.escape(var_name)
            d["variants_count"] = var_count

            result.append(d)
        return jsonify(result)

    @app.post("/api/products")
    def api_add_product():
        data = request.get_json(silent=True) or {}
        url = (data.get("url") or "").strip()
        if not url:
            return jsonify({"error": "url required"}), 400
        from .adapters.base import BaseAdapter
        from .adapters.playwright import canonicalize_url
        url = canonicalize_url(url)
        platform = BaseAdapter.parse_platform(url)
        if platform not in ("shopee", "lazada"):
            return jsonify({"error": "Chỉ hỗ trợ link Shopee và Lazada"}), 400
        item_key = BaseAdapter.parse_item_key(url)
        pid = db.add_product_url(url, platform, item_key, source="user")
        target_price = data.get("target_price")
        if target_price is not None:
            try:
                tp_val = float(target_price)
                if tp_val > 0:
                    db.set_target_price(pid, tp_val)
            except (ValueError, TypeError):
                pass

        if scanner:
            def _instant_scan():
                try:
                    scanner.scan_product(pid)
                except Exception as err:
                    log.warning("Instant scan error for product #%d: %s", pid, err)
            threading.Thread(target=_instant_scan, daemon=True, name=f"instant-scan-{pid}").start()
        return jsonify({"id": pid, "platform": platform, "item_key": item_key, "target_price": target_price})

    @app.patch("/api/products/<int:pid>/target_price")
    def api_set_target_price(pid: int):
        data = request.get_json(silent=True) or {}
        raw = data.get("target_price")
        if raw is not None and str(raw).strip() != "":
            try:
                target_val = float(raw)
                if target_val <= 0:
                    return jsonify({"error": "Giá mong muốn phải lớn hơn 0"}), 400
            except (ValueError, TypeError):
                return jsonify({"error": "Giá không hợp lệ"}), 400
        else:
            target_val = None
        db.set_target_price(pid, target_val)
        return jsonify({"id": pid, "target_price": target_val})

    @app.delete("/api/products/<int:pid>")
    def api_delete_product(pid: int):
        db.delete_product(pid)
        return jsonify({"status": "ok", "deleted_id": pid})

    @app.post("/api/products/<int:pid>/reactivate")
    def api_reactivate_product(pid: int):
        with db._lock:
            db.conn.execute("UPDATE products SET active = 1, fail_count = 0 WHERE id = ?", (pid,))
            db.conn.commit()
        return jsonify({"status": "ok", "id": pid, "active": 1})

    @app.post("/api/products/bulk-delete")
    def api_bulk_delete_products():
        data = request.get_json(silent=True) or {}
        ids = data.get("ids", [])
        if ids == "all":
            all_prods = db.get_active_products()
            clean_ids = [p["id"] for p in all_prods]
        elif isinstance(ids, list):
            clean_ids = [int(i) for i in ids if str(i).isdigit()]
        else:
            clean_ids = []

        if not clean_ids:
            return jsonify({"error": "Danh sách sản phẩm cần xóa không hợp lệ"}), 400

        db.delete_products(clean_ids)
        return jsonify({"status": "ok", "deleted_count": len(clean_ids), "deleted_ids": clean_ids})

    @app.post("/api/products/purge-junk")
    def api_purge_junk_products():
        data = request.get_json(silent=True) or {}
        min_price = data.get("min_price")
        if min_price is None:
            min_price = config.deal_min_original_price
        else:
            try:
                min_price = float(min_price)
            except (ValueError, TypeError):
                min_price = config.deal_min_original_price
        deleted_count = db.purge_junk_flash_sales(min_price)
        return jsonify({"status": "ok", "deleted_count": deleted_count, "min_price": min_price})

    for _key, _attr in [
        ("deal_min_original_price", "deal_min_original_price"),
        ("scan_interval_min", "scan_interval_min"),
        ("keyword_interval_min", "keyword_interval_min"),
        ("megasale_interval_min", "megasale_interval_min"),
        ("price_error_interval_min", "price_error_interval_min"),
    ]:
        _saved = db.get_setting(_key, "")
        if _saved:
            try:
                if _key == "deal_min_original_price":
                    setattr(config, _attr, float(_saved))
                elif _saved.isdigit():
                    setattr(config, _attr, int(_saved))
            except Exception:
                pass

    _saved_target = db.get_setting("only_target_price_alerts", "")
    if _saved_target in ("0", "1"):
        config.only_target_price_alerts = (_saved_target == "1")

    @app.get("/api/settings")
    def api_get_settings():
        saved_interval = db.get_setting("scan_interval_min", str(config.scan_interval_min))
        saved_kw_interval = db.get_setting("keyword_interval_min", str(getattr(config, "keyword_interval_min", 180)))
        saved_ms_interval = db.get_setting("megasale_interval_min", str(getattr(config, "megasale_interval_min", 60)))
        saved_pe_interval = db.get_setting("price_error_interval_min", str(getattr(config, "price_error_interval_min", 60)))
        saved_tmall_interval = db.get_setting("tmall_interval_min", str(getattr(config, "tmall_interval_min", 120)))
        saved_tmall_min = db.get_setting("tmall_min_price", str(getattr(config, "tmall_min_price", 100000.0)))
        saved_tmall_max = db.get_setting("tmall_max_price", str(getattr(config, "tmall_max_price", 20000000.0)))
        saved_min_price = db.get_setting("deal_min_original_price", str(config.deal_min_original_price))
        saved_unknown = db.get_setting("keyword_include_unknown", "1" if getattr(config, "keyword_include_unknown", False) else "0")

        saved_kw_enabled = db.get_setting("keyword_scan_enabled")
        saved_ms_enabled = db.get_setting("megasale_scan_enabled")
        saved_pe_enabled = db.get_setting("price_error_scan_enabled")
        saved_tmall_enabled = db.get_setting("tmall_scan_enabled")
        saved_only_target = db.get_setting("only_target_price_alerts")

        return jsonify({
            "scan_interval_min": int(saved_interval) if str(saved_interval).isdigit() else config.scan_interval_min,
            "keyword_interval_min": int(saved_kw_interval) if str(saved_kw_interval).isdigit() else getattr(config, "keyword_interval_min", 180),
            "megasale_interval_min": int(saved_ms_interval) if str(saved_ms_interval).isdigit() else getattr(config, "megasale_interval_min", 60),
            "price_error_interval_min": int(saved_pe_interval) if str(saved_pe_interval).isdigit() else getattr(config, "price_error_interval_min", 60),
            "tmall_interval_min": int(saved_tmall_interval) if str(saved_tmall_interval).isdigit() else getattr(config, "tmall_interval_min", 120),
            "tmall_min_price": float(saved_tmall_min) if saved_tmall_min else getattr(config, "tmall_min_price", 100000.0),
            "tmall_max_price": float(saved_tmall_max) if saved_tmall_max else getattr(config, "tmall_max_price", 20000000.0),
            "deal_min_original_price": float(saved_min_price) if saved_min_price else config.deal_min_original_price,
            "keyword_include_unknown": saved_unknown == "1",
            "keyword_result_limit": getattr(config, "keyword_result_limit", 30),
            "keyword_scan_enabled": saved_kw_enabled == "1" if saved_kw_enabled in ("0", "1") else getattr(config, "keyword_scan_enabled", True),
            "megasale_scan_enabled": saved_ms_enabled == "1" if saved_ms_enabled in ("0", "1") else getattr(config, "megasale_scan_enabled", False),
            "price_error_scan_enabled": saved_pe_enabled == "1" if saved_pe_enabled in ("0", "1") else getattr(config, "price_error_scan_enabled", True),
            "tmall_scan_enabled": saved_tmall_enabled == "1" if saved_tmall_enabled in ("0", "1") else getattr(config, "tmall_scan_enabled", True),
            "only_target_price_alerts": saved_only_target == "1" if saved_only_target in ("0", "1") else getattr(config, "only_target_price_alerts", True),
        })

    @app.post("/api/settings")
    def api_set_settings():
        data = request.get_json(silent=True) or {}

        for key in ["keyword_scan_enabled", "megasale_scan_enabled", "price_error_scan_enabled", "tmall_scan_enabled", "only_target_price_alerts"]:
            if key in data:
                b_val = bool(data[key])
                setattr(config, key, b_val)
                db.set_setting(key, "1" if b_val else "0")

        intervals = [
            ("scan_interval_min", "Tần suất quét sản phẩm theo dõi"),
            ("keyword_interval_min", "Tần suất quét từ khóa"),
            ("megasale_interval_min", "Tần suất quét Siêu Sale"),
            ("price_error_interval_min", "Tần suất quét lỗi giá"),
            ("tmall_interval_min", "Tần suất quét Lazada TMALL"),
        ]
        for key, label in intervals:
            raw_val = data.get(key)
            if raw_val is not None:
                try:
                    val = int(raw_val)
                    if val < 1 or val > 1440:
                        return jsonify({"error": f"{label} phải từ 1 đến 1440 phút"}), 400
                    setattr(config, key, val)
                    db.set_setting(key, str(val))
                except (ValueError, TypeError):
                    return jsonify({"error": f"{label} không hợp lệ"}), 400

        raw_price = data.get("deal_min_original_price")
        if raw_price is not None:
            try:
                p_val = float(raw_price)
                if p_val < 0:
                    return jsonify({"error": "Giá gốc tối thiểu không được âm"}), 400
                config.deal_min_original_price = p_val
                db.set_setting("deal_min_original_price", str(p_val))
            except (ValueError, TypeError):
                return jsonify({"error": "Giá gốc tối thiểu không hợp lệ"}), 400

        raw_tmall_min = data.get("tmall_min_price")
        if raw_tmall_min is not None:
            try:
                tm_min = float(raw_tmall_min)
                if tm_min < 0:
                    return jsonify({"error": "Giá tối thiểu TMALL không được âm"}), 400
                config.tmall_min_price = tm_min
                db.set_setting("tmall_min_price", str(tm_min))
            except (ValueError, TypeError):
                return jsonify({"error": "Giá tối thiểu TMALL không hợp lệ"}), 400

        raw_tmall_max = data.get("tmall_max_price")
        if raw_tmall_max is not None:
            try:
                tm_max = float(raw_tmall_max)
                if tm_max < 0:
                    return jsonify({"error": "Giá tối đa TMALL không được âm"}), 400
                config.tmall_max_price = tm_max
                db.set_setting("tmall_max_price", str(tm_max))
            except (ValueError, TypeError):
                return jsonify({"error": "Giá tối đa TMALL không hợp lệ"}), 400

        # Immediate cleanup of out-of-range or invalid category TMALL products
        if raw_tmall_min is not None or raw_tmall_max is not None:
            if scanner and hasattr(scanner, "cleanup_invalid_tmall_products"):
                scanner.cleanup_invalid_tmall_products()
            else:
                try:
                    min_p = getattr(config, "tmall_min_price", 100000.0)
                    max_p = getattr(config, "tmall_max_price", 20000000.0)
                    for p in db.get_products_with_latest_price():
                        d_p = dict(p)
                        if d_p.get("source") == "lazada_tmall":
                            p_cat = d_p.get("category") or ""
                            p_price = d_p.get("current_price") or 0.0
                            if p_cat not in ("Thiết Bị Điện Tử", "Phụ Kiện Điện Tử") or not (min_p <= p_price <= max_p):
                                db.delete_product(d_p["id"])
                except Exception as e:
                    log.warning("Immediate tmall cleanup error: %s", e)

        raw_unknown = data.get("keyword_include_unknown")
        if raw_unknown is not None:
            config.keyword_include_unknown = bool(raw_unknown)
            db.set_setting("keyword_include_unknown", "1" if raw_unknown else "0")

        return jsonify({
            "status": "ok",
            "scan_interval_min": config.scan_interval_min,
            "keyword_interval_min": getattr(config, "keyword_interval_min", 180),
            "megasale_interval_min": getattr(config, "megasale_interval_min", 60),
            "price_error_interval_min": getattr(config, "price_error_interval_min", 60),
            "tmall_interval_min": getattr(config, "tmall_interval_min", 120),
            "tmall_min_price": getattr(config, "tmall_min_price", 100000.0),
            "tmall_max_price": getattr(config, "tmall_max_price", 20000000.0),
            "deal_min_original_price": config.deal_min_original_price,
            "keyword_include_unknown": config.keyword_include_unknown,
            "keyword_scan_enabled": getattr(config, "keyword_scan_enabled", True),
            "megasale_scan_enabled": getattr(config, "megasale_scan_enabled", False),
            "price_error_scan_enabled": getattr(config, "price_error_scan_enabled", True),
            "tmall_scan_enabled": getattr(config, "tmall_scan_enabled", True),
            "only_target_price_alerts": getattr(config, "only_target_price_alerts", True),
        })


    @app.post("/api/search")
    def api_search():
        data = request.get_json(silent=True) or {}
        keyword = (data.get("keyword") or "").strip()
        if not keyword:
            return jsonify({"error": "keyword required"}), 400
        limit = int(data.get("limit") or 5)
        lowest_only = data.get("lowest_only", True)
        if isinstance(lowest_only, str):
            lowest_only = lowest_only.lower() in ("true", "1", "yes")
        platform = str(data.get("platform") or "all").lower()
        pids = scanner.discover_keyword(keyword, limit=limit, lowest_only=lowest_only, platform=platform)
        best_deal = None
        if pids:
            p = db.get_product(pids[0])
            if p:
                latest_price = db.get_latest_price(pids[0])
                with db._lock:
                    row = db.conn.execute("SELECT voucher_code, voucher_discount, final_price FROM price_history WHERE product_id=? ORDER BY ts DESC LIMIT 1", (pids[0],)).fetchone()
                best_deal = {
                    "id": p["id"],
                    "name": p["name"],
                    "platform": p["platform"],
                    "url": p["url"],
                    "price": latest_price,
                    "voucher_code": row["voucher_code"] if row else "",
                    "voucher_discount": row["voucher_discount"] if row else 0.0,
                    "final_price": row["final_price"] if row and row["final_price"] else latest_price,
                }
        return jsonify({
            "keyword": keyword,
            "platform": platform,
            "added_count": len(pids),
            "product_ids": pids,
            "best_deal": best_deal,
        })

    @app.post("/api/crawl-megasale")
    def api_crawl_megasale():
        data = request.get_json(silent=True) or {}
        limit = int(data.get("limit") or 25)
        platform = str(data.get("platform") or "all").lower()
        def _do_crawl():
            try:
                scanner.discover_flash_sale(limit=limit, platform=platform)
            except Exception as err:
                log.error("Crawl flash sale error: %s", err)
        threading.Thread(target=_do_crawl, daemon=True, name="crawl-flash-sale").start()
        plat_name = "Tất cả các sàn" if platform == "all" else platform.title()
        return jsonify({"status": "started", "msg": f"Đang cào các deal Siêu Sale từ {plat_name}"})

    @app.post("/api/crawl-tmall")
    def api_crawl_tmall():
        data = request.get_json(silent=True) or {}
        limit = int(data.get("limit") or 30)
        def _do_crawl():
            try:
                if scanner:
                    scanner.discover_tmall_subsidy(limit=limit)
            except Exception as err:
                log.error("Crawl TMALL error: %s", err)
        threading.Thread(target=_do_crawl, daemon=True, name="crawl-tmall").start()
        return jsonify({"status": "started", "msg": "Đang cào các deal từ chuyên trang Lazada TMALL Trợ Giá"})

    @app.get("/api/products/<int:pid>/history")
    def api_history(pid: int):
        rows = db.get_price_history_for_chart(pid)
        return jsonify(rows)

    @app.get("/api/products/<int:pid>/variants")
    def api_product_variants(pid: int):
        variants = db.get_product_variants(pid)
        return jsonify([dict(v) for v in variants])

    @app.post("/api/products/<int:pid>/compare")
    def api_compare_shops(pid: int):
        res = scanner.compare_shops(pid)
        return jsonify(res)

    @app.post("/api/scan")
    def api_scan():
        """Trigger an immediate scan of user-tracked products in a background thread."""
        if hasattr(scanner, "is_scanning") and scanner.is_scanning is True:
            return jsonify({"status": "in_progress", "msg": "Quét đang chạy..."})
        def _do_scan():
            try:
                scanner.scan_tracked_products()
            except Exception as e:
                log.exception("Manual scan thread error: %s", e)
        t = threading.Thread(target=_do_scan, daemon=True, name="manual-scan")
        t.start()
        return jsonify({"status": "started", "message": "Đã bắt đầu quét sản phẩm theo dõi"})

    @app.get("/api/session")
    def api_session():
        """Return current session validity for Shopee and Lazada."""
        cookie_file = Path("data/cookies.json")
        has_spc_ec = False
        if cookie_file.exists():
            try:
                cs = json.loads(cookie_file.read_text(encoding="utf-8"))
                has_spc_ec = any(c.get("name") == "SPC_EC" for c in cs if isinstance(c, dict))
            except Exception:
                pass
        shopee_valid = check_session_valid("data", platform="shopee")
        lazada_valid = check_session_valid("data", platform="lazada")
        return jsonify({
            "valid": shopee_valid,
            "has_spc_ec": has_spc_ec,
            "shopee": {"valid": shopee_valid, "has_spc_ec": has_spc_ec},
            "lazada": {"valid": lazada_valid},
        })

    @app.post("/api/login")
    def api_login():
        """Kick off interactive Playwright login in a background thread."""
        if _login_state["running"]:
            return jsonify({"status": "running"})
        platform = (request.get_json(silent=True) or {}).get("platform", "shopee")
        _login_state["running"] = True
        _login_state["result"] = None

        def _run():
            ok = interactive_login(platform_name=platform, data_dir="data")
            _login_state["result"] = ok
            _login_state["running"] = False

        threading.Thread(target=_run, daemon=True, name="login").start()
        return jsonify({"status": "started"})

    @app.get("/api/login/status")
    def api_login_status():
        """Poll login progress."""
        return jsonify({
            "running": _login_state["running"],
            "result": _login_state["result"],
        })

    @app.post("/api/cookies")
    def api_save_cookies():
        """Save cookies directly from paste (JSON or header string key=val; ...)."""
        data = request.get_json(silent=True) or {}
        raw = (data.get("cookies") or "").strip()
        platform = (data.get("platform") or "shopee").lower()
        if not raw:
            return jsonify({"error": "Nội dung cookie trống"}), 400

        cookie_list = []
        default_domain = ".lazada.vn" if platform == "lazada" else ".shopee.vn"
        if raw.startswith("[") and raw.endswith("]"):
            try:
                cookie_list = json.loads(raw)
            except Exception as e:
                return jsonify({"error": f"JSON cookie không hợp lệ: {e}"}), 400
        else:
            for item in raw.split(";"):
                item = item.strip()
                if not item or "=" not in item:
                    continue
                name, val = item.split("=", 1)
                cookie_list.append({
                    "name": name.strip(),
                    "value": val.strip(),
                    "domain": default_domain,
                    "path": "/",
                    "httpOnly": False,
                    "secure": True,
                    "sameSite": "Lax",
                })

        if not cookie_list:
            return jsonify({"error": "Không tìm thấy cookie hợp lệ"}), 400

        fname = "cookies_lazada.json" if platform == "lazada" else "cookies.json"
        cookie_path = Path(f"data/{fname}")
        cookie_path.parent.mkdir(parents=True, exist_ok=True)
        cookie_path.write_text(json.dumps(cookie_list, indent=2, ensure_ascii=False), encoding="utf-8")
        scanner.end_pause(platform)

        if hasattr(scanner._adapter, "reload_cookies"):
            try:
                scanner._adapter.reload_cookies(Path("data"))
            except Exception:
                pass
        elif hasattr(scanner._adapter, "_load_saved_cookies"):
            try:
                scanner._adapter._load_saved_cookies(Path("data"))
            except Exception:
                pass

        has_spc_ec = any(c.get("name") == "SPC_EC" for c in cookie_list)
        return jsonify({
            "status": "ok",
            "platform": platform,
            "count": len(cookie_list),
            "has_spc_ec": has_spc_ec,
            "valid": check_session_valid("data", platform=platform),
        })

    @app.get("/api/anomalies")
    def api_get_anomalies():
        rows = db.get_anomalies(limit=50)
        from .affiliate import AffiliateLinker
        linker = AffiliateLinker(config)
        items = []
        for r in rows:
            d = dict(r)
            d["affiliate_url"] = linker.build(d.get("platform", ""), d.get("url", ""))
            items.append(d)
        return jsonify(items)

    @app.post("/api/anomalies/<int:aid>/publish")
    def api_publish_anomaly(aid: int):
        anom = db.get_anomaly(aid)
        if not anom:
            return jsonify({"error": "Không tìm thấy dữ liệu deal lỗi giá"}), 404
        from .affiliate import AffiliateLinker
        linker = AffiliateLinker(config)
        link = linker.build(anom["platform"], anom["url"])
        disc_pct = round(anom["discount"] * 100)
        plat_badge = "🔵 [LAZADA]" if anom["platform"] == "lazada" else "🟠 [SHOPEE]"
        broadcast_text = (
            f"🚨 <b>KÈO SẬP GIÁ / LỖI GIÁ CỰC MẠNH! (-{disc_pct}%)</b>\n\n"
            f"{plat_badge} <b>{html.escape(anom['name'])}</b>\n"
            f"💰 Giá hiện tại: <b>{anom['price']:,.0f}₫</b> (Giá gốc: <s>{anom['baseline']:,.0f}₫</s>)\n"
            f"🔥 Mức giảm: <b>-{disc_pct}%</b>\n\n"
            f"⚡ <i>Lưu ý: Kèo lỗi giá có thể bị shop sửa bất cứ lúc nào, anh em tranh thủ đặt nhanh kẻo hết!</i>\n"
            f"🛒 <a href='{link}'>ĐẶT MUA NGAY TRÊN {anom['platform'].upper()} ↗</a>"
        )
        notif = getattr(scanner, "_notifier", None) if scanner else None
        if not notif and config.telegram_token:
            from .notifier import Notifier
            notif = Notifier(config)
        if notif:
            notif.broadcast_deal(broadcast_text, reply_markup={
                "inline_keyboard": [[{"text": "🛒 Mua Ngay ↗", "url": link}]]
            })
        db.update_anomaly_stage(aid, "published")
        return jsonify({"status": "ok", "stage": "published", "id": aid})

    @app.post("/api/anomalies/<int:aid>/dismiss")
    def api_dismiss_anomaly(aid: int):
        db.update_anomaly_stage(aid, "rejected", reject_reason="dismissed_by_admin")
        return jsonify({"status": "ok", "stage": "rejected", "id": aid})

    @app.post("/api/scan-price-errors")
    def api_scan_price_errors():
        if not scanner:
            return jsonify({"error": "Scanner not initialized"}), 500
        threading.Thread(target=scanner.scan_price_errors, daemon=True, name="scan-price-errors").start()
        return jsonify({"status": "started", "message": "Đang quét các từ khóa thiết bị công nghệ & gia dụng để săn lỗi giá..."})

    # ── Keyword Tracking APIs ────────────────────────────────────────────────

    @app.get("/api/keywords")
    def api_keywords():
        kws = db.get_keywords()
        return jsonify(kws)

    @app.post("/api/keywords")
    def api_add_keyword():
        data = request.get_json(silent=True) or {}
        kw_text = (data.get("keyword") or "").strip()
        if not kw_text:
            return jsonify({"error": "Từ khóa không được để trống"}), 400
        filters = {
            "origin_filter": data.get("origin_filter", "default"),
            "ship_filter": data.get("ship_filter", "default"),
            "shop_filter": data.get("shop_filter", "any"),
            "services": data.get("services", []),
            "min_price": data.get("min_price"),
            "max_price": data.get("max_price"),
            "min_rating": data.get("min_rating"),
            "max_results": int(data.get("max_results", 30)),
            "platform": data.get("platform", "all"),
        }
        kid = db.add_or_update_keyword(kw_text, filters)
        return jsonify({"status": "ok", "id": kid, "keyword": kw_text})

    @app.post("/api/keywords/<int:kid>/toggle")
    def api_toggle_keyword(kid: int):
        data = request.get_json(silent=True) or {}
        active = bool(data.get("active", True))
        db.set_keyword_active(kid, active)
        return jsonify({"status": "ok", "id": kid, "active": active})

    @app.delete("/api/keywords/<int:kid>")
    def api_delete_keyword(kid: int):
        db.delete_keyword(kid)
        return jsonify({"status": "ok", "id": kid})

    @app.post("/api/keywords/search")
    def api_search_keywords():
        if not scanner:
            return jsonify({"error": "Scanner not initialized"}), 500
        data = request.get_json(silent=True) or {}
        kid = data.get("keyword_id")
        threading.Thread(
            target=scanner.run_keyword_search,
            kwargs={"keyword_id": kid},
            daemon=True,
            name="keyword-search-worker",
        ).start()
        return jsonify({"status": "started", "message": "Đang tiến hành tìm kiếm và lọc sản phẩm theo từ khóa..."})

    @app.get("/api/keyword-products")
    def api_get_keyword_products():
        kid_param = request.args.get("keyword_id")
        kid = int(kid_param) if kid_param and kid_param.isdigit() else None
        items = db.get_keyword_products(keyword_id=kid)
        return jsonify(items)

    @app.post("/api/keywords/<int:kid>/clear-cache")
    def api_clear_keyword_cache(kid: int):
        db.clear_rejected_items(kid)
        return jsonify({"status": "ok", "message": "Đã xóa bộ nhớ đệm loại trừ cho từ khóa này."})

    return app


def _quick_detect_full(db: DB, product_row, config: Config):
    """Compute full DetectionResult for one product."""
    current_price = product_row["current_price"]
    if current_price is None:
        return None
    history = db.get_price_history_30d(product_row["id"], exclude_latest=True)
    return detect(
        current_price=current_price,
        history=history,
        list_price=product_row["current_list_price"],
        in_stock=bool(product_row["current_stock"]) if product_row["current_stock"] is not None else None,
        rating=product_row["rating"],
        min_discount=config.deal_min_discount / 100.0,
        min_rating=config.deal_min_rating,
    )


def _quick_detect(db: DB, product_row, config: Config) -> DealStatus | None:
    """Compute current DealStatus for one product (used in API responses)."""
    res = _quick_detect_full(db, product_row, config)
    return res.status if res else None
