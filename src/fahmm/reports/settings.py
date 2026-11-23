import sys
from pathlib import Path

ROOT = Path(sys.executable).resolve().parent.parent.parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent.parent
HOST = 'http://127.0.0.1:11435'
MODELS = ['qwen3.5:2b-q4_K_M', 'qwen3:4b-instruct-2507-q4_K_M', 'qwen3.5:4b-q4_K_M']
FIELDS = {
    'ten_bao_cao': 'Tên báo cáo', 'ngay_bao_cao': 'Ngày báo cáo',
    'don_vi': 'Đơn vị/phòng ban', 'chu_de': 'Chủ đề', 'noi_dung': 'Nội dung chính',
    'ket_qua': 'Kết quả đạt được', 'chua_hoan_thanh': 'Công việc chưa hoàn thành',
    'rui_ro': 'Vấn đề/rủi ro', 'phu_trach': 'Người phụ trách',
    'deadline': 'Deadline', 'hanh_dong': 'Hành động tiếp theo',
}
DEFAULT_FORM = '\n'.join(FIELDS.values()) + '\nNguồn dữ liệu\nMức độ tin cậy/cần kiểm tra'
