# Pha 2 — Hướng dẫn review cho nhóm

## Mục đích

Validator so sánh detection với panoptic để khoanh vùng **ứng viên**, không tự kết luận nhãn nào sai. Người review mở ảnh để phân biệt lỗi thật với khác biệt tự nhiên giữa hai bộ nhãn. Việc này giúp giảm false positive trước khi gộp lỗi vào `errors.json`.

## Phân công seed 34

Danh sách tổng ở [submission/r34/review_assignments.csv](../submission/r34/review_assignments.csv). Mỗi thành viên có một trang xem và một CSV riêng trong [submission/r34/review_assignments/by_member/](../submission/r34/review_assignments/by_member/). Có 55 ảnh ứng viên duy nhất, chia đều 11 ảnh/người; hai ảnh bị thiếu file được xử lý bằng kiểm tra `missing_image`, không có ảnh để review.

| Thành viên | Trang xem ảnh (mở sau khi dựng overlay) | CSV cần điền |
|---|---|---|
| Lê Trung Sang | [01_Sang.html](../submission/r34/review_assignments/by_member/01_Sang.html) | [01_Sang.csv](../submission/r34/review_assignments/by_member/01_Sang.csv) |
| Lương Hoàng Bảo Trân | [02_Tran.html](../submission/r34/review_assignments/by_member/02_Tran.html) | [02_Tran.csv](../submission/r34/review_assignments/by_member/02_Tran.csv) |
| Nguyễn Anh Tiến | [03_Tien.html](../submission/r34/review_assignments/by_member/03_Tien.html) | [03_Tien.csv](../submission/r34/review_assignments/by_member/03_Tien.csv) |
| Vũ Tuyết Trinh | [04_Trinh.html](../submission/r34/review_assignments/by_member/04_Trinh.html) | [04_Trinh.csv](../submission/r34/review_assignments/by_member/04_Trinh.csv) |
| Phan Hải Đăng | [05_Dang.html](../submission/r34/review_assignments/by_member/05_Dang.html) | [05_Dang.csv](../submission/r34/review_assignments/by_member/05_Dang.csv) |

Chương trình đã tự lọc ảnh có ứng viên và chia danh sách đều theo thành viên; không cần từng người tự lọc từ toàn bộ lô. Mỗi người chỉ review 11 ảnh được giao. Nếu một ảnh có nhiều loại ứng viên, CSV cá nhân có một dòng cho mỗi loại để ghi kết quả riêng.

Kết quả hiện tại: seed 34 có 57 hàng ứng viên trên 55 ảnh: 46 `instance_merge`, 6 `missing_box`, 4 bất đồng lớp và 1 `bbox_drift`. Lô sạch `--no-faults` có 8 hàng `instance_merge` trên 50 ảnh, nên các ứng viên không được xem là lỗi nếu chưa kiểm tra ảnh.

## Mở ảnh và làm review

1. Mở trang HTML của mình trong `submission/r34/review_assignments/by_member/`. Trang dùng ảnh overlay ở `runs/r34/review_previews/`; thư mục `runs/` bị Git bỏ qua nên mỗi máy cần có dữ liệu và overlay cục bộ.
2. Box cyan là các box detection; box vàng là box liên quan đến ứng viên. Màu mask: đỏ là bất đồng lớp, cam là `bbox_drift`, xanh dương là `missing_box`, tím là `instance_merge`.
3. Nhìn vật trong ảnh rồi ghi kết quả vào CSV cá nhân. Dùng `confirmed` khi ảnh chứng minh lỗi; dùng `rejected` khi đó là khác biệt tự nhiên. Ghi chú nêu điều nhìn thấy, ít nhất 20 ký tự và không sao chép cùng một câu cho nhiều ảnh.
4. Với `class_disagreement`, nếu detection sai thì ghi type `class_swap`; nếu panoptic sai thì ghi `category_swap`. Nếu bác ứng viên, giữ `class_disagreement`, đặt verdict `rejected` và giải thích trong note.
5. Mỗi người gửi CSV đã điền cho người tổng hợp. Người tổng hợp ghép các dòng vào `runs/r34/review_log.csv` theo đúng header `image,type,verdict,note`.

Nếu cần dựng dữ liệu và overlay trên máy mới, chạy từ thư mục gốc repo. Chỉ chạy `run_lab.py` khi `runs/r34/delivery` chưa có; lệnh đó tạo lại run nếu chạy lại.

```powershell
py -X utf8 scripts/download_public.py
$env:PYTHONUTF8 = '1'
py scripts/run_lab.py --seeds 34
py -X utf8 validator/validate.py runs/r34/delivery --out runs/r34/rules.json --candidates runs/r34/candidates.json
py -X utf8 validator/view_candidates.py --delivery runs/r34/delivery --candidates runs/r34/candidates.json --out runs/r34/review_previews
```

Sau khi cả nhóm review xong, tổng hợp và chấm tự kiểm:

```powershell
py scripts/merge_review.py --rules runs/r34/rules.json --review runs/r34/review_log.csv --out runs/r34/errors.json
py scripts/score_findings.py --run runs/r34
```

`score_findings.py` dùng để tự đo tiến độ. Không dùng điểm để dò đáp án; không đọc `_private/`, annotation COCO gốc hay dữ liệu ngoài `delivery/` trong validator.
