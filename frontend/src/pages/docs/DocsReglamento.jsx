import { useEffect, useRef } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { DocsReglamentoHtml } from './DocsReglamentoContent';

const DocsReglamento = () => {
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
    <div className="migrated-layout" ref={containerRef} dangerouslySetInnerHTML={{ __html: DocsReglamentoHtml }} />
  );
};

export default DocsReglamento;
