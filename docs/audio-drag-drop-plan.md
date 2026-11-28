# Kế hoạch kéo thả âm thanh vào cuộc họp

1. Giữ nút **Nhập âm thanh** và thêm vùng thả cạnh nút trong danh sách cuộc họp; hiển thị trạng thái kéo, định dạng hỗ trợ, trạng thái đang nhập và lỗi rõ ràng. Nút vẫn thao tác được bằng bàn phím.
2. Nhận sự kiện kéo thả gốc từ Tauri trên cửa sổ chính, chỉ xử lý khi thả trong vùng nhập ở trang Cuộc họp. Mỗi lần nhận đúng một tệp WAV, MP3, M4A hoặc FLAC; không nhập thư mục hay nhiều tệp. Từ chối các thao tác khi backend chưa sẵn sàng hoặc đang nhập.
3. Đường dẫn phải đến từ sự kiện thả gốc của hệ điều hành: host giữ tạm tệp đã thả, lệnh nhập chỉ nhận mã một lần và không cho webview tự chọn đường dẫn tùy ý. Lưu ý tọa độ vật lý và tỷ lệ DPI; loại bỏ thao tác thả ngoài vùng, mã hết hạn hoặc đã dùng.
4. Dùng cùng quy trình nhập và mở cuộc họp hiện tại; nếu có bản nháp transcript/biên bản chưa lưu, hỏi trước khi chuyển, bảo toàn khi từ chối hoặc nhập lỗi. Không gửi âm thanh ra ngoài.
5. Kiểm thử phép cấp và dùng mã, thả ngoài vùng, DPI, tệp không hợp lệ/nhiều tệp, backend bận, hủy bảo vệ bản nháp, lỗi import và truy cập bằng nút. Kiểm thử Windows kéo tệp từ Explorer trên bản desktop đóng gói khi môi trường cho phép; kiểm tra giao diện sáng/tối và không ghi đè tệp cài trước.
