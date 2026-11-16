# Tasks

## 1. Registry project cục bộ

- [ ] 1.1 Thêm registry project được lưu nguyên tử với ID ổn định, tên và tối đa một phép gán project cho mỗi ID cuộc họp; xác minh cuộc họp cũ hiện ở Unassigned và thao tác tạo/đổi tên/gán/chuyển vẫn tồn tại sau khởi động lại.
- [ ] 1.2 Triển khai xóa project sau xác nhận, xóa các phép gán của project đó nhưng không xóa thư mục cuộc họp hay đổi chế độ quyền riêng tư; kiểm tra xóa project có dữ liệu, giữ cuộc họp không liên quan và khôi phục sau khi ghi bị gián đoạn.
- [ ] 1.3 Thêm thao tác bridge liệt kê/tạo/đổi tên/gán/xóa project có kiểm tra đầu vào và viết tài liệu giải thích Project cá nhân, cục bộ trên thiết bị; kiểm tra bridge từ chối ID/đường dẫn không hợp lệ và hành vi offline được tài liệu hóa.

## 2. Tìm kiếm cục bộ có thể dựng lại

- [ ] 2.1 Thêm index SQLite FTS5 có thể bỏ đi cho tên cuộc họp đã lưu, các segment transcript đã sửa của run đang hoạt động, nội dung biên bản đang hoạt động và ID nguồn; xác minh FTS5 có trong runtime đóng gói và có thể dựng/dựng lại từ file hiện có mà không ghi lại chúng.
- [ ] 2.2 Chuẩn hóa văn bản trong index và truy vấn theo chữ hoa/thường cùng dấu tiếng Việt, kể cả `đ`, nhưng giữ đoạn trích gốc để hiển thị; xác minh fixture có dấu/không dấu và chữ hoa/thường trả đúng cùng kết quả mong muốn.
- [ ] 2.3 Cập nhật index sau khi commit thao tác đổi tên, sửa transcript/chọn run, sửa biên bản/chọn phiên bản, gán project, cập nhật action và xóa cuộc họp; xác minh văn bản chưa lưu và cuộc họp đã xóa không xuất hiện trong kết quả, còn cập nhật bị gián đoạn được sửa khi khởi động lại.
- [ ] 2.4 Thêm truy vấn từ khóa có tham số, phân trang, lọc project/ngày và ID kết quả ổn định; xác minh đầu vào sai định dạng không thể thoát khỏi index hoặc lộ đường dẫn file tùy ý, và index bị thiếu được dựng lại an toàn.
- [ ] 2.5 Viết tài liệu về vị trí index, cách xử lý nội dung Restricted cục bộ, việc dựng lại và giới hạn rollback trong hướng dẫn lưu trữ/quyền riêng tư; thử thao tác dựng lại theo tài liệu trên thư viện dùng một lần.

## 3. Tích hợp action và điều hướng nguồn

- [ ] 3.1 Sau khi có `source-linked-action-items`, lập index cho nội dung và trạng thái action đã xác nhận, hiển thị action chưa hoàn thành theo từng project; xác minh action chưa xác nhận, đã lưu trữ hoặc thuộc cuộc họp đã xóa không xuất hiện trong công việc đang hoạt động của project.
- [ ] 3.2 Đối chiếu kết quả tìm kiếm transcript, biên bản và action với ID đã lưu còn tồn tại trước khi điều hướng; xác minh chọn run cũ sẽ seek tới timestamp của nó, kết quả biên bản mở đúng phiên bản đã lưu và kết quả action mở nguồn được dẫn.

## 4. Giao diện Meetings

- [ ] 4.1 Thêm điều khiển tạo/đổi tên/xóa Project và gán cuộc họp trong Meetings, giữ điều hướng cấp cao hiện tại; kiểm tra danh sách project và Unassigned, thao tác chuyển, xác nhận và nhãn quyền riêng tư trong React test.
- [ ] 4.2 Thêm ô từ khóa, bộ lọc project/ngày và trạng thái action, loại kết quả/đoạn trích dễ đọc, trạng thái rỗng và kết quả phân trang; kiểm tra tổ hợp bộ lọc và điều hướng nguồn trong React test.
- [ ] 4.3 Cập nhật tài liệu luồng người dùng bằng tiếng Anh về nhóm project, tìm kiếm chỉ trên nội dung đã lưu, xem action và điều hướng timestamp; đối chiếu các điều khiển trong tài liệu với UI Tauri.

## 5. Nghiệm thu thư viện cục bộ tích hợp

- [ ] 5.1 Tạo dữ liệu thử ít nhất 500 cuộc họp với transcript, biên bản tiếng Việt và action đã xác nhận tiêu biểu; xác minh việc tìm kiếm/lập index không chặn Recorder hay điều khiển tài liệu và trang kết quả đầu tiên có giới hạn.
- [ ] 5.2 Khi chặn mạng, gán các cuộc họp Restricted và Cloud Allowed vào cùng project, tìm nội dung đã lưu, chuyển một cuộc họp, dựng lại index và xóa cuộc họp khác; xác minh chế độ quyền riêng tư không đổi, không nội dung nào rời thiết bị và mọi kết quả khớp với các file cục bộ còn tồn tại.
