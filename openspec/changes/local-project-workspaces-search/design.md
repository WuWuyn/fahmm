# Design

## Context

Xem [proposal.md](proposal.md), [local-projects](specs/local-projects/spec.md) và [meeting-search](specs/meeting-search/spec.md). `MeetingLibrary` hiện quét `%LOCALAPPDATA%\fahmm\meetings` và sắp xếp các cuộc họp đã lưu theo thời gian tạo. Metadata cuộc họp, transcript run, phiên bản biên bản và bản ghi action độc lập dự kiến vẫn lưu bằng file. `source-linked-action-items` phải có trước khi hoàn tất tổng hợp action theo project.

## Goals / Non-Goals

**Mục tiêu:**

- Thêm lớp nhóm project cho một người dùng mà không chuyển thư mục cuộc họp hiện có hoặc thay đổi quyết định quyền riêng tư theo từng cuộc họp.
- Tìm kiếm từ khóa đủ nhanh cho hàng trăm cuộc họp, trong khi file cuộc họp và phép gán project vẫn là nguồn dữ liệu chính thức, còn index có thể bỏ đi và dựng lại.
- Mở kết quả tại run, phiên bản, action và timestamp nguồn đã lưu tương ứng nếu có.

**Ngoài phạm vi:**

- Không có workspace nhóm, tài khoản, server đồng bộ, quyền chia sẻ, tìm kiếm ngữ nghĩa/vector, ngữ cảnh AI xuyên cuộc họp hay hỏi đáp tri thức.
- Không tự trích xuất quyết định hoặc task mới; tìm kiếm chỉ dùng nội dung đã lưu và action đã xác nhận.

## Decisions

1. **Biểu diễn project cục bộ bằng một cấp nhóm.** Registry project có phiên bản dưới `%LOCALAPPDATA%\fahmm`, được thay thế nguyên tử, lưu ID project ổn định, tên và ánh xạ cuộc họp → project. Cuộc họp không có phép gán thuộc nhóm Unassigned. Xóa project cập nhật một bản ghi registry và không đụng tới thư mục cuộc họp. UI gọi nhóm này là Project; thành viên của Workspace chia sẻ trong tương lai là mô hình khác. Nếu ghi ID project vào từng cuộc họp, việc xóa project sẽ trở thành giao dịch nhiều file.
2. **Dùng index SQLite FTS5 có thể dựng lại, không coi đó là nguồn dữ liệu chính thức.** Giữ audio, metadata, transcript, biên bản và action trong các file do ứng dụng quản lý. Chỉ lập index cho tên cuộc họp đã lưu, các segment đã sửa của transcript run đang được chọn, phiên bản biên bản đã lưu đang được chọn và action đã xác nhận. Lưu loại tài liệu, ID cuộc họp/nguồn, timestamp, văn bản tìm kiếm đã chuẩn hóa và đoạn trích hiển thị. Dùng truy vấn có tham số và chuẩn hóa chữ hoa/thường cùng dấu tiếng Việt, kể cả `đ`, trước khi lập index và tìm. Quét mọi file JSON sau mỗi phím gõ sẽ chậm khi thư viện lớn; chưa cần vector store cho tìm kiếm từ khóa.
3. **Đối chiếu thay đổi đã commit trước khi trả kết quả.** Chỉ cập nhật tài liệu trong index sau khi thao tác ghi nguồn tương ứng đã commit. Khi khởi động hoặc sau cập nhật bị gián đoạn, so sánh fingerprint nguồn và revision của registry với metadata của index, rồi dựng lại hoặc sửa tăng dần các mục cũ. Xóa cuộc họp sẽ xóa tài liệu index và kết quả tìm kiếm tương ứng; index có thể bỏ và dựng lại mà không sửa file nguồn. Chỉ tin callback sự kiện sẽ để lại kết quả lỗi thời sau crash.
4. **Chuyển việc tìm kiếm ra khỏi UI thread.** Python sidecar lập index và thực hiện truy vấn phân trang trong worker có giới hạn; bridge chỉ trả đoạn trích và ID nguồn opaque, không trả đường dẫn file tùy ý. Khu vực Meetings của React có bộ chọn project, điều khiển quản lý project, ô tìm kiếm, bộ lọc ngày/project, bộ lọc trạng thái action và kết quả phân trang. Khi chọn kết quả, ứng dụng đối chiếu ID với file còn tồn tại trước khi mở đúng màn hình. Chưa cần một khu vực điều hướng cấp cao mới cho lớp nhóm cục bộ đầu tiên này.
5. **Giữ quyền riêng tư theo từng cuộc họp.** Thao tác project và tìm kiếm không gửi request mạng; index nằm trong cùng ranh giới dữ liệu cục bộ của ứng dụng như nội dung cuộc họp. Gán project không đổi `privacy_mode`; request provider dùng nội dung nhiều cuộc họp trong tương lai sẽ cần thiết kế quyền riêng tư riêng. Coi thành viên project là đồng ý chia sẻ sẽ vi phạm bảo đảm Restricted hiện tại.

## Risks / Trade-offs

- [SQLite FTS5 hoặc cách tách từ Unicode khác nhau trong runtime đã đóng gói] → Kiểm tra đúng Python runtime đóng gói và các fixture tiếng Việt có/không dấu, chữ hoa/thường trên Windows sạch; giữ nguyên văn bản gốc để hiển thị.
- [Cập nhật index bị gián đoạn hoặc index bị hỏng] → Phát hiện sai lệch, bỏ hoặc sửa index dẫn xuất và giữ nguyên mọi file nguồn.
- [Phiên bản transcript hoặc biên bản cũ tạo kết quả trùng] → Chỉ lập index cho run/phiên bản đã lưu đang được chọn và cập nhật khi đổi lựa chọn; gắn ID nguồn cho từng kết quả.
- [Cuộc họp đã xóa còn sót phép gán hoặc dữ liệu index] → Dọn phép gán mồ côi và tài liệu index khi đối chiếu; không bao giờ trả kết quả từ cuộc họp không còn tồn tại.
- [Index cục bộ chứa nội dung Restricted] → Giữ index trong vùng lưu trữ cục bộ do ứng dụng quản lý, không đưa vào log/telemetry và ghi rõ change này không mã hóa dữ liệu lưu trên đĩa.
- [Nhập dữ liệu lớn hoặc hàng trăm cuộc họp làm UI chậm] → Phân trang kết quả, lập index trong worker và đo hiệu năng với ít nhất 500 cuộc họp có transcript và biên bản đã lưu.

## Migration Plan

Các cuộc họp hiện có xuất hiện trong nhóm Unassigned mà không ghi lại metadata. Chỉ tạo registry project khi có thay đổi project đầu tiên; dựng index từ file đã lưu và registry khi dùng tìm kiếm lần đầu. Phiên bản ứng dụng cũ bỏ qua các file mới này và vẫn đọc được các cuộc họp hiện có. Khi rollback, project và index vẫn trên đĩa để phiên bản sau dùng lại, nhưng UI cũ không duyệt được chúng; nội dung cuộc họp không bị chuyển hay biến đổi.
