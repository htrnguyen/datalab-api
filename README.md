# Datalab OCR Service

FastAPI service for OCR using Datalab API with async processing, line-level output, and infographic mode.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Configure API keys
cp .env.example .env
# Edit .env and add: DATALAB_API_KEYS=your_api_key

# Run server
uvicorn app.main:app --reload --log-level info --host 0.0.0.0 --port 8000
```

## API Endpoints

### Async OCR (Recommended)

#### Submit OCR Job
```
POST /api/v1/ocr
Content-Type: multipart/form-data
```

**Parameters:**
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `files` | UploadFile | Yes* | - | Image (PNG, JPG, WEBP) or PDF file |
| `data_url` | string | Yes* | - | Base64 data URL of image |
| `mode` | query | No | accurate | Processing mode: `fast`, `balanced`, `accurate` |
| `output_format` | query | No | json | Output format: `json`, `markdown`, `html`, `chunks` |
| `extras` | query[] | No | - | Extras: `infographic`, `chart_understanding`, `extract_links` |

*Either `files` or `data_url` is required.

**cURL Example:**
```bash
# Basic OCR
curl -X POST "http://localhost:8000/api/v1/ocr" \
  -F "files=@document.pdf"

# With infographic mode
curl -X POST "http://localhost:8000/api/v1/ocr?mode=accurate&extras=infographic" \
  -F "files=@infographic.png"

# With multiple extras
curl -X POST "http://localhost:8000/api/v1/ocr?mode=accurate&extras=infographic&extras=chart_understanding" \
  -F "files=@complex_doc.pdf"
```

**Response:**
```json
{
  "success": true,
  "request_id": "req_abc123def456",
  "request_check_url": "/api/v1/ocr/result/req_abc123def456",
  "versions": {
    "ocr_engine": "v1.0",
    "layout_engine": "v1.0"
  }
}
```

---

#### Check Job Status
```
GET /api/v1/ocr/result/{request_id}
```

**Response (processing):**
```json
{
  "request_id": "req_abc123def456",
  "status": "processing",
  "message": "Job is currently being processed"
}
```

**Response (done):**
```json
{
  "request_id": "req_abc123def456",
  "status": "done",
  "message": "Job completed successfully",
  "result": {
    "request_id": "req_abc123def456",
    "status": "done",
    "mode": "accurate",
    "extras": ["infographic"],
    "page_count": 1,
    "metadata": {
      "filename": "document.pdf",
      "file_size": 1024000,
      "mime_type": "application/pdf",
      "page_count": 1,
      "total_lines": 25,
      "languages": ["en"],
      "processed_at": "2026-06-17T13:45:00"
    },
    "pages": [
      {
        "page_index": 0,
        "width": 2480,
        "height": 3508,
        "lines": [
          {
            "id": "p0_l1",
            "text": "Invoice #12345",
            "block_type": "title",
            "bbox": [120, 180, 430, 220],
            "polygon": [[120,180],[430,180],[430,220],[120,220]],
            "confidence": 0.997,
            "reading_order": 1,
            "language": "en",
            "page": 0
          },
          {
            "id": "p0_l2",
            "text": "This is a sample invoice for services rendered.",
            "block_type": "text",
            "bbox": [120, 250, 800, 290],
            "polygon": [[120,250],[800,250],[800,290],[120,290]],
            "confidence": 0.991,
            "reading_order": 2,
            "language": "en",
            "page": 0
          }
        ]
      }
    ]
  }
}
```

---

#### Download Result
```
GET /api/v1/ocr/download/{request_id}?format=json|markdown|html|txt
```

Download OCR result in different formats.

---

#### List Jobs
```
GET /api/v1/ocr/jobs?status=processing&limit=100
```

List recent OCR jobs, optionally filtered by status.

---

#### Delete Job
```
DELETE /api/v1/ocr/result/{request_id}
```

Delete a completed or queued job.

---

### Legacy Sync Endpoint

```
POST /api/v1/ocr (sync)
```

Legacy synchronous endpoint. Use the async endpoints above instead.

---

## Response Schema

### LineData
| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique identifier (e.g., `p0_l1`) |
| `text` | string | Recognized text content |
| `block_type` | string | Content type: `text`, `table`, `figure`, `title`, `header`, `footer`, `list_item` |
| `bbox` | number[] | Bounding box `[x1, y1, x2, y2]` in original coordinates |
| `polygon` | number[][] | Polygon coordinates `[[x,y], ...]` |
| `confidence` | float | Confidence score 0-1 |
| `reading_order` | int | Reading sequence index |
| `language` | string | Detected language (ISO 639-1) |
| `page` | int | Page index (0-based) |

### PageData
| Field | Type | Description |
|-------|------|-------------|
| `page_index` | int | Page number (0-indexed) |
| `width` | int | Page width in pixels |
| `height` | int | Page height in pixels |
| `lines` | LineData[] | List of detected text lines |
| `metadata` | object | Page metadata (optional) |
| `raw_children` | object[] | Raw Datalab tree structure |

### DocumentMetadata
| Field | Type | Description |
|-------|------|-------------|
| `filename` | string | Original filename |
| `file_size` | int | File size in bytes |
| `mime_type` | string | MIME type |
| `page_count` | int | Total pages |
| `total_lines` | int | Total detected lines |
| `languages` | string[] | Detected languages |
| `processed_at` | datetime | Processing timestamp |

---

## Processing Modes

| Mode | Description | Use Case |
|------|-------------|----------|
| `fast` | Low latency | Quick previews, high-volume processing |
| `balanced` | Balanced speed/quality | General purpose |
| `accurate` | Highest quality | Complex layouts, infographics, archives |

**Recommendation:** Use `accurate` for best OCR results, especially for complex documents.

---

## Extras

Optional enhancements for specialized processing:

| Extra | Description |
|-------|-------------|
| `infographic` | Better handling of infographic/diagram content |
| `chart_understanding` | Enhanced chart and graph recognition |
| `extract_links` | Extract hyperlinks and URLs |
| `table_row_bboxes` | Include row-level bounding boxes for tables |
| `new_block_types` | Enable experimental block type detection |

---

## Configuration

Copy `.env.example` to `.env` and configure:

| Variable | Default | Description |
|----------|---------|-------------|
| `DATALAB_API_KEYS` | _(required)_ | Comma-separated API keys |
| `DATALAB_BASE_URL` | `https://www.datalab.to/api/v1` | Datalab API base URL |
| `DATALAB_POLL_INTERVAL` | `2` | Poll interval in seconds |
| `DATALAB_POLL_TIMEOUT` | `120` | Poll timeout in seconds |
| `DATALAB_HTTP_TIMEOUT` | `90` | HTTP request timeout in seconds |
| `DATALAB_MAX_RETRIES` | `2` | Max retry attempts |
| `MAX_UPLOAD_SIZE_MB` | `50` | Max upload file size in MB |

