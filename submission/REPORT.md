# Báo cáo nhóm <<XX>>

## 1. Số liệu luyện tập
- F1 theo seed (rule / cross_check / overall): **seed 34: 1.0 / 0.4 / 0.7** (theo `score_findings.py`, sau khi xem lại 3 dòng được giao cho Tiến).
- Số ứng viên trên lô sạch (`--no-faults`): **8 hàng/50 ảnh**, đều là `instance_merge`; seed 34 có **57 hàng trên 55 ảnh** trước review (46 `instance_merge`, 6 `missing_box`, 4 bất đồng lớp, 1 `bbox_drift`). Hai ảnh thiếu file và một dòng YOLO lỗi được bỏ khỏi cross-check để xử lý bằng luật/review riêng.
- Ngưỡng đã chọn và cách chọn (không dùng `_private`): ghép cặp ban đầu khi IoU ≥ 0,05 hoặc mask coverage ≥ 0,10; bất đồng lớp cần IoU ≥ 0,10 hoặc coverage ≥ 0,20; `bbox_drift` cần segment ≥ 100 pixel và coverage < 0,80; `missing_box` cần mask ≥ 600 pixel và cạnh ngắn ≥ 15 pixel. Với `instance_merge`, yêu cầu hai box cùng lớp, mỗi box chứa ít nhất 30% pixel segment và ít nhất 50 pixel, đồng thời IoU giữa hai box ≤ 0,10. Điều kiện box tách biệt giảm nhiễu lô sạch từ 28 xuống 8 hàng/50 ảnh; hàng đợi seed 34 còn 55 ảnh để nhóm review thủ công.

## 2. Vì sao báo hết ứng viên làm F1 giảm?
Báo mọi ứng viên sẽ làm tăng false positive và giảm precision, kéo F1 xuống. Trên lô `--no-faults`, bộ ghép vẫn sinh 8 ứng viên `instance_merge` trên 50 ảnh; đó là khác biệt tự nhiên cần người xem ảnh loại bỏ. Seed 34 có 57 hàng ứng viên trên 55 ảnh trước review, nên chỉ đưa lỗi vào `errors.json` sau khi có dòng `confirmed`.

### Kết quả review bằng mắt (seed 34)
- 5 người xem 55 ảnh / 57 hàng ứng viên, mỗi người khoảng 11 ảnh. Các CSV cá nhân được gộp bằng `validator/normalize_review.py` thành `review_log.csv`: script thêm tên người xem vào đầu note (`[Trinh] ...`) và **dừng, không ghi file** nếu verdict khác `confirmed`/`rejected`, thiếu hoặc trùng ứng viên, note dưới 20 ký tự hoặc note bị chép giống nhau. Script được viết sau khi kiểm tay phát hiện 11 dòng ghi `confirm`/`reject` (thay vì `confirmed`/`rejected`); `merge_review.py` chỉ nhận đúng chữ `confirmed` nên sẽ âm thầm bỏ 5 lỗi đã xác nhận. Đã thử cố ý đưa vào verdict sai chữ, dòng thiếu, note "ok" và `class_disagreement` confirmed: script đều dừng và chỉ đúng dòng.
- Kết quả: **17 confirmed / 40 rejected**. `instance_merge` bị bác nhiều nhất: 38/46 hàng rejected, chỉ 8 confirmed. Các loại khác: `missing_box` 5 confirmed / 1 rejected, bất đồng lớp 4/4 confirmed (3 `class_swap`, 1 `category_swap`), `bbox_drift` 1 rejected.
- Lý do rejected thường gặp (lệch tự nhiên của COCO, không phải lỗi):
  - **Vật nhỏ phía sau lọt trong box to của vật phía trước**: một segment chạm hai box cùng lớp nên bị báo `instance_merge`, nhưng segment chỉ phủ một vật (ví dụ `000000002153`, `000000005001`, `000000013348`, `000000025057`).
  - **Vật cùng lớp đứng sát hoặc che nhau** (đám đông, sách trên kệ, xe đậu sát): box chồng lên nhau nhưng mỗi vật vẫn có segment riêng.
  - **Segment quá nhỏ**: vài chục đến vài trăm pixel (ví dụ remote 56 pixel ở `000000013729`), không thể phủ hai vật.
  - **Nhiều segment sát nhau trông như một mảng**: công cụ xem ảnh ban đầu tô mọi segment ứng viên cùng một màu.
