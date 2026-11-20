# Báo cáo nhóm LeTrungSang

## 1. Số liệu luyện tập
- F1 theo seed (rule / cross_check / overall): **seed 34: 1.0 / 0.6 / 0.8** sau khi Tiến review bổ sung. Ban đầu là **1.0 / 0.4 / 0.7**. Đây là kết quả tự chấm làm tròn của `score_findings.py`.
- Số ứng viên ban đầu trên lô sạch (`--no-faults`): **8 hàng/50 ảnh**, đều là `instance_merge`; seed 34 có **57 hàng trên 55 ảnh** trước review. Sau các lượt bổ sung, queue đã lưu có 92 hàng trên 88 ảnh. Hai ảnh thiếu file và một dòng YOLO lỗi được bỏ khỏi cross-check để xử lý bằng luật/review riêng.
- Ngưỡng đã chọn và cách chọn (không dùng `_private`): ghép cặp ban đầu khi IoU ≥ 0,05 hoặc mask coverage ≥ 0,10; bất đồng lớp cần IoU ≥ 0,10 hoặc coverage ≥ 0,20; `bbox_drift` cần segment ≥ 100 pixel và coverage < 0,98; `missing_box` cần mask ≥ 600 pixel và cạnh ngắn ≥ 15 pixel. Với `instance_merge`, yêu cầu hai box cùng lớp, mỗi box chứa ít nhất 30% pixel segment và ít nhất 50 pixel, đồng thời IoU giữa hai box ≤ 0,10. Điều kiện box tách biệt giảm nhiễu lô sạch từ 28 xuống 8 hàng/50 ảnh; hàng đợi seed 34 còn 55 ảnh để nhóm review thủ công.

## 2. Vì sao báo hết ứng viên làm F1 giảm?
Báo mọi ứng viên sẽ làm tăng false positive và giảm precision, kéo F1 xuống. Trên lô `--no-faults`, bộ ghép vẫn sinh 8 ứng viên `instance_merge` trên 50 ảnh; đó là khác biệt tự nhiên cần người xem ảnh loại bỏ. Seed 34 có 57 hàng ứng viên trên 55 ảnh trước review, nên chỉ đưa lỗi vào `errors.json` sau khi có dòng `confirmed`.

### Kết quả review bằng mắt (seed 34)
- 5 người xem ban đầu 55 ảnh / 57 hàng ứng viên, mỗi người khoảng 11 ảnh; Tiến review bổ sung 35 hàng, thành 92 hàng trên 88 ảnh. Các CSV cá nhân được gộp bằng `validator/normalize_review.py` thành `review_log.csv`: Script thêm tên người xem vào đầu note (`[Trinh] ...`) và **dừng, không ghi file** nếu verdict khác `confirmed`/`rejected`, thiếu hoặc trùng ứng viên, note dưới 20 ký tự hoặc note bị chép giống nhau. Script được viết sau khi kiểm tay phát hiện 11 dòng ghi `confirm`/`reject` (thay vì `confirmed`/`rejected`); `merge_review.py` chỉ nhận đúng chữ `confirmed` nên sẽ âm thầm bỏ 5 lỗi đã xác nhận. Đã thử cố ý đưa vào verdict sai chữ, dòng thiếu, note "ok" và `class_disagreement` confirmed: script đều dừng và chỉ đúng dòng.
- Kết quả review: **22 confirmed / 70 rejected**. `instance_merge` có 10 confirmed / 67 rejected trên 77 hàng. Các loại khác: `missing_box` 5 confirmed / 1 rejected, bất đồng lớp 4/4 confirmed (3 `class_swap`, 1 `category_swap`), `bbox_drift` 3 confirmed / 2 rejected. Một xác nhận `instance_merge` cho `000000015254` chưa vào `errors.json` vì ảnh đã có `guideline_mismatch` và GUIDE giới hạn một lỗi mỗi ảnh.
- Lý do rejected thường gặp (lệch tự nhiên của COCO, không phải lỗi):
  - **Vật nhỏ phía sau lọt trong box to của vật phía trước**: một segment chạm hai box cùng lớp nên bị báo `instance_merge`, nhưng segment chỉ phủ một vật (ví dụ `000000002153`, `000000005001`, `000000013348`, `000000025057`).
  - **Vật cùng lớp đứng sát hoặc che nhau** (đám đông, sách trên kệ, xe đậu sát): box chồng lên nhau nhưng mỗi vật vẫn có segment riêng.
  - **Segment quá nhỏ**: vài chục đến vài trăm pixel (ví dụ remote 56 pixel ở `000000013729`), không thể phủ hai vật.
  - **Nhiều segment sát nhau trông như một mảng**: công cụ xem ảnh ban đầu tô mọi segment ứng viên cùng một màu.
