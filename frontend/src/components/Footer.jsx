const Footer = () => {
  return (
    <footer className="bg-dark text-white py-5 mt-auto">
        <div className="container py-4">
            <div className="row g-4">
                <div className="col-lg-4 mb-4 mb-lg-0">
                    <div className="d-flex align-items-center mb-3">
                        <img src="/assets/logo_white.png" alt="MetaEducación Logo" height="50" className="me-2" loading="lazy" decoding="async" />
                        <span className="fw-bolder fs-3 italic">MetaEducación</span>
                    </div>
                    <p className="text-white-50">Transformando la educación tecnológica en la región con programas intensivos, prácticos y con validez oficial.</p>
                </div>
                <div className="col-lg-2 col-md-4 mb-4 mb-md-0">
                    <h5 className="fw-bold mb-3">Programas</h5>
                    <ul className="list-unstyled text-white-50">
                        <li className="mb-2"><a href="/software" className="text-white-50 text-decoration-none">Ing. Software</a></li>
                        <li className="mb-2"><a href="/telematica" className="text-white-50 text-decoration-none">Ing. Telemática</a></li>
                        <li className="mb-2"><a href="/preparatoria" className="text-white-50 text-decoration-none">Preparatoria</a></li>
                    </ul>
                </div>
                <div className="col-lg-2 col-md-4 mb-4 mb-md-0">
                    <h5 className="fw-bold mb-3">Enlaces</h5>
                    <ul className="list-unstyled text-white-50">
                        <li className="mb-2"><a href="/login" className="text-white-50 text-decoration-none">Campus Virtual</a></li>
                    </ul>
                </div>
                <div className="col-lg-4 col-md-4">
                    <h5 className="fw-bold mb-3">Contacto</h5>
                    <ul className="list-unstyled text-white-50">
                        <li className="mb-2"><i className="bi bi-geo-alt-fill me-2 text-pink"></i> San José Iturbide, Gto.</li>
                    </ul>
                </div>
            </div>
            <hr className="my-4 border-secondary" />
            <div className="text-center text-white-50">
                <small>&copy; {new Date().getFullYear()} MetaEducación. Todos los derechos reservados.</small>
            </div>
        </div>
    </footer>
  )
}

export default Footer
