import React, { useMemo, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';

import {
  HistoryScreen,
  mapSessionsToHistoryItems,
  type HistoryItemDisplay,
} from '../components/HistoryScreen';
import { useSessionHistory } from '../hooks/useApi';

export const HistoryPage: React.FC = () => {
  const navigate = useNavigate();
  const { data: sessionsData, loading, error } = useSessionHistory();

  const historyItems = useMemo<HistoryItemDisplay[]>(
    () => mapSessionsToHistoryItems(sessionsData?.sessions ?? []),
    [sessionsData?.sessions]
  );

  useEffect(() => {
    if (error) {
      toast.error('Ошибка загрузки истории сессий');
    }
  }, [error]);

  const handleStartNew = () => {
    navigate('/');
  };

  const handleOpenChat = (item: HistoryItemDisplay) => {
    const url = `${window.location.origin}/consultation?session=${item.id}`;
    window.open(url, '_blank', 'noopener,noreferrer');
  };

  const handleDelete = (id: string) => {
    // API удаления сессии будет подключён при появлении эндпоинта на бэкенде
    toast('Удаление сессий пока недоступно', { icon: 'ℹ️' });
  };

  return (
    <HistoryScreen
      items={historyItems}
      isLoading={loading}
      onStartNew={handleStartNew}
      onOpenChat={handleOpenChat}
      onDelete={handleDelete}
    />
  );
};

export default HistoryPage;