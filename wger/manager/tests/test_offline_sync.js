const assert = require('assert');

// Mock browser globals for Node test
const storage = {};
global.localStorage = {
  getItem: (k) => storage[k] || null,
  setItem: (k, v) => { storage[k] = v; },
  removeItem: (k) => { delete storage[k]; },
  length: 0,
  key: (i) => Object.keys(storage)[i]
};
global.navigator = { onLine: true };
global.document = {
  querySelector: () => ({ value: 'dom_csrf_123' }),
  getElementById: () => null,
  cookie: 'csrftoken=cookie_csrf_456'
};

const OnyxOfflineSync = {
    QUEUE_KEY: 'onyx_offline_sync_queue',
    MAX_QUEUE_ITEMS: 100,
    MAX_RETRIES: 5,
    _syncing: false,

    generateClientId() {
        if (typeof crypto !== 'undefined' && crypto.randomUUID) {
            return crypto.randomUUID();
        }
        return 'cid_' + Date.now() + '_' + Math.random().toString(36).substring(2, 10);
    },

    _pruneStaleStorage() {
        try {
            const stalePrefixes = ['onyx_workout_start_', 'workout_draft_day_', 'onyx_active_workout_snapshot'];
            Object.keys(storage).forEach(key => {
                if (key && stalePrefixes.some(p => key.startsWith(p))) {
                    delete storage[key];
                }
            });
        } catch (e) {}
    },

    getQueue() {
        try {
            return JSON.parse(localStorage.getItem(this.QUEUE_KEY) || '[]');
        } catch(e) {
            return [];
        }
    },

    setQueue(queue) {
        try {
            const trimmed = Array.isArray(queue) ? queue.slice(-this.MAX_QUEUE_ITEMS) : [];
            localStorage.setItem(this.QUEUE_KEY, JSON.stringify(trimmed));
        } catch (err) {
            if (err.name === 'QuotaExceededError' || err.code === 22) {
                this._pruneStaleStorage();
                try {
                    const trimmed = Array.isArray(queue) ? queue.slice(-Math.floor(this.MAX_QUEUE_ITEMS / 2)) : [];
                    localStorage.setItem(this.QUEUE_KEY, JSON.stringify(trimmed));
                } catch (e) {
                    console.error('LocalStorage quota exceeded after prune:', e);
                }
            }
        }
        this.updateBadge();
    },

    removeItemFromQueue(itemId) {
        const q = this.getQueue().filter(item => item.id !== itemId);
        this.setQueue(q);
    },

    getActiveCsrfToken() {
        const formToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value;
        if (formToken) return formToken;
        const match = (document.cookie || '').match(/csrftoken=([\w-]+)/);
        if (match && match[1]) return match[1];
        return '';
    },

    async fetchFreshCsrfToken() {
        return this.getActiveCsrfToken();
    },

    enqueue(entry) {
        const queue = this.getQueue();
        const clientId = entry.clientId || entry.data?.client_id || this.generateClientId();
        const data = entry.data || {};
        data.client_id = clientId;

        const item = {
            ...entry,
            id: 'sync_' + Date.now() + '_' + Math.random().toString(36).substring(2, 8),
            clientId: clientId,
            data: data,
            retryCount: 0,
            queuedAt: Date.now()
        };
        queue.push(item);
        this.setQueue(queue);
        this.showBanner('offline', `Offline • ${queue.length} serie salvata${queue.length > 1 ? 'e' : ''} in locale`);
        return item;
    },

    reconcileSetUI(item, status) {},
    showBanner(status, text) {},
    hideBanner() {},
    updateBadge() {}
};

// Tests
const item1 = OnyxOfflineSync.enqueue({ url: '/test', data: { slot_entry_id: 10 } });
assert.strictEqual(OnyxOfflineSync.getQueue().length, 1);
assert.ok(item1.clientId, 'Must have client_id');
assert.strictEqual(item1.data.client_id, item1.clientId);

OnyxOfflineSync.removeItemFromQueue(item1.id);
assert.strictEqual(OnyxOfflineSync.getQueue().length, 0);

console.log('OnyxOfflineSync unit test PASSED!');
