"""
scan.py — CLI for one-off operations without starting the full system.

Usage:
  python scan.py            # scan once and exit
  python scan.py --loop     # scan in a loop (same as run.py but no web/bot)
  python scan.py --add URL  # add a product and exit
"""
import argparse
import logging
import time

from dotenv import load_dotenv

from deal_hunter.adapters.base import BaseAdapter
from deal_hunter.config import Config
from deal_hunter.db import DB
from deal_hunter.notifier import Notifier
from deal_hunter.quota import QuotaMonitor
from deal_hunter.scanner import Scanner, get_adapter

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s — %(message)s")
log = logging.getLogger(__name__)


def main():
    load_dotenv()
    parser = argparse.ArgumentParser(description="Deal Hunter CLI")
    parser.add_argument("--loop", action="store_true", help="scan in a loop")
    parser.add_argument("--add", metavar="URL", help="add a product URL and exit")
    args = parser.parse_args()

    config = Config.from_env()
    db = DB(config.db_path)
    notifier = Notifier(config)
    quota = QuotaMonitor(config, notifier)
    adapter = get_adapter(config)
    scanner = Scanner(config, adapter, db, notifier, quota)

    if args.add:
        url = args.add.strip()
        platform = BaseAdapter.parse_platform(url)
        item_key = BaseAdapter.parse_item_key(url)
        pid = db.add_product_url(url, platform, item_key)
        print(f"Added product #{pid} [{platform}]: {url}")
        return

    if args.loop:
        log.info("Loop mode: scan every %d minutes", config.scan_interval_min)
        while True:
            scanner.scan_all()
            time.sleep(config.scan_interval_min * 60)
    else:
        result = scanner.scan_all()
        print(f"Done: {result}")


if __name__ == "__main__":
    main()
