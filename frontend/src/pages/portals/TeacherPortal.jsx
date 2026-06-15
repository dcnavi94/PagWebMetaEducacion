import { Navigate, useNavigate } from 'react-router-dom';

const TeacherPortal = () => {
  const navigate = useNavigate();
  const token = localStorage.getItem('token');

  if (!token) {
    return <Navigate to="/login" replace />;
  }

  const handleLoad = (event) => {
    try {
      const pathname = event.currentTarget.contentWindow.location.pathname;
      if (pathname.endsWith('/login.html') || pathname === '/login') {
        navigate('/login', { replace: true });
      }
    } catch {
      // Ignored for cross-origin
    }
  };

  return (
    <iframe
      title="Aula Virtual Docente"
      src={`/portals/teacher.html?v=${Date.now()}`}
      onLoad={handleLoad}
      style={{
        position: 'fixed',
        inset: 0,
        width: '100%',
        height: '100%',
        border: 0,
        background: '#f8fafc',
        zIndex: 10000,
      }}
    />
  );
};

export default TeacherPortal;
