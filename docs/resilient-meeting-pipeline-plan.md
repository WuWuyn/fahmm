# Kế hoạch xử lý luồng họp bền vững

Ngày lập: 2026-11-23. Cơ sở: `main` tại `58ec29d`, kết quả kiểm thử cục bộ và `D:/REVIEW_AND_STREAMING_PLAN.md`. Thực hiện theo P0 → P1 → P2; mỗi mục chỉ hoàn thành khi có bằng chứng đạt tiêu chí bên dưới. Đây là kế hoạch phát triển, không phải xác nhận phát hành.

Ở baseline đã có `think: false`, lựa chọn biên bản trích xuất nhanh và cấu hình ASR CPU/CUDA thử nghiệm. Phiên âm chỉ chạy sau ghi âm; tiến độ biên bản AI và các đoạn ASR đang chạy chưa được lưu bền vững. Lần thử biên bản AI trên bản chép tổng hợp 70 phút dừng ở 34,5% do thiếu RAM; chưa chứng minh được hoàn thành trên máy đích. Tệp tổng hợp lặp một giọng không chứng minh độ chính xác họp thực tế.

Trong nhánh phát triển, checkpoint/hủy biên bản và lõi live ASR đã được triển khai để thử; live đang được nối giao diện với nhãn thử nghiệm, lưu cả giả thuyết chưa chắc chắn và chưa tự tạo transcript hoàn chỉnh. Chưa coi P0.3 hoặc P2 hoàn tất khi chưa kiểm tra live dài, hai nguồn thực và bản đóng gói trên Windows sạch. Các giới hạn và số đo Qwen được mô tả tại `docs/local-ai-metrics.md`; quy trình ASR tại `docs/asr-benchmark.md`.

## P0.1 — Checkpoint biên bản AI

1. Tạo checkpoint cục bộ có phiên bản, ghi nguyên tử sau từng phần đã xử lý và từng bước gộp: phần còn chờ, các tóm tắt/kết quả trung gian, nguồn trích dẫn, tiến độ, trạng thái và thông tin để tiếp tục. Không lưu dữ liệu họp ngoài thư mục dữ liệu cục bộ.
2. Gắn checkpoint với mã cuộc họp, bản chép đang dùng và dấu vân tay nội dung, loại cuộc họp, model/cấu hình và phiên bản xử lý. Nếu dữ liệu đầu vào đã đổi, từ chối tiếp tục checkpoint cũ và giải thích rõ; không áp kết quả cũ sang bản chép khác.
3. Sau khởi động lại hoặc lỗi, cho tiếp tục từ bước đã lưu; các bước chưa commit có thể chạy lại. Bảo toàn bản biên bản đang chọn cho đến khi bản mới hoàn tất; không tạo bản hoàn tất trùng do xử lý lại.
4. Kiểm thử ngắt ở các ranh giới xử lý/gộp/ghi, tiếp tục và so sánh nguồn trích dẫn, thay bản chép/model/cấu hình, file hỏng và thao tác đồng thời. Kiểm tra quyền riêng tư và khôi phục sau khi tiến trình bị kết thúc thật.

## P0.2 — Giới hạn thời gian và hủy tạo biên bản

1. Thêm ngân sách cho mỗi lần bắt đầu hoặc chủ động tiếp tục: tối đa 3.600 giây, 80 lượt xử lý model (tối đa hai HTTP/lượt), 64 lần chia nhỏ và giới hạn kích thước stream; công bố lý do khi chạm giới hạn. Ngân sách được đặt lại khi người dùng chủ động tiếp tục, không phải giới hạn cộng dồn qua nhiều lần tiếp tục. Giới hạn thời gian bao gồm đợi kết nối/đọc, không chỉ thời gian giữa các token.
2. Thêm Cancel qua bridge và giao diện; kiểm tra hủy trước/sau từng lượt, dừng hoặc ngắt request đang chờ trong thời gian hữu hạn, không cho tiến trình cũ ghi thành công sau khi đã hủy. Không dừng Ollama hay tác vụ khác của người dùng.
3. Lưu checkpoint tại ranh giới an toàn, phân biệt trạng thái đang hủy, đã hủy, quá thời hạn và lỗi; cho tiếp tục khi đầu vào còn phù hợp. Biên bản trích xuất nhanh vẫn là lựa chọn riêng, không tự đổi loại khi AI lỗi.
4. Kiểm thử request không trả dữ liệu, stream kéo dài, nhiều lần chia nhỏ, hủy trong lúc đọc và ngay trước khi lưu, lệnh hủy lặp, chạy lại và cạnh tranh trạng thái.

