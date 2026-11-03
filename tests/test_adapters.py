"""Tests for BaseAdapter URL parsing utilities."""
import pytest
from deal_hunter.adapters.base import BaseAdapter


@pytest.mark.parametrize("url,expected_platform", [
    ("https://shopee.vn/product-name-i.123456.789012", "shopee"),
    ("https://www.lazada.vn/products/name-i123456-s789.html", "lazada"),
    ("https://www.tiktok.com/shop/product/12345abc", "tiktok"),
    ("https://example.com/product", "unknown"),
])
def test_parse_platform(url, expected_platform):
    assert BaseAdapter.parse_platform(url) == expected_platform


@pytest.mark.parametrize("url,expected_key", [
    ("https://shopee.vn/product-i.111111.222222", "111111.222222"),
    ("https://shopee.vn/product/111111/222222", "111111.222222"),
    ("https://www.lazada.vn/products/name-i111111-s222222.html", "111111.222222"),
    ("https://www.lazada.vn/products/pdp-i260193102.html", "260193102"),
    ("https://www.tiktok.com/shop/product/abc123xyz", "abc123xyz"),
])
def test_parse_item_key(url, expected_key):
    assert BaseAdapter.parse_item_key(url) == expected_key


def test_parse_item_key_fallback_is_stable():
    url = "https://example.com/some/path"
    key1 = BaseAdapter.parse_item_key(url)
    key2 = BaseAdapter.parse_item_key(url)
    assert key1 == key2
    assert len(key1) == 16   # md5 hex truncated to 16 chars


def test_feed_adapter_csv(tmp_path):
    csv_file = tmp_path / "feed.csv"
    csv_file.write_text(
        "url,name,shop,price,list_price,stock,rating,sold\n"
        "https://shopee.vn/p-i.1.2,Test Item,Test Shop,100000,150000,1,4.5,50\n",
        encoding="utf-8",
    )
    from deal_hunter.adapters.feed import FeedAdapter
    adapter = FeedAdapter(str(csv_file))
    assert adapter.discover() == ["https://shopee.vn/p-i.1.2"]
    snap = adapter.fetch("https://shopee.vn/p-i.1.2")
    assert snap.price == 100000.0
    assert snap.list_price == 150000.0
    assert snap.stock is True
    assert snap.rating == 4.5
    assert snap.sold == 50


def test_feed_adapter_json(tmp_path):
    import json
    json_file = tmp_path / "feed.json"
    json_file.write_text(
        json.dumps([{
            "url": "https://shopee.vn/p-i.3.4",
            "name": "JSON Item",
            "price": 200000,
            "stock": "0",
        }]),
        encoding="utf-8",
    )
    from deal_hunter.adapters.feed import FeedAdapter
    adapter = FeedAdapter(str(json_file))
    snap = adapter.fetch("https://shopee.vn/p-i.3.4")
    assert snap.price == 200000.0
    assert snap.stock is False


def test_feed_adapter_missing_url(tmp_path):
    from deal_hunter.adapters.feed import FeedAdapter, FetchError
    adapter = FeedAdapter(str(tmp_path / "nonexistent.csv"))
    with pytest.raises(FetchError):
        adapter.fetch("https://shopee.vn/p-i.9.9")


def test_mock_adapter():
    from deal_hunter.adapters.mock import MockAdapter
    adapter = MockAdapter(price_sequence=[100.0, 80.0])
    s1 = adapter.fetch("https://shopee.vn/p-i.1.1")
    s2 = adapter.fetch("https://shopee.vn/p-i.1.1")
    assert s1.price == 100.0
    assert s2.price == 80.0
    urls_shopee = adapter.search("chuot logitech", limit=3, platform="shopee")
    assert len(urls_shopee) == 3
    assert all("shopee.vn" in u for u in urls_shopee)

    urls_lzd = adapter.search("chuot logitech", limit=3, platform="lazada")
    assert len(urls_lzd) == 3
    assert all("lazada.vn" in u for u in urls_lzd)

    urls_all = adapter.search("chuot logitech", limit=4, platform="all")
    assert len(urls_all) == 4
    assert any("shopee.vn" in u for u in urls_all)
    assert any("lazada.vn" in u for u in urls_all)


def test_feed_adapter_search(tmp_path):
    csv_file = tmp_path / "feed.csv"
    csv_file.write_text(
        "url,name,shop,price,list_price,stock,rating,sold\n"
        "https://shopee.vn/p-1,Chuot Logitech G102,Shop A,100000,150000,1,4.5,50\n"
        "https://shopee.vn/p-2,Ban phim Akko,Shop B,500000,600000,1,4.8,20\n",
        encoding="utf-8",
    )
    from deal_hunter.adapters.feed import FeedAdapter
    adapter = FeedAdapter(str(csv_file))
    found = adapter.search("logitech", limit=5)
    assert found == ["https://shopee.vn/p-1"]
    none_found = adapter.search("tai nghe", limit=5)
    assert none_found == []


def test_parse_shopee_extracts_lowest_instock_model(config):
    from unittest.mock import MagicMock
    from deal_hunter.adapters.playwright import PlaywrightAdapter

    adapter = PlaywrightAdapter(config)
    mock_page = MagicMock()
    pdp_payload = {
        "data": {
            "item": {
                "title": "Bàn Phím Cơ Aula F75",
                "models": [
                    {"name": "Bản Đắt", "price": 120_000_000, "price_before_discount": 150_000_000, "stock": 5},
                    {"name": "Bản Rẻ", "price": 85_000_000, "price_before_discount": 100_000_000, "stock": 10},
                    {"name": "Hết Hàng", "price": 50_000_000, "price_before_discount": 70_000_000, "stock": 0},
                ],
                "item_rating": {"rating_star": 4.9},
                "historical_sold": 1500,
            }
        }
    }
    snap = adapter._parse_shopee(mock_page, "https://shopee.vn/p-i.1.2", pdp_payload=pdp_payload)
    # Lowest in-stock model is 85_000_000 / 100_000 = 850.0 (or scaled properly)
    assert snap.price == 850.0
    assert "Bản Rẻ" in snap.name
    assert snap.list_price == 1000.0  # list price of the selected lowest model


def test_parse_shopee_prioritizes_target_sku_when_in_stock(config):
    from unittest.mock import MagicMock
    from deal_hunter.adapters.playwright import PlaywrightAdapter

    adapter = PlaywrightAdapter(config)
    mock_page = MagicMock()
    pdp_payload = {
        "data": {
            "item": {
                "title": "Bàn Phím Cơ Aula F75",
                "models": [
                    {"modelid": 111, "name": "Bản Đắt", "price": 120_000_000, "price_before_discount": 150_000_000, "stock": 5},
                    {"modelid": 222, "name": "Bản Rẻ", "price": 85_000_000, "price_before_discount": 100_000_000, "stock": 10},
                    {"modelid": 333, "name": "Hết Hàng", "price": 50_000_000, "price_before_discount": 70_000_000, "stock": 0},
                ],
                "item_rating": {"rating_star": 4.9},
                "historical_sold": 1500,
            }
        }
    }
    # 1. User decision (ADR 0054): always track lowest in-stock model across entire listing
    snap_target = adapter._parse_shopee(mock_page, "https://shopee.vn/p-i.1.2", pdp_payload=pdp_payload, target_sku="111")
    assert snap_target.price == 850.0
    assert "Bản Rẻ" in snap_target.name
    assert snap_target.list_price == 1000.0

    # 2. When target_sku 333 is out of stock, it falls back to lowest in-stock model (222)
    snap_fallback = adapter._parse_shopee(mock_page, "https://shopee.vn/p-i.1.2", pdp_payload=pdp_payload, target_sku="333")
    assert snap_fallback.price == 850.0
    assert "Bản Rẻ" in snap_fallback.name


def test_is_blocked_does_not_trigger_on_pdp_error_alone(config):
    from unittest.mock import MagicMock
    from deal_hunter.adapters.playwright import PlaywrightAdapter

    adapter = PlaywrightAdapter(config)
    mock_page = MagicMock()
    mock_page.url = "https://shopee.vn/san-pham-i.123.456"
    assert adapter._is_blocked(mock_page, {"error": 90309999}) is False

    mock_page.url = "https://shopee.vn/verify/traffic/error?home_url=..."
    assert adapter._is_blocked(mock_page) is True


def test_parse_shopee_honors_promotional_price_min(config):
    from unittest.mock import MagicMock
    from deal_hunter.adapters.playwright import PlaywrightAdapter

    adapter = PlaywrightAdapter(config)
    mock_page = MagicMock()
    pdp_payload = {
        "data": {
            "item": {
                "title": "Bàn Phím Cơ Aula F75",
                "price_min": 79_000_000,  # Promotional price min on single-SKU product
                "price": 85_000_000,
                "stock": 10,
            }
        }
    }
    snap = adapter._parse_shopee(mock_page, "https://shopee.vn/p-i.1.2", pdp_payload=pdp_payload)
    # Honors promotional 79k price_min
    assert snap.price == 790.0


def test_find_best_voucher():
    from deal_hunter.adapters.playwright import _find_best_voucher
    vouchers = [
        {"voucher_code": "VOUCHER10K", "min_spend": 50_000_00000, "discount_value": 10_000_00000},
        {"voucher_code": "VOUCHER10PCT", "min_spend": 50_000_00000, "discount_percentage": 10, "discount_cap": 20_000_00000},
        {"voucher_code": "VOUCHER50K", "min_spend": 200_000_00000, "discount_value": 50_000_00000},
    ]
    # At 70,000₫: eligible for 10k (10,000₫) and 10% (7,000₫ capped at 20,000₫). Best is VOUCHER10K.
    code, disc = _find_best_voucher(70_000.0, vouchers)
    assert code == "VOUCHER10K"
    assert disc == 10_000.0

    # At 150,000₫: 10% is 15,000₫ vs 10k fixed. Best is VOUCHER10PCT.
    code, disc = _find_best_voucher(150_000.0, vouchers)
    assert code == "VOUCHER10PCT"
    assert disc == 15_000.0

    # Below 50,000₫: none eligible
    code, disc = _find_best_voucher(40_000.0, vouchers)
    assert code == ""
    assert disc == 0.0


