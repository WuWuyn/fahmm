# Design

## Context

Xem [proposal.md](proposal.md) và [capability quản lý action](specs/action-item-management/spec.md). `offline_minutes.py` hiện đặt `actions` bên trong mỗi phiên bản biên bản; `minutes_store.py` giữ các phiên bản và tham chiếu tới transcript nguồn. Màn hình Meetings hiện tại của Tauri hiển thị biên bản dạng Markdown và có các tab Transcript, Minutes. `MeetingStore` đã điều phối hoạt động theo cuộc họp và kiểm soát việc xóa.

## Goals / Non-Goals

**Mục tiêu:**

- Tách danh tính và trạng thái action khỏi phiên bản biên bản nhưng vẫn giữ đường dẫn có thể kiểm chứng tới transcript và audio được dẫn nguồn.
- Lưu các lần sửa và lịch sử một cách nguyên tử trong thư mục cuộc họp hiện có, không cần tài khoản hay đường truyền mạng mới.
- Giúp người dùng phân biệt đề xuất chưa xác nhận với công việc đã cam kết.

**Ngoài phạm vi:**

- Không tự suy đoán người phụ trách, không có danh bạ người dùng, thông báo, dịch vụ task bên ngoài hay chuyển action sang cuộc họp khác.
- Change này không có bảng action toàn project; change project cục bộ tiếp theo sẽ dùng các action đã xác nhận.

## Decisions

1. **Lưu một bản ghi action có phiên bản cho mỗi ID trong cuộc họp.** Bản ghi `actions/<action-id>.json` gồm `schema_version`, `id`, `meeting_id`, mảng nguồn run/segment/timestamp đã lưu, `minutes_version_id` gốc, nội dung task, người phụ trách dạng văn bản tự do tùy chọn, ngày ISO tùy chọn, trạng thái rà soát, trạng thái thực hiện, cờ lưu trữ, revision và các snapshot sự kiện chỉ được thêm vào. Ghi toàn bộ bản ghi mới vào file tạm, flush rồi thay thế nguyên tử file cũ dưới activity gate của cuộc họp. Lưu action trong biên bản sẽ khiến việc tạo lại biên bản ghi đè trạng thái theo dõi; cơ sở dữ liệu chưa cần thiết cho phiên bản đầu chỉ theo từng cuộc họp.
2. **Chỉ chuyển đề xuất đã lưu và có dẫn nguồn thành action.** Bridge kiểm tra phiên bản biên bản bất biến đã chọn và chỉ số action trong đó, đối chiếu segment được dẫn với transcript run đã lưu và tạo origin key ổn định từ ID phiên bản biên bản cộng chỉ số action. Bấm lặp lại sẽ trả action hiện có. Action mới ban đầu chưa được xác nhận và chưa có trạng thái thực hiện; chỉ khi xác nhận rõ ràng mới đặt `todo`. Tự động chuyển đổi có thể khiến bản nháp trích xuất hoặc provider còn nhiễu trông như đã được phê duyệt.
3. **Coi người phụ trách là văn bản và hạn là ngày trên lịch.** Chưa có danh bạ hay hệ thống thông báo theo múi giờ. Người dùng có thể sửa cả hai trước khi xác nhận. Ứng dụng không đoán người phụ trách hoặc ngày còn thiếu; `Chưa rõ` trong biên bản được ánh xạ thành trường tùy chọn để trống. Tạo thực thể người dùng lúc này sẽ ràng buộc change với tài khoản nhóm trong tương lai.
4. **Dùng cập nhật có kiểm soát và lịch sử sự kiện.** Mỗi lần cập nhật kèm revision được đọc gần nhất; dịch vụ từ chối ghi khi revision đã cũ, tăng revision và thêm sự kiện gồm thời gian UTC, trường thay đổi và giá trị sau thay đổi. Lưu trữ là trạng thái hiển thị của bản ghi và vẫn giữ bằng chứng. Cập nhật kiểu ghi sau thắng mà không kiểm tra có thể âm thầm làm mất chỉnh sửa hoặc lịch sử.
5. **Thêm tab Action Items ở cấp cuộc họp.** Tab tách action chưa xác nhận, action đã xác nhận còn hoạt động, đã hoàn thành và đã lưu trữ. Điều khiển Create action cạnh đề xuất biên bản đã lưu sẽ mở form rà soát. Điều hướng nguồn chọn transcript run đã lưu rồi seek bằng audio player cục bộ hiện có; không tạo đường dẫn media mới. Chỉ sửa Markdown sẽ khiến trạng thái task khó truy cập ở màn hình project sau này.

## Risks / Trade-offs

- [Bản nháp trích xuất hoặc provider gợi ý task không có căn cứ] → Yêu cầu nguồn đã lưu hợp lệ và xác nhận của người dùng; hiển thị nguồn trước khi chuyển thành action.
- [Người dùng bấm cùng đề xuất hai lần hoặc thử lại sau khi mất phản hồi] → Áp dụng origin key tại ranh giới dịch vụ và trả về ID action hiện có.
- [Transcript được chạy ASR lại hoặc biên bản được tạo lại] → Giữ ID run và phiên bản bất biến trong mỗi action; không chuyển tham chiếu nguồn sang run đang hoạt động mới.
- [Một cuộc họp bị xóa] → Action của nó bị xóa cùng thư mục cuộc họp đã được bảo vệ; bản xuất bên ngoài vẫn nằm ngoài quyền kiểm soát của ứng dụng.
- [Ghi bị gián đoạn hoặc có cập nhật đồng thời] → Thay thế nguyên tử giữ revision đã commit gần nhất; cập nhật dùng revision cũ trả lỗi xung đột có thể thử lại, không làm mất lịch sử.

## Migration Plan

Các cuộc họp hiện có không có thư mục `actions` và sẽ hiển thị danh sách action rỗng. File biên bản và transcript không được ghi lại; người dùng tự chọn chuyển đề xuất thành action. Phiên bản ứng dụng cũ bỏ qua bản ghi action mới, nên rollback vẫn giữ file nhưng không hiển thị chức năng theo dõi task. Xóa cuộc họp tiếp tục xóa toàn bộ nội dung do ứng dụng quản lý trong thư mục đó.
