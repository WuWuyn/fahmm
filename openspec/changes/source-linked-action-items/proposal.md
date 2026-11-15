# Proposal

## Why

Biên bản có thể chứa các đề xuất hành động kèm dẫn nguồn, nhưng hiện chúng chỉ là một phần của tài liệu, chưa phải công việc bền vững để người dùng xác nhận và theo dõi. Bộ quản lý action item cục bộ biến kết quả cuộc họp đã được rà soát thành việc cần làm tiếp mà không coi nội dung trích xuất chưa xác minh là cam kết.

## What Changes

- Cho phép người dùng tạo action item độc lập từ đề xuất có dẫn nguồn trong biên bản, xem lại nội dung task, người phụ trách và ngày hạn tùy chọn, rồi xác nhận.
- Mỗi action có ID ổn định, tham chiếu tới cuộc họp và nguồn transcript, trạng thái rà soát, trạng thái thực hiện và lịch sử cập nhật được giữ sau khi khởi động lại ứng dụng hoặc tạo lại biên bản.
- Thêm khu vực Action Items ở cấp cuộc họp để liệt kê, sửa, hoàn thành, lưu trữ và mở lại audio nguồn của task đã xác nhận; tách rõ đề xuất chưa xác nhận.
- Giữ nguyên các phiên bản transcript và biên bản hiện có, mặc định Restricted và hành vi chỉ xử lý cục bộ.

## Capabilities

### New Capabilities

- `action-item-management`: Tạo, xác nhận, cập nhật và rà soát các task của cuộc họp được lưu độc lập với tham chiếu nguồn bền vững.

### Modified Capabilities

Không có. Yêu cầu hiện có về tạo biên bản và dẫn nguồn không thay đổi; người dùng chủ động chuyển một đề xuất trong biên bản thành action item.

## Impact

Bổ sung kho action do ứng dụng quản lý và các thao tác bridge trong dịch vụ cuộc họp cục bộ hiện có, cùng các điều khiển Action Items trong màn hình Meetings của Tauri. Việc tổng hợp task theo project được lên kế hoạch trong `local-project-workspaces-search`. Tự động giao việc, nhắc việc, tích hợp dịch vụ task bên ngoài và AI ngữ nghĩa cục bộ nằm ngoài change này.
