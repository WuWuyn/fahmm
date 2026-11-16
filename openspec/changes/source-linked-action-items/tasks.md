# Tasks

## 1. Bản ghi action bền vững

- [ ] 1.1 Thêm kho action có phiên bản theo từng cuộc họp, với ID ổn định, tham chiếu nguồn được xác thực, ghi nguyên tử và đọc trạng thái rỗng cho cuộc họp cũ; kiểm tra tạo/đọc/liệt kê và việc file transcript/biên bản không đổi trong test kho lưu trữ.
- [ ] 1.2 Triển khai chuyển action từ chỉ số đề xuất của biên bản đã lưu, kiểm tra nguồn và origin key bảo đảm gọi lặp không tạo trùng; xác minh yêu cầu lặp trả một item, còn segment không hợp lệ hoặc thuộc cuộc họp khác bị từ chối.
- [ ] 1.3 Thêm sửa trường, người phụ trách và ngày hạn ISO tùy chọn, xác nhận rõ ràng, chuyển trạng thái `todo`/`in_progress`/`done` và trạng thái lưu trữ; xác minh dữ liệu còn sau khởi động lại và các chuyển trạng thái hợp lệ trong service test.
- [ ] 1.4 Ghi nối tiếp các sự kiện thay đổi UTC bất biến với kiểm tra revision; xác minh ghi bị gián đoạn giữ bản ghi trước đó và cập nhật bằng revision cũ báo xung đột mà không mất lịch sử.
- [ ] 1.5 Viết tài liệu về nơi lưu action, giữ nguồn, khả năng hiển thị khi rollback và phạm vi xóa cuộc họp trong hướng dẫn lưu trữ; đối chiếu ví dụ với bản ghi test đã lưu.

## 2. Bridge và luồng cuộc họp

- [ ] 2.1 Thêm các thao tác bridge có giới hạn `action.list`, `action.read`, `action.createFromMinutes`, `action.update`, `action.confirm` và `action.archive` với ID được xác thực, không nhận đường dẫn tùy ý; kiểm tra contract, chuyển lặp, revision cũ và không truyền dữ liệu ở chế độ Restricted.
- [ ] 2.2 Thêm điều khiển Create action cạnh đề xuất có dẫn nguồn trong biên bản có cấu trúc, cùng form rà soát hiển thị nguồn gốc, task, người phụ trách và ngày hạn có thể sửa; xác minh Cancel hoặc thiếu dẫn nguồn hợp lệ sẽ không tạo action trong React test.
- [ ] 2.3 Thêm tab Action Items ở cấp cuộc họp với các nhóm chưa xác nhận, đang hoạt động, đã xong, đã lưu trữ và các điều khiển trạng thái, lưu trữ, lịch sử; xác minh task đã xác nhận vẫn tồn tại sau khi remount và tạo lại biên bản mà không sửa biên bản.
- [ ] 2.4 Kết nối điều hướng nguồn của action tới transcript run đã lưu và audio player theo timestamp; xác minh mở action từ run cũ sẽ seek đúng segment trong UI test.
- [ ] 2.5 Cập nhật tài liệu luồng người dùng bằng tiếng Anh để giải thích cách rà soát đề xuất, xác nhận, đổi trạng thái, lưu trữ và quyền riêng tư cục bộ; đối chiếu các bước trong tài liệu với UI Tauri.

## 3. Nghiệm thu action đầu cuối

- [ ] 3.1 Từ một cuộc họp nhập audio và một cuộc họp được ghi, tạo và xác nhận các action có dẫn nguồn, sửa trường, tiến trạng thái rồi mở lại, khởi động lại sidecar; xác minh ID, liên kết nguồn và lịch sử sự kiện còn nguyên.
- [ ] 3.2 Tạo lại biên bản và chạy lại ASR, sau đó xóa một cuộc họp; xác minh action của nó không đổi trước khi xóa, cuộc họp còn lại nguyên vẹn và không thao tác action nào gửi nội dung cuộc họp ra mạng.
