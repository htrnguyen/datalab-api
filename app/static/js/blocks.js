/**
 * Blocks module - renders OCR block cards and tab switching.
 */
import { $, $$, renderIcons, escapeHtml, copyText } from './ui.js';
import { state } from './state.js';
import { Viewer } from './viewer.js';

const TYPE_ICONS = { text: 'type', table: 'table-2', image: 'image', math: 'sigma' };

class Blocks {
    static init() {
        $$('.tab').forEach(tab => {
            tab.addEventListener('click', () => Blocks.switchTab(tab.dataset.tab));
        });
        $('search-input').addEventListener('input', () => Blocks.render());
        $('filter-type').addEventListener('change', () => Blocks.render());
    }

    static switchTab(name) {
        state.set('activeTab', name);
        $$('.tab').forEach(t => t.classList.toggle('active', t.dataset.tab === name));
        $('blocks-list').classList.toggle('hidden', name !== 'blocks');
        $('json-view').classList.toggle('hidden', name !== 'json');
        $('md-view').classList.toggle('hidden', name !== 'markdown');
        $('tables-list').classList.toggle('hidden', name !== 'tables');
    }

    static render() {
        const list = $('blocks-list');
        const tablesList = $('tables-list');
        list.innerHTML = '';
        tablesList.innerHTML = '';

        const blocks = state.get('blocks');
        if (!blocks.length) {
            list.innerHTML = Blocks._emptyState('file-search', 'No blocks yet',
                'Upload a document and click Process OCR to extract structured content.');
            renderIcons();
            return;
        }

        const search = $('search-input').value.toLowerCase();
        const type = $('filter-type').value;
        const filtered = blocks.filter(b => {
            if (type !== 'all' && b.type !== type) return false;
            if (search && !((b.text || '') + ' ' + (b.id || '')).toLowerCase().includes(search)) return false;
            return true;
        });

        if (!filtered.length) {
            list.innerHTML = Blocks._emptyState('search-x', 'No matches', 'Try a different search or filter.');
            renderIcons();
            return;
        }

        filtered.forEach(b => list.appendChild(Blocks._buildCard(b)));

        const tables = blocks.filter(b => b.type === 'table');
        if (!tables.length) {
            tablesList.innerHTML = Blocks._emptyState('table-2', 'No tables detected',
                'This document does not contain tabular content.');
        } else {
            tables.forEach(t => tablesList.appendChild(Blocks._buildCard(t)));
        }
        renderIcons();
    }

    static _emptyState(icon, title, desc) {
        return `
            <div class="results-empty">
                <div class="empty-icon"><i data-lucide="${icon}"></i></div>
                <h3>${title}</h3>
                <p>${desc}</p>
            </div>
        `;
    }

    static _buildCard(b) {
        const card = document.createElement('div');
        card.className = 'block-card';
        card.dataset.id = b.id || '';
        if (b.id === state.get('activeBlockId')) card.classList.add('active');

        const conf = Math.round((b.confidence ?? 1) * 100);
        const confClass = conf >= 90 ? '' : conf >= 70 ? 'low' : 'crit';
        const coords = (b.bbox || []).length === 4
            ? `x:${b.bbox[0]} y:${b.bbox[1]} · ${b.bbox[2] - b.bbox[0]}×${b.bbox[3] - b.bbox[1]}`
            : '—';

        card.innerHTML = `
            <div class="block-head">
                <div class="block-meta">
                    <span class="badge ${b.type}"><i data-lucide="${TYPE_ICONS[b.type] || 'file'}"></i>${b.type}</span>
                    <span class="badge id">${b.id || ''}</span>
                </div>
                <span class="confidence ${confClass}"><i data-lucide="check-circle-2"></i>${conf}%</span>
            </div>
            <div class="block-text">${escapeHtml(b.text || b.html || '[No text content]')}</div>
            <div class="block-foot">
                <span class="block-coords"><i data-lucide="move"></i>${coords}</span>
                <div class="block-actions">
                    <button class="icon-btn" data-act="highlight" title="Highlight on image"><i data-lucide="crosshair"></i></button>
                    <button class="icon-btn" data-act="copy" title="Copy text"><i data-lucide="copy"></i></button>
                </div>
            </div>
        `;

        card.addEventListener('click', (e) => {
            const act = e.target.closest('[data-act]')?.dataset.act;
            if (act === 'copy') {
                copyText(b.text || '');
                e.stopPropagation();
                return;
            }
            state.set('activeBlockId', b.id);
            Viewer.drawBoxes(b.id);
            $$('.block-card').forEach(c => c.classList.toggle('active', c.dataset.id === b.id));
        });

        return card;
    }

    static updateCounts() {
        const blocks = state.get('blocks');
        const tables = blocks.filter(b => b.type === 'table');
        $('count-blocks').textContent = blocks.length;
        $('count-tables').textContent = tables.length;
    }
}

export { Blocks };
