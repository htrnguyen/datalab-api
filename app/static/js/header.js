/**
 * Header controls: toggles, fullscreen.
 */
import { $, renderIcons } from './ui.js';
import { state } from './state.js';

class Header {
    static init() {
        Header._bindToggle('toggle-refine', 'refine');
        Header._bindToggle('toggle-bbox', 'drawBBox');

        $('btn-fullscreen').addEventListener('click', () => {
            const app = document.getElementById('app');
            app.classList.toggle('fullscreen');
            const isFs = app.classList.contains('fullscreen');
            const btn = $('btn-fullscreen');
            const oldIcon = btn.querySelector('svg, i');
            const fresh = document.createElement('i');
            fresh.setAttribute('data-lucide', isFs ? 'minimize-2' : 'maximize-2');
            if (oldIcon) oldIcon.replaceWith(fresh); else btn.prepend(fresh);
            renderIcons();
        });

        // Add fullscreen CSS dynamically
        if (!document.getElementById('fs-style')) {
            const style = document.createElement('style');
            style.id = 'fs-style';
            style.textContent = `
                .fullscreen .topbar,
                .fullscreen .page-head,
                .fullscreen .kpi-grid,
                .fullscreen .results,
                .fullscreen .card-head,
                .fullscreen .results-toolbar,
                .fullscreen .tabs,
                .fullscreen .results-list { display: none; }
                .fullscreen .workspace { grid-template-columns: 1fr; }
                .fullscreen .viewer { min-height: calc(100vh - 80px); }
            `;
            document.head.appendChild(style);
        }
    }

    static _bindToggle(id, stateKey) {
        const el = $(id);
        if (!el) return;
        el.checked = state.get(stateKey) !== false;
        el.addEventListener('change', () => {
            state.set(stateKey, el.checked);
        });
    }
}

export { Header };
