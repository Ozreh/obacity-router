const form = document.getElementById('form');
const emailInput = document.getElementById('email');
const passwordInput = document.getElementById('password');
const errorBox = document.getElementById('error');
const submitBtn = document.getElementById('submit');
const infoBox = document.getElementById('info');

let busy = false;

function setError(text) {
    errorBox.textContent = text || '';
}

if (new URLSearchParams(location.search).get('reason') === 'expired') {
    infoBox.textContent = 'Сессия истекла, войдите снова';
    infoBox.classList.remove('hidden');
}

form.addEventListener('submit', async e => {
    e.preventDefault();
    if (busy) return;
    const email = emailInput.value.trim();
    const password = passwordInput.value;
    if (!email || !password) {
        setError('Введите email и пароль');
        return;
    }
    busy = true;
    submitBtn.disabled = true;
    setError('');
    try {
        const res = await Nav.api('/auth/login', { method: 'POST', body: { email, password } });
        const err = Nav.finishAuth(res);
        if (err) setError(err);
    } catch (err) {
        setError(Nav.NO_CONNECTION);
    } finally {
        busy = false;
        submitBtn.disabled = false;
    }
});

Nav.redirectIfLoggedIn();
Nav.setupGoogle({
    block: document.getElementById('googleBlock'),
    button: document.getElementById('googleBtn'),
    text: 'signin_with',
    onError: setError
});
