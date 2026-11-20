Release: lab250_49e16bee4751_v2
Parent: lab250_49e16bee4751
Số ảnh: 237
Số nhãn: 1660
Guideline: v1.2 (J01-J04), v1.3 (J05-J10)
QC v1: 28/250 = 11.2%
Kết luận v1: Hold — Tỉ lệ lỗi 11.2% vượt ngưỡng 2%, không phát hành v1.
Kết luận v2: Release — Đã tách 13 ảnh lỗi detection/thiếu file vào rework_queue.csv; sửa metadata và giữ 237 ảnh sạch detection.
Ghi chú: Đã mở kiểm tra ảnh wrong_hash (000000003553, 000000019786) xác nhận JPEG nguyên vẹn và cập nhật sha256; sửa guideline theo jobs.csv (000000015254, 000000025096); gom split thống nhất cho scene_leak (scene_698). Ảnh rework giao đúng annotator/reviewer theo jobs.csv. Ảnh chỉ lỗi panoptic giữ lại v2 và báo team panoptic: 000000000139 (instance_merge), 000000001000 (instance_merge), 000000002157 (category_swap), 000000008277 (instance_merge), 000000010583 (thing_overlap), 000000010707 (instance_merge), 000000011760 (instance_merge), 000000013659 (instance_merge), 000000017182 (instance_merge), 000000019109 (instance_merge).
