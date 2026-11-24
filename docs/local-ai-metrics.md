# Đo tác vụ biên bản AI cục bộ

Mỗi lần bắt đầu hoặc chủ động tiếp tục tạo biên bản AI là một job riêng. Khi có thể ghi đĩa, FAHMM lưu thống kê tại:

`%LOCALAPPDATA%\fahmm\meetings\<meeting-id>\minutes\ai-metrics\<job-id>.json`

`job-id` được trả về bởi `minutes.generateLocalStart` hoặc `minutes.resumeLocalStart`. File thống kê không chứa prompt, bản phiên âm, nội dung phản hồi hay lỗi chi tiết. Nó có thời điểm chạy, tên và digest model nếu hợp lệ, trạng thái và các số đo; đây vẫn là metadata cục bộ liên quan đến cuộc họp. Xóa cuộc họp sẽ xóa các file này. Nếu không ghi được thống kê, tác vụ vẫn tiếp tục và có thể không có file thống kê.

- `state` là trạng thái cuối của lần chạy; `running` trong file sau khi ứng dụng bị dừng bất ngờ không chứng minh job còn chạy hay đã hoàn thành. `wall_seconds` chỉ có sau khi lần chạy kết thúc bình thường, kể cả hủy hoặc lỗi.
- `wire_mode` là `full` hoặc `compact` cho thử nghiệm form; không suy ra chất lượng hay tốc độ chỉ từ chế độ này.
- `model_calls` đếm lượt gọi xử lý cấp ứng dụng; mỗi lượt có tối đa hai lần thử HTTP nếu JSON lần đầu không hợp lệ. `reduce_calls` là số lượt trong pha gộp.
- `post_attempts` đếm tín hiệu bắt đầu thử POST `/api/chat` mà tiến trình giám sát đã nhận trước khi mở request. Đây không phải số request chắc chắn được server nhận. Khi `post_count_complete` là `false`, số thực sự đã mở là không rõ: tín hiệu có thể bị mất, hoặc tác vụ bị dừng giữa tín hiệu và request. GET kiểm tra digest model không được tính.
- `http_json_retries` đếm POST thứ hai của cùng một lượt do JSON lần đầu không hợp lệ; `validation_retries` đếm yêu cầu thử lại do nội dung hoặc dẫn nguồn không đạt kiểm tra ứng dụng. `split_attempts` đếm lần chia do lỗi giới hạn hoặc kiểm tra nội dung trong từng pha; không tính việc chia sẵn một segment quá dài trước request.
- `posts` có một mục cho mỗi POST đã ghi nhận. `state: interrupted` nghĩa là chưa nhận được kết thúc đầy đủ; `wall_seconds`, `done_reason` và các trường token/thời gian có thể là `null`. `null` là chưa biết, không phải số 0. Chỉ các `done_reason` đã nhận diện (`stop`, `length`, `load`, `unload`) được lưu.
- `prompt_eval_count`, `prompt_eval_cached_count`, `eval_count` và các trường `*_duration_ns` chỉ được ghi nếu Ollama trả về số nguyên hợp lệ trong chunk kết thúc. Các thời lượng này là nanosecond theo [tài liệu sử dụng Ollama](https://github.com/ollama/ollama/blob/main/docs/api/usage.mdx); `wall_seconds` là thời gian đồng hồ do FAHMM đo, gồm chờ request và đọc stream. Không tự cộng `null` thành 0 khi tính tổng hoặc tốc độ.
- Một lần tiếp tục có file và ngân sách thời gian/lượt gọi mới; muốn phân tích toàn bộ công việc phải xem các job liên quan. Không thể khôi phục số liệu của bước đã chạy trước khi tính năng đo được bật.

Các giới hạn hiện tại cho **mỗi** lần Start/Resume là một giờ, 80 lượt gọi cấp ứng dụng (tối đa 160 POST), 64 lần chia do lỗi và 300 giây cho mỗi request được giám sát. Các phép đo giả lập xác minh cách ghi nhận, không chứng minh một cuộc họp 70 phút đã hoàn thành hay chất lượng biên bản.

Ứng viên thử tiếp theo là rút gọn các trường form gửi Qwen cho từng phần. Trước khi bật, chạy A/B cùng audio và transcript được phép, model và máy giống nhau; so sánh thời gian, số POST, ý bị bỏ sót, người phụ trách, số liệu và nguồn trích dẫn với bản chuẩn đã được người kiểm tra. Chưa có bằng chứng đó nên schema và prompt mặc định chưa thay đổi.
