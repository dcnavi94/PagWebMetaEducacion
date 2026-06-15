export const getApiBase = () => {
  if (window.API_BASE) return window.API_BASE;
  return `${window.location.protocol}//${window.location.hostname}:8000`;
};

export const resolvePublicAsset = (value, fallback) => {
  const source = value || fallback;
  if (!source) return '';
  if (/^(https?:)?\/\//i.test(source) || source.startsWith('data:')) return source;
  return `/${source.replace(/^\/+/, '')}`;
};
