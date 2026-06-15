import { useEffect, useMemo, useState } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';
import './LibraryPortal.css';

const apiRequest = async (path, options = {}) => {
  const token = localStorage.getItem('token');
  const response = await fetch(`/api${path}`, {
    ...options,
    headers: {
      Authorization: `Bearer ${token}`,
      ...(options.body ? { 'Content-Type': 'application/json' } : {}),
      ...(options.headers || {}),
    },
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || 'No se pudo completar la operación');
  }
  return response.status === 204 ? null : response.json();
};

const publicLinks = [
  { id: 'l1', title: 'Internet Archive', desc: 'Acceso libre a libros, artículos, audio y video, incluyendo Wayback Machine.', url: 'https://archive.org' },
  { id: 'l2', title: 'Project Gutenberg', desc: 'Más de 70,000 libros electrónicos gratuitos de dominio público.', url: 'https://www.gutenberg.org' },
  { id: 'l3', title: 'Biblioteca Virtual Miguel de Cervantes', desc: 'Obras e investigaciones clave de literatura y cultura en español.', url: 'https://www.cervantesvirtual.com' },
  { id: 'l4', title: 'Directory of Open Access Books', desc: 'Repositorio académico de libros científicos revisados por pares en acceso abierto.', url: 'https://www.doabooks.org' },
  { id: 'l5', title: 'Elejandría', desc: 'Biblioteca digital gratuita en español con clásicos en PDF, EPUB y MOBI.', url: 'https://www.elejandria.com' },
  { id: 'l6', title: 'SciELO', desc: 'Scientific Electronic Library Online. Biblioteca electrónica de revistas científicas.', url: 'https://www.scielo.org' },
  { id: 'l7', title: 'Dialnet', desc: 'Portal de difusión de la producción científica hispana, con acceso a artículos y tesis.', url: 'https://dialnet.unirioja.es' },
  { id: 'l8', title: 'Redalyc', desc: 'Red de Revistas Científicas de América Latina y el Caribe, España y Portugal.', url: 'https://www.redalyc.org' },
  { id: 'l9', title: 'Google Académico', desc: 'Buscador especializado en artículos, tesis, libros y resúmenes de editoriales académicas.', url: 'https://scholar.google.es' },
  { id: 'l10', title: 'Open Library', desc: 'Catálogo de libros abiertos colaborativo respaldado por Internet Archive.', url: 'https://openlibrary.org' },
  { id: 'l11', title: 'Latindex', desc: 'Sistema Regional de Información en Línea para Revistas Científicas de Iberoamérica.', url: 'https://www.latindex.org' },
  { id: 'l12', title: 'Europeana', desc: 'Descubre el patrimonio cultural a través de millones de libros y documentos históricos.', url: 'https://www.europeana.eu' },
  { id: 'l13', title: 'Red de Bibliotecas Virtuales de CLACSO', desc: 'Repositorio institucional con investigaciones en ciencias sociales de América Latina.', url: 'http://biblioteca.clacso.edu.ar/' },
  { id: 'l14', title: 'Ciberoteca', desc: 'La biblioteca virtual más grande del mundo con enlaces a miles de textos literarios, científicos y técnicos.', url: 'http://www.ciberoteca.com/' },
  { id: 'l15', title: 'Biblioteca Digital Hispánica', desc: 'Portal libre y gratuito de los documentos digitalizados de la Biblioteca Nacional de España.', url: 'http://www.bne.es/es/Catalogos/BibliotecaDigitalHispanica/Inicio/' },
  { id: 'l16', title: 'OpenAIRE', desc: 'Infraestructura europea de acceso abierto para la investigación.', url: 'https://www.openaire.eu/' },
  { id: 'l17', title: 'arXiv', desc: 'Archivo de preprints de física, matemáticas, ciencias de la computación, biología cuantitativa y más.', url: 'https://arxiv.org/' },
  { id: 'l18', title: 'BASE (Bielefeld Academic Search Engine)', desc: 'Uno de los motores de búsqueda más voluminosos de documentos académicos en acceso abierto.', url: 'https://www.base-search.net/' },
  { id: 'l19', title: 'PLOS (Public Library of Science)', desc: 'Editorial sin fines de lucro de acceso abierto en ciencia y medicina.', url: 'https://plos.org/' },
  { id: 'l20', title: 'CORE', desc: 'El mayor agregador de artículos de investigación de acceso abierto del mundo.', url: 'https://core.ac.uk/' }
];

