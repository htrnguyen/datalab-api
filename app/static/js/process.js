/**
 * Process controller - orchestrates the OCR workflow.
 */
import { $, renderIcons, showToast } from './ui.js';
import { state } from './state.js';
import { runOCR } from './api.js';
import { Blocks } from './blocks.js';
import { Viewer } from './viewer.js';
import { Exporter } from './export.js';

class Processor {
    static init() {
        $('btn-process').addEventListener('click', Processor.run);
    }

    static async run() {
        const fileInput = $('file-input');
        const file = fileInput.files[0];
        if (!file) return;

        const btn = $('btn-process');
        btn.disabled = true;
        btn.innerHTML = '<i data-lucide="loader"></i><span>Processing...</span>';
        renderIcons();

        // Show processing overlay
        const viewer = $('viewer');
        const overlay = document.createElement('div');
        overlay.className = 'processing-overlay';
        overlay.innerHTML = `
            <div class="processing">
                <div class="spinner"></div>
                <div class="processing-text">Analyzing document with AI...</div>
            </div>
        `;
        viewer.appendChild(overlay);

        const t0 = performance.now();
        try {
            // Use baked image (dataURL) to ensure bbox coords match display
            const imageDataUrl = state.get('image')?.src || null;
            const data = await runOCR(file, imageDataUrl);
            const elapsed = ((performance.now() - t0) / 1000).toFixed(1);

            const blocks = data.blocks || [];
            const apiSize = data.image_size || {};
            const pageSizes = data.page_sizes || [apiSize];
            const pageCount = data.page_count || 1;

            console.log('[OCR response] image_size:', JSON.stringify(apiSize));
            console.log('[OCR response] page_sizes:', JSON.stringify(pageSizes));
            if (blocks.length > 0) {
                console.log('[OCR response] sample block:', JSON.stringify(blocks[0]));
            }

            // Datalab may internally resize; scale bbox coords from its frame to display frame
            const displaySize = state.get('imageSize') || {};
            // apiSize is Datalab's processing frame, displaySize is what user sees
            if (displaySize.w && displaySize.h && apiSize.w && apiSize.h) {
                const sx = displaySize.w / apiSize.w;
                const sy = displaySize.h / apiSize.h;
                console.log('[process] scaling bboxes from Datalab %dx%d -> display %dx%d, sx=%.4f sy=%.4f',
                    apiSize.w, apiSize.h, displaySize.w, displaySize.h, sx, sy);
                for (const b of blocks) {
                    if (b.bbox && b.bbox.length === 4) {
                        b.bbox = [
                            Math.round(b.bbox[0] * sx),
                            Math.round(b.bbox[1] * sy),
                            Math.round(b.bbox[2] * sx),
                            Math.round(b.bbox[3] * sy),
                        ];
                    }
                }
                if (blocks.length > 0) {
                    console.log('[process] scaled bbox sample:', JSON.stringify(blocks[0].bbox));
                }
            }

            state.update({
                result: data,
                blocks,
                imageSize: displaySize,
                pageCount,
                pageSizes,
                documentType: data.document_type || 'image',
            });

            Processor._updateKPIs(elapsed);
            Viewer.render();
            Viewer.drawBoxes();
            Blocks.render();
            Blocks.updateCounts();
            $('json-view').textContent = JSON.stringify(data, null, 2);
            $('md-view').textContent = Exporter.toMarkdown();
            showToast('OCR complete');
        } catch (err) {
            showToast('Error: ' + err.message, true);
        } finally {
            overlay.remove();
            btn.disabled = false;
            btn.innerHTML = '<i data-lucide="zap"></i><span>Process OCR</span>';
            renderIcons();
        }
    }

    static _updateKPIs(elapsed) {
        const blocks = state.get('blocks');
        const tables = blocks.filter(b => b.type === 'table');
        const confs = blocks.map(b => b.confidence ?? 1).filter(Boolean);
        const avg = confs.length ? confs.reduce((a, b) => a + b, 0) / confs.length : 0;

        $('kpi-blocks').textContent = blocks.length;
        $('kpi-tables').textContent = tables.length;
        $('kpi-confidence').textContent = avg ? Math.round(avg * 100) + '%' : '—';
        $('kpi-time').textContent = elapsed + 's';
    }
}

export { Processor };
