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
2. Box cyan là các box detection; box vàng là box liên quan đến ứng viên. Mỗi segment ứng viên có **một màu riêng, viền trắng và số hiệu `S1`, `S2`…**; dải chú thích ở đáy ảnh ghi loại ứng viên, lớp panoptic và số pixel (ví dụ `S1 MERGE person 2984px`). Hai vùng có viền riêng là hai segment, không phải bị gộp. `instance_merge` chỉ đúng khi **một** segment phủ hai vật; box vàng bao nhiều vật không chứng minh được điều đó.
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

### Chia hàng đợi cho seed mới

Sau khi đã sinh candidates và overlay, chia ảnh đều cho năm người. Mỗi ảnh được giao trọn cho một người; nếu ảnh có nhiều loại ứng viên thì CSV người đó có nhiều dòng. Mở `runs/r99/review_assignments/index.html` để vào trang của từng người.

```powershell
py -X utf8 scripts/split_review_queue.py --candidates runs/r99/candidates.json --out runs/r99/review_assignments --members "LÊ TRUNG SANG" "LƯƠNG HOÀNG BẢO TRÂN" "NGUYỄN ANH TIẾN" "VŨ TUYẾT TRINH" "PHAN HẢI ĐĂNG"
```

Lệnh tạo `assignments.csv` tổng, một CSV và một trang HTML cho mỗi người. Chọn thư mục output mới cho mỗi seed; script không ghi đè thư mục đã có nội dung.

Sau khi cả nhóm review xong, tổng hợp và chấm tự kiểm:

```powershell
py scripts/merge_review.py --rules runs/r34/rules.json --review runs/r34/review_log.csv --out runs/r34/errors.json
py scripts/score_findings.py --run runs/r34
```

`score_findings.py` dùng để tự đo tiến độ. Không dùng điểm để dò đáp án; không đọc `_private/`, annotation COCO gốc hay dữ liệu ngoài `delivery/` trong validator.

## Kịch bản đề ẩn (40 phút)

Đã diễn tập trên lô giả `inject_release.py --seed 99 --opaque` (tên ảnh `img_xxxx` như đề ẩn): validator khoảng 30 giây, vẽ overlay khoảng 5 giây, chia việc dưới 1 giây. Gần như toàn bộ 40 phút dành cho xem ảnh. Trước giờ làm đề: **`git pull`** để có bản mới của `validator/`.

| Phút | Việc | Ai |
|---|---|---|
| 0–3 | Tải `de_an.zip`, giải nén vào gốc repo (được `delivery/`), chạy 3 lệnh máy bên dưới | Trinh |
| 3–30 | Mỗi người mở trang HTML của mình, điền CSV cá nhân (khoảng 11 ảnh/người) | Cả nhóm |
| 3–30 | Làm `submission/de_an/trace.json` (song song với review) | Đăng |
| 30–33 | Gom 5 CSV về `runs/de_an/review_assignments/by_member/`, chạy lệnh gộp; nếu script báo DỪNG thì nhắn đúng người sửa dòng bị nêu | Trinh |
| 33–40 | Kiểm `submission/de_an/` đủ 4 file, commit, push (không commit `delivery/`) | Sang |

Lệnh máy (chạy từ gốc repo, PowerShell):

```powershell
$env:PYTHONUTF8 = '1'
py validator/validate.py delivery --out runs/de_an/rules.json --candidates submission/de_an/candidates.json
py validator/view_candidates.py --delivery delivery --candidates submission/de_an/candidates.json --out runs/de_an/review_previews
py scripts/split_review_queue.py --candidates submission/de_an/candidates.json --out runs/de_an/review_assignments --members Sang Tran Tien Trinh Dang
```

Mở `runs/de_an/review_assignments/index.html` để vào trang của từng người. Nếu mỗi người làm trên máy riêng thì mỗi máy chạy cùng ba lệnh trên (kết quả chia việc giống nhau), rồi gửi CSV cá nhân đã điền cho Trinh.

Gộp (dừng và không ghi file nếu còn verdict sai chữ, thiếu dòng, note dưới 20 ký tự hoặc note trùng):

```powershell
py validator/normalize_review.py --reviews runs/de_an/review_assignments/by_member --candidates submission/de_an/candidates.json --out submission/de_an/review_log.csv --rules runs/de_an/rules.json --errors submission/de_an/errors.json
```

Lưu ý khi review đề ẩn:
- Bất đồng lớp: mở ảnh xem vật thật là gì. Detection sai thì ghi `class_swap`, panoptic sai thì ghi `category_swap`; bác thì giữ `class_disagreement` + `rejected`.
- `instance_merge`: chỉ nhìn **segment có viền riêng**. Segment rất nhỏ (vài chục pixel) gần như không thể phủ hai vật.
- Note nói **thấy gì** trong ảnh, mỗi dòng một câu khác nhau.
