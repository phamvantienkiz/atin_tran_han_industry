# Phase 0 — Decode & Preprocess Benchmark (`bench_decode.py`)

- **Thời điểm**: `2026-11-20T01:42:24.754877+00:00`
- **AI_IMGSZ**: `640`
- **Nguồn ảnh mẫu**: `poc/data/bench/samples/`

| Chế độ | Độ phân giải sau giải mã | Decode p50 / p95 (ms) | Preprocess p50 / p95 (ms) | Tổng p50 / p95 (ms) | Đạt width ≥ imgsz |
| :--- | :---: | :---: | :---: | :---: | :---: |
| IMREAD_COLOR (k=1) | 1920x1080 | 9.087 / 10.657 | 2.605 / 3.272 | 11.853 / 13.762 | ✅ |
| IMREAD_REDUCED_COLOR_2 (k=2) | 960x540 | 7.132 / 13.773 | 5.34 / 12.143 | 12.364 / 25.286 | ✅ |
| IMREAD_REDUCED_COLOR_4 (k=4) | 480x270 | 5.78 / 9.51 | 6.007 / 12.525 | 11.784 / 21.267 | ❌ |

## Ước tính tải CPU cho 4 camera (theo phương án khuyến nghị)
- **Khuyến nghị `AI_DECODE_REDUCE`**: `k=2` (`IMREAD_REDUCED_COLOR_2 (k=2)`, tổng p95 = `25.286 ms/khung`)
- **Quyết định Phase 5 (nvJPEG)**: `CÂN NHẮC nvJPEG (> 10 ms/khung)`

| FPS mục tiêu / cam | Tổng khung / giây (4 cam) | Thời gian CPU ước tính (p50 ms/s) | Thời gian CPU ước tính (p95 ms/s) |
| :---: | :---: | :---: | :---: |
| 12 | 48 | 593.5 | 1213.7 |
| 15 | 60 | 741.8 | 1517.2 |
| 20 | 80 | 989.1 | 2022.9 |
| 25 | 100 | 1236.4 | 2528.6 |
