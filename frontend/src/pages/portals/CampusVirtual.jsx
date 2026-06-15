import { Navigate, useNavigate } from 'react-router-dom';

const CampusVirtual = () => {
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
      // Cross-origin Moodle pages cannot be inspected and should remain untouched.
    }
  };

  return (
    <iframe
      title="Aula Virtual del Alumno"
      src={`/portals/campus-virtual.html?v=${Date.now()}`}
      onLoad={handleLoad}
      style={{
        position: 'fixed',
        inset: 0,
        width: '100%',
        height: '100%',
        border: 0,
        background: '#eef4ff',
        zIndex: 10000,
      }}
    />
  );
};

export default CampusVirtual;
