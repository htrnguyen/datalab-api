# OCR Endpoint Guide

## Endpoint

- **Method:** `POST`
- **URL:** `/api/v1/ocr`
- **Content-Type:** `multipart/form-data`

## Form Fields

- `files` (required): one or many image files
- `refine` (optional): `true` or `false`, default is `true`

## cURL Example

```bash
curl -X POST "http://localhost:8000/api/v1/ocr" \
  -F "files=@/absolute/path/to/image.jpg" \
  -F "refine=true"
```

## Response Format

The API returns:

- `results`: list of OCR outputs per uploaded file
- `filename`: input file name
- `children`: OCR tree blocks
- `metadata`: page stats and related metadata

## Important Output Cleaning

Before returning response:

- `html` in each node is converted to plain `text`
- `html` field is removed from output
- cleaning is recursive for all nested `children`

This helps frontend visualization without parsing HTML tags.

## Response Example

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
          {
            "page_id": 0,
            "num_blocks": 19
          }
        ]
      }
    }
  ]
}
```
