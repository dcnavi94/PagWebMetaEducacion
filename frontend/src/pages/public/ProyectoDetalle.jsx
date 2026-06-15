import { useEffect, useRef } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { ProyectoDetalleHtml } from './ProyectoDetalleContent';
import { getApiBase, resolvePublicAsset } from '../../utils/publicApi';

const ProyectoDetalle = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const containerRef = useRef(null);

  useEffect(() => {
    if (location.hash) {
      const id = location.hash.replace('#', '');
      const element = document.getElementById(id);
      if (element) {
        element.scrollIntoView({ behavior: 'smooth' });
      }
    } else {
      window.scrollTo(0, 0);
    }
  }, [location]);

  useEffect(() => {
    const projectId = new URLSearchParams(location.search).get('id');
    const container = containerRef.current;
    if (!projectId || !container) {
      navigate('/#portafolio', { replace: true });
      return;
    }

    const controller = new AbortController();

    const loadProject = async () => {
      try {
        const response = await fetch(`${getApiBase()}/public/projects/${projectId}`, {
          signal: controller.signal,
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);

        const project = await response.json();
        const createdAt = new Date(project.created_at);
        const setText = (selector, value) => {
          const element = container.querySelector(selector);
          if (element) element.textContent = value;
        };

        const hero = container.querySelector('#projectHero');
        if (hero) {
          hero.style.backgroundImage = `url("${resolvePublicAsset(
            project.image_url,
            'assets/images/proyecto-robotica.png',
          )}")`;
        }

        setText('#projectTitle', project.title);
        setText('#projectCategory', 'Proyecto estudiantil');
        setText('#projectFullDesc', project.short_description || 'Proyecto de la Legión Axolot.');
        setText(
          '#projectDate',
          Number.isNaN(createdAt.getTime())
            ? 'Fecha no disponible'
            : createdAt.toLocaleDateString('es-MX', {
                day: 'numeric',
                month: 'long',
                year: 'numeric',
              }),
        );
        setText('#projectTeam', 'Legión Axolot');
        setText('#projectTech', 'Proyecto académico');
        container.querySelector('#projectLink')?.classList.add('d-none');
      } catch (error) {
        if (error.name !== 'AbortError') {
          navigate('/#portafolio', { replace: true });
        }
      }
    };

    loadProject();
    return () => controller.abort();
  }, [location.search, navigate]);

  // Intercept link clicks to use React Router
  useEffect(() => {
    const handleLinkClick = (e) => {
      const target = e.target.closest('a');
      if (!target) return;
      
      const href = target.getAttribute('href');
      if (!href) return;

      if (href.startsWith('http') || href.startsWith('mailto:') || href.startsWith('tel:') || href.startsWith('https://wa.me')) {
        return;
      }
      
      if (href.startsWith('#')) return;

      e.preventDefault();
      navigate(href);
    };

    const container = containerRef.current;
    if (container) {
      container.addEventListener('click', handleLinkClick);
    }

    return () => {
      if (container) {
        container.removeEventListener('click', handleLinkClick);
      }
    };
  }, [navigate]);

  return (
    <div className="migrated-layout" ref={containerRef} dangerouslySetInnerHTML={{ __html: ProyectoDetalleHtml }} />
  );
};

export default ProyectoDetalle;
