import { useEffect, useRef } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { homeHtml } from './HomeContent';
import { getApiBase, resolvePublicAsset } from '../../utils/publicApi';

const renderPortfolioMessage = (container, message) => {
  container.replaceChildren();
  const paragraph = document.createElement('p');
  paragraph.className = 'text-muted py-4';
  paragraph.textContent = message;
  container.appendChild(paragraph);
};

const createPortfolioCard = (project) => {
  const item = document.createElement('div');
  item.className = 'portfolio-item';

  const card = document.createElement('div');
  card.className = 'card border-0 shadow-sm rounded-4 overflow-hidden h-100';

  const image = document.createElement('img');
  image.src = resolvePublicAsset(project.image_url, 'assets/images/robot_creation.png');
  image.className = 'card-img-top portfolio-card-img';
  image.alt = project.title;
  image.loading = 'lazy';

  const body = document.createElement('div');
  body.className = 'card-body';

  const title = document.createElement('h5');
  title.className = 'fw-bold text-dark mb-1';
  title.textContent = project.title;

  const description = document.createElement('p');
  description.className = 'text-muted small mb-3';
  description.textContent = project.short_description || '';

  const link = document.createElement('a');
  link.href = `/proyecto-detalle?id=${encodeURIComponent(project.id)}`;
  link.className = 'btn btn-outline-pink btn-sm rounded-pill px-3';
  link.textContent = 'Ver Detalle';

  body.append(title, description, link);
  card.append(image, body);
  item.appendChild(card);
  return item;
};

const createSuccessStoryCard = (story) => {
  const column = document.createElement('div');
  column.className = 'col-md-4';

  const card = document.createElement('div');
  card.className = 'card border-0 shadow-sm rounded-4 h-100 p-3 testimonial-card';

  const imageWrap = document.createElement('div');
  imageWrap.className = 'text-center mb-3';

  const image = document.createElement('img');
  image.src = resolvePublicAsset(story.photo_url, 'assets/images/axolotl_student.png');
  image.className = 'rounded-circle success-avatar';
  image.alt = story.name;
  image.loading = 'lazy';
  imageWrap.appendChild(image);

  const name = document.createElement('h4');
  name.className = 'h5 fw-bold text-pink mb-1';
  name.textContent = story.name;

  const role = document.createElement('p');
  role.className = 'small fw-bold text-blue mb-1';
  role.textContent = story.role;

  const company = document.createElement('p');
  company.className = 'small fw-bold text-muted mb-3';
  company.textContent = story.company || '';

  const quote = document.createElement('p');
  quote.className = 'fst-italic text-muted';
  quote.textContent = `"${story.quote}"`;

  card.append(imageWrap, name, role, company, quote);
  column.appendChild(card);
  return column;
};

const reelBadgeClasses = {
  pink: 'bg-soft-pink text-pink',
  warning: 'bg-warning text-dark',
  blue: 'bg-soft-blue text-blue',
};

const createReelCard = (reel) => {
  const column = document.createElement('div');
  column.className = 'col-md-6 col-xl-4';

  const card = document.createElement('div');
  card.className = 'card h-100 border-0 shadow-sm rounded-4 overflow-hidden';

  const videoWrap = document.createElement('div');
  videoWrap.className = 'reel-video-wrap position-relative';

  const video = document.createElement('video');
  video.className = 'w-100 reel-video';
  video.controls = true;
  video.muted = true;
  video.playsInline = true;
  video.preload = 'none';
  video.style.cssText = 'aspect-ratio:9/16;object-fit:cover;display:block;';
  video.src = resolvePublicAsset(reel.video_url);

  if (reel.poster_url) {
    video.poster = resolvePublicAsset(reel.poster_url);

    const poster = document.createElement('button');
    poster.type = 'button';
    poster.className = 'reel-poster border-0 p-0';
    poster.setAttribute('aria-label', `Reproducir testimonio de ${reel.badge_text}`);

    const posterImage = document.createElement('img');
    posterImage.src = resolvePublicAsset(reel.poster_url);
    posterImage.alt = reel.badge_text;

    const play = document.createElement('span');
    play.className = 'reel-play-btn';
    play.innerHTML = '<i class="bi bi-play-circle-fill" aria-hidden="true"></i>';

    poster.append(posterImage, play);
    poster.addEventListener('click', () => {
      poster.style.display = 'none';
      video.style.display = 'block';
      video.play().catch(() => {});
    });
    video.style.display = 'none';
    videoWrap.append(video, poster);
  } else {
    videoWrap.appendChild(video);
  }

  const body = document.createElement('div');
  body.className = 'card-body p-4';

  const badge = document.createElement('span');
  badge.className = `badge ${reelBadgeClasses[reel.badge_color] || reelBadgeClasses.pink} mb-2`;
  badge.textContent = reel.badge_text;

  const quote = document.createElement('h5');
  quote.className = 'fw-bold text-blue mb-2';
  quote.textContent = `"${reel.quote}"`;

  body.append(badge, quote);
  if (reel.description) {
    const description = document.createElement('p');
    description.className = 'text-muted small mb-0';
    description.textContent = reel.description;
    body.appendChild(description);
  }

  card.append(videoWrap, body);
  column.appendChild(card);
  return column;
};

