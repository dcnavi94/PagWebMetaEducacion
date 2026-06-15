import { useEffect, useMemo, useState } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';
import './LibraryPortal.css';

const request = async (path, options = {}) => {
  const response = await fetch(`/api${path}`, {
    ...options,
    headers: {
      Authorization: `Bearer ${localStorage.getItem('token')}`,
      ...(options.body ? { 'Content-Type': 'application/json' } : {}),
    },
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || 'No se pudo completar la operación');
  }
  return response.status === 204 ? null : response.json();
};

const LaboratoryPortal = () => {
  const navigate = useNavigate();
  const token = localStorage.getItem('token');
  const [materials, setMaterials] = useState([]);
  const [requests, setRequests] = useState([]);
  const [search, setSearch] = useState('');
  const [message, setMessage] = useState('');
  const [selected, setSelected] = useState(null);
  const [quantity, setQuantity] = useState(1);
  const [project, setProject] = useState('');

  const load = async () => {
    try {
      const [items, history] = await Promise.all([
        request('/laboratory/materials'),
        request('/laboratory/requests/me'),
      ]);
      setMaterials(items);
      setRequests(history);
    } catch (error) {
      setMessage(error.message);
    }
  };

  useEffect(() => { load(); }, []);

  const filtered = useMemo(() => {
    const term = search.trim().toLowerCase();
    return term
      ? materials.filter((item) => [item.name, item.code, item.category, item.description].filter(Boolean).some((value) => value.toLowerCase().includes(term)))
      : materials;
  }, [materials, search]);

  const submit = async (event) => {
    event.preventDefault();
    try {
      await request('/laboratory/requests', {
        method: 'POST',
        body: JSON.stringify({ material_id: selected.id, quantity: Number(quantity), project_name: project || null }),
      });
      setMessage(`Solicitud enviada: ${quantity} unidad(es) de ${selected.name}.`);
      setSelected(null);
      setQuantity(1);
      setProject('');
      await load();
    } catch (error) {
      setMessage(error.message);
    }
  };

  if (!token) return <Navigate to="/login" replace />;

  return (
    <div className="library-page">
      <header className="library-topbar">
        <button className="library-back" onClick={() => navigate('/campus-virtual')}>
          <i className="bi bi-arrow-left" /> Campus del alumno
        </button>
        <strong><i className="bi bi-cpu-fill" /> Laboratorio de Electrónica</strong>
      </header>
      <main className="library-container">
        <section className="library-hero" style={{ background: 'linear-gradient(135deg,#075b4c,#17a985)' }}>
          <div>
            <span>Inventario del laboratorio</span>
            <h1>Material y equipo</h1>
            <p>Consulta existencias y solicita componentes o equipo para tus prácticas y proyectos.</p>
          </div>
          <i className="bi bi-tools" />
        </section>
        <div className="library-search">
          <i className="bi bi-search" />
          <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Buscar material, código o categoría..." />
          <span>{filtered.length} resultados</span>
        </div>
        {message && <div className="library-message">{message}</div>}
        <section className="library-grid">
          {filtered.map((item) => {
            const active = requests.some((row) => row.material_id === item.id && ['Pendiente', 'Aprobado', 'Prestado'].includes(row.status));
            return (
              <article className="library-card" key={item.id}>
                <div className="library-card-icon blue"><i className="bi bi-cpu" /></div>
                <div className="library-card-body">
                  <span className="library-category">{item.category || 'Material electrónico'}</span>
                  <h2>{item.name}</h2>
                  <p className="library-author">{item.code || 'Sin código'}</p>
                  <p>{item.description || 'Disponible para prácticas del laboratorio.'}</p>
                  <div className="library-book-meta">
                    <span><i className="bi bi-geo-alt" /> {item.storage_location || 'Consulta con el encargado'}</span>
                    <span className={item.available_units > 0 ? 'available' : 'unavailable'}>
                      {item.available_units} de {item.total_units} unidades disponibles
                    </span>
                  </div>
                </div>
                <button className="library-primary" disabled={!item.available_units || active} onClick={() => { setSelected(item); setQuantity(1); }}>
                  Solicitar material <i className="bi bi-send" />
                </button>
              </article>
            );
          })}
        </section>
        <section className="library-loans">
          <h2>Mis solicitudes de material</h2>
          {requests.length ? requests.map((item) => (
            <div className="library-loan-row" key={item.id}>
              <div><strong>{item.material?.name}</strong><small>{item.quantity} unidad(es) · {item.project_name || 'Sin proyecto indicado'}</small></div>
              <span className={`loan-${item.status.toLowerCase()}`}>{item.status}</span>
            </div>
          )) : <p>No has solicitado material.</p>}
        </section>
      </main>
      {selected && (
        <div className="lab-modal-backdrop">
          <form className="lab-request-modal" onSubmit={submit}>
            <button type="button" className="lab-modal-close" onClick={() => setSelected(null)}><i className="bi bi-x-lg" /></button>
            <h2>Solicitar {selected.name}</h2>
            <label>Cantidad</label>
            <input type="number" min="1" max={selected.available_units} value={quantity} onChange={(event) => setQuantity(event.target.value)} required />
            <label>Práctica o proyecto</label>
            <input value={project} onChange={(event) => setProject(event.target.value)} placeholder="Ej. Proyecto de robótica" />
            <button className="library-primary" type="submit">Enviar solicitud</button>
          </form>
        </div>
      )}
    </div>
  );
};

export default LaboratoryPortal;
