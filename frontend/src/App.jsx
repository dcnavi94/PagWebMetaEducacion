import { Routes, Route, Navigate, useLocation } from 'react-router-dom'
import Navbar from './components/Navbar'
import Footer from './components/Footer'
import Home from './pages/public/Home'
import Software from './pages/public/Software'
import Preparatoria from './pages/public/Preparatoria'
import Telematica from './pages/public/Telematica'
import Comunidad from './pages/public/Comunidad'
import Institucion from './pages/public/Institucion'
import TestVocacional from './pages/public/TestVocacional'
import PortafolioCompleto from './pages/public/PortafolioCompleto'
import ProcesoAcademico from './pages/public/ProcesoAcademico'
import ProyectoDetalle from './pages/public/ProyectoDetalle'
import Login from './pages/portals/Login'
import CampusVirtual from './pages/portals/CampusVirtual'
import AdminPortal from './pages/portals/AdminPortal'
import TeacherPortal from './pages/portals/TeacherPortal'
import LibraryPortal from './pages/portals/LibraryPortal'
import LaboratoryPortal from './pages/portals/LaboratoryPortal'
import KardexPortal from './pages/portals/KardexPortal'
import CalendarioPortal from './pages/portals/CalendarioPortal'
import PerfilPortal from './pages/portals/PerfilPortal'
import DocsActas from './pages/docs/DocsActas'
import DocsGrupos from './pages/docs/DocsGrupos'
import DocsInscripcion from './pages/docs/DocsInscripcion'
import DocsLaboratorio from './pages/docs/DocsLaboratorio'
import DocsPagos from './pages/docs/DocsPagos'
import DocsReglamento from './pages/docs/DocsReglamento'
import DocsServicioSocial from './pages/docs/DocsServicioSocial'
import DocsTesis from './pages/docs/DocsTesis'
import NotFound, { ErrorCatalog, ErrorPage } from './pages/errors/NotFound'

function App() {
  const location = useLocation();
  const hideNavAndFooter = ['/login', '/admin', '/teacher', '/campus-virtual', '/biblioteca', '/laboratorio-materiales', '/kardex', '/calendario', '/perfil'].includes(location.pathname);

  return (
    <>
      {!hideNavAndFooter && <Navbar />}
      
      <main>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/preparatoria" element={<Preparatoria />} />
          <Route path="/software" element={<Software />} />
          <Route path="/telematica" element={<Telematica />} />
          <Route path="/comunidad" element={<Comunidad />} />
          <Route path="/institucion" element={<Institucion />} />
          <Route path="/test-vocacional" element={<TestVocacional />} />
          <Route path="/login" element={<Login />} />
          <Route path="/login.html" element={<Navigate to="/login" replace />} />
          <Route path="/campus-virtual" element={<CampusVirtual />} />
          <Route path="/campus-virtual.html" element={<Navigate to="/campus-virtual" replace />} />
          <Route path="/admin" element={<AdminPortal />} />
          <Route path="/admin.html" element={<Navigate to="/admin" replace />} />
          <Route path="/teacher" element={<TeacherPortal />} />
          <Route path="/teacher.html" element={<Navigate to="/teacher" replace />} />
          
          <Route path="/biblioteca" element={<LibraryPortal />} />
          <Route path="/kardex" element={<KardexPortal />} />
          <Route path="/calendario" element={<CalendarioPortal />} />
          <Route path="/perfil" element={<PerfilPortal />} />
          <Route path="/laboratorio-materiales" element={<LaboratoryPortal />} />
          <Route path="/docs-actas" element={<DocsActas />} />
          <Route path="/docs-grupos" element={<DocsGrupos />} />
          <Route path="/docs-inscripcion" element={<DocsInscripcion />} />
          <Route path="/docs-laboratorio" element={<DocsLaboratorio />} />
          <Route path="/docs-pagos" element={<DocsPagos />} />
          <Route path="/docs-reglamento" element={<DocsReglamento />} />
          <Route path="/docs-servicio-social" element={<DocsServicioSocial />} />
          <Route path="/docs-tesis" element={<DocsTesis />} />
          <Route path="/portafolio-completo" element={<PortafolioCompleto />} />
          <Route path="/proceso-academico" element={<ProcesoAcademico />} />
          <Route path="/proyecto-detalle" element={<ProyectoDetalle />} />
          <Route path="/errores" element={<ErrorCatalog />} />
          <Route path="/error/:code" element={<ErrorPage />} />

          <Route path="*" element={<NotFound />} />
        </Routes>
      </main>

      {!hideNavAndFooter && <Footer />}
    </>
  )
}

export default App
