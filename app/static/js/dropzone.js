/**
 * Dropzone module - handles file selection via drag/drop and click.
 */
import { $, renderIcons, showToast } from './ui.js';
import { state } from './state.js';
import { Viewer } from './viewer.js';

/** Read EXIF Orientation tag (1-8) from a JPEG data URL. Returns 1 if absent. */
function readExifOrientation(dataUrl) {
    try {
        const b64 = dataUrl.split(',')[1];
        const binary = atob(b64);
        for (let i = 0; i < binary.length; i++) {
            if (binary.charCodeAt(i) === 0xFF && binary.charCodeAt(i + 1) === 0xD8) {
                const marker = binary.charCodeAt(i + 2);
                if (marker === 0xE1) {
                    const len = (binary.charCodeAt(i + 3) << 8) | binary.charCodeAt(i + 4);
                    const app1 = binary.slice(i + 4, i + 4 + len);
                    const exifIdx = app1.indexOf('Exif\x00\x00');
                    if (exifIdx >= 0) {
                        const tiff = app1.slice(exifIdx + 6);
                        const le = tiff.charCodeAt(0) === 0x49;
                        const buf = new ArrayBuffer(tiff.length);
                        const view = new Uint8Array(buf);
                        for (let j = 0; j < tiff.length; j++) view[j] = tiff.charCodeAt(j) & 0xff;
                        const dv = new DataView(buf);
                        const ifdOffset = le ? dv.getUint32(4, true) : dv.getUint32(4, false);
                        const entries = le ? dv.getUint16(ifdOffset, true) : dv.getUint16(ifdOffset, false);
                        for (let e = 0; e < entries; e++) {
                            const base = ifdOffset + 2 + e * 12;
                            const tag = le ? dv.getUint16(base, true) : dv.getUint16(base, false);
                            if (tag === 0x0112) {
                                return le
                                    ? dv.getUint16(base + 8, true)
                                    : dv.getUint16(base + 8, false);
                            }
                        }
                    }
                }
                break;
            }
        }
    } catch (_) { /* ignore */ }
    return 1;
}

/** Return display dimensions after applying EXIF orientation. */
function displayDims(orientation, w, h) {
    return (orientation >= 5 && orientation <= 8) ? { w: h, h: w } : { w, h };
}

/**
 * Bake EXIF orientation into a fresh Image and return it with its display dims.
 * The returned image has no EXIF and always displays in the oriented frame.
 */
function bakeExif(dataUrl) {
    return new Promise((resolve, reject) => {
        const raw = new Image();
        raw.onload = () => {
            const orientation = readExifOrientation(dataUrl);
            const { w, h } = displayDims(orientation, raw.naturalWidth, raw.naturalHeight);
            const canvas = document.createElement('canvas');
            canvas.width = w;
            canvas.height = h;
            const ctx = canvas.getContext('2d');
            ctx.fillStyle = '#fff';
            ctx.fillRect(0, 0, w, h);

            // Apply EXIF orientation to canvas
            if (orientation === 2) {
                ctx.translate(w, 0); ctx.scale(-1, 1);
            } else if (orientation === 3) {
                ctx.translate(w, h); ctx.rotate(Math.PI);
            } else if (orientation === 4) {
                ctx.translate(0, h); ctx.scale(1, -1);
            } else if (orientation === 5) {
                ctx.translate(w, 0); ctx.scale(-1, 1); ctx.rotate(Math.PI / 2);
            } else if (orientation === 6) {
                ctx.translate(w, 0); ctx.rotate(Math.PI / 2);
            } else if (orientation === 7) {
                ctx.translate(w, 0); ctx.scale(-1, 1); ctx.rotate(-Math.PI / 2);
            } else if (orientation === 8) {
                ctx.translate(0, h); ctx.rotate(-Math.PI / 2);
            }

            ctx.drawImage(raw, 0, 0);
            const baked = new Image();
            baked.onload = () => resolve({ img: baked, width: w, height: h });
            baked.onerror = reject;
            baked.src = canvas.toDataURL('image/jpeg', 0.95);
        };
        raw.onerror = reject;
        raw.src = dataUrl;
    });
}

class Dropzone {
    constructor() {
        this.input = $('file-input');
        this.bindOnce = false;
    }

    init() {
        this._bindStatic();
        this.render();
    }

    _bindStatic() {
        $('btn-upload')?.addEventListener('click', () => this.input.click());
        this.input.addEventListener('change', (e) => {
            const f = e.target.files[0];
            if (f) this._onFile(f);
        });
    }

