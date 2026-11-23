# Báo cáo cục bộ trong fahmm

Mở **Báo cáo** trên thanh điều hướng. Thêm từng tệp PDF, DOCX, XLSX, TXT hoặc Markdown bằng hộp thoại Windows; cũng có thể chọn một cuộc họp và thêm bản phiên âm đã lưu. Chọn một trong ba model, nhấn **Tạo báo cáo**, kiểm tra nội dung và cảnh báo, rồi chọn **Xuất báo cáo**. Chọn thư mục chưa chứa bốn tệp `Bao_Cao.docx`, `Bao_Cao.md`, `Ket_Qua.json` và `Bang_Tong_Hop.xlsx`; ứng dụng không ghi đè chúng.

Mục **Mô hình** có bảng so sánh Lite, Standard và Pro; mục **Báo cáo** hiển thị tóm tắt cho model đang chọn. Các số tốc độ và số dữ kiện là từ lượt thử bản mẫu với một báo cáo ngắn, không phải điểm chính xác hay kết luận về chất lượng tổng quát.

Các tài liệu và phiên âm chỉ được gửi đến Ollama trên `127.0.0.1:11435`. Các model được chạy tuần tự trên CPU, context 4.096. Mặc định dịch vụ dùng kho trước đây tại `D:\fahm\ReportAI_Local_Test\models` nếu tồn tại; nếu không, dùng `%LOCALAPPDATA%\fahmm\report-models`. Có thể đặt `FAHMM_REPORT_MODEL_DIR` trước khi chạy ứng dụng để chọn kho khác. Không thay đổi kho Ollama mặc định. Nếu model chưa tải, chọn model và nhấn **Tải model đã chọn**; cần Internet và tối thiểu 12 GiB trống trên ổ chứa kho model. Các model không được nhúng vào EXE.

Quá trình chỉ giữ dữ kiện nếu giá trị và trích dẫn khớp nguyên văn với đoạn nguồn. Quy tắc này không chứng minh ý nghĩa hoặc loại trường đúng; luôn đối chiếu thủ công. Tài liệu được chia theo ký tự và xử lý từng đoạn. Có thể hủy sau đoạn đang xử lý. Các giá trị khác nhau được đánh dấu để kiểm tra, không tự khẳng định là mâu thuẫn. Bản phiên âm có tên nguồn và các mốc thời gian trong dữ liệu đầu vào; mốc thời gian chỉ hiện trong trích dẫn khi model chọn kèm mốc đó.

Đây là bản thử nghiệm: form cố định, ghi chú form được kèm vào đầu báo cáo chứ chưa tạo bố cục động; chưa có OCR hoặc tổng hợp ngữ nghĩa nhiều tầng. PDF scan không trích được chữ cần OCR trước. DOCX không xác định số trang; Excel lưu tên sheet và khoảng dòng. Khi thiếu RAM, đóng bớt ứng dụng và thử lại. Nếu Ollama mặc định đang chạy model khác, giải phóng model đó trước khi tạo báo cáo. Không dùng báo cáo chưa rà soát cho quyết định quan trọng.
