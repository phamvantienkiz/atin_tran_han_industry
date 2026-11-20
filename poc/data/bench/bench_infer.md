# Phase 0 — GPU Inference Benchmark (`bench_infer.py`)

- **Thời điểm**: `2026-11-20T01:43:52.475425+00:00`
- **ORT Providers khả dụng**: `['TensorrtExecutionProvider', 'CUDAExecutionProvider', 'CPUExecutionProvider']`
- **VRAM limit**: `1536 MB`
- **VRAM trước khi chạy**: `1421 / 4094 MB`

| Model | Chiến lược | cuDNN Search | Số cam | Provider | Nhóm p50 / p95 (ms) | TB/cam (ms) | FPS AI tối đa/cam | VRAM (MB) | Lỗi |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| yolo26s.onnx | S1 | HEURISTIC | 1 | CUDAExecutionProvider | 67.19 / 74.21 | 67.19 | 14.9 | 1622 | - |
| yolo26s.onnx | S1 | HEURISTIC | 4 | CUDAExecutionProvider | 255.11 / 274.63 | 63.78 | 3.9 | 1622 | - |
| yolo26s.onnx | S2 | HEURISTIC | 4 | CUDAExecutionProvider | 295.63 / 324.26 | 73.91 | 3.4 | 2584 | - |
| yolo26s.onnx | S3 | HEURISTIC | 4 | CUDAExecutionProvider | 212.38 / 232.74 | 53.09 | 4.7 | 2072 | - |
| yolo26s.onnx | S1 | EXHAUSTIVE | 1 | CUDAExecutionProvider | 66.05 / 71.09 | 66.05 | 15.1 | 1638 | - |
| yolo26s.onnx | S1 | EXHAUSTIVE | 4 | CUDAExecutionProvider | 247.17 / 267.9 | 61.79 | 4.0 | 1638 | - |
| yolo26s.onnx | S2 | EXHAUSTIVE | 4 | CUDAExecutionProvider | 220.21 / 239.74 | 55.05 | 4.5 | 2584 | - |
| yolo26s.onnx | S3 | EXHAUSTIVE | 4 | CUDAExecutionProvider | 212.73 / 238.57 | 53.18 | 4.7 | 2068 | - |

## Đề xuất cấu hình Phase 2 (cho 4 camera)
- **Chiến lược thắng**: `S3` + `cudnn_conv_algo_search=HEURISTIC` (`yolo26s.onnx`)
- **Nhóm 4 cam p50 / p95**: `212.38 / 232.74 ms` → **FPS AI tối đa/cam**: `4.7`

## Kiểm tra nhất quán phát hiện người

| Ảnh mẫu | Số người phát hiện |
| :--- | :---: |
| ch16/ch16_sub0_00.jpg | 15 |
| ch17/ch17_sub0_00.jpg | 15 |
| ch18/ch18_sub0_00.jpg | 6 |
| ch21/ch21_sub0_00.jpg | 3 |