## P0.3 — Live ASR và checkpoint transcript

1. Thiết kế schema checkpoint có phiên bản và transaction: run/model/revision, watermark theo nguồn và các đoạn đã xác nhận với ID ổn định, timestamp theo trục audio gốc. Một lease/lock ngăn hai worker cùng tiếp tục; bản transcript cũ không đổi cho đến khi run mới hoàn tất.
2. Thêm worker riêng giữ model đã nạp, chỉ đọc WAV từng nguồn đã đóng và commit; ghép theo offset, chờ nguồn trễ có giới hạn, ghi nhận gap/overlap và xử lý pause/resume. Downmix/resample chỉ trên bản đệm làm việc, không sửa audio gốc. Dùng cửa sổ thử nghiệm 10–25 giây có overlap; phân biệt tạm thời/đã xác nhận và khử trùng lặp trước commit.
3. Hàng đợi thông báo bounded, không chặn capture. File đã commit là nguồn sự thật: khi hàng đợi đầy hoặc mất thông báo, quét phần chưa xử lý tăng dần; hiển thị backlog và xử lý phần còn thiếu sau Stop. Không quét/giải mã lại toàn bộ lịch sử liên tục.
   Worker thử nghiệm dùng một model worker với 1–4 CPU threads (`FAHMM_LIVE_CPU_THREADS`), lưu số thread trong cấu hình checkpoint và cố gắng hạ ưu tiên tiến trình. Đây chưa phải bằng chứng capture không bị trễ; vẫn cần đo trên máy đích.
4. Bổ sung bridge và UI start/status/cancel/resume, hiển thị độ trễ và trạng thái phần đã lưu. Khi hoàn tất, tạo original/working transcript tương thích và chỉ chọn run sau khi commit thành công. Tránh chạy model LLM nặng đồng thời với ASR theo mặc định.
5. Kiểm thử hai nguồn lệch, im lặng/gap, overlap, pause/resume/stop, thiết bị mất kết nối, queue đầy, ASR chậm hoặc bị kill, đĩa đầy, khởi động lại và resume nhiều lần. Đối chiếu timestamp seek, không trùng/mất đoạn đã commit, audio đã commit và transcript cũ được bảo toàn.
   Khi Pause/Stop xảy ra trong `stream.read()`, giữ phần mẫu thuộc trước ranh giới và không ghi phần sau ranh giới; kiểm tra cả trường hợp Pause rồi Resume trước khi read trả về. Giới hạn sai số mapping đồng hồ/thiết bị phải được nêu trong kết quả thử thực tế.
6. Đo và công bố giới hạn mất dữ liệu của phần audio đang ở bộ đệm chưa được hệ điều hành ghi bền vững; không tuyên bố không mất tuyệt đối khi máy mất điện. Chỉ chấp nhận live 70 phút sau thử wall-clock và họp hai nguồn thực tế.

## P1.1 — Tối ưu JSON và lượt gọi Qwen

1. Đo riêng số request, token đầu vào/đầu ra khi có, thời gian từng pha, split/retry, RAM/VRAM và thời gian tới bản nháp; không ghi nội dung riêng tư vào log hiệu năng.
2. Sau khi có checkpoint/giới hạn, thử schema và prompt nhỏ hơn, gom/gộp có giới hạn dựa trên bằng chứng; giữ citation IDs, loại thông tin và phân biệt đề xuất/quyết định. So sánh tính đầy đủ và nguồn trích dẫn với baseline, không xóa chi tiết chỉ để đạt tốc độ.
   - Thử wire JSON dùng khóa ngắn theo chế độ opt-in, ánh xạ ngược xác định sang đầy đủ các trường hiện có; mode/schema phải tham gia fingerprint checkpoint. Giữ mặc định cũ đến khi A/B trên cùng model và transcript được kiểm tra cho thấy chất lượng và tốc độ đạt yêu cầu.
