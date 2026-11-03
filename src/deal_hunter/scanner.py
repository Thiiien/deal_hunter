import logging

import random

import re

import threading

import time

from collections import defaultdict

from pathlib import Path

from urllib.parse import unquote



from .adapters.base import BaseAdapter, Blocked, FetchError, ProductDelisted

from .affiliate import AffiliateLinker

from .alerter import Alerter

from .config import Config

from .db import DB

from .detector import detect, check_price_error

from .models import DealStatus, Snapshot

from .notifier import Notifier

from .quota import QuotaMonitor



log = logging.getLogger(__name__)





def _is_relevant_match(search_keyword: str, candidate_name: str) -> bool:

    """Filter out accessories and unrelated products when searching for a main item."""

    if not candidate_name or "mock product" in candidate_name.lower():

        return True

    if not candidate_name or candidate_name.startswith("Mock Product"):

        return True

    sk = search_keyword.lower().strip()

    cn = candidate_name.lower().strip()

    accessory_tokens = (

        "phụ kiện", "ốp lưng", "kính cường lực", "miếng dán", "skin",

        "feet chuột", "switch lẻ", "dây thay thế", "hộp đựng", "bao da",

        "túi chống sốc", "nắp che", "bọc silicon",

    )

    for acc in accessory_tokens:

        if acc in cn and acc not in sk:

            return False

    stop_words = {"và", "cho", "của", "các", "những", "loại", "với", "là", "chính", "hãng", "mới", "giá"}

    tokens = [t for t in re.findall(r"\w+", sk) if t not in stop_words and len(t) > 1]

    if tokens:

        matched = sum(1 for t in tokens if t in cn)

        if matched / len(tokens) < 0.6:

            return False

    return True





