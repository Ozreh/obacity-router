const form = document.getElementById('form');
const nameInput = document.getElementById('name');
const emailInput = document.getElementById('email');
const passwordInput = document.getElementById('password');
const password2Input = document.getElementById('password2');
const errorBox = document.getElementById('error');
const submitBtn = document.getElementById('submit');

const PASSWORD_MIN_LEN = 8;
let busy = false;

function setError(text) {
    errorBox.textContent = text || '';
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
    if (password.length < PASSWORD_MIN_LEN) {
        setError(`Пароль должен быть не короче ${PASSWORD_MIN_LEN} символов`);
        return;
    }
    if (password !== password2Input.value) {
        setError('Пароли не совпадают');
        return;
    }
    busy = true;
    submitBtn.disabled = true;
    setError('');
    try {
        const res = await Nav.api('/auth/register', {
            method: 'POST',
            body: { email, password, name: nameInput.value.trim() }
        });
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
    text: 'signup_with',
    onError: setError
});
