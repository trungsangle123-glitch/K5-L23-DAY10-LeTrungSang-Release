# Dùng AI

| # | Ai dùng | Công cụ | Prompt (tóm tắt) | AI sai ở đâu | Nhóm kiểm lại thế nào |
|---|---|---|---|---|---|
| 1 | Trân (Validator Luật) | ChatGPT/Codex | Viết validator Pha 1 theo 9 luật; chỉ đọc delivery, Python stdlib + scripts/pngutil.py, xuất errors.json theo schema. | Cần đặc biệt xác minh quy tắc box tràn mép, duplicate box 1–2 pixel và thing_overlap có được áp dụng cho đúng segment; AI không thể khẳng định độ chính xác chỉ bằng việc viết code. | Đối chiếu GUIDE.md, DELIVERY.md, RULES.md và mã sinh lô; sau khi có dữ liệu chạy trên ít nhất 2 seed và lô sạch, kiểm tra F1 bằng score_findings.py. |