    _bindDynamic() {
        if (this.bindOnce) return;
        const dz = $('dropzone');
        if (!dz) return;
        const viewer = $('viewer');

        const onEnter = (e) => { e.preventDefault(); dz.classList.add('drag-over'); };
        const onLeave = (e) => { e.preventDefault(); dz.classList.remove('drag-over'); };
        const onDrop = (e) => {
            e.preventDefault();
            dz.classList.remove('drag-over');
            viewer.classList.remove('drag-over');
            const f = e.dataTransfer.files[0];
            if (f) this._onFile(f);
        };

        ['dragenter', 'dragover'].forEach(evt => {
            dz.addEventListener(evt, onEnter);
            viewer.addEventListener(evt, onEnter);
        });
        ['dragleave', 'drop'].forEach(evt => {
            dz.addEventListener(evt, onLeave);
        });
        dz.addEventListener('drop', onDrop);
        viewer.addEventListener('drop', onDrop);

        dz.addEventListener('click', (e) => {
            if (e.target.closest('button')) this.input.click();
        });

        this.bindOnce = true;
    }

    render() {
        const viewer = $('viewer');
        viewer.innerHTML = '';
        const dz = document.createElement('div');
        dz.className = 'dropzone';
        dz.id = 'dropzone';
        dz.innerHTML = `
            <div class="dropzone-icon"><i data-lucide="upload-cloud"></i></div>
            <h3>Drop your document here</h3>
            <p>or click <strong>Upload</strong> to choose a file.<br/>Supports JPG, PNG, WEBP, PDF.</p>
        `;
        viewer.appendChild(dz);
        this.bindOnce = false;
        this._bindDynamic();
        renderIcons();
    }

    clear() {
        const viewer = $('viewer');
        if (viewer) viewer.innerHTML = '';
        this.bindOnce = false;
    }

    _onFile(file) {
        state.update({
            filename: file.name,
            image: null,
            imageSize: null,
            pages: [],
            pageIndex: 0,
            pageCount: 1,
            pageSizes: [],
            documentType: 'image',
            blocks: [],
            result: null,
            _pdfPageBlob: null,
            _rotatedBlob: null,
            _pdfFile: null,
        });
        $('btn-process').disabled = false;
        const viewer = $('viewer');
        if (viewer) viewer.innerHTML = '';
        ['kpi-blocks', 'kpi-tables', 'kpi-confidence', 'kpi-time'].forEach(id => {
            const el = $(id);
            if (el) el.textContent = '—';
        });
        const jsonView = $('json-view'); if (jsonView) jsonView.textContent = '';
        const mdView = $('md-view'); if (mdView) mdView.textContent = '';
        if (window.Blocks) {
            try { Blocks.render(); } catch (_) {}
        }

        const isPdf = file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf');

        if (isPdf) {
            this._handlePdf(file).catch(err => {
                console.error('[dropzone] PDF error', err);
                showToast('Failed to load PDF', true);
            });
        } else {
            const reader = new FileReader();
            reader.onload = (ev) => {
                bakeExif(ev.target.result).then(({ img, width, height }) => {
                    state.set('image', img);
                    state.set('imageSize', { w: width, h: height });
                    console.log('[dropzone] image ready (baked)', width, 'x', height);
                    requestAnimationFrame(() => {
                        try { Viewer.render(); }
                        catch (err) { console.error('[viewer]', err); }
                    });
                }).catch(() => showToast('Failed to load image', true));
            };
            reader.onerror = () => showToast('Failed to read file', true);
            reader.readAsDataURL(file);
        }
    }

    async _handlePdf(file) {
        const arrayBuffer = await file.arrayBuffer();
        const pdf = await pdfjsLib.getDocument({ data: arrayBuffer }).promise;
        const totalPages = pdf.numPages;
        console.log('[dropzone] PDF pages:', totalPages);

        // Render every page in parallel, capped by DPR
        const pages = [];
        const renderPage = async (idx) => {
            const page = await pdf.getPage(idx);
            const viewport1 = page.getViewport({ scale: 1 });
            const scale = Math.min(1, 1200 / Math.max(viewport1.width, viewport1.height));
            const viewport = page.getViewport({ scale });

            const canvas = document.createElement('canvas');
            canvas.width = Math.round(viewport.width);
            canvas.height = Math.round(viewport.height);
            const ctx = canvas.getContext('2d');
            ctx.fillStyle = 'white';
            ctx.fillRect(0, 0, canvas.width, canvas.height);
            await page.render({ canvasContext: ctx, viewport }).promise;

            const blob = await new Promise(res => canvas.toBlob(res, 'image/png'));
            return { canvas, blob, size: { w: canvas.width, h: canvas.height } };
        };

        const results = await Promise.all(
            Array.from({ length: totalPages }, (_, i) => renderPage(i + 1))
        );

        for (const r of results) pages.push(r);

        // For backend upload we still need a single representative file;
        // send the first page blob, keep .pdf extension so backend renders PDF
        // and walks all pages.
        state.set('pages', pages);
        state.set('pageIndex', 0);
        state.set('pageCount', pages.length);
        state.set('pageSizes', pages.map(p => p.size));
        state.set('documentType', 'pdf');
        state.set('image', pages[0].canvas);
        state.set('imageSize', pages[0].size);
        state.set('_pdfPageBlob', pages[0].blob);
        state.set('_pdfFile', file); // Store original PDF for backend upload

        requestAnimationFrame(() => {
            try { Viewer.render(); }
            catch (err) { console.error('[viewer]', err); }
        });
    }
}

export const DropzoneCtl = new Dropzone();
