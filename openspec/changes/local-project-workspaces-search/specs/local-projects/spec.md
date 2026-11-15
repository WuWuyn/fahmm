# Spec Delta

## Purpose

Cho phép một người sắp xếp các cuộc họp đã lưu vào project cục bộ trên thiết bị và xem công việc liên quan mà không cần tài khoản, thành viên chia sẻ hay dịch vụ đồng bộ.

## ADDED Requirements

### Requirement: Quản lý project cục bộ
Ứng dụng SHALL cho phép người dùng tạo, đổi tên và liệt kê project cá nhân với ID ổn định. Quản lý project MUST hoạt động offline và MUST NOT truyền nội dung cuộc họp hay project ra ngoài.

#### Scenario: Tạo và mở lại project
- **WHEN** người dùng tạo project, đóng ứng dụng rồi mở lại
- **THEN** project giữ nguyên ID, tên và xuất hiện trong danh sách project cục bộ

#### Scenario: Đổi tên project
- **WHEN** người dùng đổi tên project
- **THEN** tên mới xuất hiện cho mọi cuộc họp được gán, còn ID ổn định và dữ liệu cuộc họp không đổi

### Requirement: Mỗi cuộc họp thuộc tối đa một project
Mỗi cuộc họp SHALL thuộc tối đa một project cục bộ hoặc nhóm Unassigned. Người dùng SHALL có thể gán hoặc chuyển cuộc họp mà không làm đổi audio, transcript, biên bản, action hay phân loại quyền riêng tư đã lưu.

#### Scenario: Gán cuộc họp hiện có
- **WHEN** người dùng gán một cuộc họp đã ghi hoặc đã nhập vào project
- **THEN** cuộc họp xuất hiện trong project đó sau khi khởi động lại, còn nội dung đã lưu và chế độ quyền riêng tư không đổi

#### Scenario: Chuyển cuộc họp
- **WHEN** người dùng chuyển cuộc họp từ project này sang project khác
- **THEN** cuộc họp xuất hiện ở project đích và không có bản sao cuộc họp thứ hai được tạo

#### Scenario: Cuộc họp từ phiên bản cũ
- **WHEN** ứng dụng mở cuộc họp được lưu trước khi có project
- **THEN** cuộc họp xuất hiện ở Unassigned và vẫn dùng được mà không bị buộc chuyển đổi dữ liệu

### Requirement: Duyệt cuộc họp và mở công việc theo project
Ứng dụng SHALL hiển thị các cuộc họp của project và các action item đã xác nhận nhưng chưa hoàn thành khi có chức năng quản lý action. Người dùng SHALL có thể mở cuộc họp hoặc action từ màn hình project.

#### Scenario: Xem công việc của project
- **WHEN** người dùng mở project có hai cuộc họp và các action đã xác nhận nhưng chưa hoàn thành
- **THEN** màn hình project hiển thị các cuộc họp, action đó và mở được cuộc họp hoặc action nguồn đã chọn

### Requirement: Xóa project mà không xóa nội dung cuộc họp
Ứng dụng SHALL yêu cầu xác nhận trước khi xóa project. Sau khi xóa, các cuộc họp SHALL chuyển sang Unassigned và ứng dụng MUST NOT xóa file cuộc họp, action, transcript, biên bản hoặc file đã xuất.

#### Scenario: Xóa project có cuộc họp
- **WHEN** người dùng xác nhận xóa project có chứa cuộc họp
- **THEN** project biến mất, các cuộc họp chuyển sang Unassigned và dữ liệu đã lưu vẫn truy cập được

### Requirement: Giữ ranh giới quyền riêng tư của project cục bộ
Việc gán project SHALL NOT đổi chế độ Restricted hoặc Cloud Allowed của cuộc họp. Ứng dụng MUST NOT suy ra sự đồng ý gửi nội dung từ việc cuộc họp thuộc project.

#### Scenario: Cuộc họp Restricted được gán vào project
- **WHEN** người dùng gán cuộc họp Restricted vào project đang có cuộc họp Cloud Allowed
- **THEN** cuộc họp đó vẫn Restricted và không thao tác project nào gửi nội dung của nó tới provider
