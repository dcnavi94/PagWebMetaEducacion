import { useEffect, useRef } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { softwareHtml } from './SoftwareContent';

const Software = () => {
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

      // Allow external links, anchor links, and mail/tel to work natively
      if (href.startsWith('http') || href.startsWith('mailto:') || href.startsWith('tel:') || href.startsWith('https://wa.me')) {
        return;
      }
      
      // If it's a hash link on the same page, let browser handle smooth scroll
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
    <div className="software-layout software-biomimic" ref={containerRef} dangerouslySetInnerHTML={{ __html: softwareHtml }} />
  );
};

export default Software;
