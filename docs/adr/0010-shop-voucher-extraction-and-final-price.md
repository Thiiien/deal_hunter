# 10. Tự động trích xuất mã giảm giá (Vouchers) và tính toán giá cuối cùng sau áp mã

Ngày: 2026-10-20

## Bối cảnh
Người dùng khi mua sắm trên các sàn thương mại điện tử (Shopee) thường xuyên được hưởng thêm các mã giảm giá (Voucher của Shop, mã giảm theo phần trăm, mã giảm số tiền cố định có điều kiện đơn hàng tối thiểu `min_spend`). Mức giá hiển thị trên sàn chưa phải là mức giá thực tế thấp nhất mà người mua phải trả nếu chưa áp các voucher hợp lệ.

Để hỗ trợ người dùng săn được deal tốt nhất tuyệt đối, hệ thống cần:
1. Thu thập tự động các mã giảm giá khả dụng của sản phẩm và shop mà không làm tăng thời gian cào dữ liệu hay tăng số lượt request (gây nguy cơ bị chặn).
2. Lọc các mã hợp lệ mà sản phẩm đủ điều kiện áp dụng (`price >= min_spend`).
3. Chọn ra mã mang lại mức chiết khấu cao nhất (tính cả giới hạn trần `discount_cap` nếu có).
4. Tính toán và lưu trữ mức giá cuối cùng sau áp mã (`final_price`), hiển thị mã voucher trực quan trên Dashboard và thông báo Telegram để người dùng chỉ cần 1 click là copy được mã.

## Quyết định kiến trúc

1. **Tận dụng dữ liệu có sẵn trong API `/pdp/get_pc`:**
   - Trong phản hồi `/pdp/get_pc` mà `PlaywrightAdapter` bắt được từ Shopee, trường `data.shop_vouchers` và `data.price_breakdown` đã chứa đầy đủ danh sách mã giảm giá của Shop (`voucher_code`), điều kiện đơn tối thiểu (`min_spend`), tỷ lệ giảm (`discount_percentage`), mức trần giảm (`discount_cap`) hoặc giá trị giảm cố định (`discount_value`).
   - Tối ưu zero-cost: Hệ thống trích xuất trực tiếp từ payload đã chặn được, không tốn thêm bất kỳ request mạng nào đến sàn.

2. **Thuật toán chọn mã giảm giá tốt nhất (`_find_best_voucher`):**
   - Với mức giá sản phẩm hiện tại, duyệt qua danh sách `shop_vouchers`:
     - Kiểm tra điều kiện `price >= min_spend`.
     - Tính toán mức giảm thực tế:
       - Nếu giảm theo `%`: `disc = min(price * (pct / 100), discount_cap)` nếu có cap.
       - Nếu giảm theo số tiền cố định: `disc = discount_value`.
     - Chọn ra mã voucher đem lại mức giảm tiền lớn nhất (`best_discount`).
     - Xác định `final_price = max(0, price - best_discount)`.

3. **Lưu trữ và đồng bộ dữ liệu:**
   - Bổ sung trường `voucher_code`, `voucher_discount`, `final_price` vào `Snapshot` và bảng `price_history`.
   - Bổ sung migration tự động trong `db._migrate()`.
   - Bổ sung vào kết quả truy vấn `get_products_with_latest_price()` cho Dashboard.

4. **Trải nghiệm người dùng:**
   - **Bảng điều khiển:** Cột giá hiển thị kèm huy hiệu mã voucher màu tím `🎫 [MÃ_CODE] (-X.XXX₫)` và dòng `Sau mã: Y.YYY₫`. Người dùng click vào huy hiệu sẽ tự động sao chép mã voucher vào clipboard.
   - **Telegram Bot & Alerter:** Khi thông báo deal đạt ngưỡng hoặc kết quả `/timkiem`, bot đính kèm chi tiết mã giảm giá và giá sau khi áp mã.
   - **Kích hoạt giá mong muốn:** Khi so sánh với giá mong muốn (`target_price`), hệ thống sử dụng giá sau áp mã (`effective_price`) giúp người dùng không bỏ lỡ cơ hội mua hàng đúng ngân sách.

## Trạng thái
Đã chấp thuận và triển khai hoàn tất trong toàn bộ hệ thống (81/81 tests passing).
