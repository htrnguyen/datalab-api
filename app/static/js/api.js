/**
 * API client for OCR backend.
 */
const ENDPOINT = '/api/v1/ocr';

/**
 * Send image to OCR endpoint using baked data URL.
 */
export async function runOCR(file, dataUrl = null) {
    const fd = new FormData();

    // Prefer baked image (dataUrl) to ensure bbox coords match display dimensions
    if (dataUrl) {
        fd.append('data_url', dataUrl);
    } else {
        fd.append('files', file);
    }

    const res = await fetch(ENDPOINT, { method: 'POST', body: fd });
    if (!res.ok) {
        const err = await res.text();
        throw new Error(`HTTP ${res.status}: ${err.slice(0, 200)}`);
    }
    return res.json();
}
