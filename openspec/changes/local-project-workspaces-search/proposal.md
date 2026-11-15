# Proposal

## Why

Thư viện hiện có thể mở lại các cuộc họp theo thứ tự thời gian, nhưng khi số bản ghi tăng lên, người dùng khó sắp xếp hoặc tìm quyết định và việc còn dang dở. Nhóm cuộc họp theo project cục bộ và tìm kiếm từ khóa giúp khai thác bằng chứng đã lưu xuyên nhiều cuộc họp mà không cần tài khoản hay đồng bộ hóa.

## What Changes

- Thêm project cá nhân lưu trên thiết bị với ID ổn định; mỗi cuộc họp được gán vào tối đa một project hoặc để ở nhóm Unassigned. Chuyển cuộc họp giữa các project mà không di chuyển hay nhân bản file của nó.
- Tìm kiếm tên cuộc họp đã lưu, transcript đã sửa, nội dung biên bản được chọn và action item đã xác nhận; hiển thị loại nguồn, cuộc họp, project và đường dẫn quay lại timestamp hoặc bản ghi khớp.
- Lọc theo project và ngày, đồng thời hiển thị các action chưa hoàn thành của project từ `source-linked-action-items`.
- Giữ index tìm kiếm có thể dựng lại từ các file cuộc họp cục bộ và registry project; cập nhật sau khi sửa, đổi project hoặc xóa.

## Capabilities

### New Capabilities

- `local-projects`: Sắp xếp các cuộc họp của một người dùng vào project cục bộ trên thiết bị, đồng thời giữ nhóm Unassigned.
- `meeting-search`: Tìm kiếm cục bộ bằng chứng cuộc họp đã lưu và action item, với kết quả có phạm vi và điều hướng về nguồn.

### Modified Capabilities

Không có. Thư viện cuộc họp hiện tại vẫn mở được các cuộc họp đã ghi hoặc nhập; hai capability này bổ sung cách tổ chức và truy xuất.

## Impact

Bổ sung registry project cục bộ, index SQLite/FTS có thể dựng lại, các thao tác bridge và điều khiển project/tìm kiếm trong khu vực Meetings của Tauri. `source-linked-action-items` là dependency chức năng để hiển thị task theo project. Workspace dùng chung, tài khoản, đồng bộ, tìm kiếm ngữ nghĩa, ngữ cảnh AI xuyên cuộc họp và hỏi đáp tri thức thuộc các change tương lai riêng.