class Scanner:

    """Orchestrates one full scan cycle.



    Responsibilities:

    - Check NopeCHA quota before scanning

    - For each active product: fetch → save → detect → alert if deal

    - Group products by platform; stop a platform's batch on Blocked

    - Log the scan result

    """



    def __init__(

        self,

        config: Config,

        adapter: BaseAdapter,

        db: DB,

        notifier: Notifier,

        quota: QuotaMonitor,

    ):

        self._config = config

        self._adapter = adapter

        self._db = db

        self._notifier = notifier

        self._quota = quota

        if hasattr(self._adapter, "_quota"):

            self._adapter._quota = quota

        self._alerter = Alerter(db)

        self._linker = AffiliateLinker(config)

        self._scan_lock = threading.Lock()

        self._verify_lock = threading.Lock()

        self._pending_verify_scans: set[int] = set()

        self._last_tracked_scan_time: float = 0.0

        self._last_keyword_scan_time: float = 0.0

        self._last_megasale_scan_time: float = 0.0

        self._last_price_error_scan_time: float = 0.0

        self._last_tmall_scan_time: float = 0.0



    def _schedule_fast_verification(self, product_id: int):

        with self._verify_lock:

            if product_id in self._pending_verify_scans:

                return

            self._pending_verify_scans.add(product_id)



        def _run_verify():

            try:

                log.info("Running fast verification scan for product #%d...", product_id)

                self.scan_product(product_id)

            except Exception as exc:

                log.warning("Fast verification scan error for product #%d: %s", product_id, exc)

            finally:

                with self._verify_lock:

                    self._pending_verify_scans.discard(product_id)



        timer = threading.Timer(180, _run_verify)

        timer.daemon = True

        timer.start()



    @property

    def is_scanning(self) -> bool:

        return self._scan_lock.locked()





    def discover_keyword(self, keyword: str, limit: int = 5, lowest_only: bool = False, platform: str = "all", source: str = "user") -> list[int]:

        """Search products by keyword via adapter and register them in DB.



        If lowest_only=True:

            Fetches snapshots for candidates, finds the one with the lowest price,

            and registers only that cheapest product for tracking.

        """

        try:

            urls = self._adapter.search(keyword, limit=limit, platform=platform)

        except Blocked:

            msg = f"🚫 Bị chặn khi tìm kiếm từ khóa '{keyword}' trên sàn."

            log.warning(msg)

            self._notifier.alert_admin(msg)

            return []

        except Exception as exc:

            log.warning("Lỗi khi tìm kiếm từ khóa '%s': %s", keyword, exc)

            return []



        if not urls:

            return []



        if lowest_only:

            import statistics



            candidates = []

            for u in urls[:min(len(urls), 4)]:

                try:

                    snap = self._adapter.fetch(u)

                    if (

                        snap

                        and snap.price

                        and snap.price > 1000

                        and snap.stock is not False

                        and _is_relevant_match(keyword, snap.name)

                    ):

                        candidates.append(snap)

                except Exception as err:

                    log.debug("Fetch candidate %s failed: %s", u, err)



            if candidates:

                prices = [getattr(s, "final_price", None) or s.price for s in candidates]

                if len(prices) >= 3:

                    med_price = statistics.median(prices)

                    candidates = [

                        s for s in candidates

                        if (getattr(s, "final_price", None) or s.price) >= 0.35 * med_price

                    ]



            if candidates:

                best = min(candidates, key=lambda s: getattr(s, "final_price", None) or s.price)

                pid = self._db.add_product_url(best.url, best.platform, best.item_key, source=source)

                with self._db._lock:

                    self._db.conn.execute(

                        "UPDATE products SET name=?, category=?, rating=? WHERE id=?",

                        (best.name, best.category, best.rating, pid),

                    )

                    self._db.conn.commit()

                self._db.save_snapshot(pid, best)

                return [pid]

            # Fallback if fetching all candidates failed: add first URL

            urls = urls[:1]



        added_ids = []

        for url in urls:

            platform = BaseAdapter.parse_platform(url)

            item_key = BaseAdapter.parse_item_key(url)

            pid = self._db.add_product_url(url, platform, item_key, source=source)

            p = self._db.get_product(pid)

            if p and not p["name"]:

                m = re.search(r"shopee\.vn/([^/]+)-i\.\d+\.\d+", url)

                if m:

                    name = unquote(m.group(1)).replace("-", " ").strip()

                    if name:

                        with self._db._lock:

                            self._db.conn.execute("UPDATE products SET name=? WHERE id=?", (name, pid))

                            self._db.conn.commit()

            added_ids.append(pid)



        if added_ids:

            def _scan_discovered():

                for pid in added_ids:

                    try:

                        self.scan_product(pid)

                    except Exception as err:

                        log.debug("Scan discovered product #%d error: %s", pid, err)

            threading.Thread(target=_scan_discovered, daemon=True, name="scan-discovered").start()



        return added_ids



    def discover_flash_sale(self, limit: int = 30, platform: str = "all") -> list[int]:

        """Crawl deep-discount flash sale products from Shopee/Lazada across categories."""

        if not hasattr(self._adapter, "crawl_flash_sale"):

            return []

        from .campaign import get_active_campaign

        current_campaign = get_active_campaign(self._db) or "Flash Sale"

        try:

            snaps = self._adapter.crawl_flash_sale(limit=limit, platform=platform)

        except TypeError:

            snaps = self._adapter.crawl_flash_sale(limit)

        added_ids = []

        min_orig = getattr(self._config, "deal_min_original_price", 500000.0)

        for s in snaps:

            if s.stock is False or s.stock == 0:

                continue

            orig_val = s.list_price or s.price or 0.0

            if orig_val < min_orig:

                continue

            pid = self._db.add_product_url(s.url, s.platform, s.item_key, source="flash_sale")

            self._db.upsert_product_meta(s, source="flash_sale")

            self._db.save_snapshot(pid, s, campaign=current_campaign)

            added_ids.append(pid)



            eff_price = getattr(s, "final_price", None) or s.price

        log.info("Discovered and saved %d Flash Sale deals (platform: %s, filter >= %s₫)", len(added_ids), platform, f"{min_orig:,.0f}")

        return added_ids



    def discover_tmall_subsidy(self, limit: int = 30) -> list[int]:

        """Crawl products from Lazada TMALL Subsidy catalog."""

        if not hasattr(self._adapter, "crawl_tmall_subsidy"):

            return []

        min_p = getattr(self._config, "tmall_min_price", 100000.0)

        max_p = getattr(self._config, "tmall_max_price", 20000000.0)

        try:

            snaps = self._adapter.crawl_tmall_subsidy(limit=limit, min_price=min_p, max_price=max_p)

        except TypeError:

            snaps = self._adapter.crawl_tmall_subsidy(limit=limit)

        except Exception as err:

            log.warning("Crawl tmall subsidy error: %s", err)

            return []



        self.cleanup_invalid_tmall_products()



        added_ids = []

        for s in snaps:

            if s.stock is False or s.stock == 0:

                continue

            if s.price is None or not (min_p <= s.price <= max_p):

                continue

            if s.category not in ("Thiết Bị Điện Tử", "Phụ Kiện Điện Tử"):

                continue

            s.rating = None

            pid = self._db.add_product_url(s.url, s.platform, s.item_key, source="lazada_tmall")

            self._db.upsert_product_meta(s, source="lazada_tmall")

            self._db.save_snapshot(pid, s, campaign="TMALL Trợ Giá")

            added_ids.append(pid)

        log.info("Discovered and saved %d Lazada TMALL products", len(added_ids))

        return added_ids



    def cleanup_invalid_tmall_products(self) -> int:

        """Purge TMALL products not matching category or price bounds."""

        min_p = getattr(self._config, "tmall_min_price", 100000.0)

        max_p = getattr(self._config, "tmall_max_price", 20000000.0)

        deleted = 0

        try:

            old_tmall = [p for p in self._db.get_products_with_latest_price() if dict(p).get("source") == "lazada_tmall"]

            for p in old_tmall:

                d_p = dict(p)

                p_cat = d_p.get("category") or ""

                p_price = d_p.get("current_price") or 0.0

                if p_cat not in ("Thiết Bị Điện Tử", "Phụ Kiện Điện Tử") or not (min_p <= p_price <= max_p):

                    self._db.delete_product(d_p["id"])

                    deleted += 1

            if deleted > 0:

                log.info("Purged %d invalid/out-of-range TMALL products", deleted)

        except Exception as e:

            log.warning("Cleanup old tmall products error: %s", e)

        return deleted





    def compare_shops(self, product_id: int, limit: int = 5) -> dict:

        """Compare the current product against other shops selling the same item."""

        p = self._db.get_product(product_id)

        if not p:

            return {"status": "error", "message": "Không tìm thấy sản phẩm"}



        raw_name = p["name"] or ""

        clean_name = re.sub(r"\[.*?\]|\(.*?\)", " ", raw_name)

        words = [w for w in re.findall(r"\w+", clean_name) if len(w) > 1][:5]

        query = " ".join(words)

        if not query:

            return {"status": "error", "message": "Không đủ thông tin tên sản phẩm để so giá"}



        try:

            urls = self._adapter.search(query, limit=limit + 3)

        except Exception as exc:

            return {"status": "error", "message": f"Lỗi tìm kiếm sàn: {exc}"}



        other_urls = [

            u for u in urls

            if p["item_key"] not in u and (not p["url"] or p["url"].split("?")[0] not in u)

        ][:limit]



        candidates = []

        for u in other_urls:

            try:

                snap = self._adapter.fetch(u)

                if (

                    snap

                    and snap.price

                    and snap.price > 1000

                    and snap.stock is not False

                    and _is_relevant_match(query, snap.name)

                ):

                    candidates.append(snap)

            except Exception:

                pass



        cur_price = self._db.get_latest_price(product_id)

        if cur_price is None:

            cur_price = p["target_price"] if "target_price" in p.keys() else 0.0



        if not candidates:

            return {

                "status": "no_candidates",

                "current_price": cur_price,

                "message": "Không tìm thấy shop khác còn hàng phù hợp",

            }



        best_alt = min(candidates, key=lambda s: getattr(s, "final_price", None) or s.price)

        best_alt_price = getattr(best_alt, "final_price", None) or best_alt.price



        if cur_price > 0 and best_alt_price < cur_price:

            savings = round(cur_price - best_alt_price, 2)

            pct = round((savings / cur_price) * 100, 1)

            return {

                "status": "found_cheaper",

                "current_price": cur_price,

                "savings": savings,

                "savings_pct": pct,

                "cheaper_product": {

                    "name": best_alt.name,

                    "url": best_alt.url,

                    "price": best_alt.price,

                    "final_price": best_alt.final_price,

                    "voucher_code": best_alt.voucher_code,

                    "voucher_discount": best_alt.voucher_discount,

                    "shop": best_alt.shop,

                    "rating": best_alt.rating,

                    "item_key": best_alt.item_key,

                },

            }

        else:

            return {

                "status": "lowest_already",

                "current_price": cur_price,

                "message": "Shop hiện tại đang có giá tốt nhất!",

            }



    def scan_all(self) -> dict:

        """Run one full scan cycle. Returns {"ok": n, "fail": n}."""

        if not self._scan_lock.acquire(blocking=False):

            log.info("Scan already in progress — skipping concurrent scan")

            return {"ok": 0, "fail": 0, "msg": "scan_in_progress"}



        try:

            self._quota.check()





            # Pre-flight session check

            if hasattr(self._adapter, "ensure_authenticated"):

                if not self._adapter.ensure_authenticated():

                    msg = (

                        "⚠️ Phiên đăng nhập sàn (cookie) chưa có hoặc đã hết hạn!\n"

                        "👉 Vui lòng cấp mới cookies vào data/cookies.json hoặc data/cookies_lazada.json hoặc đăng nhập lại qua Dashboard."

                    )

                    log.warning(msg)

                    self._notifier.alert_admin(msg)

                    return {"ok": 0, "fail": 0, "msg": "auth_required"}



            products = self._db.get_active_products()

            if not products:

                log.info("No active products to scan")

                return {"ok": 0, "fail": 0}



            # Group by platform so we can stop a whole platform on Blocked

            by_platform: dict[str, list] = defaultdict(list)

            for p in products:

                by_platform[p["platform"]].append(p)



            ok = fail = 0

            for platform, group in by_platform.items():

                platform_ok, platform_fail = self._scan_platform(platform, group)

                ok += platform_ok

                fail += platform_fail



            self._db.log_scan(ok, fail)

            log.info("Scan complete: %d ok, %d fail", ok, fail)

            return {"ok": ok, "fail": fail}

        finally:

            self._scan_lock.release()



    def scan_tracked_products(self) -> dict:

        """Scan only user-tracked products."""

        if not self._scan_lock.acquire(blocking=False):

            log.info("Scan already in progress — skipping tracked scan")

            return {"ok": 0, "fail": 0, "msg": "scan_in_progress"}



        try:

            self._quota.check()





            products = self._db.get_active_tracked_products()

            if not products:

                log.info("No active tracked products to scan")

                return {"ok": 0, "fail": 0}



            by_platform: dict[str, list] = defaultdict(list)

            for p in products:

                by_platform[p["platform"]].append(p)



            ok = fail = 0

            for platform, group in by_platform.items():

                platform_ok, platform_fail = self._scan_platform(platform, group)

                ok += platform_ok

                fail += platform_fail



            self._db.log_scan(ok, fail)

            log.info("Tracked scan complete: %d ok, %d fail", ok, fail)

            return {"ok": ok, "fail": fail}

        finally:

            self._scan_lock.release()



    def _is_subsystem_enabled(self, key: str, default: bool = True) -> bool:

        db_val = self._db.get_setting(key)

        if db_val in ("0", "1"):

            return db_val == "1"

        return bool(getattr(self._config, key, default))



    def scan_due(self) -> dict:

        """Check all 4 subsystem timers and execute any scans that are due."""

        now = time.time()

        results = {}



        # 1. User-tracked products scan

        db_interval = self._db.get_setting("scan_interval_min") if hasattr(self._db, "get_setting") else None
        if db_interval and str(db_interval).isdigit() and int(db_interval) > 0:
            tracked_interval_sec = int(db_interval) * 60
        else:
            tracked_interval_sec = (getattr(self._config, "scan_interval_min", 2) or 2) * 60

        if self._last_tracked_scan_time == 0.0 or (now - self._last_tracked_scan_time >= tracked_interval_sec):

            try:

                res = self.scan_tracked_products()

                self._last_tracked_scan_time = now

                results["tracked"] = res

            except Exception as e:

                log.warning("Tracked products scan error: %s", e)



        # 2. Keyword tracking scan

        if self._is_subsystem_enabled("keyword_scan_enabled"):

            kw_interval_sec = (getattr(self._config, "keyword_interval_min", 180) or 180) * 60

            if self._last_keyword_scan_time == 0.0 or (now - self._last_keyword_scan_time >= kw_interval_sec):

                try:

                    res = self.run_keyword_search()

                    self._last_keyword_scan_time = now

                    results["keyword"] = res

                except Exception as e:

                    log.warning("Keyword tracking search error: %s", e)



        # 3. Mega sale / Flash sale crawl (manual only via UI by default)

        if self._is_subsystem_enabled("megasale_scan_enabled", default=False):

            ms_interval_sec = (getattr(self._config, "megasale_interval_min", 60) or 60) * 60

            if self._last_megasale_scan_time == 0.0 or (now - self._last_megasale_scan_time >= ms_interval_sec):

                try:

                    res = self.discover_flash_sale(limit=getattr(self._config, "flash_sale_limit", 30))

                    self._last_megasale_scan_time = now

                    results["megasale"] = res

                except Exception as e:

                    log.warning("Megasale crawl error: %s", e)



        # 4. Price error scan

        if self._is_subsystem_enabled("price_error_scan_enabled"):

            pe_interval_sec = (getattr(self._config, "price_error_interval_min", 60) or 60) * 60

            if self._last_price_error_scan_time == 0.0 or (now - self._last_price_error_scan_time >= pe_interval_sec):

                try:

                    res = self.scan_price_errors()

                    self._last_price_error_scan_time = now

                    results["price_error"] = res

                except Exception as e:

                    log.warning("Price error scan error: %s", e)



        # 5. Lazada TMALL catalog crawl

        if self._is_subsystem_enabled("tmall_scan_enabled"):

            tmall_interval_sec = (getattr(self._config, "tmall_interval_min", 120) or 120) * 60

            if self._last_tmall_scan_time == 0.0 or (now - self._last_tmall_scan_time >= tmall_interval_sec):

                try:

                    res = self.discover_tmall_subsidy(limit=30)

                    self._last_tmall_scan_time = now

                    results["tmall"] = res

                except Exception as e:

                    log.warning("Lazada TMALL subsidy crawl error: %s", e)



        return results





    def scan_product(self, product_id: int) -> Snapshot | None:

        p = self._db.get_product(product_id)

        if not p or not p["active"]:

            return None

        from .campaign import get_active_campaign

        current_campaign = get_active_campaign(self._db) or ""

        target_sku = None

        main_vid = p["main_variant_id"] if "main_variant_id" in p.keys() else None

        if main_vid:

            var_row = self._db.get_variant(main_vid)

            if var_row and "variant_key" in var_row.keys():

                target_sku = var_row["variant_key"]

        is_user = ("source" not in p.keys() or p["source"] in ("user", "lazada_tmall"))

        # User decision (ADR 0054): always dynamically track lowest in-stock variant across entire listing

        if is_user:

            target_sku = None

        from .adapters.playwright import canonicalize_url

        clean_url = canonicalize_url(p["url"])

        try:
            snapshot = None
            if hasattr(self._adapter, "fast_fetch") and callable(self._adapter.fast_fetch):
                try:
                    res = self._adapter.fast_fetch(clean_url, target_sku=target_sku, is_tracked=is_user)
                    if isinstance(res, Snapshot):
                        snapshot = res
                except Exception as fast_err:
                    log.debug("fast_fetch failed for #%d: %s", product_id, fast_err)
                    snapshot = None

            if snapshot is None:
                snapshot = self._adapter.fetch(clean_url, target_sku=target_sku, is_tracked=is_user)
            else:
                try:
                    last_p = self._db.get_latest_price(product_id)
                    target_p = p["target_price"] if "target_price" in p.keys() else None
                    curr_p = getattr(snapshot, "final_price", None) or snapshot.price
                    should_escalate = False
                    if curr_p and curr_p > 0:
                        if target_p and curr_p <= target_p:
                            should_escalate = True
                        elif last_p and (last_p - curr_p) / last_p >= 0.20:
                            should_escalate = True
                        elif snapshot.list_price and (snapshot.list_price - curr_p) / snapshot.list_price >= 0.65:
                            should_escalate = True

                    if should_escalate:
                        log.info("Escalating #%d to Tier-2 Playwright Verifier (price %s)", product_id, curr_p)
                        verified_snap = self._adapter.fetch(clean_url, target_sku=target_sku, is_tracked=is_user)
                        if verified_snap and verified_snap.price is not None and verified_snap.price > 0:
                            snapshot = verified_snap
                except Exception as esc_err:
                    log.warning("Tier-2 verification error for #%d: %s", product_id, esc_err)

        except ProductDelisted as delist_err:

            log.info("Product #%d (%s) is delisted: %s. Auto-deactivating.", product_id, p["url"], delist_err)

            with self._db._lock:

                self._db.conn.execute("UPDATE products SET active=0 WHERE id=?", (product_id,))

                self._db.conn.commit()

            if ("source" in p.keys() and p["source"] in ("user", "lazada_tmall")) or "source" not in p.keys():

                self._notifier.alert_admin(

                    f"⚠️ <b>Sản phẩm ngừng kinh doanh hoặc đã bị xóa</b>\n"

                    f"📦 #{product_id}: <code>{p['name'] or p['url']}</code>\n"

                    f"👉 Hệ thống đã tự động ngưng theo dõi link này."

                )

            return None



        product_id = self._db.update_product_from_snapshot(product_id, snapshot)

        self._db.save_snapshot(product_id, snapshot, campaign=current_campaign)



        # Evaluate variant stock state machine (NGHI HẾT -> Fast Scan, HẾT HÀNG -> Fallback Variant)

        var_state = self._db.evaluate_variant_state(product_id)

        if var_state.get("action") == "suspect_out":

            self._schedule_fast_verification(product_id)

        elif var_state.get("action") == "fallback_applied":

            fb_price = var_state.get("price")

            if fb_price:

                snapshot.price = fb_price

                snapshot.final_price = fb_price

                snapshot.stock = True



        # In-stock check: de-activate flash sale or suppress alerts if out-of-stock

        if snapshot.stock is False or snapshot.stock == 0:

            if "source" in p.keys() and p["source"] == "flash_sale":

                log.info("Auto-deactivating sold-out flash sale deal #%d (%s)", product_id, p["url"])

                with self._db._lock:

                    self._db.conn.execute("UPDATE products SET active=0 WHERE id=?", (product_id,))

                    self._db.conn.commit()

            return snapshot





        effective_price = getattr(snapshot, "final_price", None) or snapshot.price

        history = self._db.get_price_history_30d(product_id, exclude_latest=True)

        result = detect(

            current_price=effective_price,

            history=history,

            list_price=snapshot.list_price,

            in_stock=snapshot.stock,

            rating=None if is_user else snapshot.rating,

            min_discount=self._config.deal_min_discount / 100.0,

            min_rating=0.0 if is_user else self._config.deal_min_rating,

        )



        target_price = p["target_price"] if "target_price" in p.keys() else None

        alerted = False

        if target_price is not None and effective_price is not None and effective_price <= target_price and snapshot.stock is not False:

            link = self._linker.build(p["platform"], snapshot.url)

            self._send_target_alert(snapshot, target_price, link, campaign=current_campaign)

            self._alerter.record(product_id, effective_price)

            alerted = True

        only_target_alerts = self._is_subsystem_enabled("only_target_price_alerts", default=False)

        min_orig = getattr(self._config, "deal_min_original_price", 500000.0)

        prior_price = history[0] if history and history[0] > 0 else None

        base_val = result.median_30d or prior_price or snapshot.list_price or effective_price or 0.0



        # Price Error Anomaly Detection (≥ 65% off on items with baseline >= min_orig, only when in stock)

        if not only_target_alerts and snapshot.stock is not False and base_val >= min_orig and effective_price:

            is_err, err_disc = check_price_error(effective_price, base_val, snapshot.name, min_error_discount=0.65)

            if is_err:

                recent_anom = self._db.get_recent_anomaly_for_product(product_id, hours=4)

                if not recent_anom:

                    self._handle_price_error(product_id, snapshot, effective_price, base_val, err_disc)



        is_flash_sale = ("source" in p.keys() and p["source"] == "flash_sale")

        if not only_target_alerts and not alerted and not is_flash_sale and result.status == DealStatus.REAL_DEAL:

            if base_val >= min_orig:

                if self._alerter.should_alert(product_id, effective_price):

                    link = self._linker.build(p["platform"], snapshot.url)

                    self._send_deal_alert(snapshot, result, link, campaign=current_campaign)

                    self._alerter.record(product_id, effective_price)

                    alerted = True



        # Tracked product price-drop & new voucher alert for user-tracked items (in-stock only)

        is_user_prod = ("source" not in p.keys() or p["source"] == "user")

        if not only_target_alerts and not alerted and snapshot.stock is not False and is_user_prod and history and effective_price:

            prev_price = history[0]

            if prev_price and effective_price < prev_price:

                diff = prev_price - effective_price

                pct = (diff / prev_price) * 100.0

                if diff >= 5000 or pct >= 3.0:

                    if self._alerter.should_alert(product_id, effective_price):

                        link = self._linker.build(p["platform"], snapshot.url)

                        self._send_price_drop_alert(snapshot, prev_price, effective_price, link, campaign=current_campaign)

                        self._alerter.record(product_id, effective_price)

                        alerted = True



        return snapshot



    def _scan_platform(self, platform: str, products: list) -> tuple[int, int]:

        ok = fail = 0

        consecutive_blocks = 0

        cookie_file = "cookies_lazada.json" if platform == "lazada" else "cookies.json"

        plat_name = "Lazada" if platform == "lazada" else "Shopee"



        # Platform-specific session preflight check

        if hasattr(self._adapter, "ensure_authenticated"):

            try:

                if not self._adapter.ensure_authenticated(platform=platform):

                    msg = (

                        f"⚠️ Phiên đăng nhập sàn {plat_name} (cookie) chưa có hoặc đã hết hạn!\n"

                        f"👉 Vui lòng cấp mới cookies vào data/{cookie_file} hoặc đăng nhập lại qua Dashboard để quét {len(products)} sản phẩm."

                    )

                    log.warning(msg)

                    self._notifier.alert_admin(msg)

                    return 0, len(products)

            except Exception as e:

                log.debug("Session check error for %s: %s", platform, e)



        for prod in products:

            try:

                snap = self.scan_product(prod["id"])

                if snap is None:

                    fail += 1

                else:

                    consecutive_blocks = 0

                    ok += 1

                    self._db.reset_product_fail_count(prod["id"])

                delay = self._config.request_delay_sec

                time.sleep(random.uniform(delay * 0.8, delay * 1.2))



            except ProductDelisted as exc:

                log.info("ProductDelisted for %s: %s", prod["url"], exc)

                fail += 1

                consecutive_blocks = 0



            except Blocked:

                consecutive_blocks += 1

                fail += 1

                log.warning("Blocked on %s (consecutive: %d)", prod["url"], consecutive_blocks)

                if consecutive_blocks >= 3 or (len(products) == 1 and consecutive_blocks >= 1):

                    data_dir = str(Path(self._config.db_path).parent)

                    from .login import check_session_valid

                    is_token_valid = check_session_valid(data_dir, platform=platform)



                    credits_left = self._quota.get_remaining_credits() if hasattr(self._quota, "get_remaining_credits") else 0

                    if not is_token_valid:

                        msg = (

                            f"🚨 <b>Cào sàn {plat_name} thất bại!</b>\n"

                            f"Cả Cookie phiên đăng nhập lẫn Captcha đều không thể sử dụng để vượt qua rào cản an ninh của sàn (Cookie đã hết hạn).\n"

                            f"👉 Vui lòng cấp mới cookies vào <code>data/{cookie_file}</code> hoặc đăng nhập lại qua Dashboard, hoặc nạp NopeCHA API Key để tiếp tục quét."

                        )

                    else:

                        quota_desc = "đã hết 10 lượt giải Captcha miễn phí hôm nay" if credits_left == 0 else f"còn {credits_left} lượt giải nhưng không vượt qua"

                        msg = (

                            f"🚨 <b>Cào sàn {plat_name} thất bại!</b>\n"

                            f"Cả Cookie phiên đăng nhập lẫn Captcha đều không vượt qua được rào cản bảo mật của sàn ({quota_desc}).\n"

                            f"👉 Vui lòng làm mới phiên đăng nhập trên Dashboard hoặc bổ sung NopeCHA API Key để tiếp tục theo dõi!"

                        )

                    log.warning(msg)

                    self._notifier.alert_admin(msg)

                    fail += len(products) - (ok + fail)

                    break





            except FetchError as exc:

                log.warning("FetchError for %s: %s", prod["url"], exc)

                fail += 1

                new_fails = self._db.increment_product_fail_count(prod["id"])

                is_user = ("source" not in prod.keys() or prod["source"] in ("user", None, ""))

                if new_fails >= 5:

                    if not is_user:

                        with self._db._lock:

                            self._db.conn.execute("UPDATE products SET active=0 WHERE id=?", (prod["id"],))

                            self._db.conn.commit()

                        log.warning("Discovery product #%d (%s) failed %d consecutive times — auto-deactivated", prod["id"], prod["url"], new_fails)

                    else:

                        # User-tracked products: NEVER auto-deactivate on temporary FetchError!

                        if new_fails == 5:

                            log.warning("User product #%d (%s) reached %d consecutive failures — retained active but alerted", prod["id"], prod["url"], new_fails)

                            self._notifier.alert_admin(

                                f"⚠️ <b>Sản phẩm theo dõi gặp lỗi quét liên tiếp ({new_fails} lần)</b>\n"

                                f"📦 #{prod['id']}: <code>{prod['name'] or prod['url']}</code>\n"

                                f"🌐 Link: {prod['url']}\n"

                                f"👉 Link có thể bị đổi cấu trúc, shop bị khóa hoặc lỗi kết nối. Hệ thống vẫn duy trì theo dõi trên Dashboard nhưng tạm cảnh báo lỗi."

                            )



            except Exception as exc:

                log.warning("Unexpected error scanning %s: %s", prod["url"], exc)

                fail += 1



        return ok, fail



    def _send_deal_alert(self, snapshot, result, link: str, campaign: str = ""):

        disc_pct = int((result.disc_hist or 0) * 100)

        tag = f"[{campaign.upper()}] " if campaign else ""

        plat_badge = "🔵 [LAZADA] " if snapshot.platform == "lazada" else ("🟠 [SHOPEE] " if snapshot.platform == "shopee" else "")

        category_line = f"📂 Ngành hàng: <i>{snapshot.category}</i>\n" if snapshot.category else ""

        v_code = getattr(snapshot, "voucher_code", "")

        v_disc = getattr(snapshot, "voucher_discount", 0.0)

        f_price = getattr(snapshot, "final_price", None) or snapshot.price

        voucher_line = f"🎫 Mã giảm giá: <code>{v_code}</code> (-{v_disc:,.0f}₫)\n💵 Giá sau áp mã: <b>{f_price:,.0f}₫</b>\n" if v_code else ""

        plat_title = snapshot.platform.title() if snapshot.platform else "Sàn"

        text = (

            f"🔥 <b>{plat_badge}{tag}{snapshot.name}</b>\n\n"

            f"{category_line}"

            f"💰 Giá sàn: <b>{snapshot.price:,.0f}₫</b> "

            f"(giảm <b>{disc_pct}%</b> so với trung vị 30 ngày)\n"

            f"{voucher_line}"

            f"📊 Trung vị 30 ngày: {result.median_30d:,.0f}₫\n"

            f"⭐ {snapshot.rating or 'N/A'}  |  Đã bán: {snapshot.sold or 'N/A'}"

        )

        markup = {"inline_keyboard": [[{"text": f"🛒 Xem deal {plat_title} ↗", "url": link}]]}

        self._notifier.broadcast_deal(text, reply_markup=markup)



    def _send_target_alert(self, snapshot, target_price: float, link: str, campaign: str = ""):

        tag = f"[{campaign.upper()}] " if campaign else ""

        plat_badge = "🔵 [LAZADA] " if snapshot.platform == "lazada" else ("🟠 [SHOPEE] " if snapshot.platform == "shopee" else "")

        category_line = f"📂 Ngành hàng: <i>{snapshot.category}</i>\n" if snapshot.category else ""

        v_code = getattr(snapshot, "voucher_code", "")

        v_disc = getattr(snapshot, "voucher_discount", 0.0)

        f_price = getattr(snapshot, "final_price", None) or snapshot.price

        voucher_line = f"🎫 Mã giảm giá: <code>{v_code}</code> (-{v_disc:,.0f}₫)\n💵 Giá sau áp mã: <b>{f_price:,.0f}₫</b>\n" if v_code else ""

        plat_title = snapshot.platform.title() if snapshot.platform else "Sàn"

        text = (

            f"🎯 <b>{plat_badge}{tag}ĐẠT GIÁ MONG MUỐN!</b>\n\n"

            f"📦 <b>{snapshot.name}</b>\n"

            f"{category_line}"

            f"💰 Giá sàn: <b>{snapshot.price:,.0f}₫</b>\n"

            f"{voucher_line}"

            f"🎯 Giá mong muốn: <b>{target_price:,.0f}₫</b>\n"

            f"⭐ {snapshot.rating or 'N/A'}  |  Đã bán: {snapshot.sold or 'N/A'}"

        )

        markup = {"inline_keyboard": [[{"text": f"🛒 Mua ngay trên {plat_title} ↗", "url": link}]]}

        self._notifier.broadcast_deal(text, reply_markup=markup)



    def _send_price_drop_alert(self, snapshot, prev_price: float, current_effective: float, link: str, campaign: str = ""):

        diff = prev_price - current_effective

        pct = (diff / prev_price) * 100.0

        tag = f"[{campaign.upper()}] " if campaign else ""

        plat_badge = "🔵 [LAZADA] " if snapshot.platform == "lazada" else ("🟠 [SHOPEE] " if snapshot.platform == "shopee" else "")

        category_line = f"📂 Ngành hàng: <i>{snapshot.category}</i>\n" if snapshot.category else ""

        v_code = getattr(snapshot, "voucher_code", "")

        v_disc = getattr(snapshot, "voucher_discount", 0.0)

        voucher_line = f"🎫 Mã giảm giá: <code>{v_code}</code> (-{v_disc:,.0f}₫)\n" if v_code else ""

        plat_title = snapshot.platform.title() if snapshot.platform else "Sàn"

        text = (

            f"📉 <b>{plat_badge}{tag}GIẢM GIÁ SẢN PHẨM THEO DÕI!</b>\n\n"

            f"📦 <b>{snapshot.name}</b>\n"

            f"{category_line}"

            f"💰 Giá trước đó: <s>{prev_price:,.0f}₫</s>\n"

            f"🔥 Giá hiện tại: <b>{current_effective:,.0f}₫</b> (giảm -{diff:,.0f}₫, -{pct:.1f}%)\n"

            f"{voucher_line}"

            f"⭐ {snapshot.rating or 'N/A'}  |  Đã bán: {snapshot.sold or 'N/A'}"

        )

        markup = {"inline_keyboard": [[{"text": f"🛒 Xem deal {plat_title} ↗", "url": link}]]}

        self._notifier.broadcast_deal(text, reply_markup=markup)



    def _send_flash_deal_alert(self, snapshot, disc_pct: float, link: str, campaign: str = ""):

        pct_int = int(round(disc_pct * 100))

        tag = f"[{campaign.upper()}] " if campaign else ""

        plat_badge = "🔵 [LAZADA] " if snapshot.platform == "lazada" else ("🟠 [SHOPEE] " if snapshot.platform == "shopee" else "")

        is_subsidy = disc_pct >= 0.70 or "TMALL" in snapshot.name or "TRỢ GIÁ" in snapshot.name.upper()

        header = f"🚨 <b>DEAL SIÊU TRỢ GIÁ! {plat_badge}{tag}{snapshot.name}</b>" if is_subsidy else f"⚡ <b>FLASH DEAL HOT! {plat_badge}{tag}{snapshot.name}</b>"

        category_line = f"📂 Ngành hàng: <i>{snapshot.category}</i>\n" if snapshot.category else ""

        v_code = getattr(snapshot, "voucher_code", "")

        v_disc = getattr(snapshot, "voucher_discount", 0.0)

        f_price = getattr(snapshot, "final_price", None) or snapshot.price

        voucher_line = f"🎫 Mã giảm giá: <code>{v_code}</code> (-{v_disc:,.0f}₫)\n💵 Giá sau áp mã: <b>{f_price:,.0f}₫</b>\n" if v_code else ""

        plat_title = snapshot.platform.title() if snapshot.platform else "Sàn"

        rating_line = f"⭐ {snapshot.rating:.1f}/5  |  " if snapshot.rating else ""

        sold_line = f"Đã bán: {snapshot.sold}\n" if snapshot.sold else "\n"

        price_label = "🔥 Giá sau trợ giá" if is_subsidy else "🔥 Giá Flash Sale"

        text = (

            f"{header}\n\n"

            f"{category_line}"

            f"🏷 Giá niêm yết: <s>{snapshot.list_price:,.0f}₫</s>\n"

            f"{price_label}: <b>{f_price:,.0f}₫</b> (giảm <b>{pct_int}%</b>)\n"

            f"{voucher_line}"

            f"{rating_line}{sold_line}"

        )

        markup = {"inline_keyboard": [[{"text": f"🛒 Săn Deal {plat_title} ↗", "url": link}]]}

        self._notifier.broadcast_deal(text, reply_markup=markup)



    def _handle_price_error(

        self,

        product_id: int,

        snapshot: Snapshot,

        price: float,

        baseline: float,

        discount: float,

    ):

        if not self._is_subsystem_enabled("price_error_scan_enabled") or self._is_subsystem_enabled("only_target_price_alerts", default=False):

            return

        base_type = "history" if snapshot.list_price is None or baseline != snapshot.list_price else "list_price"

        anom_id = self._db.create_anomaly(

            product_id=product_id,

            platform=snapshot.platform,

            item_key=snapshot.item_key,

            name=snapshot.name,

            url=snapshot.url,

            price=price,

            baseline=baseline,

            baseline_type=base_type,

            discount=discount,

            stage="confirming",

        )

        link = self._linker.build(snapshot.platform, snapshot.url)

        plat_badge = "🔵 [LAZADA]" if snapshot.platform == "lazada" else "🟠 [SHOPEE]"

        disc_pct = round(discount * 100)

        severity = "🚨 CỰC KỲ BẤT THƯỜNG / SẬP GIÁ" if discount >= 0.85 else "⚠️ NGHI LỖI GIÁ"

        plat_title = snapshot.platform.title() if snapshot.platform else "Sàn"



        import html

        text = (

            f"<b>{severity} (-{disc_pct}%)</b>\n\n"

            f"{plat_badge} <b>{html.escape(snapshot.name)}</b>\n"

            f"💰 Giá lỗi: <b>{price:,.0f}₫</b> (Giá gốc: <s>{baseline:,.0f}₫</s>)\n"

            f"🏪 Shop: <b>{html.escape(snapshot.shop or 'Chưa rõ')}</b>"

            f"{(' (⭐ ' + str(snapshot.rating) + ')') if snapshot.rating else ''}\n"

            f"⏳ Trạng thái: <i>Đang tự động quét lại sau 2 phút để xác minh...</i>\n\n"

            f"👉 <i>Admin vui lòng kiểm tra link bên dưới trước khi duyệt đăng kênh.</i>"

        )

        keyboard = {

            "inline_keyboard": [

                [

                    {"text": f"🛒 Mua ngay trên {plat_title} ↗", "url": link},

                    {"text": "📢 Đăng lên Kênh", "callback_data": f"publish_anomaly:{anom_id}"},

                ],

                [

                    {"text": "❌ Bỏ qua / Giá ảo", "callback_data": f"dismiss_anomaly:{anom_id}"}

                ]

            ]

        }

        msg_id = self._notifier.alert_admin(text, reply_markup=keyboard)

        if msg_id and isinstance(msg_id, int):

            self._db.update_anomaly_message_id(anom_id, msg_id)

        elif not isinstance(msg_id, int):

            msg_id = None



        # Launch 2-minute confirmation thread

        def _recheck():

            self._recheck_price_anomaly(anom_id, product_id, snapshot, price, baseline, discount, link, msg_id)



        threading.Thread(target=_recheck, daemon=True, name=f"anomaly-recheck-{anom_id}").start()



    def _recheck_price_anomaly(

        self,

        anom_id: int,

        product_id: int,

        snapshot: Snapshot,

        orig_price: float,

        baseline: float,

        discount: float,

        link: str,

        msg_id: int | None,

    ):

        time.sleep(120)  # Wait 2 minutes for re-scan confirmation

        try:

            fresh = self._adapter.fetch(snapshot.url)

            anom = self._db.get_anomaly(anom_id)

            if not anom or anom["stage"] in ("rejected", "published"):

                return



            import html

            fresh_price = getattr(fresh, "final_price", None) or (fresh.price if fresh else None)

            disc_pct = round(discount * 100)

            plat_badge = "🔵 [LAZADA]" if snapshot.platform == "lazada" else "🟠 [SHOPEE]"

            plat_title = snapshot.platform.title() if snapshot.platform else "Sàn"



            if not fresh or fresh.stock is False or fresh.stock == 0:

                self._db.update_anomaly_stage(anom_id, "rejected", reject_reason="out_of_stock")

                if msg_id:

                    self._notifier.edit_admin_message(

                        msg_id,

                        f"<b>⚠️ DEAL LỖI GIÁ ĐÃ HẾT HÀNG / BỊ HỦY (-{disc_pct}%)</b>\n\n"

                        f"{plat_badge} <b>{html.escape(snapshot.name)}</b>\n"

                        f"📦 Tình trạng: <i>Đã hết hàng (Out of stock) sau lần quét xác minh.</i>",

                    )

                return



            price_diff_ratio = abs(fresh_price - orig_price) / orig_price if orig_price > 0 else 1.0

            if fresh_price and price_diff_ratio <= 0.05 and fresh_price < baseline * 0.5:

                # Confirmed!

                self._db.update_anomaly_stage(anom_id, "confirmed")

                if msg_id:

                    text_confirmed = (

                        f"<b>✅ ĐÃ XÁC NHẬN LỖI GIÁ (GIÁ VẪN CÒN SỐNG)</b>\n\n"

                        f"{plat_badge} <b>{html.escape(snapshot.name)}</b>\n"

                        f"💰 Giá lỗi: <b>{fresh_price:,.0f}₫</b> (Giảm <b>-{disc_pct}%</b> so với <s>{baseline:,.0f}₫</s>)\n"

                        f"📦 Tình trạng: <i>Vẫn còn hàng và giá ổn định sau 2 phút!</i>\n"

                        f"🏪 Shop: <b>{html.escape(snapshot.shop or 'Chưa rõ')}</b>\n\n"

                        f"👉 <i>Bấm 'Đăng lên Kênh' để phát sóng ngay cho mọi người.</i>"

                    )

                    keyboard = {

                        "inline_keyboard": [

                            [

                                {"text": f"🛒 Mua ngay trên {plat_title} ↗", "url": link},

                                {"text": "📢 Đăng lên Kênh", "callback_data": f"publish_anomaly:{anom_id}"},

                            ],

                            [

                                {"text": "❌ Bỏ qua", "callback_data": f"dismiss_anomaly:{anom_id}"}

                            ]

                        ]

                    }

                    self._notifier.edit_admin_message(msg_id, text_confirmed, reply_markup=keyboard)

            else:

                # Shop fixed price

                self._db.update_anomaly_stage(anom_id, "rejected", reject_reason="price_fixed")

                if msg_id:

                    self._notifier.edit_admin_message(

                        msg_id,

                        f"<b>ℹ️ SHOP ĐÃ SỬA LẠI GIÁ (Deal đã kết thúc)</b>\n\n"

                        f"{plat_badge} <b>{html.escape(snapshot.name)}</b>\n"

                        f"💰 Giá ban đầu: <s>{orig_price:,.0f}₫</s> ➔ Giá mới: <b>{fresh_price:,.0f}₫</b>\n"

                        f"Shop đã phát hiện và điều chỉnh lại mức giá về bình thường.",

                    )

        except Exception as exc:

            log.warning("Error during anomaly recheck #%d: %s", anom_id, exc)



    def scan_price_errors(self, keywords: list[str] | None = None) -> list[int]:

        """Scan high-value keywords specifically to discover price errors and deep deals."""

        kws = keywords or ["laptop", "dien thoai", "man hinh", "tai nghe", "ban phim", "chuot gaming"]

        found_pids = []

        for kw in kws:

            try:

                pids = self.discover_keyword(kw, limit=5, lowest_only=True, source="price_error")

                found_pids.extend(pids)

            except Exception as e:

                log.warning("scan_price_errors failed for keyword '%s': %s", kw, e)

        return found_pids



    def run_keyword_search(self, keyword_id: int | None = None) -> dict:

        """Execute keyword-based search with structured filtering and 7-day rejection cache."""

        import json

        from .classifier import classify_product



        keywords = self._db.get_keywords(active_only=True)

        if keyword_id is not None:

            keywords = [k for k in keywords if k["id"] == keyword_id]

            self._db.clear_rejected_items(keyword_id)



        total_scanned = 0

        total_matched = 0

        total_rejected = 0



        for kw_row in keywords:

            kid = kw_row["id"]

            kw_text = kw_row["keyword"]

            try:

                filters = json.loads(kw_row.get("filters_json") or "{}")

            except Exception:

                filters = {}

            filters.setdefault("keyword", kw_text)



            limit = filters.get("max_results") or getattr(self._config, "keyword_result_limit", 30)

            platform = filters.get("platform", "all")

            if platform not in ("shopee", "lazada", "all"):

                platform = "all"



            kw_scanned = 0

            kw_matched = 0

            try:

                urls = self._adapter.search(kw_text, limit=limit, platform=platform, filters=filters)

            except Exception as e:

                log.warning("Keyword search adapter error for '%s': %s", kw_text, e)

                self._db.update_keyword_stats(kid, 0, 0, msg=f"Lỗi tìm kiếm: {e}")

                continue



            for url in urls:

                try:

                    plat = self._adapter.parse_platform(url)

                    ikey = self._adapter.parse_item_key(url)



                    # Check 7-day rejection cache

                    if self._db.is_item_rejected(plat, ikey, kid, max_age_days=7):

                        continue



                    kw_scanned += 1

                    snapshot = self._adapter.fetch(url)



                    # Evaluate filter

                    is_match, verified, reason = classify_product(

                        snapshot,

                        filters,

                        include_unknown=getattr(self._config, "keyword_include_unknown", False),

                    )



                    if not is_match:

                        self._db.record_rejected_item(plat, ikey, kid, reason=reason)

                        total_rejected += 1

                        continue



                    # Accepted match!

                    snapshot.verified = verified

                    pid = self._db.upsert_product_meta(snapshot, source="keyword")

                    self._db.save_snapshot(pid, snapshot, campaign="keyword")

                    self._db.link_keyword_product(kid, pid, verified=verified)

                    kw_matched += 1

                    total_matched += 1



                    if self._config.request_delay_sec > 0:

                        time.sleep(min(self._config.request_delay_sec, 2.0))

                except Exception as e:

                    log.warning("Error processing keyword item %s: %s", url, e)



            total_scanned += kw_scanned

            msg = f"Đã quét {kw_scanned}, tìm thấy {kw_matched} sản phẩm hợp lệ"

            self._db.update_keyword_stats(kid, kw_scanned, kw_matched, msg=msg)



        return {

            "keywords_count": len(keywords),

            "scanned": total_scanned,

            "matched": total_matched,

            "rejected": total_rejected,

        }









def get_adapter(config: Config) -> BaseAdapter:

    """Factory: returns the right adapter for FETCH_MODE. Playwright imported lazily."""

    if config.fetch_mode == "mock":

        from .adapters.mock import MockAdapter

        return MockAdapter()

    if config.fetch_mode == "feed":

        from .adapters.feed import FeedAdapter

        return FeedAdapter()

    from .adapters.playwright import PlaywrightAdapter

    return PlaywrightAdapter(config)