def test_voucher_stacking_multi_tier():
    from deal_hunter.adapters.playwright import _find_best_voucher
    vouchers = [
        {"voucher_code": "SHOP_30K", "voucher_type": "shop", "min_spend": 100_000, "discount_value": 30_000, "is_vnd": True},
        {"voucher_code": "SHOP_20K", "voucher_type": "shop", "min_spend": 100_000, "discount_value": 20_000, "is_vnd": True},
        {"voucher_code": "COIN_10PCT", "voucher_type": "coins", "min_spend": 50_000, "discount_percentage": 10, "discount_cap": 25_000, "is_vnd": True},
        {"voucher_code": "BONUS_15K", "voucher_type": "platform", "min_spend": 150_000, "discount_value": 15_000, "is_vnd": True},
    ]
    # At 200,000₫: shop SHOP_30K + platform BONUS_15K; coins never lower the price paid
    code, disc = _find_best_voucher(200_000.0, vouchers)
    assert "SHOP_30K" in code
    assert "COIN_10PCT" not in code
    assert "BONUS_15K" in code
    assert disc == 45_000.0


def test_parse_shopee_extracts_voucher(config):
    from unittest.mock import MagicMock
    from deal_hunter.adapters.playwright import PlaywrightAdapter

    adapter = PlaywrightAdapter(config)
    mock_page = MagicMock()
    pdp_payload = {
        "data": {
            "item": {
                "title": "Cáp Sạc Essager 29W",
                "price": 69_300_00000,
            },
            "shop_vouchers": [
                {
                    "voucher_code": "AUCB588",
                    "min_spend": 50_000_00000,
                    "discount_percentage": 10,
                    "discount_cap": 20_000_00000,
                }
            ]
        }
    }
    snap = adapter._parse_shopee(mock_page, "https://shopee.vn/p-i.1.2", pdp_payload=pdp_payload)
    assert snap.price == 69_300.0
    assert snap.voucher_code == "AUCB588"
    assert snap.voucher_discount == 6_930.0
    assert snap.final_price == 62_370.0


def test_parse_shopee_detects_out_of_stock(config):
    from unittest.mock import MagicMock
    from deal_hunter.adapters.playwright import PlaywrightAdapter

    adapter = PlaywrightAdapter(config)
    mock_page = MagicMock()

    # Case 1: models list exists, but all models have 0 stock
    payload_sold_out_models = {
        "data": {
            "item": {
                "title": "Bàn Phím Aula F75 Hết Hàng",
                "price": 800_000_00000,
                "models": [
                    {"name": "Trắng", "price": 800_000_00000, "stock": 0},
                    {"name": "Đen", "price": 850_000_00000, "stock": 0},
                ],
            }
        }
    }
    snap1 = adapter._parse_shopee(mock_page, "https://shopee.vn/p-i.1.2", pdp_payload=payload_sold_out_models)
    assert snap1.stock is False

    # Case 2: item status is out_of_stock
    payload_item_status = {
        "data": {
            "item": {
                "title": "Tai nghe bluetooth",
                "price": 200_000_00000,
                "stock": 0,
                "item_status": "out_of_stock",
            }
        }
    }
    snap2 = adapter._parse_shopee(mock_page, "https://shopee.vn/p-i.3.4", pdp_payload=payload_item_status)
    assert snap2.stock is False

    # Case 3: In-stock item with available models
    payload_in_stock = {
        "data": {
            "item": {
                "title": "Chuột Gaming",
                "price": 300_000_00000,
                "models": [
                    {"name": "Đen", "price": 300_000_00000, "stock": 15},
                ],
            }
        }
    }
    snap3 = adapter._parse_shopee(mock_page, "https://shopee.vn/p-i.5.6", pdp_payload=payload_in_stock)
    assert snap3.stock is True


def test_parse_lazada(config):
    import json
    from unittest.mock import MagicMock
    from deal_hunter.adapters.playwright import PlaywrightAdapter

    adapter = PlaywrightAdapter(config)
    mock_page = MagicMock()
    mock_page.url = "https://www.lazada.vn/products/tai-nghe-bluetooth-i123456-s789.html"

    # Test JSON-LD extraction
    json_ld = json.dumps({
        "@type": "Product",
        "name": "Tai Nghe Bluetooth Chống Ồn",
        "offers": {
            "price": "450000",
            "priceCurrency": "VND",
            "availability": "https://schema.org/InStock",
        },
        "aggregateRating": {
            "ratingValue": "4.9",
            "reviewCount": "120",
        }
    })
    mock_script_loc = MagicMock()
    mock_script_loc.all_inner_texts.return_value = [json_ld]
    mock_page.locator.return_value = mock_script_loc
    mock_page.evaluate.return_value = None

    snap = adapter._parse_lazada(mock_page, "https://www.lazada.vn/products/tai-nghe-bluetooth-i123456-s789.html")
    assert snap.platform == "lazada"
    assert snap.item_key == "123456.789"
    assert snap.name == "Tai Nghe Bluetooth Chống Ồn"
    assert snap.price == 450_000.0
    assert snap.stock is True
    assert snap.rating == 4.9
    assert snap.sold == 120


def test_crawl_lazada_flash_sale_blocked(config):
    from unittest.mock import MagicMock
    from deal_hunter.adapters.playwright import PlaywrightAdapter

    adapter = PlaywrightAdapter(config)
    adapter._ctx = MagicMock()
    mock_page = MagicMock()
    adapter._ctx.new_page.return_value = mock_page
    mock_page.url = "https://www.lazada.vn/punish?x5sec=blocked"

    snaps = adapter._crawl_lazada_flash_sale_sync(limit=10)
    assert snaps == []


def test_parse_lazada_vouchers(config):
    import json
    from unittest.mock import MagicMock
    from deal_hunter.adapters.playwright import PlaywrightAdapter

    adapter = PlaywrightAdapter(config)
    mock_page = MagicMock()
    mock_page.url = "https://www.lazada.vn/products/chuot-gaming-i111-s222.html"

    json_ld = json.dumps({
        "@type": "Product",
        "name": "Chuột Gaming Logitech",
        "offers": {"price": "500000", "availability": "https://schema.org/InStock"}
    })
    mock_loc = MagicMock()
    mock_loc.all_inner_texts.return_value = [json_ld]
    mock_page.locator.return_value = mock_loc

    # Return vouchers: 10% and 30k
    mock_page.evaluate.return_value = ["Voucher Giảm 10%", "Giảm 30.000₫"]
    snap = adapter._parse_lazada(mock_page, "https://www.lazada.vn/products/chuot-gaming-i111-s222.html")
    assert snap.price == 500_000.0
    assert snap.voucher_discount == 50_000.0
    assert snap.final_price == 450_000.0
    assert snap.voucher_code == "LAZADA_10PCT"


def test_crawl_lazada_flash_sale_dom_cards_parsing(config):
    from unittest.mock import MagicMock
    from deal_hunter.adapters.playwright import PlaywrightAdapter

    adapter = PlaywrightAdapter(config)
    adapter._ctx = MagicMock()
    mock_page = MagicMock()
    adapter._ctx.new_page.return_value = mock_page
    mock_page.url = "https://www.lazada.vn/flash-sale/"

    card1 = {
        "cleanUrl": "https://www.lazada.vn/products/milk-i100.html",
        "rawUrl": "https://www.lazada.vn/products/milk-i100.html",
        "title": "Vinamilk Dielac Gold Powdered Milk 4 Boxes 1400g",
        "text": "Vinamilk Dielac Gold Powdered Milk 4 Boxes 1400g | 503.442 | ₫ | 503.442 | ₫",
    }
    card2 = {
        "cleanUrl": "https://www.lazada.vn/products/earphone-i200.html",
        "rawUrl": "https://www.lazada.vn/products/earphone-i200.html",
        "title": "Tai Nghe Bluetooth 5.3 Nhét Tai X55",
        "text": "Tai Nghe Bluetooth 5.3 Nhét Tai X55 | 93.456 ₫ -51% | (2160)",
    }
    mock_page.evaluate.return_value = [card1, card2]

    snaps = adapter._crawl_lazada_flash_sale_sync(limit=10)
    assert len(snaps) == 2
    # card1: 1400g in title must not be parsed as price 1400
    assert snaps[0].price == 503442.0
    assert snaps[0].name == "Vinamilk Dielac Gold Powdered Milk 4 Boxes 1400g"

    # card2: discount and reviews/sold count extracted
    assert snaps[1].price == 93456.0
    assert snaps[1].list_price == 191000.0
    assert snaps[1].sold == 2160
    assert snaps[1].rating == 4.8


def test_parse_lazada_v2_price_module(config):
    """Test extracting salePrice and originalPrice from Lazada V2 price module."""
    import json
    from unittest.mock import MagicMock
    from deal_hunter.adapters.playwright import PlaywrightAdapter

    adapter = PlaywrightAdapter(config)
    mock_page = MagicMock()
    mock_page.url = "https://www.lazada.vn/products/sua-vinamilk-i100.html"

    # ld+json has NO price (real Lazada behavior)
    json_ld = json.dumps({
        "@type": "Product",
        "name": "5 Hộp Sữa Vinamilk 400g",
        "offers": {"availability": "https://schema.org/InStock"}
    })

    def fake_locator(sel):
        loc = MagicMock()
        if sel == 'script[type="application/ld+json"]':
            loc.all_inner_texts.return_value = [json_ld]
        elif ".pdp-v2-product-price-content-salePrice" in sel or "salePrice" in sel:
            loc.count.return_value = 1
            loc.first.inner_text.return_value = "442.147₫"
        elif ".pdp-v2-product-price-content-originalPrice-amount" in sel or "originalPrice" in sel:
            loc.count.return_value = 1
            loc.first.inner_text.return_value = "541.404 ₫"
        else:
            loc.count.return_value = 0
            loc.inner_text.return_value = ""
        return loc

    mock_page.locator.side_effect = fake_locator
    mock_page.evaluate.return_value = []

    snap = adapter._parse_lazada(mock_page, "https://www.lazada.vn/products/sua-vinamilk-i100.html")
    assert snap.price == 442147.0
    assert snap.list_price == 541404.0
    assert snap.final_price == 442147.0
    assert snap.name == "5 Hộp Sữa Vinamilk 400g"


