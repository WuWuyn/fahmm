# Design

## Context

Xem [proposal.md](proposal.md) để biết quyết định phát hành. Sản phẩm hiện tại là ứng dụng desktop Tauri/React với Python sidecar đóng gói kèm. `windows-recorder-m1` còn hai task cần kiểm tra trên phần cứng thật; `release-export-cleanup-m4` còn các task về máy sạch, giấy phép, tài liệu và quy trình đóng gói. `docs/m1-verification.md`, `docs/m4-verification.md` và `docs/tauri-verification.md` ghi nhận bằng chứng có kiểm soát trên máy phát triển; chưa tài liệu nào chứng minh v1 đã được nghiệm thu đầy đủ.

## Goals / Non-Goals

**Mục tiêu:**

- Dùng một bản Tauri ứng viên có phiên bản và có thể tái lập cho mọi kiểm tra cuối cùng; lưu kết quả đạt/không đạt cho từng tiêu chí nghiệm thu mà không lưu nội dung cuộc họp.
- Tách biệt bằng chứng về độ nghe rõ trên thiết bị, chất lượng phiên âm, đóng gói trên máy sạch, quyền riêng tư và quyền phân phối, để kết quả của nhóm này không thay thế nhóm khác.
- Chặn phát hành cho đến khi mọi điều kiện bắt buộc có bằng chứng, và mọi lỗi phát hiện đã được sửa rồi kiểm tra lại trên bản ứng viên mới.

**Ngoài phạm vi:**

- Change này không đặc tả hành vi mới cho recorder, ASR, biên bản hay cloud; lỗi thuộc các change hiện có phụ trách.
- Không đưa các tính năng P1/P2 như chỉnh gain, đổi thiết bị khi đang ghi, xuất SRT hay LLM ngữ nghĩa cục bộ vào điều kiện phát hành v1.

## Decisions

1. **Kiểm thử gói Tauri hiện tại, không dùng ZIP Qt cũ để thay thế.** Build sidecar và bản cài đặt/bản portable Tauri từ cùng một revision mã nguồn được cố định, rồi ghi hash của các artifact. Bản Qt chỉ dùng để kiểm tra rollback. Nếu chỉ chấp nhận kết quả source mode hoặc Qt thì sẽ bỏ sót ranh giới giữa host, sidecar và dependency đã đóng gói.
2. **Dùng ma trận phát hành có thông tin nguồn gốc.** Với từng mục AT-01–AT-11 và từng trường hợp giọng nói, ghi hash bản build, phiên bản Windows, phần cứng, phương pháp thử, kết quả quan sát, người phụ trách, ngày và giới hạn còn lại trong `docs/v1-release-acceptance.md`. Dẫn tới bằng chứng M1–M4 và Tauri hiện có thay vì sao chép nội dung nhạy cảm. Chỉ đánh dấu task hoàn tất dựa trên kết quả chung của bộ test sẽ làm lẫn bằng chứng phần cứng thật với bằng chứng bản đóng gói.
3. **Thử ghi âm thật khi đã được phép.** Dùng cuộc gọi Teams/Meet 20 phút được phép ghi âm với tai nghe và microphone; nghe lại cả kênh hệ thống lẫn microphone, kiểm tra trạng thái ghi và loại trừ thời gian tạm dừng. Sau đó, trong một lần ghi riêng, kết thúc đột ngột ứng dụng sau khi ít nhất một chunk đã lưu và khôi phục bản ghi. Ghi mức âm lượng và thời lượng, không ghi nội dung trao đổi. Nếu âm thanh hệ thống quá nhỏ, kiểm tra định tuyến, thiết bị đầu ra được chọn, gain hoặc adapter SoundCard. Nguồn âm thanh giả lập không chứng minh được tiếng người tham gia từ xa nghe rõ.
4. **Dùng máy Windows 10 và 11 x64 sạch.** Cài đặt hoặc giải nén đúng cùng bản ứng viên trên máy không có môi trường Python/FFmpeg phát triển. Kiểm tra tải model lần đầu theo thao tác rõ ràng, dùng lại model offline, nhập/phát audio, di chuyển theo timestamp, ASR tiếng Việt cục bộ, biên bản offline ở chế độ Restricted, xuất, xóa và không truyền dữ liệu ra ngoài. Máy phát triển đã có nhiều dependency có thể che giấu lỗi đóng gói.
5. **Chỉ phân phối khi giấy phép và hướng dẫn cài đặt đã rõ.** Lập danh mục chính xác host Tauri, sidecar, thư viện native, codec và asset thực sự có trong artifact; giải quyết nghĩa vụ phân phối và đối chiếu nội dung gói với thông báo giấy phép. Kiểm tra checksum, vị trí dữ liệu, hướng dẫn cài model đầu tiên và sử dụng offline trên bản đã cài/giải nén. Danh sách giấy phép trong source có thể bỏ sót thành phần của gói thực tế.

## Risks / Trade-offs

- [Không có cuộc họp được phép ghi âm hoặc máy Windows sạch] → Giữ điều kiện đó ở trạng thái chờ và chưa nghiệm thu v1; không dùng chạy giả lập để thay thế.
- [Âm thanh loopback hệ thống vẫn nhỏ hơn nhiều so với microphone] → Thu thập bằng chứng về thiết bị/định tuyến, sửa phần recorder phụ trách, build lại và nghe kiểm tra cả hai nguồn trên bản ứng viên mới.
- [Model hoặc provider truy cập mạng trong luồng được cho là offline] → Chặn socket trong kiểm thử Restricted trên bản đóng gói, giữ log không chứa nội dung cuộc họp và coi mọi lần truyền nội dung ra ngoài là lỗi chặn phát hành.
- [Mẫu lời nói khác nhau về tiếng ồn và vùng giọng] → Ghi nguồn gốc mẫu và lỗi quan sát riêng cho giọng Bắc, giọng Nam và tiếng Việt xen tiếng Anh; không suy rộng độ chính xác từ mẫu đọc FLEURS.
- [Bằng chứng giấy phép native chưa đầy đủ] → Không phát hành ứng viên cho đến khi thông báo và điều khoản phân phối của đúng các file đã đóng gói được giải quyết.

## Migration Plan

Không có kế hoạch chuyển đổi dữ liệu người dùng. Bản ứng viên không đạt sẽ bị giữ lại hoặc được thay bằng bản đã sửa, với cùng schema dữ liệu `%LOCALAPPDATA%\fahmm`, hash mới và lần nghiệm thu mới. Giữ gói Qt cũ làm phương án rollback có tài liệu hướng dẫn, và xác minh nó mở được cuộc họp đã lưu mà không chạy đồng thời hai ứng dụng trên cùng vùng dữ liệu.
