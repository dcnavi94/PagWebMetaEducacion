import { Routes, Route, Navigate, useLocation } from 'react-router-dom'
import Navbar from './components/Navbar'
import Footer from './components/Footer'
import Home from './pages/Home'
import Software from './pages/Software'
import Preparatoria from './pages/Preparatoria'
import Telematica from './pages/Telematica'
import Comunidad from './pages/Comunidad'
import Institucion from './pages/Institucion'
import TestVocacional from './pages/TestVocacional'
import Login from './pages/Login'
import CampusVirtual from './pages/CampusVirtual'
import AdminPortal from './pages/AdminPortal'
import TeacherPortal from './pages/TeacherPortal'
import LibraryPortal from './pages/LibraryPortal'
import LaboratoryPortal from './pages/LaboratoryPortal'
import DocsActas from './pages/DocsActas'
import DocsGrupos from './pages/DocsGrupos'
import DocsInscripcion from './pages/DocsInscripcion'
import DocsLaboratorio from './pages/DocsLaboratorio'
import DocsPagos from './pages/DocsPagos'
import DocsReglamento from './pages/DocsReglamento'
import DocsServicioSocial from './pages/DocsServicioSocial'
import DocsTesis from './pages/DocsTesis'
import PortafolioCompleto from './pages/PortafolioCompleto'
import ProcesoAcademico from './pages/ProcesoAcademico'
import ProyectoDetalle from './pages/ProyectoDetalle'
import KardexPortal from './pages/KardexPortal'
import CalendarioPortal from './pages/CalendarioPortal'
import PerfilPortal from './pages/PerfilPortal'
import NotFound, { ErrorCatalog, ErrorPage } from './pages/NotFound'

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
          <Route path="/teacher" element={<TeacherPortal />} />
          
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