def test_parse_lazada_raises_fetch_error_when_no_price(config):
    """When price cannot be parsed and item is in stock, raise FetchError instead of returning 0.0."""
    import pytest
    from unittest.mock import MagicMock
    from deal_hunter.adapters.base import FetchError
    from deal_hunter.adapters.playwright import PlaywrightAdapter

    adapter = PlaywrightAdapter(config)
    mock_page = MagicMock()
    mock_page.url = "https://www.lazada.vn/products/item-i100.html"

    mock_loc = MagicMock()
    mock_loc.count.return_value = 0
    mock_loc.all_inner_texts.return_value = []
    mock_loc.inner_text.return_value = "Item description without price"
    mock_page.locator.return_value = mock_loc
    mock_page.evaluate.return_value = False

    with pytest.raises(FetchError):
        adapter._parse_lazada(mock_page, "https://www.lazada.vn/products/item-i100.html")


def test_parse_lazada_voucher_promotion_tags_and_min_spend(config):
    """Voucher with min_spend higher than price is rejected; valid voucher is accepted."""
    import json
    from unittest.mock import MagicMock
    from deal_hunter.adapters.playwright import PlaywrightAdapter

    adapter = PlaywrightAdapter(config)
    mock_page = MagicMock()
    mock_page.url = "https://www.lazada.vn/products/item-i100.html"

    json_ld = json.dumps({
        "@type": "Product",
        "name": "Nồi Cơm Điện Cao Tần",
        "offers": {"price": "200000", "availability": "https://schema.org/InStock"}
    })
    mock_loc = MagicMock()
    mock_loc.all_inner_texts.return_value = [json_ld]
    mock_page.locator.return_value = mock_loc

    # Two vouchers:
    # 1. Giảm 50k đơn từ 300k (min_spend 300k > item price 200k -> rejected)
    # 2. 10% Giảm (discount 20k -> accepted)
    mock_page.evaluate.return_value = ["Giảm 50k đơn từ 300k", "10% Giảm"]

    snap = adapter._parse_lazada(mock_page, "https://www.lazada.vn/products/item-i100.html")
    assert snap.price == 200_000.0
    assert snap.voucher_code == "LAZADA_10PCT"
    assert snap.voucher_discount == 20_000.0
    assert snap.final_price == 180_000.0


def test_parse_lazada_voucher_from_title(config):
    """When DOM has no voucher but title contains [VOUCHER 25%], voucher is extracted from title."""
    import json
    from unittest.mock import MagicMock
    from deal_hunter.adapters.playwright import PlaywrightAdapter

    adapter = PlaywrightAdapter(config)
    mock_page = MagicMock()
    mock_page.url = "https://www.lazada.vn/products/vifon-i100.html"

    json_ld = json.dumps({
        "@type": "Product",
        "name": "[VOUCHER 25%] Thùng 30 Gói Bún Riêu Cua Vifon 80g",
        "offers": {"price": "100000", "availability": "https://schema.org/InStock"}
    })
    mock_loc = MagicMock()
    mock_loc.all_inner_texts.return_value = [json_ld]
    mock_page.locator.return_value = mock_loc

    # DOM has no vouchers
    mock_page.evaluate.return_value = []

    snap = adapter._parse_lazada(mock_page, "https://www.lazada.vn/products/vifon-i100.html")
    assert snap.price == 100_000.0
    assert snap.voucher_code == "LAZADA_25PCT"
    assert snap.voucher_discount == 25_000.0
    assert snap.final_price == 75_000.0


def test_parse_voucher_coins_and_cashback():
    from deal_hunter.adapters.playwright import _parse_lazada_voucher_text
    v1 = _parse_lazada_voucher_text("Giảm thêm 5% qua Xu")
    assert v1["voucher_code"] == "COIN_5PCT"
    assert v1["discount_percentage"] == 5.0

    v2 = _parse_lazada_voucher_text("Hoàn tiền MAX 10%")
    assert v2["voucher_code"] == "CASHBACK_10PCT"
    assert v2["discount_percentage"] == 10.0

    v3 = _parse_lazada_voucher_text("Tích lũy 30k")
    assert v3["discount_value"] == 30_000.0

    v4 = _parse_lazada_voucher_text("TMALL Trợ giá 50k")
    assert v4["voucher_code"] == "TMALL_SUBSIDY_50K"
    assert v4["discount_value"] == 50_000.0


def test_parse_lazada_tmall_subsidy_sku(config):
    """When a product has TMALL TRỢ GIÁ badge and subsidized SKU, lowest SKU price and badge are extracted."""
    from unittest.mock import MagicMock
    from deal_hunter.adapters.playwright import PlaywrightAdapter
    import json

    adapter = PlaywrightAdapter(config)
    mock_page = MagicMock()
    mock_page.url = "https://www.lazada.vn/products/akko-gem-01-i111-s222.html"

    json_ld = json.dumps({
        "@type": "Product",
        "name": "Akko | Bàn Phím Cơ Chơi Game Nhôm Hỗ Trợ VIA Tùy Chỉnh",
        "offers": {"price": "3407000", "availability": "https://schema.org/InStock"}
    })
    mock_loc = MagicMock()
    mock_loc.all_inner_texts.return_value = [json_ld]
    mock_page.locator.return_value = mock_loc

    def mock_eval(script):
        if "moduleData" in script:
            return {
                "root": {
                    "fields": {
                        "productTitle": {"title": "Akko | Bàn Phím Cơ Chơi Game Nhôm Hỗ Trợ VIA Tùy Chỉnh"},
                        "skuGalleries": {
                            "skuInfos": {
                                "sku1": {"price": "3407000", "originalPrice": "3407000", "stock": 5},
                                "sku2": {"subsidyPrice": "357735", "originalPrice": "3407000", "stock": 2},
                            }
                        }
                    }
                }
            }
        if "tmall" in script or "badge" in script:
            return True
        return []

    mock_page.evaluate.side_effect = mock_eval

    snap = adapter._parse_lazada(mock_page, "https://www.lazada.vn/products/akko-gem-01-i111-s222.html")
    assert snap.price == 357735.0
    assert snap.list_price == 3407000.0
    assert "[TMALL TRỢ GIÁ]" in snap.name


def test_clean_price_val():
    from deal_hunter.adapters.playwright import _clean_price_val
    assert _clean_price_val("357.735 ₫") == 357735.0
    assert _clean_price_val("₫3.407.000") == 3407000.0
    assert _clean_price_val({"value": 588550, "text": "588.550 ₫"}) == 588550.0
    assert _clean_price_val({"salePrice": "21.001₫"}) == 21001.0
    assert _clean_price_val(123456) == 123456.0
    assert _clean_price_val(None) is None
    assert _clean_price_val("0đ") is None


def test_find_sku_infos():
    from deal_hunter.adapters.playwright import _find_sku_infos
    # Standard nested in skuGalleries
    d1 = {"root": {"fields": {"skuGalleries": {"skuInfos": {"s1": {"price": 1000}}}}}}
    assert "s1" in _find_sku_infos(d1)

    # Nested under tradeInfo
    d2 = {"data": {"tradeInfo": {"skuInfos": {"s2": {"price": 2000}}}}}
    assert "s2" in _find_sku_infos(d2)

    # Directly in data
    d3 = {"skuInfos": {"s3": {"price": 3000}}}
    assert "s3" in _find_sku_infos(d3)


def test_parse_super_subsidy_vouchers():
    from deal_hunter.adapters.playwright import _parse_lazada_voucher_text, _find_best_voucher
    # 96.5% discount voucher (like Ga đệm)
    v_96 = _parse_lazada_voucher_text("Trợ giá 96% đơn từ 0đ")
    assert v_96 is not None
    assert v_96["voucher_code"] == "TMALL_SUBSIDY_96PCT"
    assert v_96["discount_percentage"] == 96.0
    assert v_96["voucher_type"] == "platform"

    # Momclub voucher in millions (like Destiny Gundam)
    v_mom = _parse_lazada_voucher_text("MOMCLUB Giảm 629.850₫")
    assert v_mom is not None
    assert v_mom["voucher_code"] == "MOMCLUB_629K"
    assert v_mom["discount_value"] == 629850.0
    assert v_mom["voucher_type"] == "platform"

    # Stack MOMCLUB platform voucher with Shop Voucher and Coins
    v_shop = {"voucher_code": "SHOP_50K", "voucher_type": "shop", "discount_value": 50000.0, "min_spend": 500000.0}
    v_coin = {"voucher_code": "COIN_5PCT", "voucher_type": "coins", "discount_percentage": 5.0, "min_spend": 0.0}
    code, disc = _find_best_voucher(741000.0, [v_mom, v_shop, v_coin], allow_stacking=True)
    assert "MOMCLUB" in code
    assert "SHOP" in code
    assert "COIN" not in code
    # MOMCLUB: 629850, Shop: 50000; coins excluded -> Total: 679850
    assert disc == 679850.0


def test_coins_badges_never_lower_effective_price():
    """1.000.000₫ item with 'Hoàn 10% xu' + 'Giảm 12%' badges: only the real 12% counts."""
    from deal_hunter.adapters.playwright import _parse_lazada_voucher_text, _find_best_voucher
    vouchers = [_parse_lazada_voucher_text(t) for t in ("Hoàn 10% xu", "Giảm 12%")]
    code, disc = _find_best_voucher(1_000_000.0, [v for v in vouchers if v], allow_stacking=True)
    assert "COIN" not in code and "CASHBACK" not in code
    assert disc == 120_000.0


