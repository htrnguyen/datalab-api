/**
 * Centralized application state.
 */
class AppState {
    constructor() {
        this._state = {
            filename: null,
            image: null,
            imageSize: { w: 0, h: 0 },
            pages: [],
            pageIndex: 0,
            pageCount: 1,
            pageSizes: [],
            documentType: 'image',
            blocks: [],
            result: null,
            activeTab: 'blocks',
            activeBlockId: null,
            zoom: 1,
            drawBBox: true,
        };
        this._listeners = new Map();
    }

    get(key) {
        if (key === undefined) return { ...this._state };
        return this._state[key];
    }

    set(key, value) {
        const old = this._state[key];
        if (old === value) return;
        this._state[key] = value;
        this._emit(key, value, old);
    }

    update(patch) {
        Object.entries(patch).forEach(([k, v]) => this.set(k, v));
    }

    on(key, fn) {
        if (!this._listeners.has(key)) this._listeners.set(key, new Set());
        this._listeners.get(key).add(fn);
        return () => this._listeners.get(key).delete(fn);
    }

    _emit(key, value, old) {
        const set = this._listeners.get(key);
        if (!set) return;
        set.forEach(fn => fn(value, old));
    }
}

export const state = new AppState();
