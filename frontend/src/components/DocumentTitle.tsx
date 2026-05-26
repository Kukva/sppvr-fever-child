import { useEffect } from 'react';
import { useLocation } from 'react-router-dom';

const DEFAULT_TITLE = 'Диагностика лихорадки — ИИ-ассистент';

const BY_PATH: Record<string, string> = {
  '/': DEFAULT_TITLE,
  '/consultation': 'Консультация — ИИ-ассистент',
  '/history': 'История консультаций',
  '/about': 'О системе',
};

/** Единый заголовок вкладки браузера вместо «frontend». */
export function DocumentTitle() {
  const { pathname } = useLocation();

  useEffect(() => {
    document.title = BY_PATH[pathname] ?? DEFAULT_TITLE;
  }, [pathname]);

  return null;
}