def test_parse_lazada_with_mtop_payload(config):
    """When MTOP response is intercepted, it is parsed authoritative with formatted strings."""
    from unittest.mock import MagicMock
    from deal_hunter.adapters.playwright import PlaywrightAdapter

    adapter = PlaywrightAdapter(config)
    mock_page = MagicMock()
    mock_page.url = "https://www.lazada.vn/products/ram-lenovo-16gb-i999.html"

    # Page evaluate returns empty moduleData and no badge
    mock_page.evaluate.return_value = []
    mock_loc = MagicMock()
    mock_loc.all_inner_texts.return_value = []
    mock_page.locator.return_value = mock_loc

    # Intercepted MTOP payload
    mtop_payload = {
        "api": "mtop.lazada.item.detail.getdetail",
        "data": {
            "fields": {
                "productTitle": {"title": "RAM Laptop Lenovo DDR4 16GB 3200MHz Chính Hãng"},
                "skuInfos": {
                    "sku_8gb": {"price": "2.500.000 ₫", "originalPrice": "2.500.000 ₫", "stock": 10},
                    "sku_16gb": {"subsidyPrice": "588.550 ₫", "originalPrice": "5.257.000 ₫", "stock": 3},
                },
                "promotions": {
                    "promotionList": [
                        {"name": "TMALL Trợ giá 89% đơn từ 0đ"},
                        {"name": "Voucher Shop Giảm 30.000₫"}
                    ]
                }
            }
        }
    }

    snap = adapter._parse_lazada(mock_page, "https://www.lazada.vn/products/ram-lenovo-16gb-i999.html", lazada_payload=mtop_payload)
    assert snap.price == 588550.0
    assert snap.list_price == 5257000.0
    # TMALL subsidy is NOT double-discounted, but external Shop Voucher is stacked!
    assert snap.voucher_code == "LAZADA_30K"
    assert snap.voucher_discount == 30000.0
    assert snap.final_price == 558550.0


def test_shopee_voucher_stacking_and_variant_trap(config):
    """Test Shopee picks absolute lowest price in-stock variation and appends option name."""
    from unittest.mock import MagicMock
    from deal_hunter.adapters.playwright import PlaywrightAdapter

    adapter = PlaywrightAdapter(config)
    mock_page = MagicMock()

    pdp_payload = {
        "data": {
            "item": {
                "title": "Điện thoại Apple iPhone 15 Pro Max 256GB",
                "price": 50_000_00000,
                "price_min": 50_000_00000,
                "price_before_discount": 29_990_000_00000,
                "models": [
                    {"name": "Ốp lưng trong suốt", "price": 50_000_00000, "stock": 50},
                    {"name": "Titan Tự Nhiên 256GB", "price": 28_000_000_00000, "stock": 10},
                    {"name": "Titan Xanh 256GB", "price": 28_500_000_00000, "stock": 5},
                ],
            },
            "shop_vouchers": [
                {
                    "voucher_code": "APPLE_SHOP_200K",
                    "min_spend": 10_000_000_00000,
                    "discount_value": 200_000_00000,
                }
            ],
        }
    }

    mock_page.evaluate.return_value = ["Mã giảm giá Shopee: Giảm 500k cho đơn hàng từ 15.000.000₫"]

    snap = adapter._parse_shopee(mock_page, "https://shopee.vn/iphone-15-i.111.222", pdp_payload=pdp_payload)

    assert snap.price == 50_000.0
    assert "(Ốp lưng trong suốt)" in snap.name
    assert snap.final_price == 50_000.0

def test_lazada_variant_trap_filter(config):
    """Test Lazada picks lowest price in-stock variation without filtering accessories."""
    from unittest.mock import MagicMock
    from deal_hunter.adapters.playwright import PlaywrightAdapter

    adapter = PlaywrightAdapter(config)
    mock_page = MagicMock()
    mock_page.url = "https://www.lazada.vn/products/laptop-dell-i111.html"
    mock_page.evaluate.return_value = []
    mock_loc = MagicMock()
    mock_loc.all_inner_texts.return_value = []
    mock_page.locator.return_value = mock_loc

    lazada_payload = {
        "root": {
            "fields": {
                "productTitle": {"title": "Laptop Dell XPS 13 9315 Core i7"},
                "skuGalleries": {
                    "skuInfos": {
                        "sku_cable": {"name": "Cáp sạc type-c thay thế", "price": "150.000 ₫", "stock": 10},
                        "sku_laptop": {"name": "Dell XPS 13 16GB 512GB", "price": "25.000.000 ₫", "originalPrice": "30.000.000 ₫", "stock": 2},
                    }
                }
            }
        }
    }

    snap = adapter._parse_lazada(mock_page, "https://www.lazada.vn/products/laptop-dell-i111.html", lazada_payload=lazada_payload)
    assert snap.price == 150_000.0
    assert "(Cáp sạc type-c thay thế)" in snap.name

def test_voucher_regex_exclusions_and_min_spend():
    """Test voucher regex filters shipping/bundles and correctly parses complex min spend text."""
    from deal_hunter.adapters.playwright import _parse_lazada_voucher_text

    # Exclusions
    assert _parse_lazada_voucher_text("Freeship Extra Giảm 30k phí vận chuyển") is None
    assert _parse_lazada_voucher_text("Giảm 15k phí ship cho đơn từ 50k") is None
    assert _parse_lazada_voucher_text("Mua 2 giảm 10%") is None
    assert _parse_lazada_voucher_text("Combo mua kèm deal sốc giảm 20k") is None

    # Complex min spend formats
    v1 = _parse_lazada_voucher_text("Giảm 100k cho đơn hàng từ 1.000.000₫")
    assert v1 is not None
    assert v1["discount_value"] == 100_000.0
    assert v1["min_spend"] == 1_000_000.0

    v2 = _parse_lazada_voucher_text("Voucher giảm 50k áp dụng từ 500k")
    assert v2 is not None
    assert v2["discount_value"] == 50_000.0
    assert v2["min_spend"] == 500_000.0

    v3 = _parse_lazada_voucher_text("Giảm 20% tối đa 50k từ đơn 200k")
    assert v3 is not None
    assert v3["discount_percentage"] == 20.0
    assert v3["discount_cap"] == 50_000.0
    assert v3["min_spend"] == 200_000.0


def test_keyboard_layout_percentage_not_parsed_as_voucher():
    """Ensure percentages without discount keywords (e.g. Layout 75%) are NOT parsed as vouchers."""
    from deal_hunter.adapters.playwright import _parse_lazada_voucher_text

    assert _parse_lazada_voucher_text("Bàn phím cơ AULA S75 Pro 75% Kết nối 3 chế độ") is None
    assert _parse_lazada_voucher_text("AULA | Bàn Phím Cơ AULA S75PRO - Tri-mode Layout 75% LED RGB") is None
    assert _parse_lazada_voucher_text("Áo sơ mi 100% cotton") is None
    assert _parse_lazada_voucher_text("Bàn phím cơ layout 65% gaming") is None


def test_deduplicate_identical_voucher_codes_stacking():
    """Ensure identical voucher codes across categories cannot stack with each other."""
    from deal_hunter.adapters.playwright import _find_best_voucher

    vouchers = [
        {"voucher_code": "LAZADA_75PCT", "voucher_type": "shop", "discount_percentage": 75.0, "min_spend": 0.0},
        {"voucher_code": "LAZADA_75PCT", "voucher_type": "platform", "discount_percentage": 75.0, "min_spend": 0.0},
    ]
    code, disc = _find_best_voucher(1_000_000.0, vouchers, allow_stacking=True)
    assert code == "LAZADA_75PCT"
    assert disc == 750_000.0


def test_lazada_sku_all_zero_stock_detected_as_out_of_stock(config):
    """When all SKUs in skuInfos have stock=0, Lazada product is marked out-of-stock."""
    from unittest.mock import MagicMock
    from deal_hunter.adapters.playwright import PlaywrightAdapter

    adapter = PlaywrightAdapter(config)
    mock_page = MagicMock()
    mock_page.url = "https://www.lazada.vn/products/keyboard-aula-i1.html"
    mock_page.locator.return_value.all_inner_texts.return_value = []
    mock_page.evaluate.return_value = False

    payload = {
        "root": {
            "fields": {
                "productTitle": {"title": "Bàn phím cơ AULA S75 Pro"},
                "skuInfos": {
                    "sku1": {"price": 1_000_000, "stock": 0, "name": "Bàn phím"},
                    "sku2": {"price": 1_200_000, "quantity": 0, "name": "Bàn phím Pro"},
                }
            }
        }
    }
    snap = adapter._parse_lazada(mock_page, mock_page.url, lazada_payload=payload)
    assert snap.stock is False


def test_lazada_dom_disabled_button_overrides_jsonld(config):
    """When JSON-LD reports InStock but DOM buy button is disabled, stock is False."""
    import json
    from unittest.mock import MagicMock
    from deal_hunter.adapters.playwright import PlaywrightAdapter

    adapter = PlaywrightAdapter(config)
    mock_page = MagicMock()
    mock_page.url = "https://www.lazada.vn/products/mouse-i2.html"

    json_ld = json.dumps({
        "@type": "Product",
        "name": "Chuột Gaming",
        "offers": {"price": "500000", "availability": "https://schema.org/InStock"}
    })
    mock_loc = MagicMock()
    mock_loc.all_inner_texts.return_value = [json_ld]
    mock_page.locator.return_value = mock_loc

    # evaluate: has_tmall_badge -> False, crumbs -> [], shop -> '', is_dom_out_of_stock -> True
    mock_page.evaluate.side_effect = [
        None,  # mod_data
        False, # has_tmall_badge
        True,  # is_dom_out_of_stock
        [],    # breadcrumb
        "Shop A" # shop_raw
    ]

    snap = adapter._parse_lazada(mock_page, mock_page.url)
    assert snap.stock is False


def test_shopee_dom_out_of_stock_detected(config):
    """When Shopee DOM has disabled buy button or out of stock text, stock is False."""
    from unittest.mock import MagicMock
    from deal_hunter.adapters.playwright import PlaywrightAdapter

    adapter = PlaywrightAdapter(config)
    mock_page = MagicMock()
    mock_page.url = "https://shopee.vn/product-i.1.2"
    mock_page.locator.return_value.all_inner_texts.return_value = []
    mock_page.locator.return_value.count.return_value = 1
    mock_page.locator.return_value.first.inner_text.return_value = "500.000₫"

    # evaluate: cat_items -> [], is_shopee_out -> True
    mock_page.evaluate.side_effect = [
        True,  # is_shopee_out
        [],    # category breadcrumbs
        [],    # shopee_v_elements
    ]

    snap = adapter._parse_shopee(mock_page, mock_page.url, pdp_payload=None)
    assert snap.stock is False


