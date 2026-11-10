const Nav = (() => {
    const API_BASE = location.protocol.startsWith('http') && location.port === '8000'
        ? location.origin
        : 'http://127.0.0.1:8000';
    const TOKEN_KEY = 'obama_nav_token';
    const PAGES = { map: 'index.html', login: 'login.html', register: 'register.html' };
    const NO_CONNECTION = 'Нет связи с сервером. Проверьте, что бэкенд запущен';

    function readToken() {
        try { return localStorage.getItem(TOKEN_KEY); } catch (e) { return null; }
    }

    function saveToken(token) {
        try {
            if (token) localStorage.setItem(TOKEN_KEY, token);
            else localStorage.removeItem(TOKEN_KEY);
        } catch (e) {}
    }

    async function api(path, { method = 'GET', body, signal } = {}) {
        const headers = {};
        if (body) headers['Content-Type'] = 'application/json';
        const token = readToken();
        if (token) headers.Authorization = `Bearer ${token}`;
        const res = await fetch(`${API_BASE}${path}`, {
            method, headers, signal, body: body ? JSON.stringify(body) : undefined
        });
        let data = null;
        try { data = await res.json(); } catch (e) {}
        return { ok: res.ok, status: res.status, data };
    }

    function errorText(res) {
        const detail = res.data && res.data.detail;
        return typeof detail === 'string' ? detail : 'Проверьте введённые данные';
    }

    function goTo(page) {
        location.replace(PAGES[page]);
    }

    async function redirectIfLoggedIn() {
        if (!readToken()) return;
        try {
            const me = await api('/auth/me');
            if (me.ok) goTo('map');
            else if (me.status === 401) saveToken(null);
        } catch (e) {}
    }

    function finishAuth(res) {
        if (res.ok && res.data && res.data.token) {
            saveToken(res.data.token);
            goTo('map');
            return null;
        }
        return errorText(res);
    }

    async function setupGoogle({ block, button, text, onError }) {
        try {
            const config = await api('/auth/config');
            const clientId = config.ok && config.data && config.data.google_client_id;
            if (!clientId) return;
            const script = document.createElement('script');
            script.src = 'https://accounts.google.com/gsi/client';
            script.async = true;
            script.onload = () => {
                if (!window.google || !google.accounts || !google.accounts.id) return;
                google.accounts.id.initialize({
                    client_id: clientId,
                    callback: async response => {
                        try {
                            const res = await api('/auth/google', {
                                method: 'POST', body: { credential: response.credential }
                            });
                            const err = finishAuth(res);
                            if (err) onError(err);
                        } catch (e) {
                            onError(NO_CONNECTION);
                        }
                    }
                });
                google.accounts.id.renderButton(button, {
                    theme: 'outline', size: 'large', text, locale: 'ru', width: 320
                });
                block.classList.remove('hidden');
            };
            document.head.appendChild(script);
        } catch (e) {}
    }

    return { api, readToken, saveToken, errorText, goTo, redirectIfLoggedIn, finishAuth, setupGoogle, NO_CONNECTION };
})();
