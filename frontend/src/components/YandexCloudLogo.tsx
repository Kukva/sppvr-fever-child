import React from 'react';
import brandLogo from '../assets/yc-logotype.svg';

export function YandexCloudLogo({ className = '' }: { className?: string }) {
  return (
    <div
      className={`inline-flex items-center rounded-lg border border-gray-200/80 bg-white/90 px-2.5 py-1 shadow-sm ${className}`}
      role="img"
      aria-label="Yandex Cloud"
    >
      <img
        src={brandLogo}
        alt="Yandex Cloud"
        className="h-5 w-auto max-h-[1.25rem] object-contain object-left sm:h-6 sm:max-h-[1.5rem]"
        style={{ maxWidth: 'min(200px, 52vw)' }}
        decoding="async"
      />
    </div>
  );
}

export default YandexCloudLogo;
