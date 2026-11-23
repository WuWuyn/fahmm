# ReportAI Local Test

Ứng dụng thử nghiệm Windows để trích xuất dữ kiện báo cáo bằng ba model Ollama, không cần Internet sau khi đã cài thư viện và tải model. Dữ liệu tài liệu được gửi tới Ollama trên `127.0.0.1:11435` của máy này. Đây là bản thử nghiệm; luôn đối chiếu với tài liệu gốc.

## Khởi động

Mở `dist\ReportAI_Local_Test\ReportAI_Local_Test.exe`, giữ nguyên cả thư mục `dist\ReportAI_Local_Test` và vị trí dự án. Hoặc từ PowerShell:

```powershell
cd D:\fahm\ReportAI_Local_Test
.\scripts\run.ps1
```

Trong tab **Xử lý tài liệu**, thêm file, chọn model rồi bắt đầu. Tab **Kết quả** cho phép xuất Word, Markdown, JSON và Excel vào thư mục chưa có bốn file cùng tên. Tab **Benchmark** chạy lần lượt ba model trên cùng các file đang chọn. Hủy có hiệu lực sau lượt suy luận hiện tại. Có thể chọn GPU nhưng CPU là mặc định.

Ollama cần được cài riêng. Ứng dụng khởi động dịch vụ riêng nếu cổng 11435 chưa chạy, dùng kho `models` trong dự án, không thay đổi cấu hình hệ thống. Tránh dùng cổng này cho dịch vụ khác. Các model hiện có trong kho Ollama mặc định không bị xóa hay di chuyển. Nếu Ollama đặt ở vị trí khác đường dẫn cài đặt mặc định, hãy khởi động dịch vụ riêng thủ công với `OLLAMA_HOST=127.0.0.1:11435`, `OLLAMA_MODELS=<đường dẫn models>` rồi mở ứng dụng.

## Cài lại / build

```powershell
.\scripts\install.ps1
.\scripts\build_exe.ps1
.\scripts\benchmark.ps1
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Ollama: https://ollama.com/download/windows. Tải model cần Internet. Bản EXE không bao gồm model. Không xóa thư mục `models`, `.venv`, `dist` khi đang sử dụng; giữ đủ dung lượng ổ D. Bản Python cần Python 3.11+ và các gói trong `requirements.txt`.

## Phạm vi và giới hạn quan trọng

- PDF trích xuất văn bản; PDF scan không được OCR. DOCX không cung cấp số trang chính xác; XLSX ghi tên sheet và khoảng dòng. TXT/Markdown cần UTF-8.
- Chia theo khoảng 4.000 ký tự với 400 ký tự chồng lấn, không phải token chính xác. Xử lý tuần tự và schema Pydantic; câu trích dẫn phải khớp nguyên văn, nhưng sự khớp này **không chứng minh giá trị suy luận đúng nghĩa**.
- Báo cáo hiện là tập hợp dữ kiện theo các trường cố định; nội dung form tùy chỉnh được kèm trong báo cáo, chưa điều khiển thứ tự/bố cục hoặc tạo trường động. Đây chưa phải pipeline tổng hợp ngữ nghĩa nhiều tầng.
- Giá trị deadline/người phụ trách/ngày khác nhau được gắn cờ để xem xét, không tự khẳng định mâu thuẫn. Không phát hiện được mọi mâu thuẫn, dữ kiện trùng có cách diễn đạt khác, hoặc nội dung bịa dù câu trích dẫn tồn tại.
- Không thể hủy giữa một request đang chạy; giới hạn RAM là ngưỡng cảnh báo, không bảo đảm tránh hết RAM do các tiến trình khác. Dịch vụ riêng giới hạn một model, không quản lý model của các Ollama khác.
- Kết quả benchmark trong GUI đo thời gian, token/giây và số dữ kiện có nguồn; chưa tự chấm chính xác hay ảo giác. Benchmark dòng lệnh có bộ dữ liệu giả lập với một số từ khóa mong đợi; đây chỉ là phép kiểm tra thô, không thay thế đánh giá thủ công, và không công bố tỷ lệ nếu có lỗi xử lý.
- Không xử lý toàn diện bảng phức tạp, file mã hóa, định dạng biểu đồ, metadata, chống prompt injection trong tài liệu, hoặc chống tràn tài nguyên. Chưa phù hợp vận hành production hay tài liệu nhạy cảm cần bảo đảm kiểm soát truy cập.