---

## Client Examples

### Python
```python
import requests
import time

# Submit job
with open("document.pdf", "rb") as f:
    response = requests.post(
        "http://localhost:8000/api/v1/ocr",
        files={"files": f},
        params={"mode": "accurate", "extras": ["infographic"]}
    )

request_id = response.json()["request_id"]

# Poll for result
while True:
    result = requests.get(f"http://localhost:8000/api/v1/ocr/result/{request_id}")
    data = result.json()

    if data["status"] == "done":
        print(data["result"]["pages"])
        break
    elif data["status"] == "failed":
        print("Error:", data["error"])
        break

    time.sleep(2)
```

### JavaScript
```javascript
// Submit job
const formData = new FormData();
formData.append('files', fileInput.files[0]);

const response = await fetch('http://localhost:8000/api/v1/ocr?mode=accurate', {
  method: 'POST',
  body: formData
});

const { request_id } = await response.json();

// Poll for result
while (true) {
  const result = await fetch(`http://localhost:8000/api/v1/ocr/result/${request_id}`);
  const data = await result.json();

  if (data.status === 'done') {
    console.log(data.result.pages);
    break;
  } else if (data.status === 'failed') {
    console.error('Error:', data.error);
    break;
  }

  await new Promise(r => setTimeout(r, 2000));
}
```

---

## Architecture

```
┌─────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Client    │────▶│  FastAPI Server │────▶│   Datalab API   │
│             │     │  (Async OCR)    │     │   (Cloud)       │
└─────────────┘     └─────────────────┘     └─────────────────┘
                            │
                            ▼
                    ┌─────────────────┐
                    │   Job Store     │
                    │  (In-Memory)    │
                    └─────────────────┘
```

Jobs are processed asynchronously in background threads. For production deployment, consider using Redis for job persistence.
