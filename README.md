# ESG Lab

Tool phân tích panel regression cho dữ liệu ESG. FastAPI + HTML, không cần build step.

## Yêu cầu

- Python 3.10+
- macOS / Linux / Windows

## Cài đặt

```bash
cd tools
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Chạy

```bash
python app.py
```

Mở trình duyệt: <http://127.0.0.1:8765/>

Để chạy ở port khác hoặc cho LAN truy cập:

```bash
python -m uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

## Workflow

1. **Datasets** (`/`) — Click *Upload file* để load Excel/CSV. Tool đọc cấu trúc và lưu vào `uploads/`.
2. **Dataset detail** (`/datasets/<id>`) — Xem Overview, Columns, Correlation, Preview.
3. **Merge** (`/merge`) — Chọn ≥2 dataset, set key columns (vd. `COID`, `Year`), pick strategy (inner/left/outer).
4. **Train** (`/train`) — Chọn dataset, click **Apply ESG defaults** để auto-fill config theo schema TEJ. Chỉnh `WINSORIZE_LIMITS`, base/rev lag, FE, DID nếu cần. Click **Run regression**.
5. **Run results** (`/runs/<id>`) — Forest plot, p-value heatmap, bảng coefficient theo từng model. Click **Export Excel** để xuất report.

## Cấu trúc thư mục

```
tools/
├── app.py              FastAPI routes
├── db.py               SQLite metadata
├── core/               Analysis logic (loader, profiler, pipeline, …)
├── templates/          HTML pages (Tailwind + Alpine + Plotly via CDN)
├── uploads/            File data (auto-tạo)
├── runs/               Output mỗi run (auto-tạo)
└── tool.db             SQLite (auto-tạo lần đầu chạy)
```

## Reset

Để xóa toàn bộ data và bắt đầu lại:

```bash
rm -rf uploads/* runs/* tool.db
```

## Tech stack

- **Backend**: FastAPI, Pydantic, pandas, linearmodels, scipy, openpyxl
- **Storage**: SQLite + filesystem
- **Frontend**: HTML + Tailwind CSS + Alpine.js + Plotly (tất cả qua CDN)
