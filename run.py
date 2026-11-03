"""
run.py — Main entrypoint: starts Web + Bot + Scheduler in one Python process.

Architecture:
  Main thread  → scheduler loop (scan every N minutes)
  Daemon thread → Flask web dashboard
  Daemon thread → Telegram bot polling (if token configured)
"""
import logging
import threading
import time

from dotenv import load_dotenv

from deal_hunter.bot import create_bot
from deal_hunter.config import Config
from deal_hunter.db import DB
from deal_hunter.notifier import Notifier
from deal_hunter.quota import QuotaMonitor
from deal_hunter.scanner import Scanner, get_adapter
from deal_hunter.web import create_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


def main():
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "login":
        platform = sys.argv[2] if len(sys.argv) > 2 else "shopee"
        from deal_hunter.login import interactive_login
        interactive_login(platform_name=platform, data_dir="data", timeout_sec=180)
        return

    load_dotenv()
    config = Config.from_env()
    db = DB(config.db_path)

    # Load saved intervals & enabled status from DB
    for key, attr in [
        ("scan_interval_min", "scan_interval_min"),
        ("keyword_interval_min", "keyword_interval_min"),
        ("megasale_interval_min", "megasale_interval_min"),
        ("price_error_interval_min", "price_error_interval_min"),
        ("tmall_interval_min", "tmall_interval_min"),
    ]:
        saved = db.get_setting(key)
        if saved and saved.isdigit():
            setattr(config, attr, int(saved))

    for key, attr in [
        ("keyword_scan_enabled", "keyword_scan_enabled"),
        ("megasale_scan_enabled", "megasale_scan_enabled"),
        ("price_error_scan_enabled", "price_error_scan_enabled"),
        ("tmall_scan_enabled", "tmall_scan_enabled"),
    ]:
        saved = db.get_setting(key)
        if saved in ("0", "1"):
            setattr(config, attr, saved == "1")

    for key, attr in [
        ("tmall_min_price", "tmall_min_price"),
        ("tmall_max_price", "tmall_max_price"),
    ]:
        saved = db.get_setting(key)
        if saved is not None:
            try:
                setattr(config, attr, float(saved))
            except ValueError:
                pass

    log.info(
        "Scheduler settings: Tracked=%dm | Keyword=%dm (enabled=%s) | MegaSale=%dm (enabled=%s) | PriceError=%dm (enabled=%s) | TMALL=%dm (enabled=%s)",
        config.scan_interval_min,
        getattr(config, "keyword_interval_min", 180),
        config.keyword_scan_enabled,
        getattr(config, "megasale_interval_min", 60),
        config.megasale_scan_enabled,
        getattr(config, "price_error_interval_min", 60),
        config.price_error_scan_enabled,
        getattr(config, "tmall_interval_min", 120),
        config.tmall_scan_enabled,
    )

    notifier = Notifier(config)
    quota = QuotaMonitor(config, notifier, db=db)
    adapter = get_adapter(config)
    scanner = Scanner(config, adapter, db, notifier, quota)

    # Flask web dashboard (daemon thread)
    app = create_app(config, db, scanner)
    threading.Thread(
        target=lambda: app.run(host=config.web_host, port=config.web_port, debug=False, threaded=True),
        daemon=True,
        name="web",
    ).start()
    log.info("Dashboard: http://%s:%d", config.web_host, config.web_port)

    # Telegram bot polling (daemon thread, only if configured)
    if config.telegram_token:
        bot = create_bot(config, db, scanner, notifier, quota)
        threading.Thread(
            target=bot.infinity_polling,
            kwargs={"timeout": 20, "long_polling_timeout": 5},
            daemon=True,
            name="bot",
        ).start()
        log.info("Telegram bot started")
    else:
        log.warning("TELEGRAM_TOKEN not set — bot disabled")


    while True:
        try:
            scanner.scan_due()
        except Exception as scan_err:
            log.exception("Scheduler scan_due error: %s", scan_err)
        quota.reset()
        time.sleep(10)


if __name__ == "__main__":
    main()
