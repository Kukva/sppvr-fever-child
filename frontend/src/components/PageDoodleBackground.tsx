import React from 'react';

/** Боковой фон в духе Figma Group 12: колонки ~305px, opacity 0.7. Ассет — figma-group-12.webp (305×866). */
export function PageDoodleBackground() {
  return (
    <>
      <div
        className="pointer-events-none absolute -left-1 sm:-left-3 top-0 bottom-0 z-0 hidden w-[min(305px,22vw)] overflow-hidden opacity-70 md:block"
        aria-hidden
      >
        <img
          src="/figma-group-12.webp"
          alt=""
          className="h-full min-h-[100vh] w-full object-cover object-left object-top"
          decoding="async"
        />
      </div>
      <div
        className="pointer-events-none absolute -right-1 sm:-right-3 top-0 bottom-0 z-0 hidden w-[min(305px,22vw)] overflow-hidden opacity-70 md:block"
        aria-hidden
      >
        <img
          src="/figma-group-12.webp"
          alt=""
          className="h-full min-h-[100vh] w-full scale-x-[-1] object-cover object-right object-top"
          decoding="async"
        />
      </div>
    </>
  );
}

export default PageDoodleBackground;
