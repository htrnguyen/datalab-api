/**
 * Viewer module - displays image with zoom + bounding box overlay.
 */
import { $, renderIcons, showToast } from './ui.js';
import { state } from './state.js';
import { Blocks } from './blocks.js';

const COLORS = {
    text: 'rgba(37, 99, 235, 0.85)',
    table: 'rgba(22, 163, 74, 0.85)',
    image: 'rgba(190, 24, 93, 0.85)',
    math: 'rgba(217, 119, 6, 0.85)',
};

class Viewer {
    static applyRotation(deltaDeg) {
        return new Promise((resolve) => {
            const curImg = state.get('image');
            if (!curImg || !deltaDeg) { resolve(); return; }
            const w0 = curImg.naturalWidth || curImg.width || 0;
            const h0 = curImg.naturalHeight || curImg.height || 0;
            if (!w0 || !h0) { resolve(); return; }
            const rad = (deltaDeg * Math.PI) / 180;
            const cos = Math.abs(Math.cos(rad));
            const sin = Math.abs(Math.sin(rad));
            const nw = Math.round(w0 * cos + h0 * sin);
            const nh = Math.round(w0 * sin + h0 * cos);
            const canvas = document.createElement('canvas');
            canvas.width = nw;
            canvas.height = nh;
            const ctx = canvas.getContext('2d');
            ctx.fillStyle = '#fff';
            ctx.fillRect(0, 0, nw, nh);
            ctx.translate(nw / 2, nh / 2);
            ctx.rotate(rad);
            ctx.drawImage(curImg, -w0 / 2, -h0 / 2);
            const out = new Image();
            out.onload = () => {
                const cur = state.get('rotation') || 0;
                const next = ((cur + deltaDeg) % 360 + 360) % 360;
                state.set('image', out);
                state.set('imageSize', { w: nw, h: nh });
                state.set('rotation', next);
                canvas.toBlob((blob) => state.set('_rotatedBlob', blob), 'image/png');
                Viewer.render();
                resolve();
            };
            out.onerror = () => resolve();
            out.src = canvas.toDataURL('image/png');
        });
    }

    static render() {
        try {
            const viewer = $('viewer');
            if (!viewer) return;
            const image = state.get('image');
            const imageSize = state.get('imageSize') || {};
            if (!image || !imageSize.w || !imageSize.h) {
                return;
            }
            viewer.innerHTML = '';
            Viewer._render();
        } catch (err) {
            console.error('[viewer] render threw', err);
        }
    }

    static _render() {
        try {
            const viewer = $('viewer');
            const image = state.get('image');
            const imageSize = state.get('imageSize') || {};
            if (!viewer || !image) return;

            const imgW = image.naturalWidth || image.width || imageSize.w || 0;
            const imgH = image.naturalHeight || image.height || imageSize.h || 0;
            if (!imgW || !imgH) {
                console.warn('[viewer] image dimensions unknown', { naturalWidth: image.naturalWidth, width: image.width, size: imageSize });
                return;
            }

            const totalPages = state.get('pageCount') || 1;
            const pageIdx = state.get('pageIndex') || 0;

            // Toolbar
            const toolbar = document.createElement('div');
            toolbar.className = 'viewer-toolbar';
            toolbar.innerHTML = `
                <button class="tool-btn" id="zoom-out" title="Zoom out"><i data-lucide="minus"></i></button>
                <span class="page-label" id="zoom-label" title="Click to reset">100%</span>
                <button class="tool-btn" id="zoom-in" title="Zoom in"><i data-lucide="plus"></i></button>
                <span class="tool-sep"></span>
                <button class="tool-btn" id="rotate-ccw" title="Rotate 90° counter-clockwise"><i data-lucide="rotate-ccw"></i></button>
                <button class="tool-btn" id="rotate-cw" title="Rotate 90° clockwise"><i data-lucide="rotate-cw"></i></button>
                <span class="tool-sep"></span>
                <button class="tool-btn" id="page-prev" title="Previous page"><i data-lucide="chevron-left"></i></button>
                <span class="page-label" id="page-label">${totalPages > 1 ? `${pageIdx + 1} / ${totalPages}` : ''}</span>
                <button class="tool-btn" id="page-next" title="Next page"><i data-lucide="chevron-right"></i></button>
            `;
            viewer.appendChild(toolbar);

            // Page info badge
            const info = document.createElement('div');
            info.className = 'page-info';
            const pageLabel = totalPages > 1 ? `Page ${pageIdx + 1} / ${totalPages}` : 'Page 1';
            info.innerHTML = `<i data-lucide="file-image"></i> ${pageLabel} · ${imgW} × ${imgH}`;
            viewer.appendChild(info);

            // Page nav buttons
            const prevBtn = $('page-prev');
            const nextBtn = $('page-next');
            if (prevBtn) prevBtn.disabled = totalPages <= 1 || pageIdx <= 0;
            if (nextBtn) nextBtn.disabled = totalPages <= 1 || pageIdx >= totalPages - 1;

            // Compute fit-to-viewer scale
            const padding = 24;
            const maxW = Math.max(viewer.clientWidth - padding, 200);
            const maxH = Math.max(viewer.clientHeight - padding, 200);
            const fitScale = Math.max(0.05, Math.min(maxW / imgW, maxH / imgH));

            // Canvas for image + bbox overlay
            const canvas = document.createElement('canvas');
            canvas.className = 'viewer-canvas';
            canvas.width = imgW;
            canvas.height = imgH;
            const ctx = canvas.getContext('2d');
            ctx.fillStyle = '#fff';
            ctx.fillRect(0, 0, imgW, imgH);
            ctx.drawImage(image, 0, 0, imgW, imgH);
            canvas.style.position = 'absolute';
            canvas.style.top = '50%';
            canvas.style.left = '50%';
            canvas.style.transformOrigin = 'center center';
            viewer.appendChild(canvas);

            state.set('zoom', fitScale);
            Viewer._applyZoom(fitScale);

            const zoomLabel = $('zoom-label');
            if (zoomLabel) zoomLabel.textContent = Math.round(fitScale * 100) + '%';
            renderIcons();

            // Zoom controls
            const applyZoom = (z) => {
                state.set('zoom', z);
                Viewer._applyZoom(z);
                const label = $('zoom-label');
                if (label) label.textContent = Math.round(z * 100) + '%';
            };
            $('zoom-in').onclick = () => applyZoom(Math.min(3, state.get('zoom') + 0.2));
            $('zoom-out').onclick = () => applyZoom(Math.max(0.2, state.get('zoom') - 0.2));
            $('zoom-label').onclick = () => applyZoom(fitScale);

            // Rotation
            const rotateBtn = (deltaDeg) => Viewer.applyRotation(deltaDeg).then(() => {
                const hadResults = (state.get('blocks') || []).length > 0;
                if (hadResults) {
                    state.update({ blocks: [], result: null });
                    if (window.Blocks) Blocks.render();
                }
                showToast(hadResults ? 'Rotated. Click Process OCR to re-analyze.' : 'Rotated.');
            });
            $('rotate-ccw').onclick = () => rotateBtn(-90);
            $('rotate-cw').onclick = () => rotateBtn(90);

            // Page navigation (PDF)
            const goToPage = (delta) => {
                const pages = state.get('pages') || [];
                if (pages.length <= 1) return;
                const cur = state.get('pageIndex') || 0;
                const next = Math.max(0, Math.min(pages.length - 1, cur + delta));
                if (next === cur) return;
                state.set('pageIndex', next);
                state.set('image', pages[next].canvas);
                state.set('imageSize', pages[next].size);
                Viewer.render();
            };
            $('page-prev')?.addEventListener('click', () => goToPage(-1));
            $('page-next')?.addEventListener('click', () => goToPage(1));

        } catch (err) {
            console.error('[viewer] _render threw', err);
        }
    }

