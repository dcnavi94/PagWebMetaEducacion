import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import './PerfilPortal.css';

export default function PerfilPortal() {
  const navigate = useNavigate();
  const fileInputRef = useRef(null);

  const [profile, setProfile] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState({ text: '', type: '' });

  // Form states
  const [phone, setPhone] = useState('');
  const [altEmail, setAltEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [avatar, setAvatar] = useState(null);

  // Preferences states
  const [darkMode, setDarkMode] = useState(false);
  const [emailAlerts, setEmailAlerts] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem('token');
    if (!token) {
      navigate('/login');
      return;
    }

    // Load from local storage mocks
    setPhone(localStorage.getItem('user_phone') || '');
    setAltEmail(localStorage.getItem('user_alt_email') || '');
    setAvatar(localStorage.getItem('user_avatar') || null);
    setDarkMode(localStorage.getItem('user_dark_mode') === 'true');
    setEmailAlerts(localStorage.getItem('user_email_alerts') !== 'false');

    const fetchProfile = async () => {
      try {
        const res = await fetch('/api/users/me/profile', {
          headers: { Authorization: `Bearer ${token}` }
        });
        if (res.ok) {
          setProfile(await res.json());
        }
      } catch (error) {
        console.error('Error fetching Profile data:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchProfile();
  }, [navigate]);

  useEffect(() => {
    if (darkMode) {
      document.body.classList.add('dark-mode');
    } else {
      document.body.classList.remove('dark-mode');
    }
  }, [darkMode]);

  const showToast = (text, type = 'success') => {
    setMessage({ text, type });
    setTimeout(() => setMessage({ text: '', type: '' }), 4000);
  };

  const handleAvatarChange = (e) => {
    const file = e.target.files[0];
    if (file) {
      const reader = new FileReader();
      reader.onloadend = () => {
        setAvatar(reader.result);
        localStorage.setItem('user_avatar', reader.result);
        showToast('Foto de perfil actualizada exitosamente.');
      };
      reader.readAsDataURL(file);
    }
  };

  const savePersonalInfo = (e) => {
    e.preventDefault();
    localStorage.setItem('user_phone', phone);
    localStorage.setItem('user_alt_email', altEmail);
    showToast('Información de contacto guardada exitosamente.');
  };

  const toggleDarkMode = () => {
    const val = !darkMode;
    setDarkMode(val);
    localStorage.setItem('user_dark_mode', val);
  };

  const toggleEmailAlerts = () => {
    const val = !emailAlerts;
    setEmailAlerts(val);
    localStorage.setItem('user_email_alerts', val);
  };

  const saveSecurity = async (e) => {
    e.preventDefault();
    if (password !== confirmPassword) {
      showToast('Las contraseñas no coinciden.', 'danger');
      return;
    }
    if (password.length < 6) {
      showToast('La contraseña debe tener al menos 6 caracteres.', 'danger');
      return;
    }

    setSaving(true);
    const token = localStorage.getItem('token');
    try {
      const res = await fetch('/api/users/me', {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ password })
      });
      if (res.ok) {
        showToast('Contraseña actualizada correctamente.');
        setPassword('');
        setConfirmPassword('');
      } else {
        showToast('Error al actualizar la contraseña.', 'danger');
      }
    } catch (error) {
      console.error(error);
      showToast('Error de conexión.', 'danger');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="d-flex justify-content-center align-items-center vh-100" style={{ background: '#f8f9fa' }}>
        <div className="spinner-border text-primary" role="status">
          <span className="visually-hidden">Cargando perfil...</span>
        </div>
      </div>
    );
  }

  return (
    <div className={`profile-page min-vh-100 transition-all ${darkMode ? 'bg-dark text-light' : 'text-dark'}`} style={{ background: darkMode ? '#121212' : 'linear-gradient(135deg, #fdfbfb 0%, #ebedee 100%)' }}>
      <div className="container profile-container py-4 py-md-5 px-3 px-md-4">
        
        {/* Toast Notification */}
        {message.text && (
          <div className={`profile-toast alert alert-${message.type} alert-dismissible fade show position-fixed top-0 end-0 m-3 shadow`} role="alert">
            <i className={`bi ${message.type === 'success' ? 'bi-check-circle-fill' : 'bi-exclamation-triangle-fill'} me-2`}></i>
            <span className="small d-inline-block">{message.text}</span>
            <button type="button" className="btn-close" onClick={() => setMessage({ text: '', type: '' })}></button>
          </div>
        )}

        {/* Header */}
        <div className="profile-header d-flex align-items-center justify-content-between mb-4 mb-md-5">
          <button className={`profile-back btn rounded-circle shadow-sm d-flex align-items-center justify-content-center ${darkMode ? 'btn-outline-light' : 'btn-light'}`} onClick={() => navigate('/campus-virtual')} aria-label="Volver al campus">
            <i className="bi bi-arrow-left fs-5"></i>
          </button>
          <h1 className="profile-title mb-0 fw-bold text-center px-2"><i className="bi bi-person-circle me-2 text-primary"></i>Mi Perfil</h1>
          <div className="profile-header-spacer" aria-hidden="true"></div>
        </div>

        <div className="row g-4">
          
          {/* Left Column: Avatar & Preferences */}
          <div className="col-12 col-lg-4">
            {/* Avatar Card */}
            <div className="profile-card card border-0 shadow-sm mb-4 text-center" style={{ background: darkMode ? '#1e1e1e' : 'rgba(255, 255, 255, 0.9)', backdropFilter: 'blur(10px)' }}>
              <div className="card-body profile-card-body p-4 p-md-5">
                <div className="profile-avatar-wrap position-relative d-inline-block mb-3">
                  {avatar ? (
                    <img src={avatar} alt="Avatar" className="profile-avatar rounded-circle object-fit-cover border border-4 border-white shadow-sm" />
                  ) : (
                    <div className="profile-avatar rounded-circle bg-primary text-white d-flex align-items-center justify-content-center shadow-sm mx-auto">
                      {profile?.full_name?.charAt(0) || 'A'}
                    </div>
                  )}
                  <button onClick={() => fileInputRef.current.click()} className="profile-camera btn btn-primary rounded-circle position-absolute shadow d-flex align-items-center justify-content-center" aria-label="Cambiar foto de perfil">
                    <i className="bi bi-camera-fill fs-6"></i>
                  </button>
                  <input type="file" accept="image/*" ref={fileInputRef} onChange={handleAvatarChange} className="d-none" />
                </div>
                <h2 className="profile-name fw-bold mb-1">{profile?.full_name}</h2>
                <p className={`profile-identity small mb-0 ${darkMode ? 'text-light opacity-75' : 'text-muted'}`}>{profile?.username} • {profile?.role?.toUpperCase()}</p>
                <div className="mt-3">
                  <span className={`badge rounded-pill ${profile?.user_status === 'Activo' ? 'bg-success bg-opacity-10 text-success' : 'bg-secondary bg-opacity-10 text-secondary'} px-3 py-2 small`}>
                    Estatus: {profile?.user_status || 'Activo'}
                  </span>
                </div>
              </div>
            </div>

            {/* Preferences Card */}
            <div className="profile-card card border-0 shadow-sm" style={{ background: darkMode ? '#1e1e1e' : 'rgba(255, 255, 255, 0.9)' }}>
              <div className="card-body profile-card-body p-4">
                <h5 className="fw-bold mb-4 fs-5"><i className="bi bi-sliders me-2 text-primary"></i>Preferencias</h5>
                
                <div className="d-flex justify-content-between align-items-center mb-3">
                  <div>
                    <h6 className="mb-0 fw-medium fs-6">Modo Oscuro</h6>
                    <small className={`${darkMode ? 'text-light opacity-50' : 'text-muted'}`} style={{ fontSize: '0.8rem' }}>Diseño visual adaptativo</small>
                  </div>
                  <div className="form-check form-switch fs-5 m-0">
                    <input className="form-check-input shadow-none m-0" type="checkbox" role="switch" checked={darkMode} onChange={toggleDarkMode} />
                  </div>
                </div>

                <div className="d-flex justify-content-between align-items-center">
                  <div>
                    <h6 className="mb-0 fw-medium fs-6">Notificaciones</h6>
                    <small className={`${darkMode ? 'text-light opacity-50' : 'text-muted'}`} style={{ fontSize: '0.8rem' }}>Alertas a correo personal</small>
                  </div>
                  <div className="form-check form-switch fs-5 m-0">
                    <input className="form-check-input shadow-none m-0" type="checkbox" role="switch" checked={emailAlerts} onChange={toggleEmailAlerts} />
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Right Column: Forms */}
          <div className="col-12 col-lg-8">
            
            {/* Contact Info Form */}
            <div className="profile-card card border-0 shadow-sm mb-4" style={{ background: darkMode ? '#1e1e1e' : 'rgba(255, 255, 255, 0.9)' }}>
              <div className="card-body profile-card-body p-4 p-md-5">
                <h5 className="fw-bold mb-4 fs-5"><i className="bi bi-info-circle-fill me-2 text-primary"></i>Datos de Contacto</h5>
                <form onSubmit={savePersonalInfo}>
                  <div className="row g-3">
                    <div className="col-12 col-md-6">
                      <label className={`form-label small fw-medium ${darkMode ? 'text-light' : 'text-secondary'}`}>Correo Institucional (Solo lectura)</label>
                      <input type="email" className={`form-control ${darkMode ? 'bg-dark text-light border-secondary' : 'bg-light border-0'}`} value={profile?.email || ''} readOnly />
                    </div>
                    <div className="col-12 col-md-6">
                      <label className={`form-label small fw-medium ${darkMode ? 'text-light' : 'text-secondary'}`}>Teléfono / Móvil</label>
                      <input type="tel" className={`form-control shadow-none ${darkMode ? 'bg-dark text-light border-secondary' : ''}`} placeholder="Ej. 55 1234 5678" value={phone} onChange={e => setPhone(e.target.value)} />
                    </div>
                    <div className="col-12">
                      <label className={`form-label small fw-medium ${darkMode ? 'text-light' : 'text-secondary'}`}>Correo Personal Alternativo</label>
                      <input type="email" className={`form-control shadow-none ${darkMode ? 'bg-dark text-light border-secondary' : ''}`} placeholder="correo@ejemplo.com" value={altEmail} onChange={e => setAltEmail(e.target.value)} />
                    </div>
                  </div>
                  <div className="profile-form-actions mt-4 text-end">
                    <button type="submit" className="btn btn-primary px-4 rounded-pill fw-medium shadow-sm">Guardar Datos</button>
                  </div>
                </form>
              </div>
            </div>

            {/* Security Form */}
            <div className="profile-card card border-0 shadow-sm" style={{ background: darkMode ? '#1e1e1e' : 'rgba(255, 255, 255, 0.9)' }}>
              <div className="card-body profile-card-body p-4 p-md-5">
                <h5 className="fw-bold mb-4 text-danger fs-5"><i className="bi bi-shield-lock-fill me-2"></i>Seguridad y Contraseña</h5>
                <form onSubmit={saveSecurity}>
                  <div className="row g-3">
                    <div className="col-12 col-md-6">
                      <label className={`form-label small fw-medium ${darkMode ? 'text-light' : 'text-secondary'}`}>Nueva Contraseña</label>
                      <input type="password" required className={`form-control shadow-none ${darkMode ? 'bg-dark text-light border-secondary' : ''}`} placeholder="Mínimo 6 caracteres" value={password} onChange={e => setPassword(e.target.value)} />
                    </div>
                    <div className="col-12 col-md-6">
                      <label className={`form-label small fw-medium ${darkMode ? 'text-light' : 'text-secondary'}`}>Confirmar Nueva Contraseña</label>
                      <input type="password" required className={`form-control shadow-none ${darkMode ? 'bg-dark text-light border-secondary' : ''}`} placeholder="Repita la contraseña" value={confirmPassword} onChange={e => setConfirmPassword(e.target.value)} />
                    </div>
                  </div>
                  <div className="profile-security-actions mt-4 d-flex flex-column flex-md-row justify-content-between align-items-md-center gap-3">
                    <small className={`${darkMode ? 'text-light opacity-50' : 'text-muted'} order-2 order-md-1 text-center text-md-start`} style={{ fontSize: '0.8rem' }}>Se cerrará tu sesión si tienes dispositivos no autorizados.</small>
                    <button type="submit" className="btn btn-danger px-4 rounded-pill fw-medium shadow-sm order-1 order-md-2" disabled={saving}>
                      {saving ? 'Actualizando...' : 'Actualizar Contraseña'}
                    </button>
                  </div>
                </form>
              </div>
            </div>

          </div>
        </div>
      </div>
    </div>
  );
}
