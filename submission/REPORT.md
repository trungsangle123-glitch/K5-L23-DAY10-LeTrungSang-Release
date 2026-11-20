# Báo cáo nhóm <<XX>>

## 1. Số liệu luyện tập
- F1 theo seed (rule / cross_check / overall): **seed 34: 1.0 / 0.4 / 0.7** (theo `score_findings.py`, sau khi xem lại 3 dòng được giao cho Tiến).
- Số ứng viên trên lô sạch (`--no-faults`): **8 hàng/50 ảnh**, đều là `instance_merge`; seed 34 có **57 hàng trên 55 ảnh** trước review (46 `instance_merge`, 6 `missing_box`, 4 bất đồng lớp, 1 `bbox_drift`). Hai ảnh thiếu file và một dòng YOLO lỗi được bỏ khỏi cross-check để xử lý bằng luật/review riêng.
- Ngưỡng đã chọn và cách chọn (không dùng `_private`): ghép cặp ban đầu khi IoU ≥ 0,05 hoặc mask coverage ≥ 0,10; bất đồng lớp cần IoU ≥ 0,10 hoặc coverage ≥ 0,20; `bbox_drift` cần segment ≥ 100 pixel và coverage < 0,80; `missing_box` cần mask ≥ 600 pixel và cạnh ngắn ≥ 15 pixel. Với `instance_merge`, yêu cầu hai box cùng lớp, mỗi box chứa ít nhất 30% pixel segment và ít nhất 50 pixel, đồng thời IoU giữa hai box ≤ 0,10. Điều kiện box tách biệt giảm nhiễu lô sạch từ 28 xuống 8 hàng/50 ảnh; hàng đợi seed 34 còn 55 ảnh để nhóm review thủ công.

## 2. Vì sao báo hết ứng viên làm F1 giảm?
Báo mọi ứng viên sẽ làm tăng false positive và giảm precision, kéo F1 xuống. Trên lô `--no-faults`, bộ ghép vẫn sinh 8 ứng viên `instance_merge` trên 50 ảnh; đó là khác biệt tự nhiên cần người xem ảnh loại bỏ. Seed 34 có 57 hàng ứng viên trên 55 ảnh trước review, nên chỉ đưa lỗi vào `errors.json` sau khi có dòng `confirmed`.

## 3. Quyết định và lineage
QC v1 có **29 mục lỗi / 250 ảnh (11,6%)**, trên **28 ảnh có phát hiện**; ảnh `000000016958` có hai phát hiện (`invalid_class` và `missing_box`). Tỉ lệ lỗi vượt ngưỡng 2%, nên quyết định **HOLD**. Lineage ghi `R-021: affected=True action=review_or_retrain`; sửa dữ liệu không tự cập nhật model đã train, nên run này phải được xem lại hoặc train lại trước khi phát hành.

## 4. Hash chứng minh gì, không chứng minh gì?
<<>>

## 5. Truy vết
<<Tiêu chí tầng a/b, vì sao lấy guideline theo job.>>

## 6. Bug hoặc điểm chưa rõ trong lab (nếu có)
<<>>
