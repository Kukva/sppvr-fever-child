import React from 'react';
import {
  ClockIcon,
  ChatBubbleLeftRightIcon,
  TrashIcon,
  PlusIcon,
} from '@heroicons/react/24/outline';
import { Header } from './Header';
import { PageDoodleBackground } from './PageDoodleBackground';
import type { SessionHistory } from '../types';

const statCardClass =
  'rounded-[24px] sm:rounded-[30px] border border-figma-accentBorder bg-white/85 shadow-figma-card backdrop-blur-sm p-6';
const listCardClass =
  'rounded-[24px] sm:rounded-[30px] border border-figma-accentBorder bg-white/85 shadow-figma-card backdrop-blur-sm p-5 sm:p-6 hover:border-figma-accent transition-all cursor-pointer group';

export interface HistoryItemDisplay {
  id: string;
  title: string;
  preview: string;
  date: Date;
  messagesCount: number;
}

interface HistoryScreenProps {
  items: HistoryItemDisplay[];
  isLoading?: boolean;
  onStartNew: () => void;
  onOpenChat?: (item: HistoryItemDisplay) => void;
  onDelete?: (id: string) => void;
}

function formatDate(date: Date) {
  const today = new Date();
  const yesterday = new Date(today);
  yesterday.setDate(yesterday.getDate() - 1);

  if (date.toDateString() === today.toDateString()) {
    return `Сегодня, ${date.toLocaleTimeString('ru-RU', {
      hour: '2-digit',
      minute: '2-digit',
    })}`;
  }
  if (date.toDateString() === yesterday.toDateString()) {
    return `Вчера, ${date.toLocaleTimeString('ru-RU', {
      hour: '2-digit',
      minute: '2-digit',
    })}`;
  }
  return date.toLocaleDateString('ru-RU', {
    day: 'numeric',
    month: 'long',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function HistoryScreen({
  items,
  isLoading = false,
  onStartNew,
  onOpenChat,
  onDelete,
}: HistoryScreenProps) {
  const handleDelete = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    onDelete?.(id);
  };

  const totalMessages = items.reduce(
    (acc, item) => acc + item.messagesCount,
    0
  );
  const lastDate = items.length > 0 ? new Date(items[0].date) : null;

  if (isLoading) {
    return (
      <div className="min-h-screen bg-gradient-to-b from-[#F0F4F8] to-white flex flex-col relative overflow-hidden">
        <PageDoodleBackground />
        <Header />
        <main className="flex-1 px-4 sm:px-6 py-10 sm:py-12 relative z-10 max-w-6xl mx-auto w-full">
          <div className="animate-pulse space-y-4">
            <div className="h-10 bg-gray-200/80 rounded-xl w-1/3 mb-8 max-w-xs" />
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
              {[1, 2, 3].map((i) => (
                <div
                  key={i}
                  className="h-28 rounded-[24px] border border-figma-accentSoft bg-white/50"
                />
              ))}
            </div>
            <div className="space-y-4">
              {[1, 2, 3, 4, 5].map((i) => (
                <div
                  key={i}
                  className="h-32 rounded-[24px] border border-figma-accentSoft bg-white/50"
                />
              ))}
            </div>
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-b from-[#F0F4F8] to-white flex flex-col relative overflow-hidden">
      <PageDoodleBackground />
      <Header />

      <main className="flex-1 px-4 sm:px-6 py-10 sm:py-12 relative z-10 max-w-6xl mx-auto w-full">
        <div className="flex flex-col gap-6 sm:flex-row sm:items-start sm:justify-between mb-8 sm:mb-10">
          <div>
            <h1 className="text-2xl sm:text-3xl md:text-4xl font-semibold text-figma-ink mb-2">
              История консультаций
            </h1>
            <p className="text-gray-600 text-sm sm:text-base">
              Все ваши предыдущие обращения к AI-ассистенту
            </p>
          </div>
          <button
            type="button"
            onClick={onStartNew}
            className="inline-flex shrink-0 items-center justify-center gap-2 px-6 py-3 bg-[#2A9FFF] hover:bg-[#2290e6] text-white rounded-xl transition-colors font-medium shadow-md"
          >
            <PlusIcon className="w-5 h-5" />
            Новая консультация
          </button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
          <div className={statCardClass}>
            <div className="flex items-center gap-3 mb-2">
              <div className="w-10 h-10 rounded-[10px] bg-[#2A9FFF]/15 flex items-center justify-center border border-figma-accentSoft">
                <ChatBubbleLeftRightIcon className="w-5 h-5 text-figma-accent" />
              </div>
              <span className="text-sm font-medium text-figma-ink">
                Всего консультаций
              </span>
            </div>
            <p className="text-3xl font-semibold text-figma-ink">
              {items.length}
            </p>
          </div>

          <div className={statCardClass}>
            <div className="flex items-center gap-3 mb-2">
              <div className="w-10 h-10 rounded-[10px] bg-[#2A9FFF]/15 flex items-center justify-center border border-figma-accentSoft">
                <ChatBubbleLeftRightIcon className="w-5 h-5 text-figma-accent" />
              </div>
              <span className="text-sm font-medium text-figma-ink">
                Всего сообщений
              </span>
            </div>
            <p className="text-3xl font-semibold text-figma-ink">
              {totalMessages}
            </p>
          </div>

          <div className={statCardClass}>
            <div className="flex items-center gap-3 mb-2">
              <div className="w-10 h-10 rounded-[10px] bg-[#2A9FFF]/15 flex items-center justify-center border border-figma-accentSoft">
                <ClockIcon className="w-5 h-5 text-figma-accent" />
              </div>
              <span className="text-sm font-medium text-figma-ink">
                Последняя консультация
              </span>
            </div>
            <p className="text-lg font-semibold text-figma-ink">
              {lastDate ? formatDate(lastDate).split(',')[0] : '—'}
            </p>
          </div>
        </div>

        {items.length > 0 ? (
          <div className="space-y-4">
            {items.map((item) => (
              <div
                key={item.id}
                role="button"
                tabIndex={0}
                onClick={() => onOpenChat?.(item)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    onOpenChat?.(item);
                  }
                }}
                className={listCardClass}
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-3 mb-3">
                      <div className="w-10 h-10 rounded-full bg-[#2A9FFF]/12 border border-figma-accentSoft flex items-center justify-center shrink-0">
                        <ChatBubbleLeftRightIcon className="w-5 h-5 text-figma-accent" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <h3 className="font-medium text-figma-ink text-lg mb-1 group-hover:text-figma-accent transition-colors">
                          {item.title}
                        </h3>
                        <div className="flex items-center gap-4 text-sm text-gray-600 flex-wrap">
                          <span className="flex items-center gap-1">
                            <ClockIcon className="w-4 h-4 shrink-0 text-figma-accent" />
                            {formatDate(item.date)}
                          </span>
                          <span className="flex items-center gap-1">
                            <ChatBubbleLeftRightIcon className="w-4 h-4 shrink-0 text-figma-accent" />
                            {item.messagesCount} сообщений
                          </span>
                        </div>
                      </div>
                    </div>
                    <p className="text-gray-600 text-sm line-clamp-2 pl-[52px]">
                      {item.preview}
                    </p>
                  </div>
                  {onDelete && (
                    <button
                      type="button"
                      onClick={(e) => handleDelete(item.id, e)}
                      className="p-2 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors opacity-0 group-hover:opacity-100 shrink-0"
                      aria-label="Удалить"
                    >
                      <TrashIcon className="w-5 h-5" />
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div
            className={`${statCardClass} text-center py-16 max-w-lg mx-auto`}
          >
            <div className="w-20 h-20 rounded-full bg-[#2A9FFF]/10 border border-figma-accentSoft flex items-center justify-center mx-auto mb-6">
              <ChatBubbleLeftRightIcon className="w-10 h-10 text-figma-accent opacity-70" />
            </div>
            <h3 className="text-xl font-semibold text-figma-ink mb-2">
              История пуста
            </h3>
            <p className="text-gray-600 mb-6 text-sm sm:text-base">
              У вас пока нет сохранённых консультаций
            </p>
            <button
              type="button"
              onClick={onStartNew}
              className="px-6 py-3 bg-[#2A9FFF] hover:bg-[#2290e6] text-white rounded-xl transition-colors font-medium shadow-md"
            >
              Начать первую консультацию
            </button>
          </div>
        )}
      </main>

      <footer className="py-4 border-t border-gray-200/80 bg-white/60 backdrop-blur-sm relative z-10">
        <p className="text-xs text-gray-500 text-center max-w-3xl mx-auto px-4">
          Вспомогательный инструмент. Не заменяет очный приём и осмотр врача.
        </p>
      </footer>
    </div>
  );
}

/** Маппинг SessionHistory API → HistoryItemDisplay для HistoryScreen */
export function mapSessionsToHistoryItems(
  sessions: SessionHistory[]
): HistoryItemDisplay[] {
  return sessions
    .slice()
    .sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime())
    .map((s) => ({
      id: s.id,
      title:
        s.patientName && s.patientName !== 'Anonymous'
          ? s.patientName
          : s.summary,
      preview: s.summary,
      date: new Date(s.date),
      messagesCount: s.recommendationsCount ?? 0,
    }));
}