    static _applyZoom(scale) {
        const canvas = $('viewer')?.querySelector('.viewer-canvas');
        if (!canvas) return;
        canvas.style.transform = `translate(-50%, -50%) scale(${scale})`;
        canvas.style.transformOrigin = 'center center';
        canvas.style.position = 'absolute';
        canvas.style.top = '50%';
        canvas.style.left = '50%';
    }

    static drawBoxes(highlightId = null) {
        const canvas = $('viewer')?.querySelector('.viewer-canvas');
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        const image = state.get('image');
        const imageSize = state.get('imageSize') || {};

        const imgW = canvas.width || image?.naturalWidth || imageSize.w || 0;
        const imgH = canvas.height || image?.naturalHeight || imageSize.h || 0;
        if (!imgW || !imgH) return;

        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.fillStyle = '#fff';
        ctx.fillRect(0, 0, imgW, imgH);
        ctx.drawImage(image, 0, 0, imgW, imgH);

        if (!state.get('drawBBox')) return;

        const pageIdx = state.get('pageIndex') || 0;
        const blocks = (state.get('blocks') || []).filter(b => {
            if (b.page === undefined) return true;
            return b.page === pageIdx;
        });

        console.log('[drawBoxes] canvas:', imgW, 'x', imgH, 'blocks:', blocks.length);
        if (blocks.length > 0) {
            console.log('[drawBoxes] sample bbox:', JSON.stringify(blocks[0].bbox));
        }

        blocks.forEach((b) => {
            const bb = b.bbox;
            if (!bb || !Array.isArray(bb) || bb.length < 4) return;
            const [x1, y1, x2, y2] = bb;

            // Normalize coordinates if needed (handle [0-1] normalized coords)
            let nx1 = x1, ny1 = y1, nx2 = x2, ny2 = y2;
            if (x2 <= 1 && y2 <= 1) {
                nx1 = x1 * imgW;
                ny1 = y1 * imgH;
                nx2 = x2 * imgW;
                ny2 = y2 * imgH;
            }

            const isActive = b.id === highlightId;
            const typeColor = COLORS[b.type] || COLORS.text;

            const w = nx2 - nx1;
            const h = ny2 - ny1;
            if (w <= 0 || h <= 0) return;

            if (isActive) {
                ctx.fillStyle = 'rgba(251, 191, 36, 0.18)';
                ctx.fillRect(nx1, ny1, w, h);
            }

            ctx.lineWidth = isActive ? 3.5 : 2.5;
            ctx.strokeStyle = isActive ? '#2563EB' : typeColor;
            ctx.strokeRect(nx1 + 0.5, ny1 + 0.5, w - 1, h - 1);

            ctx.beginPath();
            ctx.arc(nx1 + 5, ny1 + 5, isActive ? 5 : 3.5, 0, Math.PI * 2);
            ctx.fillStyle = isActive ? '#2563EB' : typeColor;
            ctx.fill();
        });
    }
}

export { Viewer };
