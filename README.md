# Datalab OCR Service

FastAPI service for OCR using Datalab API with async processing, line-level output, and infographic mode.

## Features

- **Async OCR Processing** - Non-blocking image/PDF processing
- **Multiple Modes** - `fast`, `balanced`, `accurate`
- **Infographic Support** - Enhanced recognition for diagrams and infographics
- **Rate Limiting** - Built-in concurrency control
- **Line-level Output** - Bounding boxes and polygon coordinates for each text line

## Quick Start

### Docker (Recommended)

```bash
cp .env.docker .env
docker compose up -d --build
```

API: http://localhost:4242

### Python (Development)

```bash
pip install -r requirements.txt
cp .env.docker .env
uvicorn app.main:app --reload --host 0.0.0.0 --port 4242
```

## Docker Commands

```bash
docker compose up -d --build
docker compose logs -f
docker compose down
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATALAB_API_KEYS` | _(required)_ | Comma-separated API keys |
| `DATALAB_BASE_URL` | `https://www.datalab.to/api/v1` | Datalab API base URL |
| `DATALAB_POLL_INTERVAL` | `2` | Poll interval in seconds |
| `DATALAB_POLL_TIMEOUT` | `120` | Poll timeout in seconds |
| `DATALAB_HTTP_TIMEOUT` | `90` | HTTP request timeout in seconds |
| `MAX_UPLOAD_SIZE_MB` | `50` | Max upload file size in MB |
| `MAX_CONCURRENT_REQUESTS` | `5` | Max concurrent requests |

## API Endpoints

### POST /api/v1/ocr

Process an image or PDF file for OCR.

| Parameter | Type | Location | Required | Default | Description |
|-----------|------|----------|---------|---------|-------------|
| `file` | UploadFile | form | Yes | - | Image (PNG, JPG, WEBP) or PDF file |
| `mode` | string | query | No | accurate | Processing mode: `fast`, `balanced`, `accurate` |
| `infographic` | bool | query | No | false | Enable infographic mode |

### cURL Examples

**Basic OCR with accurate mode:**

```bash
curl -X POST \
  'http://localhost:4242/api/v1/ocr?mode=accurate&infographic=false' \
  -H 'accept: application/json' \
  -H 'Content-Type: multipart/form-data' \
  -F 'file=@image.png;type=image/png'
```

**Fast mode:**

```bash
curl -X POST \
  'http://localhost:4242/api/v1/ocr?mode=fast' \
  -F 'file=@document.pdf'
```

**Infographic mode for diagrams:**

```bash
curl -X POST \
  'http://localhost:4242/api/v1/ocr?mode=accurate&infographic=true' \
  -F 'file=@diagram.png'
```

### Response Example

```json
{
  "success": true,
  "page_count": 1,
  "pages": [
    {
      "page_index": 0,
      "width": 2464,
      "height": 1540,
      "blocks": [
        {
          "id": "/page/0/Text/0",
          "block_type": "text",
          "content": "挑戰題*21* 1. 大的表面积, 2. 薄的交换表面...",
          "confidence": 1,
          "polygon": {
            "points": [
              [56.94, 40.40],
              [683.66, 40.40],
              [683.66, 82.80],
              [56.94, 82.80]
            ]
          },
          "html": "<p>挑戰題*21* 1. 大的表面积, 2. 薄的交换表面...</p>"
        }
      ]
    }
  ],
  "runtime_seconds": 3.53,
  "cost_cents": 1
}
```

**Response Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `success` | bool | Whether OCR succeeded |
| `page_count` | int | Number of pages processed |
| `pages` | array | Array of page results |
| `pages[].page_index` | int | Page number (0-indexed) |
| `pages[].width` | int | Page width in pixels |
| `pages[].height` | int | Page height in pixels |
| `pages[].blocks` | array | Array of text blocks detected |
| `blocks[].id` | string | Unique block identifier |
| `blocks[].block_type` | string | Block type (e.g., "text") |
| `blocks[].content` | string | Extracted text content |
| `blocks[].confidence` | float | Confidence score (0-1) |
| `blocks[].polygon.points` | array | Bounding polygon coordinates |
| `blocks[].html` | string | HTML formatted text |
| `runtime_seconds` | float | Processing time in seconds |
| `cost_cents` | int | Estimated cost in cents |

### GET /api/v1/ocr/stats

Get current rate limiter statistics.

```json
{
  "active_requests": 2,
  "queued_requests": 0,
  "max_concurrent": 5
}
```

### GET /health

Health check endpoint.

```json
{"status": "healthy"}
```

## Processing Modes

| Mode | Description | Use Case |
|------|-------------|----------|
| `fast` | Low latency | Quick previews, high-volume processing |
| `balanced` | Balanced speed/quality | General purpose |
| `accurate` | Highest quality | Complex layouts, infographics |

## Client Examples

### Python

```python
import requests

with open("document.pdf", "rb") as f:
    response = requests.post(
        "http://localhost:4242/api/v1/ocr",
        files={"file": f},
        params={"mode": "accurate", "infographic": True}
    )

data = response.json()
if data["success"]:
    for page in data["pages"]:
        for block in page["blocks"]:
            print(f"[{block['confidence']:.0%}] {block['content']}")
```

### JavaScript

```javascript
const formData = new FormData();
formData.append('file', fileInput.files[0]);

const response = await fetch('http://localhost:4242/api/v1/ocr?mode=accurate', {
  method: 'POST',
  body: formData
});

const data = await response.json();
if (data.success) {
  data.pages.forEach(page => {
    page.blocks.forEach(block => {
      console.log(`[${(block.confidence * 100).toFixed(0)}%] ${block.content}`);
    });
  });
}
```

## Architecture

```
Client → FastAPI Server → Datalab API
```
