import React from 'react';
import { DocumentTextIcon, ArrowTopRightOnSquareIcon } from '@heroicons/react/24/outline';
import type { ClinicalSource } from '../types';

interface ClinicalSourcesPanelProps {
  sources: ClinicalSource[];
}

function isMinzdravUrl(url: string | undefined): boolean {
  if (!url) return false;
  return url.toLowerCase().includes('cr.minzdrav.gov.ru');
}

export const ClinicalSourcesPanel: React.FC<ClinicalSourcesPanelProps> = ({ sources }) => {
  if (!sources || sources.length === 0) {
    return (
      <div className="rounded-xl border border-gray-200 bg-gray-50/50 p-6 text-center text-gray-500">
        <DocumentTextIcon className="w-10 h-10 mx-auto mb-2 text-gray-400" />
        <p className="text-sm">Ссылки на клинические рекомендации появятся после анализа.</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <h3 className="text-sm font-semibold text-gray-700 flex items-center gap-2">
        <DocumentTextIcon className="w-4 h-4" />
        Клинические рекомендации
      </h3>
      <p className="text-xs text-gray-500">
        Источники для проверки выводов: прямые ссылки на КР, раздел в документе и фрагмент текста для сверки с
        первоисточником.
      </p>
      <ul className="space-y-3">
        {sources.map((source, index) => {
          const minzdrav = isMinzdravUrl(source.url);
          return (
            <li key={index}>
              <div
                className={`rounded-lg border bg-white p-4 shadow-sm transition-colors ${
                  minzdrav
                    ? 'border-[#2A9FFF]/50 border-l-4 border-l-[#2A9FFF] bg-blue-50/40'
                    : 'border-gray-200 hover:border-[#2A9FFF]/60'
                }`}
              >
                <div className="flex flex-wrap items-center gap-2">
                  {minzdrav && (
                    <span className="inline-flex items-center rounded-full bg-[#2A9FFF]/15 px-2.5 py-0.5 text-xs font-medium text-[#1a7fd4]">
                      КР МЗ РФ
                    </span>
                  )}
                  <p className="font-medium text-gray-900 min-w-0 flex-1">{source.title}</p>
                </div>
                {source.description && <p className="mt-1 text-sm text-gray-600">{source.description}</p>}
                {source.supports_claim && (
                  <p className="mt-2 text-xs text-gray-600">
                    <span className="font-medium text-gray-700">Относится к выводу:</span> {source.supports_claim}
                  </p>
                )}
                {source.section_or_paragraph && (
                  <p className="mt-2 text-xs text-gray-500 border-l-2 border-[#2A9FFF]/40 pl-2">
                    <span className="font-medium text-gray-600">Где в документе:</span> {source.section_or_paragraph}
                  </p>
                )}
                {source.verbatim_excerpt && (
                  <blockquote className="mt-3 border-l-4 border-gray-300 bg-gray-50/80 py-2 pl-3 pr-2 text-sm text-gray-700 italic">
                    <p className="text-xs font-normal not-italic text-gray-500 mb-1">Фрагмент для сверки с КР</p>
                    {source.verbatim_excerpt}
                  </blockquote>
                )}
                <div className="mt-3 flex items-center gap-2">
                  {source.url ? (
                    <a
                      href={source.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1.5 text-sm font-medium text-[#2A9FFF] hover:underline"
                    >
                      <ArrowTopRightOnSquareIcon className="w-4 h-4 shrink-0" />
                      Открыть рекомендацию
                    </a>
                  ) : (
                    <span className="text-xs text-gray-400">URL не указан — уточните по названию в реестре КР</span>
                  )}
                </div>
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
};

export default ClinicalSourcesPanel;