const LibraryPortal = () => {
  const navigate = useNavigate();
  const token = localStorage.getItem('token');
  const [items, setItems] = useState([]);
  const [loans, setLoans] = useState([]);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState('');

  const loadData = async () => {
    setLoading(true);
    setMessage('');
    try {
      setItems(await apiRequest('/library/books'));
      setLoans(await apiRequest('/library/loans/me'));
    } catch (error) {
      setMessage(error.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const filtered = useMemo(() => {
    const term = search.trim().toLowerCase();
    if (!term) return items;
    return items.filter((item) =>
      [item.title, item.author, item.category, item.isbn, item.description]
        .filter(Boolean)
        .some((value) => value.toLowerCase().includes(term))
    );
  }, [items, search]);

  const requestLoan = async (book) => {
    setMessage('');
    try {
      await apiRequest('/library/loans', {
        method: 'POST',
        body: JSON.stringify({ book_id: book.id }),
      });
      setMessage(`Solicitud enviada para "${book.title}".`);
      setLoans(await apiRequest('/library/loans/me'));
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
      </header>

      <main className="library-container">
        <section className="library-hero physical">
          <div>
            <span>Biblioteca MetaEducación</span>
            <h1>Biblioteca del Campus</h1>
            <p>
              Busca libros físicos disponibles, solicita préstamos desde tu cuenta y accede a repositorios de acceso abierto.
            </p>
          </div>
          <i className="bi bi-book-half" />
        </section>

        <div className="library-search">
          <i className="bi bi-search" />
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Buscar libros físicos por título, autor, ISBN o categoría..."
          />
          <span>{filtered.length} resultados físicos</span>
        </div>

        {message && <div className="library-message">{message}</div>}

        {loading ? (
          <div className="library-empty">Cargando biblioteca...</div>
        ) : filtered.length === 0 ? (
          <div className="library-empty">No se encontraron libros físicos.</div>
        ) : (
          <section className="library-grid">
            {filtered.map((item) => (
              <article className="library-card" key={item.id}>
                <div className="library-card-icon orange">
                  <i className="bi bi-book" />
                </div>
                <div className="library-card-body">
                  <span className="library-category">{item.category || 'Catálogo general'}</span>
                  <h2>{item.title}</h2>
                  <p className="library-author">{item.author || 'MetaEducación'}</p>
                  <p>{item.description || 'Sin descripción adicional.'}</p>
                  <div className="library-book-meta">
                    <span><i className="bi bi-geo-alt" /> {item.shelf_location || 'Consulta en mostrador'}</span>
                    <span className={item.available_copies > 0 ? 'available' : 'unavailable'}>
                      {item.available_copies} de {item.total_copies} disponibles
                    </span>
                  </div>
                </div>
                <button
                  className="library-primary"
                  disabled={item.available_copies < 1 || loans.some((loan) => loan.book_id === item.id && ['Pendiente', 'Aprobado', 'Prestado'].includes(loan.status))}
                  onClick={() => requestLoan(item)}
                >
                  Solicitar préstamo <i className="bi bi-send" />
                </button>
              </article>
            ))}
          </section>
        )}

        <section className="library-loans">
          <h2>Mis solicitudes de préstamo físico</h2>
          {loans.length === 0 ? (
            <p>No has solicitado préstamos físicos.</p>
          ) : (
            loans.map((loan) => (
              <div className="library-loan-row" key={loan.id}>
                <div>
                  <strong>{loan.book?.title || 'Libro'}</strong>
                  <small>Solicitado el {new Date(loan.requested_at).toLocaleDateString('es-MX')}</small>
                </div>
                <span className={`loan-${loan.status.toLowerCase()}`}>{loan.status}</span>
              </div>
            ))
          )}
        </section>

        <section className="library-loans" style={{ marginTop: '2rem' }}>
          <h2>Recursos Académicos Abiertos (Biblioteca Virtual)</h2>
          <p style={{ color: 'var(--muted)', marginBottom: '1rem', fontSize: '0.9rem' }}>
            Bibliotecas y repositorios listos para consulta inmediata del alumno.
          </p>
          <div className="library-grid">
            {publicLinks.map((link) => (
              <article className="library-card" key={link.id} style={{ minHeight: 'auto' }}>
                <div className="library-card-icon blue">
                  <i className="bi bi-link-45deg" />
                </div>
                <div className="library-card-body">
                  <span className="library-category">Recurso académico externo</span>
                  <h2>{link.title}</h2>
                  <p>{link.desc}</p>
                </div>
                <a className="library-primary" href={link.url} target="_blank" rel="noreferrer">
                  Abrir enlace <i className="bi bi-box-arrow-up-right" />
                </a>
              </article>
            ))}
          </div>
        </section>
      </main>
    </div>
  );
};

export default LibraryPortal;
