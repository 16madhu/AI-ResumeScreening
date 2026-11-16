document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.password-toggle').forEach(toggle => {
    toggle.addEventListener('click', () => {
      const input = document.getElementById(toggle.dataset.target);
      if (!input) return;

      const showPassword = input.type === 'password';
      input.type = showPassword ? 'text' : 'password';
      toggle.textContent = showPassword ? 'Hide' : 'Show';
      toggle.setAttribute('aria-label', `${showPassword ? 'Hide' : 'Show'} password`);
      toggle.setAttribute('aria-pressed', String(showPassword));
    });
  });

  const form = document.querySelector('#login-form, #signup-form');
  if (!form) return;

  form.addEventListener('submit', async event => {
    event.preventDefault();

    const message = document.getElementById('msg');
    const submit = form.querySelector('[type="submit"]');
    const isSignup = form.id === 'signup-form';
    const values = Object.fromEntries(new FormData(form).entries());
    values.email = values.email.trim();

    if (isSignup && values.username.trim().length < 2) {
      message.textContent = 'Please enter a name with at least 2 characters.';
      message.dataset.state = 'error';
      return;
    }

    if (isSignup && values.password.length < 8) {
      message.textContent = 'Password must be at least 8 characters.';
      message.dataset.state = 'error';
      return;
    }
    if (isSignup) values.username = values.username.trim();

    message.textContent = '';
    message.dataset.state = '';
    submit.disabled = true;
    submit.textContent = isSignup ? 'Creating account…' : 'Signing in…';

    try {
      const response = await fetch(isSignup ? '/api/signup' : '/api/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(values)
      });
      const result = await response.json().catch(() => null);

      if (!result) {
        throw new Error('The server returned an invalid response. Please try again.');
      }
      if (!response.ok || !result.success) {
        throw new Error(result.error || 'Unable to complete your request.');
      }

      message.dataset.state = 'success';
      message.textContent = isSignup
        ? 'Account created. Redirecting to sign in…'
        : 'Signed in. Opening your dashboard…';
      window.setTimeout(() => {
        window.location.assign(isSignup ? '/login' : '/');
      }, isSignup ? 900 : 400);
    } catch (error) {
      message.dataset.state = 'error';
      message.textContent = error.message || 'Unable to connect. Please try again.';
      submit.disabled = false;
      submit.textContent = isSignup ? 'Create Account' : 'Sign In';
    }
  });
});
