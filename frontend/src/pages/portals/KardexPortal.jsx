import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';

export default function KardexPortal() {
  const navigate = useNavigate();
  const [profile, setProfile] = useState(null);
  const [kardex, setKardex] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem('token');
    if (!token) {
      navigate('/login');
      return;
    }

    const fetchData = async () => {
      try {
        const [profileRes, kardexRes] = await Promise.all([
          fetch('/api/users/me/profile', { headers: { Authorization: `Bearer ${token}` } }),
          fetch('/api/users/me/kardex-summary', { headers: { Authorization: `Bearer ${token}` } })
        ]);

        if (profileRes.ok && kardexRes.ok) {
          setProfile(await profileRes.json());
          setKardex(await kardexRes.json());
        }
      } catch (error) {
        console.error('Error fetching Kardex data:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [navigate]);

  if (loading) {
    return (
      <div className="d-flex justify-content-center align-items-center vh-100" style={{ background: '#eef4ff' }}>
        <div className="spinner-border text-primary" role="status">
          <span className="visually-hidden">Cargando...</span>
        </div>
      </div>
    );
  }

  const { gpa, earned_credits, total_career_credits, progress_percentage, history } = kardex || {};

  // Group history by semester/cycle
  const historyByPeriod = (history || []).reduce((acc, item) => {
    const period = item.semester || item.cycle || 'Sin Periodo';
    if (!acc[period]) acc[period] = [];
    acc[period].push(item);
    return acc;
  }, {});

  // Sort periods logically if possible
  const sortedPeriods = Object.keys(historyByPeriod).sort();

  return (
    <div style={{ background: 'linear-gradient(135deg, #eef4ff 0%, #dbe7ff 100%)', minHeight: '100vh', padding: '2rem 1rem' }}>
      <div className="container" style={{ maxWidth: '1000px' }}>
        
        {/* Header */}
        <div className="d-flex align-items-center justify-content-between mb-4">
          <button className="btn btn-light rounded-circle shadow-sm" onClick={() => navigate('/campus-virtual')} style={{ width: '45px', height: '45px' }}>
            <i className="bi bi-arrow-left text-primary fs-5"></i>
          </button>
          <h2 className="mb-0 fw-bold" style={{ color: '#0b2673' }}>Historial Académico</h2>
          <div style={{ width: '45px' }}></div> {/* Spacer for centering */}
        </div>

        {/* Profile Info */}
        <div className="card border-0 shadow-sm mb-4" style={{ borderRadius: '20px', background: 'rgba(255, 255, 255, 0.85)', backdropFilter: 'blur(10px)' }}>
          <div className="card-body p-4 d-flex align-items-center gap-3">
            <div className="bg-primary text-white rounded-circle d-flex align-items-center justify-content-center" style={{ width: '60px', height: '60px', fontSize: '1.5rem' }}>
              <i className="bi bi-person-fill"></i>
            </div>
            <div>
              <h4 className="mb-1 fw-bold text-dark">{profile?.full_name || 'Alumno'}</h4>
              <p className="mb-0 text-muted">
                {profile?.career_name || 'Carrera no especificada'} • {profile?.modality_name || ''}
              </p>
            </div>
          </div>
        </div>

        {/* Summary Metrics */}
        <div className="row g-4 mb-5">
          <div className="col-md-4">
            <div className="card border-0 shadow-sm h-100" style={{ borderRadius: '20px', background: 'linear-gradient(135deg, #1141b8 0%, #0b2673 100%)', color: 'white' }}>
              <div className="card-body p-4 text-center">
                <i className="bi bi-award fs-1 opacity-75 mb-2 d-block"></i>
                <h5 className="fw-normal opacity-75 mb-1">Promedio General</h5>
                <h1 className="fw-bold display-4 mb-0">{gpa?.toFixed(2) || '0.00'}</h1>
              </div>
            </div>
          </div>
          
          <div className="col-md-8">
            <div className="card border-0 shadow-sm h-100" style={{ borderRadius: '20px', background: 'rgba(255, 255, 255, 0.9)' }}>
              <div className="card-body p-4 d-flex flex-column justify-content-center">
                <div className="d-flex justify-content-between align-items-end mb-2">
                  <div>
                    <h5 className="fw-bold mb-1" style={{ color: '#0b2673' }}>Avance de la Carrera</h5>
                    <p className="text-muted mb-0 small">{earned_credits} de {total_career_credits} créditos aprobados</p>
                  </div>
                  <h3 className="fw-bold text-primary mb-0">{progress_percentage}%</h3>
                </div>
                <div className="progress mt-3" style={{ height: '14px', borderRadius: '10px', backgroundColor: 'rgba(17,65,184,0.1)' }}>
                  <div className="progress-bar progress-bar-striped progress-bar-animated bg-primary" role="progressbar" style={{ width: `${progress_percentage}%`, borderRadius: '10px' }} aria-valuenow={progress_percentage} aria-valuemin="0" aria-valuemax="100"></div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Academic History Table/Grid */}
        <h4 className="fw-bold mb-4" style={{ color: '#0b2673' }}>Detalle de Materias</h4>
        
        {sortedPeriods.length === 0 ? (
          <div className="text-center py-5">
            <i className="bi bi-folder-x fs-1 text-muted"></i>
            <p className="mt-3 text-muted">No se encontró historial académico.</p>
          </div>
        ) : (
          sortedPeriods.map(period => (
            <div key={period} className="mb-4">
              <h5 className="fw-bold mb-3 ms-2" style={{ color: '#667085' }}>
                <i className="bi bi-calendar3 me-2"></i>{period}
              </h5>
              <div className="card border-0 shadow-sm" style={{ borderRadius: '16px', overflow: 'hidden' }}>
                <div className="table-responsive mb-0">
                  <table className="table table-hover align-middle mb-0" style={{ fontSize: '0.95rem' }}>
                    <thead style={{ background: 'rgba(17,65,184,0.03)' }}>
                      <tr>
                        <th className="border-0 text-muted fw-semibold py-3 px-4">Materia</th>
                        <th className="border-0 text-muted fw-semibold py-3 text-center">Créditos</th>
                        <th className="border-0 text-muted fw-semibold py-3 text-center">Calificación</th>
                        <th className="border-0 text-muted fw-semibold py-3 px-4 text-end">Estatus</th>
                      </tr>
                    </thead>
                    <tbody>
                      {historyByPeriod[period].map((item, idx) => (
                        <tr key={idx}>
                          <td className="py-3 px-4 fw-medium text-dark">{item.subject_name || 'Materia desconocida'}</td>
                          <td className="py-3 text-center text-muted">{item.credits || 8}</td>
                          <td className="py-3 text-center">
                            <span className={`fw-bold ${item.final_score >= 6 ? 'text-primary' : (item.final_score ? 'text-danger' : 'text-muted')}`}>
                              {item.final_score !== null ? item.final_score.toFixed(1) : '-'}
                            </span>
                          </td>
                          <td className="py-3 px-4 text-end">
                            {item.status === 'Aprobada' ? (
                              <span className="badge rounded-pill bg-success bg-opacity-10 text-success px-3 py-2">Aprobada</span>
                            ) : item.status === 'Reprobada' ? (
                              <span className="badge rounded-pill bg-danger bg-opacity-10 text-danger px-3 py-2">Reprobada</span>
                            ) : (
                              <span className="badge rounded-pill bg-warning bg-opacity-10 text-warning px-3 py-2">{item.status || 'Cursando'}</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          ))
        )}

      </div>
    </div>
  );
}