3. Chạy 70 phút trên máy đích với input và model ghi rõ, theo dõi giới hạn RAM/VRAM; ghi kết quả thành công/thất bại, thời gian và các phần chưa đạt. Tổng hợp một giọng không thay cho kiểm thử họp thực.

## P1.2 — Benchmark ASR Base/Small

1. Tạo runner dùng cùng audio, cấu hình và transcript chuẩn; chạy Base/Small CPU int8, beam 1/5 và các biến thể GPU chỉ khi đủ điều kiện. Ghi phiên bản model/revision, thời gian, real-time factor, RAM/VRAM, số đoạn và lỗi.
2. Tính WER/CER với quy tắc chuẩn hóa Việt–Anh có thể tái lập; kiểm tra riêng tên, con số và thuật ngữ. Không công bố WER khi thiếu transcript chuẩn hoặc audio chưa được phép sử dụng.
3. Thử audio dài và audio họp hai nguồn được phép; ghi rõ độ dài, đặc điểm tiếng nói và hạn chế mẫu. Chọn cấu hình theo tốc độ **và** độ chính xác, không giả định beam thấp hay model nhỏ cho kết quả tương đương.

## P1.3 — Môi trường CUDA

1. Kiểm tra driver, khả năng truy cập GPU, phiên bản CTranslate2/CUDA/cuDNN và DLL cần thiết; `nvidia-smi` một mình không chứng minh inference chạy. CPU int8 vẫn là mặc định.
2. Phân loại lỗi GPU an toàn, không lộ đường dẫn riêng tư: DLL thiếu/không tương thích, driver, VRAM không đủ và worker crash. Đưa thông báo rõ qua bridge/UI; không tự fallback âm thầm sang CPU.
3. Kiểm thử các lỗi trên bằng dữ liệu giả; chỉ đánh dấu GPU hoạt động sau inference thật, có model, device/compute type và VRAM ghi nhận. Không tự cài hay thay DLL hệ thống của người dùng.

## P2 — Kiểm thử thực tế và đóng gói

Luồng ưu tiên cho bản cài thử: ghi hai nguồn → mở đúng cuộc họp → phiên âm và xuất transcript → tạo một biên bản đang chọn → chỉnh bằng các nút, lưu và xuất. Kiểm thử thêm Preview, chuyển tab/cuộc họp, chỉnh transcript và biên bản đồng thời để không làm mất phần chưa lưu; lịch sử phiên bản vẫn được giữ bên trong.

1. Chạy toàn bộ kiểm thử Python/Ruff, frontend/typecheck/build, Rust và protocol trên revision cuối; kiểm thử đầu-cuối với audio được phép, hai nguồn và crash/recovery.
2. Kiểm tra privacy: dữ liệu họp hạn chế không được gửi ra ngoài nếu chưa preview/đồng ý; kiểm thử xuất, xóa và khởi động lại. Kiểm tra cài đặt/chạy offline trên Windows 10/11 sạch không có Python/FFmpeg/model sẵn, và quá trình cài hoặc dùng model.
3. Hoàn thành rà soát license/notice cho mã và binary native, gồm FFmpeg/libx264/libx265/CTranslate2/CUDA theo dependency và hash thực tế. Giữ trạng thái chặn phát hành nếu chưa có kết luận pháp lý/native.
4. Sau khi các cổng trên đạt, build host và sidecar cùng revision, ghi phiên bản/phụ thuộc/SHA256 và kiểm tra gói trên máy sạch. EXE thử cục bộ trước thời điểm đó phải được ghi rõ là bản thử, không phải bản phát hành.