def test_lazada_multi_variation_one_in_stock_and_tracking_price(config):
    """When a Lazada product has multiple variations and at least one is in-stock, stock is True and in-stock variant price is parsed."""
    from unittest.mock import MagicMock
    from deal_hunter.adapters.playwright import PlaywrightAdapter

    adapter = PlaywrightAdapter(config)
    mock_page = MagicMock()
    mock_page.url = "https://www.lazada.vn/products/aula-s75-i1.html"
    mock_page.locator.return_value.all_inner_texts.return_value = []
    mock_page.locator.return_value.count.return_value = 0

    payload = {
        "root": {
            "fields": {
                "productTitle": {"title": "Bàn phím cơ AULA S75 Pro"},
                "tracking": {"pdt_price": "2.230.000 ₫", "pdt_name": "AULA S75 Pro"},
                "skuInfos": {
                    "sku1": {"operation": {"disable": True}, "quantity": 0, "name": "Switch Red"},
                    "sku2": {"operation": {"disable": False}, "price": "2.230.000", "quantity": {"limit": {"max": 5, "min": 1}}, "name": "Switch Blue"},
                }
            }
        }
    }
    # evaluate: mod_data -> None, has_tmall_badge -> False, is_dom_out_of_stock -> False, crumbs -> [], shop -> ''
    mock_page.evaluate.side_effect = [
        None,  # mod_data
        False, # has_tmall_badge
        False, # is_dom_out_of_stock
        [],    # breadcrumb
        "AULA Official" # shop_raw
    ]
    snap = adapter._parse_lazada(mock_page, mock_page.url, lazada_payload=payload)
    assert snap.stock is True
    assert snap.price == 2_230_000.0


def test_lazada_multi_variation_all_disabled(config):
    """When all variations in skuInfos are disabled, stock is False."""
    from unittest.mock import MagicMock
    from deal_hunter.adapters.playwright import PlaywrightAdapter

    adapter = PlaywrightAdapter(config)
    mock_page = MagicMock()
    mock_page.url = "https://www.lazada.vn/products/aula-s75-i1.html"
    mock_page.locator.return_value.all_inner_texts.return_value = []
    mock_page.locator.return_value.count.return_value = 0

    payload = {
        "root": {
            "fields": {
                "productTitle": {"title": "Bàn phím cơ AULA S75 Pro"},
                "tracking": {"pdt_price": "2.230.000 ₫"},
                "skuInfos": {
                    "sku1": {"operation": {"disable": True}, "quantity": {"limit": {"max": 0}}, "name": "Switch Red"},
                    "sku2": {"operation": {"disable": True}, "quantity": 0, "name": "Switch Blue"},
                }
            }
        }
    }
    mock_page.evaluate.side_effect = [
        None,  # mod_data
        False, # has_tmall_badge
        True,  # is_dom_out_of_stock
        [],    # breadcrumb
        "AULA Official" # shop_raw
    ]
    snap = adapter._parse_lazada(mock_page, mock_page.url, lazada_payload=payload)
    assert snap.stock is False


def test_extract_sku_names():
    from deal_hunter.adapters.playwright import _extract_sku_names
    data = {
        "root": {
            "fields": {
                "skuBase": {
                    "properties": [
                        {
                            "pid": "100",
                            "name": "Màu sắc",
                            "values": [
                                {"vid": "1", "name": "Trắng Switch Reaper"},
                                {"vid": "2", "name": "Pack 10 Switch lẻ"},
                            ]
                        }
                    ],
                    "skus": [
                        {"skuId": "111", "propPath": "100:1"},
                        {"skuId": "222", "propPath": "100:2"},
                    ]
                }
            }
        }
    }
    name_map = _extract_sku_names(data)
    assert name_map["111"] == "Trắng Switch Reaper"
    assert name_map["222"] == "Pack 10 Switch lẻ"


def test_lazada_filters_accessory_skus_and_preserves_genuine_variation(config):
    """Lazada crawler picks lowest in-stock option and appends variation name."""
    from unittest.mock import MagicMock
    from deal_hunter.adapters.playwright import PlaywrightAdapter

    adapter = PlaywrightAdapter(config)
    mock_page = MagicMock()
    mock_page.url = "https://www.lazada.vn/products/aula-f75-i1.html"
    mock_page.locator.return_value.all_inner_texts.return_value = []
    mock_page.locator.return_value.count.return_value = 0

    payload = {
        "root": {
            "fields": {
                "productTitle": {"title": "Bàn phím cơ AULA F75 Pro"},
                "skuBase": {
                    "properties": [
                        {
                            "pid": "100",
                            "values": [
                                {"vid": "1", "name": "Pack 10 Switch lẻ"},
                                {"vid": "2", "name": "Trắng Switch Reaper"},
                            ]
                        }
                    ],
                    "skus": [
                        {"skuId": "s1", "propPath": "100:1"},
                        {"skuId": "s2", "propPath": "100:2"},
                    ]
                },
                "skuInfos": {
                    "s1": {"price": "45.000", "operation": {"disable": False}, "quantity": 10},
                    "s2": {"price": "1.050.000", "originalPrice": "2.230.000", "operation": {"disable": False}, "quantity": 5},
                }
            }
        }
    }
    mock_page.evaluate.side_effect = [
        None,
        False,
        False,
        [],
        "AULA Official"
    ]
    snap = adapter._parse_lazada(mock_page, mock_page.url, lazada_payload=payload)
    assert snap.price == 45_000.0
    assert snap.stock is True
    assert "(Pack 10 Switch lẻ)" in snap.name

def test_lazada_swatch_probing_when_target_or_lowest_sku_out_of_stock(config):
    """When target SKU or lowest MTOP SKU is out-of-stock, swatch probing extracts lowest in-stock variant."""
    from unittest.mock import MagicMock
    from deal_hunter.adapters.playwright import PlaywrightAdapter

    adapter = PlaywrightAdapter(config)
    mock_page = MagicMock()
    mock_page.url = "https://www.lazada.vn/products/atk-n9-i13359329012.html"
    mock_page.locator.return_value.all_inner_texts.return_value = []
    mock_page.locator.return_value.count.return_value = 0

    payload = {
        "root": {
            "fields": {
                "productTitle": {"title": "ATK Neptune N9"},
                "skuInfos": {
                    "sku_den": {"skuId": "sku_den", "price": "518.900", "operation": {"disable": True}, "quantity": 0, "name": "ATK Neptune N9 Pro Đen"},
                    "sku_trang": {"skuId": "sku_trang", "price": "1.005.000", "operation": {"disable": False}, "quantity": 9, "name": "ATK Neptune N9 Pro Trắng"},
                }
            }
        }
    }
    mock_page.evaluate.side_effect = [
        None,  # mod_data
        False, # has_tmall_badge
        False, # is_dom_out_of_stock
        [
            {"index": 0, "name": "ATK Neptune N9 Pro Đen", "isDisabled": False},
            {"index": 1, "name": "ATK Neptune N9 Pro Trắng", "isDisabled": False},
        ], # swatch_info
        None,  # click swatch 0
        {"price": 518900.0, "listPrice": 1314000.0, "inStock": False}, # probe swatch 0
        None,  # click swatch 1
        {"price": 540700.0, "listPrice": 1711000.0, "inStock": True},  # probe swatch 1 (V2 salePrice)
        [],    # breadcrumb
        "ElecHome", # shop_raw
    ]

    snap = adapter._parse_lazada(mock_page, mock_page.url, lazada_payload=payload, target_sku="sku_den")
    assert snap.price == 540_700.0
    assert snap.stock is True
    assert "(ATK Neptune N9 Pro Trắng)" in snap.name
    pro_trang = next(v for v in snap.variants if "Trắng" in v.name)
    assert pro_trang.price == 540_700.0
    assert pro_trang.stock_state == "in"
    # the wait after each click is event-based (price text changed), capped at 500 ms
    assert mock_page.wait_for_function.call_count == 2
    assert mock_page.wait_for_function.call_args.kwargs["timeout"] == 500


def test_lazada_resource_blocking_aborts_images_only_when_enabled(config):
    """Image-blocking trial: images aborted only with block_images; Lazada scripts always continue."""
    from unittest.mock import MagicMock
    from deal_hunter.adapters.playwright import PlaywrightAdapter
    def route(url, rtype):
        r = MagicMock(); r.request.url = url; r.request.resource_type = rtype
        return r
    page = MagicMock()
    PlaywrightAdapter._enable_resource_blocking(page, block_images=True)
    handler = page.route.call_args[0][1]
    img, js = route("https://img.lazcdn.com/a.jpg", "image"), route("https://g.lazcdn.com/x.js", "script")
    handler(img); handler(js)
    img.abort.assert_called_once(); js.continue_.assert_called_once()
    page2 = MagicMock()
    PlaywrightAdapter._enable_resource_blocking(page2)
    img2 = route("https://img.lazcdn.com/a.jpg", "image")
    page2.route.call_args[0][1](img2)
    img2.continue_.assert_called_once()


def test_lazada_target_sku_in_stock_matches_price(config):
    """When target SKU is in-stock, Lazada parser tracks its exact price instead of the minimum."""
    from unittest.mock import MagicMock
    from deal_hunter.adapters.playwright import PlaywrightAdapter

    adapter = PlaywrightAdapter(config)
    mock_page = MagicMock()
    mock_page.url = "https://www.lazada.vn/products/ban-phim-i100-s222.html"
    mock_page.locator.return_value.all_inner_texts.return_value = []
    mock_page.locator.return_value.count.return_value = 0

    payload = {
        "root": {
            "fields": {
                "productTitle": {"title": "Bàn phím cơ AULA S75 Pro"},
                "skuInfos": {
                    "111": {"skuId": "111", "price": "600.000", "operation": {"disable": False}, "quantity": 10, "name": "Kit Barebone"},
                    "222": {"skuId": "222", "price": "1.921.000", "originalPrice": "4.049.000", "operation": {"disable": False}, "quantity": 5, "name": "Bản Full Caramel Latte"},
                }
            }
        }
    }
    mock_page.evaluate.return_value = None

    snap = adapter._parse_lazada(mock_page, mock_page.url, lazada_payload=payload, target_sku="222")
    # User decision (ADR 0054): always track lowest in-stock variation across entire listing
    assert snap.price == 600_000.0
    assert snap.stock is True
    assert "(Kit Barebone)" in snap.name


