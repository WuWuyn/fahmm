# Tasks

## 1. Cố định bản ứng viên và hồ sơ nghiệm thu

- [ ] 1.1 Build một bản cài đặt Tauri và một bản portable cùng sidecar từ commit đã ghi nhận; xác minh cả hai artifact khởi động được, rồi ghi hash, phiên bản dependency và lệnh build vào `docs/v1-release-acceptance.md`.
- [x] 1.2 Tạo ma trận AT-01–AT-11 và giọng Bắc/giọng Nam/lời nói pha trộn trong `docs/v1-release-acceptance.md`; xác minh từng dòng phân biệt bằng chứng có kiểm soát, phần cứng thật và máy sạch, đồng thời dẫn tới báo cáo M1–M4 hoặc Tauri phụ trách.

## 2. Nghiệm thu ghi âm và lời nói trên thiết bị thật

- [ ] 2.1 Thực hiện cuộc gọi Teams/Meet 20 phút được phép ghi âm với tai nghe và microphone trên bản ứng viên; xác minh cả âm thanh hệ thống và microphone đều nghe hiểu được khi phát lại, không có bot tham gia, và ghi chi tiết thiết bị/định tuyến không chứa nội dung cuộc họp cho AT-01.
- [ ] 2.2 Thử Record/Pause/Resume/Stop trên cùng phần cứng; xác minh trạng thái chỉ báo và đồng hồ, audio lưu hợp lệ và lời nói trong thời gian Pause không xuất hiện cho AT-02; ghi lại kết quả quan sát.
- [ ] 2.3 Ngắt đột ngột một lần ghi thật sau khi ít nhất một chunk đã lưu, mở lại bản ứng viên, khôi phục audio và xác minh cuộc họp khác vẫn nguyên vẹn cho AT-10; ghi thời lượng khôi phục và mọi chunk bị bỏ qua.
- [ ] 2.4 Dùng các mẫu lời nói giọng Bắc, giọng Nam và tiếng Việt xen tiếng Anh đã được chấp thuận; xác minh phiên âm cục bộ hoàn tất với đầu ra có timestamp và có thể rà soát; ghi nguồn gốc mẫu cùng lỗi quan sát mà không tuyên bố độ chính xác phổ quát.

## 3. Nghiệm thu bản đóng gói trên Windows và quyền riêng tư

- [ ] 3.1 Trên Windows 10 x64 sạch, không có Python/FFmpeg phát triển, cài hoặc giải nén bản ứng viên đã cố định; xác minh GUI/sidecar khởi động, tải model đầu tiên theo thao tác rõ ràng, dùng lại model offline, nhập/phát audio và di chuyển theo timestamp; ghi môi trường và kết quả.
- [ ] 3.2 Trên Windows 11 x64 sạch với cùng điều kiện và cùng hash bản ứng viên, lặp lại các kiểm tra khởi động/model/nhập/phát audio và ghi môi trường cùng kết quả.
- [ ] 3.3 Trên cả hai máy sạch, chạy luồng Record hoặc Import → ASR tiếng Việt cục bộ → xem lại transcript đã lưu → biên bản offline Restricted → xuất → xóa đúng phạm vi; xác minh không cần API key, file xuất mở được ngoài fahmm và các cuộc họp trước không bị ảnh hưởng.
- [ ] 3.4 Chặn hoặc quan sát lưu lượng mạng của luồng Restricted trên bản đóng gói và thử Cancel/Confirm ở bước xem trước payload gửi provider bằng endpoint có kiểm soát; xác minh không gửi nội dung cuộc họp ở chế độ Restricted và chỉ gửi một lần sau xác nhận rõ ràng ở chế độ Cloud Allowed.

## 4. Điều kiện phân phối và phát hành

- [ ] 4.1 Lập danh mục các thành phần native và asset thực sự đóng gói trong host Tauri và sidecar, giải quyết điều khoản cùng thông báo giấy phép cho từng thành phần, rồi xác minh danh sách thông báo khớp với bản ứng viên, không chứa model weights hay dữ liệu người dùng.
- [ ] 4.2 Viết và thử hướng dẫn chạy lần đầu, checksum, cài model, dùng offline, vị trí dữ liệu, xuất, xóa và rollback trên bản ứng viên đã giải nén ở máy sạch; xác minh mọi lệnh và đường dẫn trong tài liệu.
- [ ] 4.3 Đối chiếu các checkbox còn mở của `windows-recorder-m1` và `release-export-cleanup-m4` với bằng chứng; sau mỗi lần sửa lỗi, chạy lại các test liên quan trên bản ứng viên có hash mới; chỉ nghiệm thu v1 khi mọi dòng bắt buộc của ma trận đều đạt và không còn điều kiện giấy phép hay máy sạch đang mở.
