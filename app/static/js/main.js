/**
 * Application entry point. Bootstraps all modules.
 */
import { renderIcons } from './ui.js';
import { DropzoneCtl } from './dropzone.js';
import { Header } from './header.js';
import { Blocks } from './blocks.js';
import { Exporter } from './export.js';
import { Processor } from './process.js';

function boot() {
    renderIcons();
    Header.init();
    DropzoneCtl.init();
    Blocks.init();
    Exporter.init();
    Processor.init();
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
} else {
    boot();
}
