# Datalab OCR Service

FastAPI service exposing two OCR-related endpoints:

- `POST /api/v1/ocr` - Datalab `/convert` pipeline with infographic refinement
- `POST /api/v1/text-detection` - PaddleOCRv5 text detection on a locally trained model

## 1. OCR Endpoint

### Endpoint

- **Method:** `POST`
- **URL:** `/api/v1/ocr`
- **Content-Type:** `multipart/form-data`

### Form Fields

- `files` (required): one or many image files
- `refine` (optional): `true` or `false`, default is `true`

### cURL Example

```bash
curl -X POST "http://localhost:8000/api/v1/ocr" \
  -F "files=@/absolute/path/to/image.jpg" \
  -F "refine=true"
```

### Response Format

The API returns:

- `results`: list of OCR outputs per uploaded file
- `filename`: input file name
- `children`: OCR tree blocks
- `metadata`: page stats and related metadata

`html` in each node is converted to plain `text` recursively before returning.

### Response Example

```json
{
  "results": [
    {
      "filename": "sample.jpg",
      "children": [
        {
          "id": "/page/0/Text/0",
          "block_type": "Text",
          "text": "Ten: Le Hoai An",
          "bbox": [376, 68, 879, 170],
          "polygon": [[376, 68], [879, 68], [879, 170], [376, 170]],
          "children": []
        }
      ],
      "metadata": {
        "page_stats": [
          {"page_id": 0, "num_blocks": 19}
        ]
      }
    }
  ]
}
```

## 2. PaddleOCRv5 Text Detection Endpoint

Runs `paddlex.create_model` against a locally trained PP-OCRv5 detection model.
The model is loaded once on application startup (`lifespan`) and re-used for
every request. Heavy `predict()` calls are dispatched to a worker thread so the
event loop stays responsive.

### Endpoint

- **Method:** `POST`
- **URL:** `/api/v1/text-detection`
- **Content-Type:** `multipart/form-data`

### Form Fields

- `files` (required): one or many image files

### cURL Example

```bash
curl -X POST "http://localhost:8000/api/v1/text-detection" \
  -F "files=@/absolute/path/to/image.jpg"
```

### Configuration (env vars)

| Variable | Default | Description |
|---|---|---|
| `PADDLE_TEXT_DET_MODEL_NAME` | `PP-OCRv5_server_det` | PaddleX model name |
| `PADDLE_TEXT_DET_MODEL_DIR` | _(empty = official weights)_ | Path to your trained inference dir |
| `PADDLE_TEXT_DET_DEVICE` | `gpu:0` | `gpu:0`, `gpu:1`, `cpu`, `npu:0`, ... |
| `PADDLE_TEXT_DET_EAGER_LOAD` | `1` | Set `0` to disable startup warm-up |

The directory in `PADDLE_TEXT_DET_MODEL_DIR` should contain the converted
inference artifacts (e.g. `inference.yml`, `inference.json`,
`inference.pdiparams`).

### Dependency Install

`paddlepaddle-gpu` requires the matching CUDA wheel index, e.g.:

```bash
pip install paddlepaddle-gpu==3.0.0 \
  -i https://www.paddlepaddle.org.cn/packages/stable/cu118/
pip install "paddlex[ocr]==3.0.3"
```

Adjust the index URL for your CUDA version (`cu118`, `cu121`, ...).

### Response Format

```json
{
  "results": [
    {
      "filename": "sample.jpg",
      "image_size": {"width": 1280, "height": 960},
      "detections": [
        {
          "polygon": [[120,80],[640,80],[640,140],[120,140]],
          "bbox": [120, 80, 640, 140],
          "score": 0.94
        }
      ]
    }
  ]
}
```
