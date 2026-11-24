# Benchmark ASR cục bộ

`scripts/benchmark_asr.py` so sánh các model đã cài trên cùng audio và bản chép chuẩn nếu có. Nếu bỏ `--reference`, công cụ chỉ đo tốc độ và tài nguyên, để WER/CER trống. Chỉ sử dụng dữ liệu được phép xử lý; không đưa bản chép, audio, báo cáo hoặc checkpoint cuộc họp vào Git. Không dùng transcript do model tự tạo làm chuẩn để kết luận độ chính xác.

Ví dụ trên Windows (thay đường dẫn, revision và license bằng dữ liệu thực tế):

```powershell
.venv\Scripts\python.exe scripts\benchmark_asr.py `
  --audio D:\corpus\meeting.wav --reference D:\corpus\meeting-reference.txt `
  --model 'base=D:\models\faster-whisper-base' `
  --model 'small=D:\models\faster-whisper-small' `
  --revision 'base=<revision>' --revision 'small=<revision>' `
  --corpus-label 'authorized-meeting' --corpus-license 'user-authorized' `
  --language auto --output .build\asr-comparison.jsonl
```

Mặc định chạy tuần tự CPU int8, beam 1 và 5, mỗi cấu hình trong tiến trình riêng. Có thể chọn `--beam` nhiều lần, `--device cuda` và `--gpu-metrics` để thử GPU nếu môi trường hỗ trợ. CUDA không tự chuyển sang CPU. File báo cáo phải chưa tồn tại; nếu một cấu hình lỗi hoặc dừng, công cụ dừng các cấu hình còn lại và trả mã lỗi khác 0.

Để sửa sự cố RAM từng giảm còn 76 MiB, mỗi cấu hình phải kiểm tra headroom trước khi khởi chạy; watchdog lấy mẫu RAM khả dụng theo `psutil.virtual_memory().available`, dừng ngay tại ngưỡng khẩn cấp và cũng dừng khi dưới ngưỡng cảnh báo quá thời gian cho phép. Khâu theo dõi GPU phải chạy độc lập để không làm chậm kiểm tra RAM; chỉ dừng tiến trình benchmark do script tạo, không dừng Ollama hoặc ứng dụng khác. Các ngưỡng được ghi vào báo cáo. Các test dùng mẫu RAM/tiến trình giả, không tạo tải inference. Lấy mẫu vẫn có thể bỏ sót biến động RAM giữa các lần đọc; không coi đây là bảo đảm chống hết bộ nhớ.

Mặc định cần ít nhất **5.120 MiB** RAM khả dụng trước mỗi cấu hình; sau khi chạy, dừng ngay tại hoặc dưới **1.536 MiB**, hoặc dừng nếu dưới **2.048 MiB** liên tục **5 giây**. Watchdog đọc khoảng mỗi 0,2 giây trên luồng riêng; số thực tế là giá trị thấp nhất đã lấy mẫu, không phải mức thấp nhất tuyệt đối. Có thể chỉnh `--min-start-free-mib`, `--min-free-mib`, `--emergency-free-mib` và `--grace-seconds`; giảm ngưỡng sẽ tăng rủi ro. Thời gian inference gồm nạp model và giải mã; real-time factor là thời gian inference chia thời lượng audio. RSS và CPU là số liệu lấy mẫu của tiến trình ASR; GPU là mức dùng toàn GPU, không quy hết cho FAHMM.

Script `measure_70min_resources.py` áp dụng cùng ngưỡng, không còn hạ yêu cầu RAM bằng file `allow-current-ram`. Khi cần dừng, nó chỉ dừng sidecar đã tạo và các tiến trình con quan sát được; máy chủ Ollama dùng chung không bị script tắt. Một checkpoint đang ghi dở có thể cần khôi phục khi chạy lại. Nếu Ollama dùng chung tiếp tục chiếm RAM sau khi sidecar dừng, cần xử lý Ollama riêng; script không thể bảo đảm máy tránh hết RAM khi ứng dụng khác cấp phát đột ngột.

Báo cáo JSONL chứa hash audio, bản chuẩn, các file model, revision do người chạy cung cấp, phiên bản runtime, số liệu và trạng thái; không chứa bản chép hoặc nội dung được nhận dạng. Kiểm tra nhãn corpus/license trước khi chia sẻ báo cáo. WER dùng các đơn vị tách bằng khoảng trắng sau NFKC/casefold, thay dấu câu và ký hiệu bằng khoảng trắng; với tiếng Việt các đơn vị này thường là âm tiết, không phải phân đoạn từ. CER dùng cùng chuẩn hóa và bỏ khoảng trắng. Cả hai không thay thế việc kiểm tra tên riêng, số, người phụ trách, quyết định và citation.

Kết quả từ audio tổng hợp lặp hoặc transcript không được kiểm chứng chỉ dùng thử công cụ. Để chọn Base/Small cần corpus Việt–Anh dài, transcript chuẩn được đối chiếu, cùng điều kiện chạy và kiểm tra chất lượng bởi người nghe.

Đối với dữ liệu công khai, `scripts/build_fleurs_benchmark.py` có thể tạo ba fixture `vi_vn`, `en_us` và `mixed` từ archive `dev.tar.gz` và `dev.tsv` của [Google FLEURS](https://huggingface.co/datasets/google/fleurs), license CC BY 4.0. Ví dụ dùng bản dữ liệu `70bb2e84b976b7e960aa89f1c648e09c59f894dd` đã tải cục bộ:

```powershell
.venv\Scripts\python.exe scripts\build_fleurs_benchmark.py D:\fleurs\data D:\benchmarks\fleurs-35x2 `
  --minutes-per-language 35 --revision 70bb2e84b976b7e960aa89f1c648e09c59f894dd
```

Script giữ nguyên từng clip và transcript của clip, chèn 0,2 giây im lặng và luân phiên ngôn ngữ ở fixture `mixed`; thời lượng có thể dài hơn mục tiêu vì không cắt clip. Đây là các câu đọc được ghép, không phải cuộc họp hai nguồn hoặc hội thoại chuyển ngôn ngữ tự nhiên. Chế độ `auto` của ASR hiện chọn ngôn ngữ cho cả tệp, nên phải ghi ngôn ngữ được nhận diện khi diễn giải kết quả mixed.