def test_lazada_target_sku_out_of_stock_falls_back_to_cheapest_in_stock(config):
    """When tracked target SKU is out of stock, Lazada parser automatically falls back to cheapest in-stock variant."""
    from unittest.mock import MagicMock
    from deal_hunter.adapters.playwright import PlaywrightAdapter

    adapter = PlaywrightAdapter(config)
    mock_page = MagicMock()
    mock_page.url = "https://www.lazada.vn/products/ban-phim-i100-s222.html"
    mock_page.locator.return_value.all_inner_texts.return_value = []
    mock_page.locator.return_value.count.return_value = 0

    payload = {
        "root": {
            "fields": {
                "productTitle": {"title": "Bàn phím cơ AULA S75 Pro"},
                "skuInfos": {
                    "111": {"skuId": "111", "price": "1.921.000", "operation": {"disable": False}, "quantity": 10, "name": "Bản Đen Xám"},
                    "222": {"skuId": "222", "price": "2.236.000", "operation": {"disable": True}, "quantity": 0, "name": "Bản Trắng Silent"},
                    "333": {"skuId": "333", "price": "2.489.000", "operation": {"disable": False}, "quantity": 5, "name": "Bản Xanh Glacier"},
                }
            }
        }
    }
    mock_page.evaluate.return_value = None

    # Target SKU 222 is out of stock -> fallback to cheapest in-stock variant (111: 1.921.000)
    snap = adapter._parse_lazada(mock_page, mock_page.url, lazada_payload=payload, target_sku="222")
    assert snap.price == 1_921_000.0
    assert snap.stock is True
    assert "(Bản Đen Xám)" in snap.name


def test_lazada_pdt_price_never_assigned_to_sale_price_and_prefers_dom(config):
    """tracking.pdt_price must never be assigned to price; DOM sale price takes precedence and pdt_price becomes list_price."""
    from unittest.mock import MagicMock
    from deal_hunter.adapters.playwright import PlaywrightAdapter

    adapter = PlaywrightAdapter(config)
    mock_page = MagicMock()
    mock_page.url = "https://www.lazada.vn/products/ban-phim-i100.html"

    # Module data has tracking.pdt_price = 4.049.000 (undiscounted catalog max) and skuInfos without price (MTOP challenged)
    mod_data = {
        "root": {
            "fields": {
                "productTitle": {"title": "Bàn phím cơ AULA S75 Pro"},
                "tracking": {"pdt_price": "4.049.000 ₫"},
                "skuInfos": {
                    "111": {"skuId": "111", "operation": {"disable": False}, "quantity": 10, "name": "Bản Đen"}
                }
            }
        }
    }

    def fake_locator(sel):
        loc = MagicMock()
        if sel == 'script[type="application/ld+json"]':
            loc.all_inner_texts.return_value = []
        elif ".pdp-v2-product-price-content-salePrice" in sel or "salePrice" in sel:
            loc.count.return_value = 1
            loc.first.inner_text.return_value = "1.921.000 ₫"
        else:
            loc.count.return_value = 0
            loc.inner_text.return_value = ""
        return loc

    mock_page.locator.side_effect = fake_locator
    mock_page.evaluate.side_effect = [
        mod_data, # mod_data
        False,    # has_tmall_badge
        False,    # is_dom_out_of_stock
        [],       # breadcrumb
        "Shop A", # shop_raw
    ]

    snap = adapter._parse_lazada(mock_page, mock_page.url)
    assert snap.price == 1_921_000.0
    # ADR 0054: tracking.pdt_price is completely eliminated as list_price to prevent fake 80-90% discount alerts
    assert snap.list_price is None
    assert snap.final_price == 1_921_000.0


def test_shopee_prioritizes_lowest_in_stock_model_ignoring_soldout_and_accessory(config):
    """Shopee strictly tracks the lowest price among in-stock models, ignoring sold-out price_min."""
    from unittest.mock import MagicMock
    from deal_hunter.adapters.playwright import PlaywrightAdapter

    adapter = PlaywrightAdapter(config)
    mock_page = MagicMock()

    payload = {
        "data": {
            "item": {
                "title": "Bàn Phím Cơ AULA S75",
                "price_min": 300_000_00000,
                "models": [
                    {"name": "Trắng - Out of stock", "price": 300_000_00000, "stock": 0},
                    {"name": "Keycap lẻ ESC", "price": 50_000_00000, "stock": 10},
                    {"name": "Xanh Switch Graywood", "price": 1_400_000_00000, "stock": 5},
                    {"name": "Đen Switch Reaper", "price": 950_000_00000, "price_before_discount": 1_500_000_00000, "stock": 8},
                ]
            }
        }
    }
    snap = adapter._parse_shopee(mock_page, "https://shopee.vn/p-i.1.2", pdp_payload=payload)
    assert snap.price == 50_000.0
    assert snap.stock is True
    assert "(Keycap lẻ ESC)" in snap.name

def test_lazada_transitions_to_next_lowest_when_lowest_sku_goes_out_of_stock(config):
    """Lazada transitions dynamically to the next lowest in-stock variation when previous lowest runs out of stock."""
    from unittest.mock import MagicMock
    from deal_hunter.adapters.playwright import PlaywrightAdapter

    adapter = PlaywrightAdapter(config)
    mock_page = MagicMock()
    mock_page.url = "https://www.lazada.vn/products/aula-f75-i2.html"
    mock_page.locator.return_value.all_inner_texts.return_value = []
    mock_page.locator.return_value.count.return_value = 0

    # Case 1: SKU 1 (900k) and SKU 2 (1,300k) are both in stock -> picks SKU 1
    payload1 = {
        "root": {
            "fields": {
                "productTitle": {"title": "Bàn phím cơ AULA F75"},
                "skuInfos": {
                    "s1": {"price": "900.000", "operation": {"disable": False}, "name": "Bản Tiêu Chuẩn", "quantity": 3},
                    "s2": {"price": "1.300.000", "operation": {"disable": False}, "name": "Bản Cao Cấp", "quantity": 10},
                }
            }
        }
    }
    mock_page.evaluate.side_effect = [None, False, False, [], "AULA Official"]
    snap1 = adapter._parse_lazada(mock_page, mock_page.url, lazada_payload=payload1)
    assert snap1.price == 900_000.0
    assert "(Bản Tiêu Chuẩn)" in snap1.name

    # Case 2: Later scan, SKU 1 is out of stock (disable=True) -> dynamically transitions to SKU 2 (1,300k)
    payload2 = {
        "root": {
            "fields": {
                "productTitle": {"title": "Bàn phím cơ AULA F75 (Bản Tiêu Chuẩn)"},
                "skuInfos": {
                    "s1": {"price": "900.000", "operation": {"disable": True}, "name": "Bản Tiêu Chuẩn", "quantity": 0},
                    "s2": {"price": "1.300.000", "operation": {"disable": False}, "name": "Bản Cao Cấp", "quantity": 10},
                }
            }
        }
    }
    mock_page.evaluate.side_effect = [None, False, False, [], "AULA Official"]
    snap2 = adapter._parse_lazada(mock_page, mock_page.url, lazada_payload=payload2)
    assert snap2.price == 1_300_000.0
    assert snap2.stock is True
    # Name must cleanly update to Bản Cao Cấp without stacking parentheses
    assert snap2.name == "Bàn phím cơ AULA F75 (Bản Cao Cấp)"


def test_lazada_all_variations_sold_out_wishlist_operation(config):
    """Lazada marks product as stock=False when all SKUs have wishlist operation or quantity.limit.max = 0."""
    from unittest.mock import MagicMock
    from deal_hunter.adapters.playwright import PlaywrightAdapter

    adapter = PlaywrightAdapter(config)
    mock_page = MagicMock()
    mock_page.url = "https://www.lazada.vn/products/aula-s75pro-i13467967356-s117392597274.html"
    mock_page.locator.return_value.all_inner_texts.return_value = []
    mock_page.locator.return_value.count.return_value = 0

    payload = {
        "root": {
            "fields": {
                "productTitle": {"title": "AULA | Bàn Phím Cơ AULA S75PRO"},
                "skuInfos": {
                    "sku1": {
                        "price": "596.444",
                        "operation": {"disable": False, "type": "wishlist", "text": "Thêm vào danh sách Yêu thích"},
                        "quantity": {"limit": {"max": 0, "min": 0}, "text": "Hết hàng"},
                        "name": "Interstellar Black",
                    },
                    "sku2": {
                        "price": "2.307.000",
                        "operation": {"disable": False, "type": "wishlist", "text": "Thêm vào danh sách Yêu thích"},
                        "quantity": {"limit": {"max": 0, "min": 0}, "text": "Hết hàng"},
                        "name": "Trục mũi tên sao",
                    },
                    "sku3": {
                        "price": "2.635.000",
                        "operation": {"disable": False, "type": "wishlist", "text": "Thêm vào danh sách Yêu thích"},
                        "quantity": {"limit": {"max": 0, "min": 0}, "text": "Hết hàng"},
                        "name": "Quiet White",
                    },
                    "sku4": {
                        "price": "2.231.000",
                        "operation": {"disable": False, "type": "wishlist", "text": "Thêm vào danh sách Yêu thích"},
                        "quantity": {"limit": {"max": 0, "min": 0}, "text": "Hết hàng"},
                        "name": "Bột đào",
                    },
                }
            }
        }
    }
    # DOM evaluation returns is_dom_out_of_stock = True because of wishlist button
    mock_page.evaluate.side_effect = [None, False, True, [], "AULA Official"]
    snap = adapter._parse_lazada(mock_page, mock_page.url, lazada_payload=payload)

    # Product must be marked as out of stock
    assert snap.stock is False
    # Preserves minimum variation price for history tracking
    assert snap.price == 596_444.0


