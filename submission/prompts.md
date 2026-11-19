# Dùng AI

| # | Ai dùng | Công cụ | Prompt (tóm tắt) | AI sai ở đâu | Nhóm kiểm lại thế nào |
|---|---|---|---|---|---|
| 1 | Trân (Validator Luật) | ChatGPT/Codex | Viết validator Pha 1 theo 9 luật; chỉ đọc delivery, Python stdlib + scripts/pngutil.py, xuất errors.json theo schema. | Cần đặc biệt xác minh quy tắc box tràn mép, duplicate box 1–2 pixel và thing_overlap có được áp dụng cho đúng segment; AI không thể khẳng định độ chính xác chỉ bằng việc viết code. | Đối chiếu GUIDE.md, DELIVERY.md, RULES.md và mã sinh lô; sau khi có dữ liệu chạy trên ít nhất 2 seed và lô sạch, kiểm tra F1 bằng score_findings.py. |
| 2 | Nguyễn Anh Tiến (Pha 2) | ChatGPT/Codex | Thêm ghép detection ↔ panoptic theo tên lớp và pixel mask, sinh candidates.json/CSV, đo nhiễu trên lô sạch, tạo overlay để người review ảnh. | Ngưỡng `instance_merge` ban đầu báo 28 ứng viên/50 ảnh sạch do box cùng lớp chồng lấn tự nhiên; AI không thể xác định `class_swap` hay `category_swap` hoặc tự xác nhận lỗi chỉ từ nhãn. | Siết điều kiện hai box phải tách biệt; lô sạch còn 8 hàng/50 ảnh, seed 34 có 57 hàng/55 ảnh. Nhóm vẫn phải xem overlay và ghi confirmed/rejected vào review_log.csv trước khi gộp lỗi. |