- Review chéo: người tổng hợp đọc lại note và gắn cờ các dòng confirmed có note tả *box detection gom nhiều vật* thay vì *một segment panoptic phủ hai vật* (định nghĩa của `instance_merge`). Người xem tự mở lại ảnh và tự sửa; số confirmed giảm từ **22 xuống 17** (`000000004134`, `000000006763`, `000000024610`, `000000013729`, `000000015335` đổi sang rejected).
- Bài học từ `000000015335` (ban đầu confirmed, sau đổi rejected): góc trên phải trông như một mảng tím liền phủ 3 người, nhưng thực ra là 6 segment riêng, mỗi segment khớp đúng một box của một người. Hai điều rút ra: (1) **công cụ xem ảnh ảnh hưởng trực tiếp tới kết luận**, nên `view_candidates.py` đã được sửa để mỗi segment một màu, có viền trắng, số hiệu `S1, S2…` và số pixel; (2) **đối chiếu số liệu trước khi confirmed**: nếu khung của segment khớp đúng một box riêng (xem `candidates.json`) thì segment đó chỉ là một vật, không phải bị gộp.

## 3. Quyết định và lineage
`errors.json` có **33 mục lỗi**, nhưng QC v1 đếm theo target duy nhất: **31 target ảnh + 1 `scene_leak` được tính như một ảnh = 32/250 (12,8%)**. Ảnh `000000016958` có hai phát hiện (`invalid_class` và `missing_box`), nên không tính thành hai ảnh lỗi. Tỉ lệ vẫn vượt ngưỡng 2%, nên quyết định **HOLD**. Lineage ghi `R-021: affected=True action=review_or_retrain`; sửa dữ liệu không tự cập nhật model đã train, nên run này phải được xem lại hoặc train lại trước khi phát hành.

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
Không phát hiện bug cản trở việc hoàn thành seed 34. Đề ẩn đã được xử lý: validator sinh 11 lỗi luật và 55 ứng viên trên 54 ảnh; nhóm review đủ 55 dòng, gồm 8 `confirmed` và 47 `rejected`. Sau khi gộp, `submission/de_an/errors.json` có 19 dòng lỗi nhưng 17 target duy nhất (hai target ảnh có hai loại lỗi); QC theo target duy nhất là **17/250 = 6,8%** trên 250 mục trong manifest. Tỷ lệ này vượt ngưỡng 2% của GUIDE, tương ứng **HOLD**. Truy vết có `tier_a = 2`, `tier_b = 5`, `notify = 5`. Không đọc `_private/` và không báo F1 cho đề ẩn.

## 7. Thử nghiệm local giảm nhiễu `instance_merge`
Ứng viên `instance_merge` trước đây chỉ cần mask segment phủ ít nhất 30% và 50 pixel trong mỗi box; một box lớn nhưng chỉ có một phần rất nhỏ thuộc segment vẫn có thể làm thành bằng chứng. Bản local thêm điều kiện mỗi box phải chứa ít nhất **3% mask pixel của chính segment so với diện tích pixel của box**. Ngưỡng 3% được chọn từ review seed 34 và lô sạch; tỷ lệ dùng diện tích box sau khi rasterize/clamp để đồng nhất với cách đếm pixel giao nhau.

Chạy lại bộ sinh ứng viên trong bộ nhớ (không ghi đè candidate, review hay errors đã có) cho kết quả: seed 34 **57 → 41** hàng; giữ cả **8/8** instance_merge đã confirmed và loại **16/38** instance_merge đã rejected. Lô sạch giảm **8 → 5** hàng. Kiểm tra sau đó trên đề ẩn giảm **55 → 39** hàng, giữ ứng viên instance_merge confirmed **1/1** và loại **16/46** rejected; seed 99 giảm **55 → 39** hàng, chưa có review thủ công để kết luận chất lượng.

Thử nghiệm riêng với `bbox_drift`: nới giới hạn coverage từ **0,80 lên 0,98** không làm tăng hàng đợi lô sạch. Bốn ứng viên mới được đưa ra review: `000000017899`, `000000022892`, `000000011699`, `000000025393`; Tiến xác nhận `000000017899`, `000000022892`, `000000025393` và bác `000000011699`. Ba lỗi xác nhận được thêm vào `errors.json`. Tự chấm lại cho kết quả cross-check F1 **0,6**, F1 tổng **0,8**; chưa đạt mục tiêu 0,9.

Thử nghiệm tiếp với `instance_merge`: giảm mask coverage từ **0,30 xuống 0,20** thêm 13 ứng viên seed 34 và thêm 6 ứng viên tự nhiên trên 50 ảnh sạch; Tiến bác cả 13. Thử 10% thêm 10 ứng viên seed 34 và 9 ứng viên sạch so với 20%; Tiến xác nhận `000000015254` và bác 9 ảnh còn lại. `000000015254` đã có `guideline_mismatch` trong `errors.json`. GUIDE.md quy định mỗi ảnh mang nhiều nhất một lỗi, nên `instance_merge` thứ hai chưa được thêm vào `errors.json`.

Thử 5% thêm 7 ứng viên seed 34 và đưa số ứng viên sạch lên **22/50**; Tiến xác nhận `000000000632` và bác 6 ảnh còn lại. Thử 1% chỉ thêm `000000025139`, bị Tiến bác; lô sạch có **24/50** ứng viên. Không có lỗi mới để thêm, F1 vẫn làm tròn **0,8**. Các ngưỡng thấp hơn chưa được đưa vào code chính.