const Home = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const containerRef = useRef(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    container.querySelectorAll('[data-bg]').forEach((element) => {
      element.style.background = element.dataset.bg;
    });
  }, []);

  useEffect(() => {
    const portfolioContainer = containerRef.current?.querySelector('#portfolioContainer');
    if (!portfolioContainer) return;

    const controller = new AbortController();

    const loadPortfolio = async () => {
      try {
        const response = await fetch(
          `${getApiBase()}/public/projects?category=portfolio`,
          { signal: controller.signal },
        );
        if (!response.ok) throw new Error(`HTTP ${response.status}`);

        const projects = await response.json();
        if (!projects.length) {
          renderPortfolioMessage(portfolioContainer, 'Próximamente nuevos proyectos.');
          return;
        }

        portfolioContainer.replaceChildren(
          ...projects.slice(0, 6).map(createPortfolioCard),
        );
      } catch (error) {
        if (error.name !== 'AbortError') {
          renderPortfolioMessage(
            portfolioContainer,
            'No se pudieron cargar los proyectos.',
          );
        }
      }
    };

    loadPortfolio();
    return () => controller.abort();
  }, []);

  useEffect(() => {
    const root = containerRef.current;
    const reelsContainer = root?.querySelector('#reelsContainer');
    const storiesContainer = root?.querySelector('#successStoriesContainer');
    if (!reelsContainer && !storiesContainer) return;

    const controller = new AbortController();

    const loadCommunityStories = async () => {
      const requests = [
        fetch(`${getApiBase()}/public/testimonial-reels`, { signal: controller.signal }),
        fetch(`${getApiBase()}/public/success-stories`, { signal: controller.signal }),
      ];

      try {
        const [reelsResponse, storiesResponse] = await Promise.all(requests);
        if (!reelsResponse.ok || !storiesResponse.ok) {
          throw new Error('No se pudo cargar el contenido de comunidad');
        }

        const [reels, stories] = await Promise.all([
          reelsResponse.json(),
          storiesResponse.json(),
        ]);

        if (reelsContainer) {
          if (reels.length) {
            reelsContainer.replaceChildren(...reels.map(createReelCard));
          } else {
            renderPortfolioMessage(reelsContainer, 'Próximamente nuevos testimonios.');
          }
        }

        if (storiesContainer) {
          if (stories.length) {
            storiesContainer.replaceChildren(...stories.map(createSuccessStoryCard));
          } else {
            renderPortfolioMessage(storiesContainer, 'Próximamente nuevas historias de éxito.');
          }
        }
      } catch (error) {
        if (error.name === 'AbortError') return;
        if (reelsContainer) {
          renderPortfolioMessage(reelsContainer, 'No se pudieron cargar los testimonios.');
        }
        if (storiesContainer) {
          renderPortfolioMessage(storiesContainer, 'No se pudieron cargar las historias de éxito.');
        }
      }
    };

    loadCommunityStories();
    return () => controller.abort();
  }, []);

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
    <div className="index-layout" ref={containerRef} dangerouslySetInnerHTML={{ __html: homeHtml }} />
  );
};

export default Home;
