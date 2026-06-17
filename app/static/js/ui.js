/**
 * DOM helpers and icon renderer.
 */

/** Render all Lucide icons in the current document. */
export function renderIcons() {
    if (window.lucide) window.lucide.createIcons();
}

export const $ = (id) => document.getElementById(id);
export const $$ = (sel, root = document) => root.querySelectorAll(sel);

/** Escape unsafe HTML characters. */
export function escapeHtml(s) {
    return String(s)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

/** Show a toast notification. */
let toastTimer = null;
export function showToast(message, isError = false) {
    const t = $('toast');
    if (!t) return;
    $('toast-msg').textContent = message;
    t.classList.toggle('error', isError);
    let icon = t.querySelector('svg, i');
    if (!icon) {
        icon = document.createElement('i');
        t.insertBefore(icon, t.firstChild);
    }
    icon.setAttribute('data-lucide', isError ? 'alert-circle' : 'check-circle');
    // Reset the icon: replace with a fresh <i> so lucide re-renders the svg
    const fresh = document.createElement('i');
    fresh.setAttribute('data-lucide', isError ? 'alert-circle' : 'check-circle');
    icon.replaceWith(fresh);
    renderIcons();
    t.classList.add('show');
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(() => t.classList.remove('show'), 2200);
}

/** Copy text to clipboard. */
export async function copyText(text) {
    try {
        await navigator.clipboard.writeText(text);
        showToast('Copied to clipboard');
    } catch (e) {
        showToast('Copy failed', true);
    }
}

/** Trigger a browser download. */
export function downloadFile(filename, content, mime) {
    const blob = new Blob([content], { type: mime });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
    showToast(`Downloaded ${filename}`);
}