- Review chéo: người tổng hợp đọc lại note và gắn cờ các dòng confirmed có note tả *box detection gom nhiều vật* thay vì *một segment panoptic phủ hai vật* (định nghĩa của `instance_merge`). Người xem tự mở lại ảnh và tự sửa; số confirmed giảm từ **22 xuống 17** (`000000004134`, `000000006763`, `000000024610`, `000000013729`, `000000015335` đổi sang rejected).
- Bài học từ `000000015335` (ban đầu confirmed, sau đổi rejected): góc trên phải trông như một mảng tím liền phủ 3 người, nhưng thực ra là 6 segment riêng, mỗi segment khớp đúng một box của một người. Hai điều rút ra: (1) **công cụ xem ảnh ảnh hưởng trực tiếp tới kết luận**, nên `view_candidates.py` đã được sửa để mỗi segment một màu, có viền trắng, số hiệu `S1, S2…` và số pixel; (2) **đối chiếu số liệu trước khi confirmed**: nếu khung của segment khớp đúng một box riêng (xem `candidates.json`) thì segment đó chỉ là một vật, không phải bị gộp.

## 3. Quyết định và lineage
QC v1 có **29 mục lỗi / 250 ảnh (11,6%)**, trên **28 ảnh có phát hiện**; ảnh `000000016958` có hai phát hiện (`invalid_class` và `missing_box`). Tỉ lệ lỗi vượt ngưỡng 2%, nên quyết định **HOLD**. Lineage ghi `R-021: affected=True action=review_or_retrain`; sửa dữ liệu không tự cập nhật model đã train, nên run này phải được xem lại hoặc train lại trước khi phát hành.

## 4. Hash chứng minh gì, không chứng minh gì?
- **Hash (SHA-256 trong `manifest.csv` và `.sha256`) chứng minh:** tính toàn vẹn ở mức bit (file ảnh, nhãn và gói `.zip` bàn giao v2 không bị sửa đổi, cắt xén, hỏng hoặc tráo đổi kể từ thời điểm đóng gói). Khi có lỗi `wrong_hash` ở v1, nhóm mở kiểm tra file ảnh trước: ảnh mở được bình thường nên chỉ hỏng/lệch manifest và được tính lại hash mới trong v2; ảnh/nhãn v2 giữ nguyên không sửa tay.
- **Hash KHÔNG chứng minh:** nội dung gán nhãn là đúng về mặt ngữ nghĩa. Một file `.txt` gán nhầm lớp (`class_swap`), lệch khung (`bbox_drift`) hay thiếu box (`missing_box`) vẫn cho ra mã SHA-256 hợp lệ; chất lượng nhãn vẫn phải kiểm tra bằng đối chiếu nguồn và review bằng mắt.

## 5. Truy vết
- **Tiêu chí phân tầng (`validator/trace_ticket.py`):**
  - Đọc `incoming/ticket.md` và `guideline/changelog.md` để xác định các `scene_id` team AI nêu (`scene_449`, `scene_699`), phiên bản guideline mới nhất (`v1.3`) và lớp bị đổi quy tắc (`surfboard`).
  - **`tier_a`:** ảnh thuộc các `scene_id` team AI đã báo, nằm trong job dùng guideline cũ (`v1.2`), và có ít nhất một box detection lớp `surfboard` trong `labels/` của lô.
  - **`tier_b`:** các ảnh khác cũng thuộc job guideline cũ (`v1.2`) và có box `surfboard` nhưng chưa được team AI báo trong ticket.
  - **`notify`:** tập mã `annotator` và `reviewer` của các job chứa ảnh thuộc `tier_a` và `tier_b` (tra từ `jobs.csv`).
- **Vì sao lấy guideline theo job (`jobs.csv`) chứ không theo metadata ảnh (`metadata.json`):** vì `guideline_version` ghi ở từng ảnh trong `metadata.json` có thể đang bị lỗi `guideline_mismatch` (không phản ánh đúng quy tắc áp dụng cho job đó). Lấy theo `jobs.csv` bảo đảm truy vết đúng các ảnh thực sự được gán theo guideline cũ.
- **Kết quả trên seed 34:** `tier_a = 2`, `tier_b = 4`, `notify = 4`; tự kiểm bằng `score_findings.py` đạt `tier_a 1.0 · tier_b 1.0 · notify 1.0`.

## 6. Bug hoặc điểm chưa rõ trong lab (nếu có)
<<>>