def test_canonicalize_lazada_url():
    from deal_hunter.adapters.playwright import canonicalize_url, _canonicalize_lazada_url
    url1 = "https://www.lazada.vn/products/aula-wireless-bluetooth-3-mode-rgb-i13409556827-s117098513613.html"
    assert canonicalize_url(url1) == "https://www.lazada.vn/products/aula-wireless-bluetooth-3-mode-rgb-i13409556827.html"
    assert _canonicalize_lazada_url(url1) == "https://www.lazada.vn/products/aula-wireless-bluetooth-3-mode-rgb-i13409556827.html"

    url2 = "https://www.lazada.vn/products/aula-i13409556827-s117098513613.html?spm=a2o4n"
    assert canonicalize_url(url2) == "https://www.lazada.vn/products/aula-i13409556827.html?spm=a2o4n"

    url3 = "https://www.lazada.vn/products/aula-i13409556827.html"
    assert canonicalize_url(url3) == "https://www.lazada.vn/products/aula-i13409556827.html"

    shopee_url1 = "https://shopee.vn/product-i.123.456?modelid=789&spm=1"
    assert canonicalize_url(shopee_url1) == "https://shopee.vn/product-i.123.456?spm=1"

    shopee_url2 = "https://shopee.vn/product-i.123.456?modelid=789"
    assert canonicalize_url(shopee_url2) == "https://shopee.vn/product-i.123.456"

def test_lazada_lowest_in_stock_variation_priority(config):
    from unittest.mock import MagicMock
    from deal_hunter.adapters.playwright import PlaywrightAdapter
    adapter = PlaywrightAdapter(config)
    mock_page = MagicMock()
    mock_page.url = "https://www.lazada.vn/products/keyboard-i13409556827.html"

    # Multi-variation item:
    # sku1: 1,153,000₫ but SOLD OUT (wishlist)
    # sku2: 1,623,000₫ IN STOCK
    # sku3: 2,004,000₫ IN STOCK
    # sku4: 4,105,000₫ IN STOCK (max/combo)
    payload = {
        "skuInfos": {
            "117098513607": {
                "name": "F75 Tuyết Xanh",
                "price": {"salePrice": {"value": 1153000}},
                "operation": {"type": "wishlist", "disable": False, "text": "Thêm vào danh sách Yêu thích"},
                "quantity": {"limit": {"max": 0, "min": 0}, "text": "Hết hàng"},
            },
            "117098513606": {
                "name": "F75 Glacier Blue",
                "price": {"salePrice": {"value": 1623000}},
                "operation": {"type": "default", "disable": False, "text": "Thêm vào giỏ"},
                "quantity": {"limit": {"max": 5, "min": 1}},
            },
            "117098513618": {
                "name": "F75 Xanh Băng",
                "price": {"salePrice": {"value": 2004000}},
                "operation": {"type": "default", "disable": False, "text": "Thêm vào giỏ"},
                "quantity": {"limit": {"max": 5, "min": 1}},
            },
            "117098513613": {
                "name": "F75 Đường Viền Trắng",
                "price": {"salePrice": {"value": 4105000}},
                "operation": {"type": "default", "disable": False, "text": "Thêm vào giỏ"},
                "quantity": {"limit": {"max": 5, "min": 1}},
            },
        }
    }
    mock_page.evaluate.side_effect = [
        {"root": {"fields": {"productTitle": {"title": "Bàn Phím Cơ AULA F75"}}}},  # mod_data
        False,  # is_dom_out_of_stock
        [],     # voucher tags
        "AULA Shop"
    ]
    snap = adapter._parse_lazada(mock_page, mock_page.url, lazada_payload=payload)

    assert snap.stock is True
    # Must pick the lowest IN-STOCK variation (1,623,000₫, not 1,153,000₫ which is sold out, nor 4,105,000₫)
    assert snap.price == 1623000.0
    assert "F75 Glacier Blue" in snap.name


def test_lazada_punish_iframe_raises_blocked(config):
    from unittest.mock import MagicMock
    from deal_hunter.adapters.base import Blocked
    from deal_hunter.adapters.playwright import PlaywrightAdapter
    adapter = PlaywrightAdapter(config)
    mock_page = MagicMock()
    mock_page.url = "https://www.lazada.vn/products/keyboard-i13409556827.html"

    # Captcha punish iframe present and no valid sku prices
    with pytest.raises(Blocked, match="challenged by captcha punish"):
        adapter._parse_lazada(mock_page, mock_page.url, lazada_payload={}, is_punished=True)


def test_is_tracked_skips_rating_in_adapters(config):
    from unittest.mock import MagicMock
    from deal_hunter.adapters.mock import MockAdapter
    from deal_hunter.adapters.playwright import PlaywrightAdapter

    # Mock adapter
    mock_adapter = MockAdapter(price_sequence=[100_000])
    snap_tracked = mock_adapter.fetch("https://shopee.vn/p-i.1.2", is_tracked=True)
    assert snap_tracked.rating is None

    snap_normal = mock_adapter.fetch("https://shopee.vn/p-i.1.2", is_tracked=False)
    assert snap_normal.rating == 4.8

    # Playwright Shopee parsing with is_tracked=True
    pw_adapter = PlaywrightAdapter(config)
    mock_page = MagicMock()
    mock_page.url = "https://shopee.vn/product-i.123.456"
    pdp_payload = {
        "data": {
            "item": {
                "title": "Shopee Tracked Item",
                "price": 5000000000,
                "stock": 10,
                "item_rating": {"rating_star": 4.9},
            }
        }
    }
    s_tracked = pw_adapter._parse_shopee(mock_page, mock_page.url, pdp_payload=pdp_payload, is_tracked=True)
    assert s_tracked.rating is None
    assert s_tracked.stock is True

    s_full = pw_adapter._parse_shopee(mock_page, mock_page.url, pdp_payload=pdp_payload, is_tracked=False)
    assert s_full.rating == 4.9


def test_ensure_nopecha_extension_exists(tmp_path):
    from deal_hunter.adapters.playwright import _ensure_nopecha_extension
    ext_dir = tmp_path / "nopecha"
    ext_dir.mkdir(parents=True)
    (ext_dir / "manifest.json").write_text("{}", encoding="utf-8")
    assert _ensure_nopecha_extension(ext_dir) is True


def test_playwright_wait_for_captcha_solve():
    from unittest.mock import MagicMock
    from deal_hunter.adapters.playwright import PlaywrightAdapter
    cfg = MagicMock()
    adapter = PlaywrightAdapter(cfg)
    adapter._quota = MagicMock()

    mock_page = MagicMock()
    mock_page.url = "https://www.lazada.vn/products/item.html"
    mock_page.evaluate.return_value = False

    # Solved
    res = adapter._wait_for_captcha_solve(mock_page, timeout_sec=2)
    assert res is True
    adapter._quota.record_solve.assert_called_once_with(1)

    # Not solved (stuck on /verify/slider)
    mock_page.url = "https://www.lazada.vn/verify/slider"
    adapter._quota.reset_mock()
    res_fail = adapter._wait_for_captcha_solve(mock_page, timeout_sec=2)
    assert res_fail is False
    adapter._quota.record_solve.assert_not_called()


def test_try_drag_slider_handles_no_slider():
    from unittest.mock import MagicMock
    from deal_hunter.adapters.playwright import PlaywrightAdapter
    cfg = MagicMock()
    adapter = PlaywrightAdapter(cfg)
    mock_page = MagicMock()
    mock_page.locator.return_value.count.return_value = 0
    mock_page.frames = []
    assert adapter._try_drag_slider(mock_page) is False


def test_try_drag_slider_success():
    from unittest.mock import MagicMock
    from deal_hunter.adapters.playwright import PlaywrightAdapter
    cfg = MagicMock()
    adapter = PlaywrightAdapter(cfg)
    mock_page = MagicMock()
    slider_loc = MagicMock()
    slider_loc.count.return_value = 1
    slider_loc.first.is_visible.return_value = True
    slider_loc.first.bounding_box.return_value = {"x": 100, "y": 200, "width": 40, "height": 40}
    mock_page.locator.return_value = slider_loc
    mock_page.evaluate.return_value = True

    assert adapter._try_drag_slider(mock_page) is True
    mock_page.mouse.down.assert_called_once()
    mock_page.mouse.up.assert_called_once()


def test_reload_cookies_safe_when_context_not_started(tmp_path):
    from unittest.mock import MagicMock
    from deal_hunter.adapters.playwright import PlaywrightAdapter
    cfg = MagicMock()
    cfg.db_path = str(tmp_path / "deals.db")
    cookie_file = tmp_path / "cookies.json"
    cookie_file.write_text('[{"name": "SPC_EC", "value": "test"}]', encoding="utf-8")

    adapter = PlaywrightAdapter(cfg)
    assert adapter._ctx is None
    # Must run safely without AttributeError: 'NoneType' object has no attribute 'add_cookies'
    adapter.reload_cookies(tmp_path)
    adapter._load_saved_cookies(tmp_path)


