"""
bot.py — Telegram bot for admin management.

Commands (admin only):
  /theodoi [url] [gia] — add a product URL to the watch list (with interactive buttons)
  /setgia <ref> <gia>  — set target price for product (by ID, Link, or last active)
  /xoa <ref>           — remove product from watch list (by ID or Link)
  /list                — list all tracked products with current prices and quick actions
  /help                — show bot guide and command overview
  /status              — system status: products, last scan, today's deals
  /quota               — check NopeCHA remaining credits
  /quetngay            — trigger an immediate scan
"""
import html
import logging
import threading

import telebot
from telebot.types import (
    BotCommand,
    BotCommandScopeChat,
    BotCommandScopeDefault,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from .config import Config
from .db import DB
from .notifier import Notifier
from .quota import QuotaMonitor
from .scanner import Scanner
from .adapters.base import BaseAdapter
from .affiliate import AffiliateLinker

log = logging.getLogger(__name__)


def _parse_price_input(text: str) -> float | None:
    """Parse flexible price formats: 850k, 1.2m, 850.000, 850,000, 850000."""
    if not text:
        return None
    clean = text.lower().strip()
    if clean.endswith("k"):
        clean = clean[:-1].strip() + "000"
    elif clean.endswith("m") or clean.endswith("tr"):
        val_str = clean.rstrip("mtr").strip()
        try:
            return float(val_str.replace(",", ".")) * 1_000_000
        except ValueError:
            return None
    clean = clean.replace(".", "").replace(",", "").replace("đ", "").replace("vnd", "").strip()
    try:
        val = float(clean)
        return val if val > 0 else None
    except ValueError:
        return None


def create_bot(
    config: Config,
    db: DB,
    scanner: Scanner,
    notifier: Notifier,
    quota: QuotaMonitor,
) -> telebot.TeleBot:
    bot = telebot.TeleBot(config.telegram_token, parse_mode="HTML")
    admin_id = _parse_admin_id(config.admin_chat_id)
    linker = AffiliateLinker(config)
    user_context: dict[int, dict] = {}

    try:
        commands = [
            BotCommand("list", "📦 Danh sách sản phẩm theo dõi"),
            BotCommand("theodoi", "➕ Thêm link theo dõi giá mới"),
            BotCommand("setgia", "🎯 Đặt mức giá mong muốn"),
            BotCommand("quetngay", "⚡ Quét giá ngay lập tức"),
            BotCommand("status", "📊 Trạng thái hệ thống & cào"),
            BotCommand("xoa", "🗑️ Xóa sản phẩm theo dõi"),
            BotCommand("quota", "🛡️ Kiểm tra lượt giải Captcha"),
            BotCommand("tansuat", "⏱️ Xem/đổi tần suất quét (phút)"),
            BotCommand("bienthe", "🏷️ Xem biến thể của sản phẩm"),
            BotCommand("help", "❓ Hướng dẫn sử dụng & cú pháp"),
        ]
        bot.set_my_commands(commands, scope=BotCommandScopeDefault())
        if admin_id:
            try:
                bot.set_my_commands(commands, scope=BotCommandScopeChat(admin_id))
            except Exception:
                pass
    except Exception as exc:
        log.debug("Failed to set bot commands: %s", exc)

    def guard(fn):
        """Decorator: silently ignore messages from non-admin users."""
        def wrapper(msg):
            if msg.from_user.id != admin_id:
                return
            fn(msg)
        return wrapper

    def _execute_track_product(msg, url: str, target_price: float | None = None):
        chat_id = msg.chat.id
        from .adapters.playwright import canonicalize_url
        url = canonicalize_url(url)
        try:
            platform = BaseAdapter.parse_platform(url)
            if platform not in ("shopee", "lazada"):
                raise ValueError(platform)
            item_key = BaseAdapter.parse_item_key(url)
        except Exception:
            bot.reply_to(msg, "⚠️ Link sản phẩm không hợp lệ (hỗ trợ Shopee và Lazada).")
            return

        pid = db.add_product_url(url, platform, item_key, source="user")
        if target_price:
            db.set_target_price(pid, target_price)

        user_context[chat_id] = {"last_product_id": pid}

        wait_msg = bot.reply_to(msg, f"⏳ Đã thêm #{pid} [{platform.upper()}]. Đang quét thông tin sản phẩm...")

        def _scan_and_reply():
            try:
                snap = scanner.scan_product(pid)
                if snap:
                    pname = html.escape(snap.name or f"Sản phẩm #{pid}")
                    price_val = snap.price or 0.0
                    price_str = f"{price_val:,.0f}₫" if price_val > 0 else "Đang cập nhật"
                    list_price_str = f" <s>{snap.list_price:,.0f}₫</s>" if snap.list_price and snap.list_price > price_val else ""
                    v_line = ""
                    if getattr(snap, "voucher_code", "") and getattr(snap, "voucher_discount", 0.0) > 0:
                        v_line = f"🎫 Mã giảm giá: <code>{snap.voucher_code}</code> (-{snap.voucher_discount:,.0f}₫)\n💵 Giá sau áp mã: <b>{(snap.final_price or snap.price):,.0f}₫</b>\n"
                    stock_line = "⚠️ Tình trạng: <i>Hết hàng</i>\n" if snap.stock is False else "📦 Tình trạng: <i>Còn hàng</i>\n"

                    target_line = ""
                    prod_row = db.get_product(pid)
                    tp = prod_row["target_price"] if prod_row and "target_price" in prod_row.keys() else None
                    if tp:
                        target_line = f"🎯 Giá mong muốn: <b>{tp:,.0f}₫</b>\n"

                    plat_badge = "🔵 [Lazada]" if snap.platform == "lazada" else "🟠 [Shopee]"
                    reply_text = (
                        f"✅ <b>Đã theo dõi thành công!</b>\n\n"
                        f"{plat_badge} <b>#{pid} | {pname}</b>\n"
                        f"💰 Giá sàn: <b>{price_str}</b>{list_price_str}\n"
                        f"{v_line}"
                        f"{target_line}"
                        f"{stock_line}"
                        f"🔗 <a href='{linker.build(snap.platform, snap.url)}'>Xem ngay trên {snap.platform.title()} ↗</a>"
                    )
                    markup = InlineKeyboardMarkup()
                    markup.add(
                        InlineKeyboardButton("🎯 Đặt giá mong muốn", callback_data=f"setgia_{pid}"),
                        InlineKeyboardButton("🗑️ Xóa", callback_data=f"del_{pid}"),
                    )
                    bot.edit_message_text(
                        reply_text,
                        chat_id=chat_id,
                        message_id=wait_msg.message_id,
                        parse_mode="HTML",
                        reply_markup=markup,
                        disable_web_page_preview=True,
                    )
            except Exception as err:
                log.warning("Instant scan for /theodoi product #%d error: %s", pid, err)
                try:
                    bot.edit_message_text(
                        f"✅ Đã thêm theo dõi #{pid} [{platform.upper()}]\n<code>{url}</code>\n(Đang chờ chu kỳ quét cập nhật giá)",
                        chat_id=chat_id,
                        message_id=wait_msg.message_id,
                    )
                except Exception:
                    pass

        threading.Thread(target=_scan_and_reply, daemon=True, name=f"bot-theodoi-{pid}").start()

    @bot.message_handler(commands=["theodoi", "track", "add"])
    @guard
    def cmd_theodoi(msg):
        parts = msg.text.split(maxsplit=2)
        if len(parts) < 2:
            markup = InlineKeyboardMarkup(row_width=1)
            markup.add(
                InlineKeyboardButton("🔗 Nhập Link Sản Phẩm", callback_data="td_link"),
                InlineKeyboardButton("🎯 Đặt Giá Mong Muốn", callback_data="td_price"),
            )
            bot.reply_to(
                msg,
                "📦 <b>Quản lý Sản phẩm theo dõi</b>\n\n"
                "Chọn một thao tác bên dưới:\n"
                "• <b>[🔗 Nhập Link Sản Phẩm]</b>: Dán link Shopee / Lazada để theo dõi.\n"
                "• <b>[🎯 Đặt Giá Mong Muốn]</b>: Đặt giá cho sản phẩm vừa thêm gần nhất.\n\n"
                "💡 <i>Hoặc dán nhanh cú pháp:</i>\n"
                "<code>/theodoi &lt;link_sản_phẩm&gt; [giá_mong_muốn]</code>",
                parse_mode="HTML",
                reply_markup=markup,
            )
            return

        url = parts[1].strip()
        target_price = None
        if len(parts) >= 3:
            target_price = _parse_price_input(parts[2])
        _execute_track_product(msg, url, target_price=target_price)

    def _send_list_page(chat_id: int, page: int = 1, reply_msg=None):
        items = db.get_tracked_products_with_latest_price()
        if not items:
            text = (
                "ℹ️ Bạn chưa theo dõi sản phẩm nào trong tab này.\n"
                "👉 Dùng lệnh <code>/theodoi</code> để thêm liên kết sản phẩm."
            )
            if reply_msg:
                bot.reply_to(reply_msg, text, parse_mode="HTML")
            else:
                bot.send_message(chat_id, text, parse_mode="HTML")
            return

        page_size = 5
        total = len(items)
        total_pages = max(1, (total + page_size - 1) // page_size)
        page = max(1, min(page, total_pages))

        start_idx = (page - 1) * page_size
        chunk = items[start_idx : start_idx + page_size]

        header = f"📋 <b>SẢN PHẨM THEO DÕI ({page}/{total_pages})</b> — Tổng: <b>{total}</b> sản phẩm"
        bot.send_message(chat_id, header, parse_mode="HTML")

        for p in chunk:
            pid = p["id"]
            pname = html.escape(p["name"] or "Sản phẩm đang theo dõi")
            url = linker.build(p["platform"], p["url"]) if p["url"] else ""

            price_val = p["current_price"]
            if price_val and price_val > 0:
                price_str = f"{price_val:,.0f}₫"
                if p["current_list_price"] and p["current_list_price"] > price_val:
                    price_str += f" <s>{p['current_list_price']:,.0f}₫</s>"
            else:
                price_str = "<i>Chưa có dữ liệu giá</i>"

            v_line = ""
            if p["current_voucher_code"]:
                v_disc = p["current_voucher_discount"] or 0
                f_price = p["current_final_price"] or price_val or 0
                v_line = f"  🎫 Voucher: <code>{p['current_voucher_code']}</code> (-{v_disc:,.0f}₫) ➔ <b>{f_price:,.0f}₫</b>\n"

            target_line = ""
            if p["target_price"] and p["target_price"] > 0:
                target_line = f"  🎯 Giá mong muốn: <b>{p['target_price']:,.0f}₫</b>\n"

            stock_str = "Hết hàng" if p["current_stock"] == 0 else "Còn hàng"

            card_text = (
                f"• <b>#{pid} | {pname}</b>\n"
                f"  💰 Giá: <b>{price_str}</b>\n"
                f"{v_line}"
                f"{target_line}"
                f"  📦 Tình trạng: <i>{stock_str}</i>\n"
                f"  🔗 <a href='{url}'>Xem sản phẩm ↗</a>"
            )
            markup = InlineKeyboardMarkup(row_width=2)
            markup.row(
                InlineKeyboardButton("🎯 Đặt giá", callback_data=f"setgia_{pid}"),
                InlineKeyboardButton("🗑️ Xóa", callback_data=f"del_{pid}"),
            )
            bot.send_message(
                chat_id,
                card_text,
                parse_mode="HTML",
                reply_markup=markup,
                disable_web_page_preview=True,
            )

        if total_pages > 1:
            nav_markup = InlineKeyboardMarkup()
            nav_buttons = []
            if page > 1:
                nav_buttons.append(InlineKeyboardButton("◀️ Trang trước", callback_data=f"listpage_{page - 1}"))
            nav_buttons.append(InlineKeyboardButton(f"📄 {page}/{total_pages}", callback_data="noop"))
            if page < total_pages:
                nav_buttons.append(InlineKeyboardButton("Trang sau ▶️", callback_data=f"listpage_{page + 1}"))
            nav_markup.row(*nav_buttons)
            bot.send_message(
                chat_id,
                f"📑 <b>Điều hướng trang ({page}/{total_pages}):</b>",
                parse_mode="HTML",
                reply_markup=nav_markup,
            )

    @bot.message_handler(commands=["list", "ds"])
    @guard
    def cmd_list(msg):
        parts = msg.text.split()
        page = 1
        if len(parts) >= 2 and parts[1].isdigit():
            page = int(parts[1])
        _send_list_page(msg.chat.id, page=page, reply_msg=msg)

    @bot.message_handler(commands=["timkiem", "search", "tim", "find"])
    @guard
    def cmd_timkiem(msg):
        parts = msg.text.split(maxsplit=1)
        if len(parts) < 2:
            bot.reply_to(msg, "Dùng: /timkiem &lt;từ khóa sản phẩm&gt;")
            return
        keyword = parts[1].strip()
        bot.reply_to(msg, f"🔍 Đang tìm kiếm & so sánh các shop để tìm giá thấp nhất cho: <b>{html.escape(keyword)}</b>...")
        pids = scanner.discover_keyword(keyword, limit=5, lowest_only=True)
        if pids:
            pid = pids[0]
            p = db.get_product(pid)
            latest_price = db.get_latest_price(pid)
            price_str = f"{latest_price:,.0f}₫" if latest_price else "Đang cập nhật"
            pname = html.escape(p["name"] or f"Sản phẩm #{pid}") if p else f"Sản phẩm #{pid}"
            purl = linker.build(p["platform"], p["url"]) if p else ""

            with db._lock:
                row = db.conn.execute("SELECT voucher_code, voucher_discount, final_price FROM price_history WHERE product_id=? ORDER BY ts DESC LIMIT 1", (pid,)).fetchone()
            v_line = ""
            if row and row["voucher_code"]:
                f_price = row["final_price"] or latest_price
                disc = row["voucher_discount"] or 0
                v_line = f"🎫 Mã giảm giá: <code>{row['voucher_code']}</code> (-{disc:,.0f}₫)\n💵 Giá sau áp mã: <b>{f_price:,.0f}₫</b>\n"

            plat = (p["platform"] or "shopee").lower() if p else "shopee"
            plat_badge = "🔵 [Lazada] " if plat == "lazada" else ("🟠 [Shopee] " if plat == "shopee" else "")
            bot.reply_to(msg, (
                f"🏆 <b>{plat_badge}ĐÃ TÌM THẤY SẢN PHẨM GIÁ THẤP NHẤT!</b>\n\n"
                f"📦 <b>{pname}</b>\n"
                f"💰 Giá sàn: <b>{price_str}</b>\n"
                f"{v_line}"
                f"🔗 <a href='{purl}'>Xem ngay trên {plat.title()} ↗</a>\n\n"
                f"✅ Đã tự động thêm vào danh sách theo dõi giá."
            ))

        else:
            bot.reply_to(msg, f"⚠️ Không tìm thấy sản phẩm hoặc sàn chặn tìm kiếm với từ khóa: <b>{html.escape(keyword)}</b>")

    @bot.message_handler(commands=["status"])
    @guard
    def cmd_status(msg):
        products = db.get_active_products()
        last = db.get_last_scan()
        last_info = f"Lần cuối: {last['ts']} ({last['ok']} ok / {last['fail']} lỗi)" if last else "Chưa quét"
        bot.reply_to(msg, (
            f"📊 <b>Deal Hunter Status</b>\n"
            f"Sản phẩm đang theo dõi: <b>{len(products)}</b>\n"
            f"{last_info}"
        ))

    @bot.message_handler(commands=["quota"])
    @guard
    def cmd_quota(msg):
        if config.nopecha_api_key:
            credits = quota.check()
            if credits is None:
                bot.reply_to(msg, "⚠️ Không thể kiểm tra hạn ngạch NopeCHA qua API.")
            else:
                bot.reply_to(msg, f"🔑 NopeCHA API còn <b>{credits}</b> lượt giải hôm nay.")
        else:
            credits = quota.get_remaining_credits()
            solves = quota.get_daily_solves()
            bot.reply_to(
                msg,
                f"🔑 <b>NopeCHA Extension (Chế độ Miễn Phí)</b>\n"
                f"• Lượt giải còn lại hôm nay: <b>{credits}/10</b>\n"
                f"• Đã sử dụng hôm nay: <b>{solves}</b> lượt\n"
                f"<i>(Lượt miễn phí tự động đặt lại vào 00:00 hàng ngày)</i>"
            )

    @bot.message_handler(commands=["quetngay"])
    @guard
    def cmd_quetngay(msg):
        bot.reply_to(msg, "⏳ Đang kích hoạt quét ngay...")
        threading.Thread(target=scanner.scan_all, daemon=True, name="manual-scan-bot").start()

    @bot.message_handler(commands=["setgia", "gia", "target"])
    @guard
    def cmd_setgia(msg):
        parts = msg.text.split(maxsplit=2)
        if len(parts) == 1:
            last_pid = user_context.get(msg.chat.id, {}).get("last_product_id")
            if not last_pid:
                bot.reply_to(msg, "Dùng: <code>/setgia &lt;ID hoặc Link&gt; &lt;giá_mong_muốn&gt;</code>\nVí dụ: <code>/setgia 3261 1200k</code>")
                return
            p = db.get_product(last_pid)
            if not p:
                bot.reply_to(msg, "Dùng: <code>/setgia &lt;ID hoặc Link&gt; &lt;giá_mong_muốn&gt;</code>")
                return
            user_context.setdefault(msg.chat.id, {})["awaiting"] = "target_price"
            user_context[msg.chat.id]["pending_product_id"] = last_pid
            pname = html.escape((p["name"] or f"#{last_pid}")[:40])
            bot.reply_to(msg, f"🎯 Nhập mức giá mong muốn (VNĐ) cho <b>#{last_pid} | {pname}</b>:\n(Ví dụ: <code>850k</code> hoặc <code>850000</code>)")
            return

        if len(parts) == 2:
            val = _parse_price_input(parts[1])
            last_pid = user_context.get(msg.chat.id, {}).get("last_product_id")
            if val and last_pid:
                p = db.get_product(last_pid)
                if p:
                    db.set_target_price(last_pid, val)
                    pname = html.escape((p["name"] or f"#{last_pid}")[:40])
                    bot.reply_to(msg, f"🎯 Đã đặt giá mong muốn cho <b>#{last_pid} | {pname}</b>: <b>{val:,.0f}₫</b>")
                    return
            bot.reply_to(msg, "Dùng: <code>/setgia &lt;ID hoặc Link&gt; &lt;giá_mong_muốn&gt;</code>\nVí dụ: <code>/setgia 3261 1200k</code>")
            return

        ref = parts[1].strip()
        val = _parse_price_input(parts[2])
        if val is None:
            bot.reply_to(msg, "⚠️ Mức giá không hợp lệ (Ví dụ hợp lệ: <code>850000</code> hoặc <code>850k</code>).")
            return

        p = db.get_product_by_ref(ref)
        if not p:
            bot.reply_to(msg, f"⚠️ Không tìm thấy sản phẩm với mã hoặc liên kết: <code>{html.escape(ref)}</code>")
            return

        pid = p["id"]
        db.set_target_price(pid, val)
        user_context.setdefault(msg.chat.id, {})["last_product_id"] = pid
        pname = html.escape((p["name"] or f"#{pid}")[:40])
        bot.reply_to(msg, f"🎯 Đã đặt giá mong muốn cho <b>#{pid} | {pname}</b>: <b>{val:,.0f}₫</b>")

    @bot.message_handler(commands=["xoa", "xoasp", "untrack"])
    @guard
    def cmd_xoa(msg):
        parts = msg.text.split(maxsplit=1)
        if len(parts) < 2:
            bot.reply_to(msg, "Dùng: <code>/xoa &lt;ID hoặc Link sản phẩm&gt;</code>\nVí dụ: <code>/xoa 3261</code> hoặc <code>/xoa https://shopee.vn/...</code>")
            return
        ref = parts[1].strip()
        p = db.get_product_by_ref(ref)
        if not p:
            bot.reply_to(msg, f"⚠️ Không tìm thấy sản phẩm với mã hoặc liên kết: <code>{html.escape(ref)}</code>")
            return
        pid = p["id"]
        pname = html.escape((p["name"] or f"#{pid}")[:40])
        db.delete_product(pid)
        bot.reply_to(msg, f"🗑️ Đã xóa sản phẩm <b>#{pid} | {pname}</b> khỏi danh sách theo dõi.")

    @bot.message_handler(commands=["help", "start"])
    @guard
    def cmd_help(msg):
        text = (
            "🤖 <b>HỆ THỐNG QUẢN LÝ SẢN PHẨM THEO DÕI</b>\n\n"
            "1️⃣ <b>Thêm sản phẩm theo dõi:</b>\n"
            "• Gõ <code>/theodoi</code> để mở nút chọn dán link hoặc đặt giá.\n"
            "• Hoặc gõ nhanh: <code>/theodoi &lt;link_shopee_hoặc_lazada&gt; [giá_mong_muốn]</code>\n"
            "<i>(Bí danh: /track, /add)</i>\n\n"
            "2️⃣ <b>Đặt giá mong muốn:</b>\n"
            "• <code>/setgia &lt;ID hoặc Link&gt; &lt;giá&gt;</code> (Ví dụ: <code>/setgia 3261 1200k</code>)\n"
            "• Hoặc bấm nút <b>[🎯 Đặt giá]</b> ngay dưới mỗi sản phẩm trong danh sách.\n"
            "<i>(Bí danh: /gia, /target)</i>\n\n"
            "3️⃣ <b>Xóa theo dõi:</b>\n"
            "• <code>/xoa &lt;ID hoặc Link&gt;</code> (Ví dụ: <code>/xoa 3261</code>)\n"
            "• Hoặc bấm nút <b>[🗑️ Xóa]</b> trực tiếp dưới sản phẩm.\n"
            "<i>(Bí danh: /untrack)</i>\n\n"
            "4️⃣ <b>Xem danh sách theo dõi:</b>\n"
            "• <code>/list</code> hoặc <code>/ds</code> — Xem toàn bộ sản phẩm kèm mã #ID và nút bấm thao tác nhanh.\n\n"
            "⚡ <b>Các lệnh quản trị khác:</b>\n"
            "• <code>/quetngay</code> — Kích hoạt quét ngay\n"
            "• <code>/status</code> — Trạng thái hệ thống\n"
            "• <code>/quota</code> — Hạn ngạch giải Captcha\n"
            "• <code>/bienthe &lt;ID&gt;</code> — Xem các biến thể của sản phẩm"
        )
        kb = InlineKeyboardMarkup(row_width=2)
        kb.add(
            InlineKeyboardButton("📦 Danh sách", callback_data="btn_list"),
            InlineKeyboardButton("⚡ Quét ngay", callback_data="btn_quetngay"),
            InlineKeyboardButton("📊 Trạng thái", callback_data="btn_status"),
            InlineKeyboardButton("🛡️ Quota Captcha", callback_data="btn_quota"),
            InlineKeyboardButton("➕ Thêm link", callback_data="btn_theodoi"),
            InlineKeyboardButton("❓ Hướng dẫn", callback_data="btn_help"),
        )
        bot.reply_to(msg, text, reply_markup=kb, parse_mode="HTML")

    @bot.message_handler(commands=["menu"])
    @guard
    def cmd_menu(msg):
        kb = InlineKeyboardMarkup(row_width=2)
        kb.add(
            InlineKeyboardButton("📦 Danh sách", callback_data="btn_list"),
            InlineKeyboardButton("⚡ Quét ngay", callback_data="btn_quetngay"),
            InlineKeyboardButton("📊 Trạng thái", callback_data="btn_status"),
            InlineKeyboardButton("🛡️ Quota Captcha", callback_data="btn_quota"),
            InlineKeyboardButton("➕ Thêm link", callback_data="btn_theodoi"),
            InlineKeyboardButton("❓ Hướng dẫn", callback_data="btn_help"),
        )
        bot.reply_to(msg, "🎛️ <b>BẢNG ĐIỀU KHIỂN NHANH</b>\nChọn một chức năng bên dưới:", reply_markup=kb)

    @bot.message_handler(commands=["tansuat"])
    @guard
    def cmd_tansuat(msg):
        parts = msg.text.split()
        if len(parts) < 2:
            saved = db.get_setting("scan_interval_min", str(config.scan_interval_min))
            bot.reply_to(msg, f"⏱️ Tần suất quét hiện tại: <b>{saved}</b> phút/lần.\nĐể đổi: /tansuat &lt;số_phút&gt;")
            return
        try:
            val = int(parts[1])
            if val < 1 or val > 1440:
                bot.reply_to(msg, "⚠️ Tần suất quét phải từ 1 đến 1440 phút.")
                return
            config.scan_interval_min = val
            db.set_setting("scan_interval_min", str(val))
            bot.reply_to(msg, f"✅ Đã cập nhật tần suất quét: <b>{val}</b> phút/lần.")
        except ValueError:
            bot.reply_to(msg, "⚠️ Số phút không hợp lệ.")

    @bot.callback_query_handler(func=lambda call: call.data.startswith("publish_anomaly:") or call.data.startswith("dismiss_anomaly:"))
    def handle_anomaly_callback(call):
        if call.from_user.id != admin_id:
            bot.answer_callback_query(call.id, "Không có quyền thực hiện!", show_alert=True)
            return
        action, anom_id_str = call.data.split(":", 1)
        anom_id = int(anom_id_str)
        anom = db.get_anomaly(anom_id)
        if not anom:
            bot.answer_callback_query(call.id, "Không tìm thấy dữ liệu deal!", show_alert=True)
            return

        if action == "publish_anomaly":
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
            notifier.broadcast_deal(broadcast_text, reply_markup={
                "inline_keyboard": [[{"text": "🛒 Mua Ngay ↗", "url": link}]]
            })
            db.update_anomaly_stage(anom_id, "published")
            bot.answer_callback_query(call.id, "✅ Đã duyệt và phát sóng lên Kênh công khai!")
            try:
                bot.edit_message_reply_markup(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    reply_markup={
                        "inline_keyboard": [
                            [{"text": "✅ ĐÃ DUYỆT ĐĂNG KÊNH", "callback_data": "none"}],
                            [{"text": "🛒 Mở link ↗", "url": link}]
                        ]
                    }
                )
            except Exception:
                pass
        elif action == "dismiss_anomaly":
            db.update_anomaly_stage(anom_id, "rejected", reject_reason="dismissed_by_admin")
            bot.answer_callback_query(call.id, "❌ Đã bỏ qua deal này.")
            try:
                bot.edit_message_reply_markup(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    reply_markup={
                        "inline_keyboard": [[{"text": "❌ ĐÃ BỎ QUA", "callback_data": "none"}]]
                    }
                )
            except Exception:
                pass

    @bot.message_handler(commands=["loigia", "anomalies", "loi_gia"])
    @guard
    def cmd_loigia(msg):
        anomalies = db.get_anomalies(limit=10)
        if not anomalies:
            bot.reply_to(msg, "ℹ️ Hiện chưa có cảnh báo lỗi giá nào được ghi nhận.")
            return
        lines = ["<b>⚠️ DANH SÁCH DEAL NGHI LỖI GIÁ GẦN ĐÂY:</b>\n"]
        for a in anomalies:
            stage_icon = {
                "confirming": "⏳ Đang xác minh",
                "confirmed": "✅ Đã xác nhận",
                "rejected": "❌ Bị từ chối/Sửa giá",
                "published": "📢 Đã đăng kênh",
            }.get(a["stage"], a["stage"])
            disc_pct = round(a["discount"] * 100)
            lines.append(
                f"• #{a['id']} [{a['platform'].upper()}] -{disc_pct}%: <b>{a['price']:,.0f}₫</b>\n"
                f"  {html.escape(a['name'][:40])}…\n"
                f"  Trạng thái: <i>{stage_icon}</i>\n"
            )
    @bot.message_handler(commands=["tukhoa", "kw"])
    @guard
    def cmd_tukhoa(msg):
        parts = msg.text.split(maxsplit=1)
        if len(parts) < 2:
            bot.reply_to(msg, "Dùng: /tukhoa &lt;từ khóa cần theo dõi&gt;\nVí dụ: <code>/tukhoa chuột logitech g102</code>")
            return
        kw_text = parts[1].strip()
        filters = {
            "origin_filter": "default",
            "ship_filter": "default",
            "shop_filter": "any",
            "services": [],
            "max_results": 30,
            "platform": "all",
        }
        kid = db.add_or_update_keyword(kw_text, filters)
        dash_url = f"http://{config.web_host}:{config.web_port}/"
        reply_markup = {
            "inline_keyboard": [
                [{"text": "⚙️ Cài bộ lọc nâng cao trên Dashboard ↗", "url": dash_url}],
            ]
        }
        bot.reply_to(
            msg,
            f"✅ <b>Đã lưu từ khóa theo dõi #{kid}:</b> <code>{html.escape(kw_text)}</code>\n"
            f"🛡️ <i>Bộ lọc: Mặc định (Tất cả). Bạn có thể bấm nút dưới để chọn Việt Nam hoặc Nước ngoài.</i>\n"
            f"⚡ Đang tiến hành quét và lọc sản phẩm...",
            reply_markup=reply_markup,
            parse_mode="HTML",
        )
        def _scan_kw():
            try:
                scanner.run_keyword_search(kid)
            except Exception as e:
                log.warning("Bot keyword search error: %s", e)
        threading.Thread(target=_scan_kw, daemon=True, name=f"bot-kw-{kid}").start()

    @bot.message_handler(commands=["dstukhoa", "keywords"])
    @guard
    def cmd_dstukhoa(msg):
        kws = db.get_keywords()
        if not kws:
            bot.reply_to(msg, "ℹ️ Hiện chưa có từ khóa theo dõi nào. Dùng /tukhoa để thêm.")
            return
        lines = ["<b>📋 DANH SÁCH TỪ KHÓA THEO DÕI:</b>\n"]
        for k in kws:
            st = "🟢 Đang bật" if k["active"] else "⚪ Đã tắt"
            lines.append(
                f"• #{k['id']} <b>{html.escape(k['keyword'])}</b> ({st})\n"
                f"  📊 Lần quét cuối: {k['last_run'] or 'Chưa chạy'} | Đã quét: {k['last_scanned']} | Khớp: <b>{k['last_matched']}</b>"
            )
        bot.reply_to(msg, "\n".join(lines), parse_mode="HTML")

    @bot.message_handler(commands=["bienthe", "variants"])
    @guard
    def cmd_bienthe(msg):
        parts = msg.text.split()
        if len(parts) < 2:
            bot.reply_to(msg, "Dùng: /bienthe &lt;id_sản_phẩm&gt;\nVí dụ: <code>/bienthe 2790</code>")
            return
        try:
            pid = int(parts[1])
        except ValueError:
            bot.reply_to(msg, "⚠️ ID sản phẩm không hợp lệ.")
            return

        prod = db.get_product(pid)
        if not prod:
            bot.reply_to(msg, f"⚠️ Không tìm thấy sản phẩm #{pid}")
            return

        variants = db.get_product_variants(pid)
        pname = html.escape(prod["name"] or "")
        if not variants:
            bot.reply_to(msg, f"ℹ️ Sản phẩm #{pid} (<b>{pname[:40]}</b>) chưa có dữ liệu biến thể chi tiết hoặc là sản phẩm đơn.")
            return

        main_vid = prod["main_variant_id"] if "main_variant_id" in prod.keys() else None
        active_event = db.get_active_fallback_event(pid)
        chosen_vid = active_event["chosen_variant_id"] if active_event and "chosen_variant_id" in active_event.keys() else None
        event_state = active_event["state"] if active_event else None

        in_stock_cnt = sum(1 for v in variants if v["stock_state"] == "in")
        out_stock_cnt = sum(1 for v in variants if v["stock_state"] == "out")

        lines = [
            f"📦 <b>PHÂN LOẠI SẢN PHẨM #{pid}:</b>",
            f"<b>{pname}</b>",
            f"📊 Tổng số: <b>{len(variants)}</b> phân loại ({in_stock_cnt} còn hàng, {out_stock_cnt} hết hàng)\n",
        ]

        for v in variants:
            is_main = (v["id"] == main_vid)
            is_chosen = (v["id"] == chosen_vid)
            prefix = "⭐ [Chính] " if is_main else ("🔄 [Tạm thay] " if is_chosen else "▪️ ")
            stk_str = "Còn hàng" if v["stock_state"] == "in" else ("Hết hàng" if v["stock_state"] == "out" else "Chưa rõ")
            p_str = f"{v['price']:,.0f}₫" if v["price"] else "Chưa có giá"
            v_title = html.escape(v["name"] or f"Phân loại #{v['variant_key']}")
            lines.append(f"{prefix}<b>{v_title}</b>: {p_str} (<i>{stk_str}</i>)")

        if event_state == "suspect_out":
            lines.append("\n⚠️ <i>Biến thể chính nghi hết hàng — hệ thống đang tự động quét nhanh xác minh (Fast Scan)...</i>")
        elif event_state == "active" and chosen_vid:
            lines.append(f"\n🔄 <i>Biến thể chính đã hết hàng — đang tự động tạm thay bằng phân loại #{chosen_vid}.</i>")
        elif event_state == "active" and not chosen_vid:
            lines.append("\n⚠️ <i>Biến thể chính đã hết hàng — không có biến thể thay thế nào đạt chuẩn còn hàng.</i>")

        bot.reply_to(msg, "\n".join(lines), parse_mode="HTML")

    @bot.callback_query_handler(func=lambda call: True)
    def on_callback_query(call):
        if call.from_user.id != admin_id:
            try:
                bot.answer_callback_query(call.id, "⚠️ Không có quyền truy cập.", show_alert=True)
            except Exception:
                pass
            return

        data = call.data or ""
        chat_id = call.message.chat.id
        call.message.from_user = call.from_user

        if data == "btn_list":
            try:
                bot.answer_callback_query(call.id)
            except Exception:
                pass
            cmd_list(call.message)
            return
        elif data == "btn_quetngay":
            try:
                bot.answer_callback_query(call.id)
            except Exception:
                pass
            cmd_quetngay(call.message)
            return
        elif data == "btn_status":
            try:
                bot.answer_callback_query(call.id)
            except Exception:
                pass
            cmd_status(call.message)
            return
        elif data == "btn_quota":
            try:
                bot.answer_callback_query(call.id)
            except Exception:
                pass
            cmd_quota(call.message)
            return
        elif data == "btn_theodoi":
            try:
                bot.answer_callback_query(call.id)
            except Exception:
                pass
            cmd_theodoi(call.message)
            return
        elif data == "btn_help":
            try:
                bot.answer_callback_query(call.id)
            except Exception:
                pass
            cmd_help(call.message)
            return

        if data == "td_link":
            user_context.setdefault(chat_id, {})["awaiting"] = "theodoi_url"
            try:
                bot.answer_callback_query(call.id)
            except Exception:
                pass
            bot.send_message(
                chat_id,
                "👉 <b>Vui lòng gửi link sản phẩm Shopee hoặc Lazada bạn muốn theo dõi:</b>",
                parse_mode="HTML",
            )
            return

        if data == "td_price":
            last_pid = user_context.get(chat_id, {}).get("last_product_id")
            if not last_pid:
                try:
                    bot.answer_callback_query(call.id, "⚠️ Chưa có sản phẩm nào vừa thêm.", show_alert=True)
                except Exception:
                    pass
                return
            p = db.get_product(last_pid)
            if not p:
                try:
                    bot.answer_callback_query(call.id, "⚠️ Không tìm thấy sản phẩm gần nhất.", show_alert=True)
                except Exception:
                    pass
                return
            pname = html.escape((p["name"] or f"#{last_pid}")[:40])
            user_context.setdefault(chat_id, {})["awaiting"] = "target_price"
            user_context[chat_id]["pending_product_id"] = last_pid
            try:
                bot.answer_callback_query(call.id)
            except Exception:
                pass
            bot.send_message(
                chat_id,
                f"🎯 <b>Nhập mức giá mong muốn (VNĐ)</b> cho <b>#{last_pid} | {pname}</b>:\n(Ví dụ: <code>850k</code> hoặc <code>850000</code>)",
                parse_mode="HTML",
            )
            return

        if data.startswith("setgia_"):
            pid_str = data.split("_")[1]
            if pid_str.isdigit():
                pid = int(pid_str)
                p = db.get_product(pid)
                if p:
                    pname = html.escape((p["name"] or f"#{pid}")[:40])
                    user_context.setdefault(chat_id, {})["awaiting"] = "target_price"
                    user_context[chat_id]["pending_product_id"] = pid
                    user_context[chat_id]["last_product_id"] = pid
                    try:
                        bot.answer_callback_query(call.id)
                    except Exception:
                        pass
                    bot.send_message(
                        chat_id,
                        f"🎯 <b>Nhập mức giá mong muốn (VNĐ)</b> cho <b>#{pid} | {pname}</b>:\n(Ví dụ: <code>850k</code> hoặc <code>850000</code>)",
                        parse_mode="HTML",
                    )
                    return
            try:
                bot.answer_callback_query(call.id, "⚠️ Sản phẩm không tồn tại.", show_alert=True)
            except Exception:
                pass
            return

        if data.startswith("del_"):
            pid_str = data.split("_")[1]
            if pid_str.isdigit():
                pid = int(pid_str)
                markup = InlineKeyboardMarkup(row_width=2)
                markup.row(
                    InlineKeyboardButton("⚠️ Xác nhận xóa", callback_data=f"confirmdel_{pid}"),
                    InlineKeyboardButton("❌ Hủy", callback_data=f"cancel_del_{pid}"),
                )
                try:
                    bot.answer_callback_query(call.id)
                except Exception:
                    pass
                try:
                    bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=markup)
                except Exception:
                    pass
                return
            try:
                bot.answer_callback_query(call.id, "⚠️ Thao tác không hợp lệ.", show_alert=True)
            except Exception:
                pass
            return

        if data.startswith("confirmdel_"):
            pid_str = data.split("_")[1]
            if pid_str.isdigit():
                pid = int(pid_str)
                p = db.get_product(pid)
                pname = html.escape((p["name"] or f"#{pid}")[:40]) if p else f"#{pid}"
                db.delete_product(pid)
                try:
                    bot.answer_callback_query(call.id, f"Đã xóa #{pid}")
                except Exception:
                    pass
                try:
                    bot.edit_message_text(
                        f"🗑️ Đã xóa sản phẩm <b>#{pid} | {pname}</b> khỏi danh sách theo dõi.",
                        chat_id=chat_id,
                        message_id=call.message.message_id,
                        parse_mode="HTML",
                    )
                except Exception:
                    pass
                return

        if data.startswith("cancel_del"):
            try:
                bot.answer_callback_query(call.id, "Đã hủy")
            except Exception:
                pass
            parts = data.split("_")
            if len(parts) >= 3 and parts[2].isdigit():
                pid = int(parts[2])
                markup = InlineKeyboardMarkup(row_width=2)
                markup.row(
                    InlineKeyboardButton("🎯 Đặt giá", callback_data=f"setgia_{pid}"),
                    InlineKeyboardButton("🗑️ Xóa", callback_data=f"del_{pid}"),
                )
                try:
                    bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=markup)
                except Exception:
                    pass
            else:
                try:
                    bot.delete_message(chat_id, call.message.message_id)
                except Exception:
                    pass
            return

        if data.startswith("listpage_"):
            page_str = data.split("_")[1]
            try:
                bot.answer_callback_query(call.id)
            except Exception:
                pass
            if page_str.isdigit():
                _send_list_page(chat_id, page=int(page_str))
            return

        if data == "noop":
            try:
                bot.answer_callback_query(call.id)
            except Exception:
                pass
            return

    @bot.message_handler(func=lambda msg: msg.text and not msg.text.startswith("/"))
    @guard
    def on_plain_message(msg):
        chat_id = msg.chat.id
        ctx = user_context.get(chat_id, {})
        awaiting = ctx.get("awaiting")

        if awaiting == "theodoi_url":
            ctx["awaiting"] = None
            url = msg.text.strip()
            _execute_track_product(msg, url)
            return

        if awaiting == "target_price":
            ctx["awaiting"] = None
            pid = ctx.get("pending_product_id") or ctx.get("last_product_id")
            val = _parse_price_input(msg.text)
            if not val or not pid:
                bot.reply_to(msg, "⚠️ Mức giá không hợp lệ. Vui lòng nhập số tiền, ví dụ: <code>850k</code> hoặc <code>850000</code>.")
                return
            p = db.get_product(pid)
            if not p:
                bot.reply_to(msg, "⚠️ Không tìm thấy sản phẩm cần đặt giá.")
                return
            db.set_target_price(pid, val)
            pname = html.escape((p["name"] or f"#{pid}")[:40])
            bot.reply_to(msg, f"🎯 Đã đặt giá mong muốn cho <b>#{pid} | {pname}</b>: <b>{val:,.0f}₫</b>\n(Hệ thống sẽ gửi cảnh báo khi giá chạm hoặc thấp hơn mức này).")
            return


    return bot



def _parse_admin_id(raw: str) -> int:
    try:
        return int(raw.strip())
    except (ValueError, AttributeError):
        return 0   # no valid admin configured — all commands silently ignored
