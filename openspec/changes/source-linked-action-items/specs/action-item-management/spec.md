# Spec Delta

## Purpose

Cho phép người dùng biến kết quả cuộc họp có dẫn nguồn thành công việc cục bộ được theo dõi độc lập, vẫn giữ bằng chứng và phân biệt rõ đề xuất với cam kết đã xác nhận.

## ADDED Requirements

### Requirement: Chủ động chuyển đề xuất có dẫn nguồn thành action
Ứng dụng SHALL cho phép người dùng rà soát đề xuất action trong biên bản và nguồn của nó trước khi tạo action item riêng. Ứng dụng MUST NOT âm thầm biến nội dung biên bản được tạo tự động thành công việc đã xác nhận.

#### Scenario: Tạo action từ biên bản
- **WHEN** người dùng chọn đề xuất action có dẫn nguồn, xem lại nội dung và nguồn, rồi chọn Create action
- **THEN** ứng dụng tạo action item mới liên kết với cuộc họp và nguồn đó, ban đầu được đánh dấu chưa xác nhận

#### Scenario: Đề xuất không có nguồn hợp lệ
- **WHEN** đề xuất trong biên bản không có source segment còn thuộc transcript run đã lưu của cuộc họp
- **THEN** ứng dụng từ chối tạo action có dẫn nguồn và giải thích tham chiếu nào cần được sửa

### Requirement: Giữ danh tính và nguồn gốc action bền vững
Mỗi action item SHALL có ID ổn định, ID cuộc họp gốc, một hoặc nhiều tham chiếu tới transcript run/segment đã lưu cùng timestamp, và phiên bản biên bản gốc. Việc tạo lại biên bản hoặc đổi transcript run đang hoạt động MUST NOT ghi đè action hoặc nguồn gốc của nó.

#### Scenario: Tạo lại biên bản
- **WHEN** người dùng tạo lại hoặc sửa biên bản sau khi tạo action item
- **THEN** action giữ nguyên ID, các trường đã lưu và liên kết nguồn ban đầu

#### Scenario: Mở lại nguồn
- **WHEN** người dùng mở nguồn của action từ cuộc họp
- **THEN** ứng dụng mở segment transcript được tham chiếu trong run đã lưu và đưa audio cục bộ tới timestamp được dẫn

### Requirement: Xác nhận và theo dõi công việc
Ứng dụng SHALL cho phép người dùng sửa nội dung task, người phụ trách và ngày hạn tùy chọn, đồng thời đặt trạng thái rà soát là chưa xác nhận hoặc đã xác nhận. Action đã xác nhận SHALL hỗ trợ các trạng thái thực hiện `todo`, `in_progress` và `done`, kể cả mở lại việc đã hoàn thành.

#### Scenario: Xác nhận task
- **WHEN** người dùng rà soát action chưa xác nhận, sửa các trường và xác nhận
- **THEN** ứng dụng lưu action đã xác nhận với trạng thái `todo` và hiển thị riêng khỏi đề xuất chưa xác nhận

#### Scenario: Tiến trạng thái rồi mở lại
- **WHEN** người dùng chuyển action đã xác nhận từ `todo` sang `in_progress` rồi `done`, sau đó mở lại
- **THEN** mỗi trạng thái đã chọn đều được lưu và action mở lại không còn nằm trong danh sách hoàn thành

### Requirement: Giữ lịch sử cập nhật action
Ứng dụng SHALL giữ lịch sử cục bộ theo thứ tự thời gian của các thay đổi trường, xác nhận, trạng thái và lưu trữ cho từng action mà không sửa các mục lịch sử trước đó.

#### Scenario: Xem lại chỉnh sửa sau khi khởi động lại
- **WHEN** người dùng sửa người phụ trách hoặc trạng thái, đóng ứng dụng rồi mở lại action
- **THEN** giá trị hiện tại và các mục thay đổi trước đó vẫn truy cập được

### Requirement: Lưu trữ action an toàn
Ứng dụng SHALL cho phép người dùng lưu trữ action sai hoặc không còn phù hợp sau khi xác nhận, đồng thời giữ nguồn và lịch sử để xem lại. Action đã lưu trữ SHALL không xuất hiện trong các danh sách công việc đang hoạt động.

#### Scenario: Lưu trữ task
- **WHEN** người dùng xác nhận Archive cho một task
- **THEN** task rời danh sách đang hoạt động và vẫn xem được trong danh sách lưu trữ cùng nguồn và lịch sử

### Requirement: Ngăn chuyển đề xuất thành action trùng lặp
Ứng dụng SHALL nhận diện action đã tạo từ cùng một đề xuất trong biên bản và cho phép mở action hiện có thay vì tạo thêm do bấm lặp ngoài ý muốn.

#### Scenario: Kích hoạt hai lần
- **WHEN** người dùng chọn Create action hai lần cho cùng một đề xuất
- **THEN** chỉ một action được tạo và action hiện có được hiển thị

### Requirement: Giữ công việc cục bộ và có thể khôi phục
Tạo, xem, sửa và lưu trữ action MUST hoạt động khi không có tài khoản, API key, kết nối mạng hoặc fallback lên cloud. Nếu lưu thất bại, ứng dụng MUST giữ bản action và lịch sử đã commit gần nhất ở trạng thái đọc được, đồng thời MUST báo lỗi.

#### Scenario: Cập nhật action khi offline
- **WHEN** người dùng cập nhật action đã xác nhận trong lúc không có mạng
- **THEN** thay đổi được lưu cục bộ và không có nội dung cuộc họp nào được gửi ra ngoài

#### Scenario: Lưu bị gián đoạn
- **WHEN** thao tác ghi action thất bại trước khi commit
- **THEN** ứng dụng báo lỗi và khi mở lại sẽ thấy action cùng lịch sử đã commit trước đó
