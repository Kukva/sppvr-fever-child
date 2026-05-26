import React from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import marinaSiteLogo from '../assets/marina-site-logo.svg';

function navLinkClass(active: boolean) {
  return active
    ? 'text-sm font-medium text-figma-accent border-b-2 border-figma-accent pb-0.5'
    : 'text-sm text-figma-ink hover:text-figma-accent transition-colors pb-0.5 border-b-2 border-transparent';
}

export const Header: React.FC = () => {
  const navigate = useNavigate();
  const { pathname } = useLocation();

  const chatActive = pathname === '/' || pathname.startsWith('/consultation');
  const historyActive = pathname.startsWith('/history');
  const aboutActive = pathname.startsWith('/about');

  return (
    <header className="relative z-10 w-full border-b border-gray-200/80 bg-white/90 backdrop-blur-sm">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 py-3 sm:py-4 flex flex-wrap items-center justify-between gap-y-3 gap-x-4">
        <div className="flex items-center gap-4 sm:gap-8 min-w-0">
          <img
            src={marinaSiteLogo}
            alt="Марина Ивановна"
            className="h-8 sm:h-9 w-auto max-w-[min(280px,55vw)] object-contain object-left shrink-0"
            decoding="async"
          />
        </div>
        <nav className="flex flex-wrap items-center gap-4 sm:gap-6">
          <button
            type="button"
            onClick={() => navigate('/')}
            className={navLinkClass(chatActive)}
          >
            Чат с Мариной Ивановной
          </button>
          <button
            type="button"
            onClick={() => navigate('/history')}
            className={navLinkClass(historyActive)}
          >
            История консультаций
          </button>
          <button
            type="button"
            onClick={() => navigate('/about')}
            className={navLinkClass(aboutActive)}
          >
            О системе
          </button>
        </nav>
      </div>
    </header>
  );
};
