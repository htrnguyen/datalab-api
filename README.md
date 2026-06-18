# Datalab OCR Service

FastAPI service for OCR using Datalab API with async processing, line-level output, and infographic mode.

## Features

- **Async OCR Processing** - Non-blocking image/PDF processing
- **Multiple Modes** - `fast`, `balanced`, `accurate`
- **Infographic Support** - Enhanced recognition for diagrams and infographics
- **Rate Limiting** - Built-in concurrency control
- **Line-level Output** - Bounding boxes and polygon coordinates for each text line

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Configure API keys
cp .env.example .env
# Edit .env and add: DATALAB_API_KEYS=your_api_key

# Run server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

For production with multiple workers:
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

## API Endpoints

### POST /api/v1/ocr

Process an image or PDF file for OCR.

**Request:**
```
POST /api/v1/ocr
Content-Type: multipart/form-data
```

| Parameter | Type | Location | Required | Default | Description |
|-----------|------|----------|---------|---------|-------------|
| `file` | UploadFile | form | Yes | - | Image (PNG, JPG, WEBP) or PDF file |
| `mode` | string | query | No | accurate | Processing mode: `fast`, `balanced`, `accurate` |
| `infographic` | bool | query | No | false | Enable infographic mode |

**cURL Examples:**
```bash
# Basic OCR
curl -X POST "http://localhost:8000/api/v1/ocr" \
  -F "file=@document.pdf"

# Fast mode
curl -X POST "http://localhost:8000/api/v1/ocr?mode=fast" \
  -F "file=@image.png"

# Infographic mode
curl -X POST "http://localhost:8000/api/v1/ocr?mode=accurate&infographic=true" \
  -F "file=@infographic.png"
```

**Response:**
```json
{
  "success": true,
  "request_id": "req_abc123def456",
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
          }
        ]
      }
    ]
  }
}
```

### GET /api/v1/ocr/stats

Get current rate limiter statistics.

**Response:**
```json
{
  "active": 2,
  "max": 5,
  "total_requests": 150,
  "total_rejected": 0
}
```

### GET /health

Health check endpoint.

## Processing Modes

| Mode | Description | Use Case |
|------|-------------|----------|
| `fast` | Low latency | Quick previews, high-volume processing |
| `balanced` | Balanced speed/quality | General purpose |
| `accurate` | Highest quality | Complex layouts, infographics, archives |

**Recommendation:** Use `accurate` for best OCR results, especially for complex documents.

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
| `MAX_CONCURRENT_REQUESTS` | `5` | Max concurrent requests (rate limiting) |
| `DEBUG_LOG_ENABLED` | `false` | Enable debug logging |

## Client Examples

### Python
```python
import requests

with open("document.pdf", "rb") as f:
    response = requests.post(
        "http://localhost:8000/api/v1/ocr",
        files={"file": f},
        params={"mode": "accurate", "infographic": True}
    )

data = response.json()
if data["success"]:
    for page in data["result"]["pages"]:
        for line in page["lines"]:
            print(f"{line['text']} (conf: {line['confidence']:.2f})")
```

### JavaScript
```javascript
const formData = new FormData();
formData.append('file', fileInput.files[0]);

const response = await fetch('http://localhost:8000/api/v1/ocr?mode=accurate', {
  method: 'POST',
  body: formData
});

const data = await response.json();
if (data.success) {
  data.result.pages.forEach(page => {
    page.lines.forEach(line => {
      console.log(`${line.text} (conf: ${line.confidence.toFixed(2)})`);
    });
  });
}
```

## Architecture

```
┌─────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Client    │────▶│  FastAPI Server │────▶│   Datalab API   │
│             │     │  (Async OCR)    │     │   (Cloud)       │
└─────────────┘     └─────────────────┘     └─────────────────┘
```

## License

MIT
