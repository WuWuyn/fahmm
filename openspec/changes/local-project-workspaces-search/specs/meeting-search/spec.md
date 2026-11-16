# Spec Delta

## Purpose

Giúp người dùng tìm bằng chứng cuộc họp đã lưu và công việc theo sau đã xác nhận trong thư viện cục bộ, rồi quay lại nguồn hỗ trợ từng kết quả.

## ADDED Requirements

### Requirement: Tìm kiếm cục bộ bằng chứng cuộc họp đã lưu
Ứng dụng SHALL tìm trong tên cuộc họp đã lưu, bản transcript đã sửa và lưu của run được chọn, phiên bản biên bản đã lưu được chọn và action item đã xác nhận. Tìm kiếm MUST hoạt động offline và MUST NOT gửi nội dung đã lập index hoặc từ khóa truy vấn tới endpoint bên ngoài.

#### Scenario: Tìm quyết định hoặc task
- **WHEN** người dùng nhập từ khóa có trong biên bản đã lưu hoặc action đã xác nhận
- **THEN** ứng dụng hiển thị cuộc họp, loại nội dung và đoạn trích dễ đọc khớp với từ khóa

#### Scenario: Văn bản trong editor chưa lưu
- **WHEN** người dùng tìm văn bản đã nhập nhưng chưa lưu trong editor transcript hoặc biên bản
- **THEN** ứng dụng không hiển thị văn bản đó như một kết quả tìm kiếm đã lưu

#### Scenario: Văn bản tiếng Việt
- **WHEN** người dùng tìm từ tiếng Việt với kiểu chữ hoa/thường khác hoặc không dấu
- **THEN** vẫn tìm được nội dung đã lưu khớp với các từ đó mà không thay đổi văn bản gốc khi hiển thị

### Requirement: Giới hạn phạm vi và lọc kết quả
Ứng dụng SHALL cho phép giới hạn kết quả từ khóa vào một project hoặc toàn bộ cuộc họp cục bộ và lọc theo ngày họp. Kết quả action SHALL hỗ trợ lọc theo trạng thái thực hiện.

#### Scenario: Lọc theo project
- **WHEN** người dùng giới hạn truy vấn vào project A
- **THEN** kết quả từ project B và cuộc họp Unassigned không xuất hiện

#### Scenario: Không có kết quả
- **WHEN** không có nội dung đã lưu nào khớp với truy vấn và bộ lọc
- **THEN** ứng dụng hiển thị trạng thái rỗng mà không thay đổi dữ liệu cuộc họp

### Requirement: Điều hướng tới nguồn khớp
Mỗi kết quả SHALL xác định cuộc họp, loại nguồn và ID run, phiên bản hoặc action đã lưu. Kết quả transcript và action có dẫn nguồn SHALL mở nguồn đã lưu rồi đưa audio cục bộ tới timestamp được tham chiếu; kết quả biên bản SHALL mở phiên bản biên bản đã lưu và hiển thị dẫn nguồn nếu có.

#### Scenario: Mở kết quả transcript
- **WHEN** người dùng chọn kết quả transcript từ run cũ hiện đang được chọn cho cuộc họp
- **THEN** ứng dụng mở run đó trong cuộc họp và đưa audio tới thời điểm bắt đầu segment khớp

#### Scenario: Mở kết quả action
- **WHEN** người dùng chọn kết quả action đã xác nhận
- **THEN** ứng dụng mở action và cho phép truy cập transcript cùng audio nguồn được dẫn

### Requirement: Phản ánh thay đổi đã commit và việc xóa
Tìm kiếm SHALL phản ánh việc đổi tên đã lưu, sửa transcript, chọn phiên bản biên bản, cập nhật action, chuyển project và xóa cuộc họp. Nội dung cuộc họp đã xóa MUST NOT còn trong kết quả; cập nhật index thất bại hoặc gián đoạn MUST có thể được sửa từ dữ liệu cục bộ đã lưu.

#### Scenario: Sửa rồi tìm
- **WHEN** người dùng lưu bản sửa transcript rồi tìm cách diễn đạt mới
- **THEN** cách diễn đạt đã sửa xuất hiện, còn cách diễn đạt bị thay thế trong working copy đang được chọn không xuất hiện như nội dung hiện tại

#### Scenario: Xóa cuộc họp
- **WHEN** cuộc họp bị xóa và người dùng tìm văn bản từng có trong đó
- **THEN** không có kết quả nào từ cuộc họp đó được trả về

#### Scenario: Dựng lại index
- **WHEN** index tìm kiếm cục bộ bị thiếu hoặc hỏng trong khi file cuộc họp vẫn nguyên vẹn
- **THEN** ứng dụng có thể dựng lại khả năng tìm kiếm từ các file đó mà không thay đổi cuộc họp

### Requirement: Giữ thư viện phản hồi nhanh
Việc tìm kiếm và bảo trì index SHALL giữ cho điều khiển ghi âm và tài liệu phản hồi nhanh trong thư viện cục bộ có ít nhất 500 cuộc họp. Số lượng kết quả SHALL có giới hạn và có thể duyệt theo từng trang.

#### Scenario: Tìm trong thư viện lớn
- **WHEN** người dùng tìm kiếm trong thư viện có ít nhất 500 cuộc họp
- **THEN** UI vẫn phản hồi và hiển thị trang kết quả đầu tiên có giới hạn, cùng cách tải thêm kết quả
