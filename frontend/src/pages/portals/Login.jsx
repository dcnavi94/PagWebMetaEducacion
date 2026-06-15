import { useEffect, useRef, useContext } from 'react';
import { AuthContext } from '../../contexts/AuthContext';
import { useNavigate, Navigate } from 'react-router-dom';
import { LoginHtml } from './LoginContent';

const Login = () => {
  const { login, user } = useContext(AuthContext);
  const navigate = useNavigate();
  const containerRef = useRef(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const loginForm = container.querySelector('#loginForm');
    const errorBox = container.querySelector('#errorMessage');
    const errorText = container.querySelector('#errorText');
    const btnLogin = container.querySelector('#btnLogin');
    const btnText = container.querySelector('.btn-text');
    const btnLoading = container.querySelector('.btn-loading');
    const togglePw = container.querySelector('#togglePw');
    const toggleIcon = container.querySelector('#togglePwIcon');
    const pwInput = container.querySelector('#password');
    const usernameInput = container.querySelector('#username');

    if (!loginForm) return;

    const setLoading = (loading) => {
      if (loading) {
        btnText.classList.add('d-none');
        btnLoading.classList.remove('d-none');
        btnLogin.disabled = true;
      } else {
        btnText.classList.remove('d-none');
        btnLoading.classList.add('d-none');
        btnLogin.disabled = false;
      }
    };

    const showError = (msg) => {
      if (!errorText || !errorBox) return;
      errorText.textContent = msg;
      errorBox.style.display = 'flex';
      errorBox.style.animation = 'none';
      requestAnimationFrame(() => { errorBox.style.animation = ''; });
    };

    const handleTogglePw = () => {
      if (!pwInput || !toggleIcon) return;
      const isText = pwInput.type === 'text';
      pwInput.type = isText ? 'password' : 'text';
      toggleIcon.className = isText ? 'bi bi-eye' : 'bi bi-eye-slash';
    };

    const handleSubmit = async (e) => {
      e.preventDefault();
      if (errorBox) errorBox.style.display = 'none';
      setLoading(true);

      const username = usernameInput.value.trim();
      const password = pwInput.value;

      try {
        await login(username, password);
        window.location.reload();
      } catch (err) {
        const apiMessage =
          err?.response?.data?.error?.message ||
          err?.response?.data?.detail ||
          err?.response?.data?.message;
        const status = err?.response?.status;
        const fallback = status === 429
          ? 'Demasiados intentos. Espera unos minutos e intenta nuevamente.'
          : status >= 500
            ? 'El servidor no pudo iniciar sesión. Intenta nuevamente.'
            : 'Credenciales incorrectas. Verifica tu usuario y contraseña.';
        showError(typeof apiMessage === 'string' ? apiMessage : fallback);
      } finally {
        setLoading(false);
      }
    };

    togglePw?.addEventListener('click', handleTogglePw);
    loginForm.addEventListener('submit', handleSubmit);

    return () => {
      togglePw?.removeEventListener('click', handleTogglePw);
      loginForm.removeEventListener('submit', handleSubmit);
    };
  }, [login, navigate]);

  // If already logged in, redirect based on role
  if (user && localStorage.getItem('token')) {
    if (user.role === 'admin') { return <Navigate to="/admin" replace />; }
    if (user.role === 'teacher') { return <Navigate to="/teacher" replace />; }
    return <Navigate to="/campus-virtual" replace />;
  }


  return (
    <div ref={containerRef} dangerouslySetInnerHTML={{ __html: LoginHtml }} />
  );
};

export default Login;
