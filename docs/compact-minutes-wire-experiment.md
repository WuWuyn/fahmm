# Thử nghiệm JSON ngắn cho biên bản AI

Đây là thử nghiệm opt-in, chưa phải cấu hình khuyến nghị. Mặc định `full` giữ schema và prompt hiện tại. Để thử chế độ `compact` trên một tiến trình sidecar mới, đặt biến môi trường trước khi chạy:

```powershell
$env:FAHMM_LLM_WIRE_FORMAT = 'compact'
# Chạy sidecar hoặc ứng dụng từ chính phiên PowerShell này.
```

Đặt `full` hoặc bỏ biến để trở lại mặc định. Các giá trị khác bị từ chối. Chế độ được chốt khi bắt đầu job và được ghi vào file thống kê của job. Việc đổi biến không thay đổi tiến trình đã khởi động bằng môi trường khác.

Trong form của cuộc họp loại `general`, khóa ngắn ánh xạ hai chiều sang toàn bộ trường gốc: `s=summary`, `r=source_ids`, `i=items`; trong từng item, `c=section`, `l=label`, `t=text`, `m=method`, `d=data_source`, `q=open_point`, `o=owner`, `u=due_date`, `r=source_ids`. Tám mã section được định nghĩa cố định trong mã nguồn. Tất cả trường có mặt, thứ tự và các ID nguồn trong mỗi item đều được giữ khi giải mã; trường phụ vắng mặt được hiển thị là “Chưa rõ” theo hợp đồng biên bản hiện tại. Trường phụ rỗng, khóa lạ, mã section lạ, ID sai hoặc trùng khóa JSON bị từ chối, không tự suy đoán. Không có chuyển sang `full` âm thầm khi lỗi.

Pha gộp tóm tắt vẫn dùng schema cũ: nguồn được mô hình lựa chọn và cơ chế gộp hiện tại giới hạn số nguồn của tóm tắt. Việc giữ nguyên các ID mà model trả về trong từng item không chứng minh model đã chọn đủ dữ kiện hoặc đủ nguồn.

Checkpoint `full` cũ vẫn dùng được ở chế độ `full`. Fingerprint của checkpoint `compact` bao gồm mode, schema và bảng ánh xạ; không thể tiếp tục chéo hai chế độ. Nếu muốn bắt đầu chế độ khác, chỉ xóa checkpoint cũ sau khi đã quyết định không tiếp tục tiến độ đó. Các bản biên bản đã hoàn thành không bị xóa bởi thao tác xóa checkpoint.

## Cách so sánh A/B trước khi đổi mặc định

1. Dùng cùng transcript được phép sử dụng, cùng meeting type, phiên bản/digest model và máy đích; chạy `full` và `compact` trong các job riêng. Chỉ so sánh các lần chạy đã hoàn tất, đồng thời ghi cả lỗi, số lần tách và retry.
2. Đọc hai file thống kê `ai-metrics/<job-id>.json`: `wire_mode`, tổng thời gian, POST, token đầu vào/đầu ra, thời gian model và `done_reason`; các giá trị thiếu là không rõ. Đo RAM/VRAM riêng trên cùng điều kiện. Độ dài JSON theo byte không chứng minh số token hay tốc độ.
3. Đối chiếu từng section, ý, người phụ trách, thời hạn, số liệu và tất cả nguồn trong item với transcript và bản chuẩn được người kiểm tra. Đánh giá cả ý bị bỏ sót, nguồn sai, dữ kiện suy diễn và việc phân biệt đề xuất với quyết định; không chỉ so số lượng item.
4. Lặp thử với dữ liệu và giọng nói đại diện, rồi thử cuộc họp 70 phút trên máy mục tiêu. Không bật mặc định nếu chưa đạt đồng thời độ chính xác, nguồn và hiệu năng cần thiết.

Unit test và server Ollama giả xác nhận ánh xạ và cách từ chối dữ liệu sai. Chúng không đo tốc độ Qwen, không chứng minh chất lượng ngữ nghĩa hoặc hoàn thành cuộc họp 70 phút.
