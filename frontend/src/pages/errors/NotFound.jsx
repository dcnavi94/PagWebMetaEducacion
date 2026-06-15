import { Link, useNavigate, useParams } from 'react-router-dom';
import './NotFound.css';

export const errorContent = {
  400: {
    title: 'El ajolote no entendió lo que escribiste.',
    description: 'La solicitud llegó con datos incompletos o en un formato que no pudimos procesar.',
    note: 'Revisa la información e inténtalo nuevamente.',
    icon: 'bi-pencil-square',
    image: '/assets/images/errors/ajolote-error-400.png',
  },
  401: {
    title: 'Necesitas credencial escolar para entrar a este estanque.',
    description: 'Tu sesión no está iniciada o tu acceso ya venció.',
    note: 'Inicia sesión para continuar con tus actividades.',
    icon: 'bi-person-badge',
    image: '/assets/images/errors/ajolote-error-401.png',
  },
  403: {
    title: 'El ajolote guardián no te deja pasar aquí.',
    description: 'Tu cuenta está activa, pero no tiene permiso para consultar esta sección.',
    note: 'Si crees que es un error, comunícate con el administrador.',
    icon: 'bi-shield-lock-fill',
    image: '/assets/images/errors/ajolote-error-403.png',
  },
  404: {
    title: 'Nuestro ajolote se llevó esta página al estanque.',
    description: 'La página que buscas no existe, cambió de lugar o fue archivada por accidente.',
    note: 'El ajolote asegura que “así estaba cuando llegó”.',
    icon: 'bi-map-fill',
    image: '/assets/images/errors/ajolote-error-404.png',
  },
  408: {
    title: 'El ajolote esperó mucho y se quedó dormido.',
    description: 'La solicitud tardó demasiado tiempo y la conexión fue cerrada.',
    note: 'Despiértalo intentando nuevamente en unos segundos.',
    icon: 'bi-alarm-fill',
    image: '/assets/images/errors/ajolote-error-408.png',
  },
  429: {
    title: '¡Calma! El ajolote está recibiendo demasiadas visitas.',
    description: 'Se realizaron muchas solicitudes en muy poco tiempo.',
    note: 'Espera un momento antes de volver a intentarlo.',
    icon: 'bi-people-fill',
    image: '/assets/images/errors/ajolote-error-429.png',
  },
  500: {
    title: 'Algo salió mal en el laboratorio del ajolote.',
    description: 'Ocurrió un problema interno mientras procesábamos tu solicitud.',
    note: 'Nuestro equipo ya está revisando los tubos y los cables.',
    icon: 'bi-tools',
    image: '/assets/images/errors/ajolote-error-500.png',
  },
  502: {
    title: 'El ajolote pidió ayuda, pero el servidor respondió raro.',
    description: 'Uno de nuestros servicios recibió una respuesta que no pudo interpretar.',
    note: 'No fue tu culpa. Intenta nuevamente dentro de un momento.',
    icon: 'bi-hdd-network-fill',
    image: '/assets/images/errors/ajolote-error-502.png',
  },
  503: {
    title: 'El estanque está en mantenimiento, vuelve pronto.',
    description: 'El servicio no se encuentra disponible temporalmente.',
    note: 'Estamos limpiando el estanque para que todo funcione mejor.',
    icon: 'bi-cone-striped',
    image: '/assets/images/errors/ajolote-error-503.png',
  },
  504: {
    title: 'El ajolote nadó por la respuesta, pero tardó demasiado.',
    description: 'Otro servicio no respondió dentro del tiempo esperado.',
    note: 'Puedes regresar al inicio o probar nuevamente más tarde.',
    icon: 'bi-hourglass-split',
    image: '/assets/images/errors/ajolote-error-504.png',
  },
};

const validCodes = Object.keys(errorContent);

export function ErrorPage({ code: fixedCode }) {
  const { code: routeCode } = useParams();
  const navigate = useNavigate();
  const requestedCode = String(fixedCode || routeCode || '404');
  const code = validCodes.includes(requestedCode) ? requestedCode : '404';
  const error = errorContent[code];

  return (
    <section className={`not-found-page error-theme-${code}`} aria-labelledby="error-page-title">
      <div className="not-found-bubble bubble-one" aria-hidden="true"></div>
      <div className="not-found-bubble bubble-two" aria-hidden="true"></div>

      <div className="not-found-card">
        <div className="not-found-copy">
          <span className="not-found-code">ERROR {code}</span>
          <h1 id="error-page-title">{error.title}</h1>
          <p>{error.description}</p>

          <div className="not-found-note">
            <i className={`bi ${error.icon}`} aria-hidden="true"></i>
            <span>{error.note}</span>
          </div>

          <div className="not-found-actions">
            <Link className="btn not-found-primary" to="/">
              <i className="bi bi-house-door-fill"></i>
              Volver al inicio
            </Link>
            <button className="btn not-found-secondary" type="button" onClick={() => navigate(-1)}>
              <i className="bi bi-arrow-left"></i>
              Regresar
            </button>
          </div>
        </div>

        <div className="not-found-scene" aria-hidden="true">
          <span className="not-found-number">{code}</span>
          <div className="not-found-image-wrap">
            <img src={error.image} alt="" />
          </div>
          <span className="not-found-fish fish-one">?</span>
          <span className="not-found-fish fish-two">{code}</span>
        </div>
      </div>
    </section>
  );
}

export function ErrorCatalog() {
  return (
    <section className="error-catalog">
      <header className="error-catalog-header">
        <span>Centro de errores</span>
        <h1>Ajolotes al rescate</h1>
        <p>Selecciona un código para visualizar la página que verá el usuario.</p>
      </header>

      <div className="error-catalog-grid">
        {validCodes.map((code) => {
          const error = errorContent[code];
          return (
            <Link className="error-catalog-card" to={`/error/${code}`} key={code}>
              <div className="error-catalog-code">{code}</div>
              <i className={`bi ${error.icon}`} aria-hidden="true"></i>
              <h2>{error.title}</h2>
              <span>Ver página <i className="bi bi-arrow-right"></i></span>
            </Link>
          );
        })}
      </div>
    </section>
  );
}

export default function NotFound() {
  return <ErrorPage code="404" />;
}
