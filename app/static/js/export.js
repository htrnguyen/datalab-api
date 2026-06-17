/**
 * Export module - JSON / Markdown / TXT download + copy.
 */
import { $, $$, downloadFile, copyText, showToast } from './ui.js';
import { state } from './state.js';

class Exporter {
    static init() {
        const dd = $('export-dropdown');
        $('btn-export').addEventListener('click', (e) => {
            e.stopPropagation();
            dd.classList.toggle('open');
        });
        document.addEventListener('click', () => dd.classList.remove('open'));
        $$('.dropdown-item').forEach(item => {
            item.addEventListener('click', (e) => {
                e.stopPropagation();
                Exporter.handle(item.dataset.export);
                dd.classList.remove('open');
            });
        });
    }

    static handle(type) {
        const result = state.get('result');
        if (!result) { showToast('No data to export', true); return; }
        const filename = (state.get('filename') || 'document').replace(/\.[^.]+$/, '');

        if (type === 'json') {
            downloadFile(`${filename}.json`, JSON.stringify(result, null, 2), 'application/json');
        } else if (type === 'markdown') {
            downloadFile(`${filename}.md`, Exporter.toMarkdown(), 'text/markdown');
        } else if (type === 'txt') {
            downloadFile(`${filename}.txt`, result.text || '', 'text/plain');
        } else if (type === 'copy') {
            copyText(result.text || '');
        }
    }

    static toMarkdown() {
        return state.get('blocks').map(b => {
            if (b.type === 'text') return b.text || '';
            if (b.type === 'table') return `\n${b.html || ''}\n`;
            if (b.type === 'image') return `![image](${b.id})`;
            return '';
        }).join('\n\n');
    }
}

export { Exporter };
