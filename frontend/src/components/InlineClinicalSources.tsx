import React from 'react';
import { ArrowTopRightOnSquareIcon, ChevronDownIcon } from '@heroicons/react/24/outline';
import type { ClinicalSource } from '../types';

function dedupeSources(sources: ClinicalSource[]): ClinicalSource[] {
  const seen = new Set<string>();
  return sources.filter((s) => {
    const key = `${(s.url || '').trim()}|${(s.title || '').trim()}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function sourcesCountRu(n: number): string {
  const m10 = n % 10;
  const m100 = n % 100;
  if (m100 >= 11 && m100 <= 14) return `${n} источников`;
  if (m10 === 1) return `${n} источник`;
  if (m10 >= 2 && m10 <= 4) return `${n} источника`;
  return `${n} источников`;
}

/** Блок ссылок на КР внутри пузыря сообщения ассистента */
export function InlineClinicalSources({ sources }: { sources: ClinicalSource[] }) {
  const list = dedupeSources(sources);
  if (list.length === 0) return null;

  return (
    <div className="mt-3 pt-3 border-t border-gray-200">
      <details className="rounded-lg border border-gray-200/90 bg-gray-50/70 open:[&_.clinical-sources-chevron]:rotate-180">
        <summary className="cursor-pointer select-none list-none px-2.5 py-2 flex items-center gap-2 [&::-webkit-details-marker]:hidden">
          <span className="text-xs font-semibold text-gray-800 flex-1 min-w-0">
            Клинические рекомендации (первоисточники)
          </span>
          <span className="text-[10px] font-normal text-gray-500 shrink-0 hidden sm:inline tabular-nums">
            {sourcesCountRu(list.length)}
          </span>
          <ChevronDownIcon
            className="clinical-sources-chevron w-4 h-4 shrink-0 text-gray-500 transition-transform duration-200"
            aria-hidden
          />
        </summary>
        <ul className="space-y-2.5 px-2.5 pb-2.5 pt-0">
          {list.map((s, i) => (
            <li key={i} className="text-sm leading-snug">
              {s.url ? (
                <a
                  href={s.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="font-medium text-[#2A9FFF] hover:underline inline-flex items-center gap-1 flex-wrap"
                >
                  <span className="min-w-0 break-words">{s.title || 'Открыть документ'}</span>
                  <ArrowTopRightOnSquareIcon className="w-3.5 h-3.5 shrink-0 opacity-80" aria-hidden />
                </a>
              ) : (
                <span className="font-medium text-gray-900">{s.title}</span>
              )}
              {s.description ? (
                <span className="block text-xs text-gray-600 mt-0.5">{s.description}</span>
              ) : null}
              {s.section_or_paragraph ? (
                <span className="block text-xs text-gray-500 mt-1 border-l-2 border-[#2A9FFF]/40 pl-2">
                  Раздел: {s.section_or_paragraph}
                </span>
              ) : null}
            </li>
          ))}
        </ul>
      </details>
    </div>
  );
}

export default InlineClinicalSources;