def test_parse_lazada_single_option_prefers_dom_over_jsonld():
    """Single-option product prefers visible promotional DOM price over stale JSON-LD/catalog price."""
    from unittest.mock import MagicMock
    from deal_hunter.adapters.playwright import PlaywrightAdapter

    cfg = MagicMock()
    adapter = PlaywrightAdapter(cfg)
    mock_page = MagicMock()
    mock_page.url = "https://www.lazada.vn/products/sony-zv-e10-i13456649407.html"
    # JSON-LD has stale price 27.000.000
    mock_page.locator.return_value.all_inner_texts.return_value = [
        '{"@type": "Product", "name": "Sony ZV-E10", "offers": {"price": "27000000", "availability": "https://schema.org/InStock"}}'
    ]

    # Mock DOM price locator to return promotional price 25.500.000
    mock_loc = MagicMock()
    mock_loc.count.return_value = 1
    mock_loc.first.inner_text.return_value = "25.500.000 ₫"

    def locator_side_effect(selector):
        if "salePrice" in selector or "subsidy" in selector:
            return mock_loc
        m = MagicMock()
        m.count.return_value = 0
        m.all_inner_texts.return_value = []
        return m

    mock_page.locator.side_effect = locator_side_effect
    mock_page.evaluate.side_effect = [None, False, False, [], "Sony Official Store"]

    # 1 single SKU in MTOP with 27.000.000
    payload = {
        "root": {
            "fields": {
                "productTitle": {"title": "Sony ZV-E10"},
                "skuInfos": {
                    "s1": {"price": "27.000.000", "operation": {"disable": False}, "name": "Standard", "quantity": 5}
                }
            }
        }
    }

    snap = adapter._parse_lazada(mock_page, mock_page.url, lazada_payload=payload)
    assert snap.price == 25_500_000.0
    assert snap.list_price == 27_000_000.0
    assert snap.stock is True


def test_parse_lazada_multi_option_preserves_lowest_sku():
    """Multi-option product strictly preserves lowest in-stock SKU and is not overridden by DOM."""
    from unittest.mock import MagicMock
    from deal_hunter.adapters.playwright import PlaywrightAdapter

    cfg = MagicMock()
    adapter = PlaywrightAdapter(cfg)
    mock_page = MagicMock()
    mock_page.url = "https://www.lazada.vn/products/keychron-k2-i9999.html"

    # DOM locator shows a higher/different price
    mock_loc = MagicMock()
    mock_loc.count.return_value = 1
    mock_loc.first.inner_text.return_value = "1.800.000 ₫"

    def locator_side_effect(selector):
        if "salePrice" in selector:
            return mock_loc
        m = MagicMock()
        m.count.return_value = 0
        m.all_inner_texts.return_value = []
        return m

    mock_page.locator.side_effect = locator_side_effect
    mock_page.evaluate.side_effect = [None, False, False, [], "Keychron Official"]

    # 2 SKUs: s1 (1.200.000) and s2 (1.800.000)
    payload = {
        "root": {
            "fields": {
                "productTitle": {"title": "Keychron K2"},
                "skuInfos": {
                    "s1": {"price": "1.200.000", "operation": {"disable": False}, "name": "Bản Nhôm", "quantity": 10},
                    "s2": {"price": "1.800.000", "operation": {"disable": False}, "name": "Bản Led RGB", "quantity": 5},
                }
            }
        }
    }

    snap = adapter._parse_lazada(mock_page, mock_page.url, lazada_payload=payload)
    # Must strictly pick the lowest in-stock SKU (1.200.000), NOT the DOM price (1.800.000)
    assert snap.price == 1_200_000.0
    assert "(Bản Nhôm)" in snap.name


def test_parse_shopee_single_option_prefers_dom_when_lower():
    """Shopee single-option product prefers DOM price when lower than catalog raw price."""
    from unittest.mock import MagicMock
    from deal_hunter.adapters.playwright import PlaywrightAdapter

    cfg = MagicMock()
    adapter = PlaywrightAdapter(cfg)
    mock_page = MagicMock()
    mock_page.url = "https://shopee.vn/product-i.12345.67890"

    mock_loc = MagicMock()
    mock_loc.count.return_value = 1
    mock_loc.first.inner_text.return_value = "₫270.000"

    def locator_side_effect(selector):
        if "priceSectionPrice" in selector or "pqTWkA" in selector:
            return mock_loc
        m = MagicMock()
        m.count.return_value = 0
        m.all_inner_texts.return_value = []
        return m

    mock_page.locator.side_effect = locator_side_effect
    mock_page.evaluate.side_effect = [None, False, False, [], "Shop Test"]

    pdp_payload = {
        "data": {
            "item": {
                "name": "Chuột Không Dây M331",
                "stock": 50,
                "price": 30000000000,  # 300.000
                "models": []  # Single-option (no models list)
            }
        }
    }

    snap = adapter._parse_shopee(mock_page, mock_page.url, pdp_payload=pdp_payload)
    assert snap.price == 270_000.0


def test_parse_lazada_single_option_with_duplicate_sku_keys_and_coupon():
    """Lazada product with duplicate sku keys ('0' and '117120756839') with coupon price is parsed correctly."""
    from unittest.mock import MagicMock
    from deal_hunter.adapters.playwright import PlaywrightAdapter

    cfg = MagicMock()
    adapter = PlaywrightAdapter(cfg)
    mock_page = MagicMock()
    mock_page.url = "https://www.lazada.vn/products/pdp-i13410801053.html"

    # Mock DOM price locator to return promotional price 5.156.330
    mock_loc = MagicMock()
    mock_loc.count.return_value = 1
    mock_loc.first.inner_text.return_value = "5.156.330 ₫"

    def locator_side_effect(selector):
        if "salePrice" in selector:
            return mock_loc
        m = MagicMock()
        m.count.return_value = 0
        m.all_inner_texts.return_value = []
        return m

    mock_page.locator.side_effect = locator_side_effect
    mock_page.evaluate.side_effect = [None, False, False, [], "Gmarket korea Official"]

    # Payload with duplicate SKU keys '0' and '117120756839' but same skuId, with coupon
    payload = {
        "root": {
            "fields": {
                "productTitle": {"title": "AMD Ryzen 5 thế hệ 5 7500F"},
                "skuInfos": {
                    "0": {
                        "skuId": "117120756839",
                        "operation": {"disable": False},
                        "price": {
                            "coupon": {"priceNumber": 5156330, "priceText": "5.156.330 ₫"},
                            "originalPrice": {"value": 8484000, "text": "8.484.000 ₫"},
                            "salePrice": {"value": 6527000, "text": "6.527.000 ₫"}
                        }
                    },
                    "117120756839": {
                        "skuId": "117120756839",
                        "operation": {"disable": False},
                        "price": {
                            "coupon": {"priceNumber": 5156330, "priceText": "5.156.330 ₫"},
                            "originalPrice": {"value": 8484000, "text": "8.484.000 ₫"},
                            "salePrice": {"value": 6527000, "text": "6.527.000 ₫"}
                        }
                    }
                }
            }
        }
    }

    snap = adapter._parse_lazada(mock_page, mock_page.url, lazada_payload=payload)
    assert snap.price == 5_156_330.0
    assert snap.list_price == 8_484_000.0
    assert snap.stock is True
    # Must only extract 1 deduplicated variant, not 2!
    assert len(snap.variants) == 1
    assert snap.variants[0].variant_key == "117120756839"




def test_base_adapter_fast_fetch_default_none():
    from deal_hunter.adapters.base import BaseAdapter, Snapshot
    class DummyAdapter(BaseAdapter):
        def fetch(self, url: str, target_sku: str | None = None, is_tracked: bool = False) -> Snapshot:
            pass
    adapter = DummyAdapter()
    assert adapter.fast_fetch("https://shopee.vn/test") is None


def test_playwright_adapter_fast_fetch_shopee_mock(monkeypatch, tmp_path):
    from deal_hunter.adapters.playwright import PlaywrightAdapter
    from deal_hunter.config import Config
    import httpx
    
    cfg = Config(fetch_mode="playwright", db_path=str(tmp_path / "deals.db"))
    adapter = PlaywrightAdapter(cfg)
    
    fake_pdp = {
        "data": {
            "item": {
                "title": "Bàn phím cơ Akko",
                "price": 50000000000,
                "models": [
                    {"modelid": 111, "name": "Blue Switch", "price": 45000000000, "stock": 10}
                ]
            }
        }
    }
    
    class FakeResponse:
        status_code = 200
        def json(self):
            return fake_pdp

    monkeypatch.setattr(httpx, "get", lambda *args, **kwargs: FakeResponse())
    snap = adapter.fast_fetch("https://shopee.vn/product/123/456")
    assert snap is not None
    assert snap.name == "Bàn phím cơ Akko (Blue Switch)"
    assert snap.price == 450000.0


def test_playwright_cdp_connection_success(tmp_path, monkeypatch):
    """When cdp_url is configured and connect_over_cdp succeeds, use external Chrome context."""
    from deal_hunter.adapters.playwright import PlaywrightAdapter
    from deal_hunter.config import Config
    from unittest.mock import MagicMock

    cfg = Config(fetch_mode="playwright", db_path=str(tmp_path / "deals.db"), cdp_url="http://127.0.0.1:9222")
    adapter = PlaywrightAdapter(cfg)

    mock_pw = MagicMock()
    mock_browser = MagicMock()
    mock_context = MagicMock()
    mock_browser.contexts = [mock_context]
    mock_pw.chromium.connect_over_cdp.return_value = mock_browser

    monkeypatch.setattr("playwright.sync_api.sync_playwright", lambda: MagicMock(start=lambda: mock_pw))

    adapter._ensure_started()
    assert adapter._using_cdp is True
    assert adapter._ctx == mock_context

    adapter.close()
    mock_pw.stop.assert_called_once()
    mock_browser.close.assert_not_called()


def test_playwright_cdp_connection_fallback(tmp_path, monkeypatch):
    """When cdp_url fails, automatically fallback to internal persistent context."""
    from deal_hunter.adapters.playwright import PlaywrightAdapter
    from deal_hunter.config import Config
    from unittest.mock import MagicMock

    cfg = Config(fetch_mode="playwright", db_path=str(tmp_path / "deals.db"), cdp_url="http://127.0.0.1:9222")
    adapter = PlaywrightAdapter(cfg)

    mock_pw = MagicMock()
    mock_pw.chromium.connect_over_cdp.side_effect = Exception("Connection refused")
    mock_fallback_ctx = MagicMock()
    mock_pw.chromium.launch_persistent_context.return_value = mock_fallback_ctx

    monkeypatch.setattr("playwright.sync_api.sync_playwright", lambda: MagicMock(start=lambda: mock_pw))

    adapter._ensure_started()
    assert adapter._using_cdp is False
    assert adapter._ctx == mock_fallback_ctx

    adapter.close()
    mock_fallback_ctx.close.assert_called_once()

