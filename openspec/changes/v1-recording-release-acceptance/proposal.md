# Proposal

## Why

Quy trình desktop trên Windows đã được triển khai, nhưng tuyên bố sẵn sàng phát hành vẫn thiếu bằng chứng ghi âm cuộc họp thật được phép, kiểm thử bản đóng gói trên máy sạch và rà soát giấy phép của các dependency native. Cần hoàn tất các điều kiện này trên ứng dụng Tauri hiện tại trước khi coi v1 là đáng tin cậy hoặc phát hành công khai.

## What Changes

- Thực hiện các kiểm thử nghiệm thu M1 còn mở trên thiết bị thật: âm thanh hệ thống và microphone phải nghe rõ, Pause/Resume hoạt động, và có thể khôi phục bản ghi bị gián đoạn. Chỉ dùng cuộc họp đã được phép ghi âm và lưu bằng chứng không chứa nội dung cuộc họp.
- Kiểm thử ứng dụng Tauri đã đóng gói cùng Python sidecar trên Windows 10 và 11 x64 sạch theo luồng Record hoặc Import → phiên âm tiếng Việt cục bộ → xem lại theo timestamp → tạo biên bản offline → xuất và xóa; bao gồm kiểm tra không truyền dữ liệu ra ngoài ở chế độ Restricted.
- Rà soát chính xác các dependency native và thông báo giấy phép được đóng gói, kiểm tra tính toàn vẹn gói và hướng dẫn sử dụng lần đầu; tiếp tục chặn phát hành khi còn điều kiện bắt buộc chưa được giải quyết.
- Ghi nhận chất lượng lời nói giọng Bắc, giọng Nam và tiếng Việt xen tiếng Anh, nhưng không coi mẫu đọc có kiểm soát là bằng chứng về độ chính xác trong cuộc họp thật.

## Capabilities

### New Capabilities

Không có. Change này xác minh các hành vi đã được đặc tả trong `windows-recorder-m1`, `local-asr-m2`, `minutes-privacy-m3`, `release-export-cleanup-m4` và `tauri-desktop-python-sidecar`.

### Modified Capabilities

Không có. Lỗi phát hiện khi nghiệm thu phải được sửa trong capability hiện có chịu trách nhiệm; change này không định nghĩa lại yêu cầu của capability đó.

## Impact

Đây là change về nghiệm thu và mức độ sẵn sàng phát hành, nên `.openspec.yaml` khai báo `skip_specs: true`. Phạm vi tác động gồm ma trận xác minh, kiểm tra gói có thể tái lập, danh mục giấy phép, tài liệu phát hành và có thể cả mã sửa lỗi ở khu vực phụ trách nếu một điều kiện không đạt. Không cần tài khoản, server, provider trả phí hay luồng xử lý cloud mới.
