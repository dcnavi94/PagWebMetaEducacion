import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';

export default function CalendarioPortal() {
  const navigate = useNavigate();
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('all');

  useEffect(() => {
    const token = localStorage.getItem('token');
    if (!token) {
      navigate('/login');
      return;
    }

    const fetchEvents = async () => {
      try {
        const res = await fetch('/api/users/me/calendar', {
          headers: { Authorization: `Bearer ${token}` }
        });
        if (res.ok) {
          const data = await res.json();
          // Sort by date
          data.sort((a, b) => new Date(a.date) - new Date(b.date));
          setEvents(data);
        }
      } catch (error) {
        console.error('Error fetching Calendar data:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchEvents();
  }, [navigate]);

  if (loading) {
    return (
      <div className="d-flex justify-content-center align-items-center vh-100" style={{ background: '#f8f9fa' }}>
        <div className="spinner-border text-primary" role="status">
          <span className="visually-hidden">Cargando calendario...</span>
        </div>
      </div>
    );
  }

  // Determine styles for categories
  const categoryStyles = {
    exam: { color: '#e74c3c', bg: 'rgba(231, 76, 60, 0.1)', icon: 'bi-pencil-square', label: 'Exámenes' },
    payment: { color: '#2ecc71', bg: 'rgba(46, 204, 113, 0.1)', icon: 'bi-cash-coin', label: 'Pagos' },
    enrollment: { color: '#3498db', bg: 'rgba(52, 152, 219, 0.1)', icon: 'bi-journal-check', label: 'Inscripciones' },
    holiday: { color: '#9b59b6', bg: 'rgba(155, 89, 182, 0.1)', icon: 'bi-calendar-x', label: 'Feriado / Suspensión' },
  };

  // Filter events
  const filteredEvents = events.filter(ev => filter === 'all' || ev.category === filter);

  // Group by month
  const eventsByMonth = filteredEvents.reduce((acc, ev) => {
    const dateObj = new Date(ev.date + 'T12:00:00'); // Prevent timezone shift
    const month = dateObj.toLocaleDateString('es-MX', { month: 'long', year: 'numeric' });
    const capitalizedMonth = month.charAt(0).toUpperCase() + month.slice(1);
    if (!acc[capitalizedMonth]) acc[capitalizedMonth] = [];
    acc[capitalizedMonth].push({ ...ev, dateObj });
    return acc;
  }, {});

  return (
    <div style={{ background: 'linear-gradient(135deg, #fdfbfb 0%, #ebedee 100%)', minHeight: '100vh', padding: '2rem 1rem' }}>
      <div className="container" style={{ maxWidth: '900px' }}>
        
        {/* Header */}
        <div className="d-flex align-items-center justify-content-between mb-4">
          <button className="btn btn-light rounded-circle shadow-sm" onClick={() => navigate('/campus-virtual')} style={{ width: '45px', height: '45px' }}>
            <i className="bi bi-arrow-left text-primary fs-5"></i>
          </button>
          <h2 className="mb-0 fw-bold text-dark"><i className="bi bi-calendar3 me-2 text-primary"></i>Calendario Académico</h2>
          <div style={{ width: '45px' }}></div>
        </div>

        {/* Filters */}
        <div className="card border-0 shadow-sm mb-5" style={{ borderRadius: '20px', background: 'rgba(255, 255, 255, 0.9)', backdropFilter: 'blur(10px)' }}>
          <div className="card-body p-3 d-flex flex-wrap gap-2 justify-content-center">
            <button 
              onClick={() => setFilter('all')} 
              className={`btn rounded-pill px-4 fw-medium ${filter === 'all' ? 'btn-dark shadow-sm' : 'btn-light text-muted border'}`}>
              Todos
            </button>
            {Object.entries(categoryStyles).map(([key, style]) => (
              <button 
                key={key}
                onClick={() => setFilter(key)} 
                className={`btn rounded-pill px-4 fw-medium border`}
                style={{ 
                  background: filter === key ? style.color : 'white', 
                  color: filter === key ? 'white' : style.color,
                  borderColor: style.color
                }}>
                <i className={`bi ${style.icon} me-2`}></i>{style.label}
              </button>
            ))}
          </div>
        </div>

        {/* Event Agenda List */}
        {Object.keys(eventsByMonth).length === 0 ? (
          <div className="text-center py-5">
            <i className="bi bi-calendar2-x fs-1 text-muted opacity-50"></i>
            <h5 className="mt-3 text-muted">No hay eventos para esta categoría.</h5>
          </div>
        ) : (
          Object.entries(eventsByMonth).map(([monthStr, monthEvents]) => (
            <div key={monthStr} className="mb-5">
              <h4 className="fw-bold mb-4" style={{ color: '#495057', borderBottom: '2px solid #dee2e6', paddingBottom: '0.5rem' }}>
                {monthStr}
              </h4>
              <div className="d-flex flex-column gap-3">
                {monthEvents.map(ev => {
                  const s = categoryStyles[ev.category] || { color: '#6c757d', bg: '#f8f9fa', icon: 'bi-calendar' };
                  const day = ev.dateObj.getDate();
                  const weekday = ev.dateObj.toLocaleDateString('es-MX', { weekday: 'short' }).toUpperCase();
                  
                  return (
                    <div key={ev.id} className="card border-0 shadow-sm" style={{ borderRadius: '16px', overflow: 'hidden', transition: 'transform 0.2s', cursor: 'default' }} onMouseEnter={e => e.currentTarget.style.transform = 'translateY(-2px)'} onMouseLeave={e => e.currentTarget.style.transform = 'translateY(0)'}>
                      <div className="d-flex">
                        <div className="d-flex flex-column align-items-center justify-content-center px-4 py-3" style={{ background: s.color, color: 'white', minWidth: '90px' }}>
                          <span className="small fw-bold opacity-75">{weekday}</span>
                          <span className="fs-2 fw-bold lh-1 my-1">{day}</span>
                        </div>
                        <div className="p-3 d-flex flex-column justify-content-center w-100" style={{ background: 'white' }}>
                          <div className="d-flex justify-content-between align-items-start mb-1">
                            <h5 className="fw-bold mb-0 text-dark">{ev.title}</h5>
                            <span className="badge rounded-pill" style={{ background: s.bg, color: s.color }}>
                              <i className={`bi ${s.icon} me-1`}></i>{s.label}
                            </span>
                          </div>
                          {ev.description && (
                            <p className="text-muted mb-0 small mt-1">{ev.description}</p>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          ))
        )}

      </div>
    </div>
  );
}
