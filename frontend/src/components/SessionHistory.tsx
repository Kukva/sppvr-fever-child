import React, { useState } from 'react';
import { 
  ClockIcon,
  CalendarIcon,
  DocumentTextIcon,
  EyeIcon,
  FunnelIcon,
  MagnifyingGlassIcon
} from '@heroicons/react/24/outline';
import type { SessionHistory as SessionHistoryType } from '../types';

interface SessionHistoryProps {
  sessions: SessionHistoryType[];
  isLoading?: boolean;
  onViewSession?: (sessionId: string) => void;
  onExportSession?: (sessionId: string) => void;
}

export const SessionHistoryComponent: React.FC<SessionHistoryProps> = ({
  sessions,
  isLoading = false,
  onViewSession,
  onExportSession,
}) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [sortBy, setSortBy] = useState<'date' | 'status' | 'recommendations'>('date');

  const filteredSessions = sessions.filter(session => {
    const matchesSearch = session.patientName.toLowerCase().includes(searchTerm.toLowerCase()) ||
                         session.summary.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesStatus = statusFilter === 'all' || session.status === statusFilter;
    return matchesSearch && matchesStatus;
  });

  const sortedSessions = [...filteredSessions].sort((a, b) => {
    switch (sortBy) {
      case 'date':
        return new Date(b.date).getTime() - new Date(a.date).getTime();
      case 'status':
        return a.status.localeCompare(b.status);
      case 'recommendations':
        return b.recommendationsCount - a.recommendationsCount;
      default:
        return 0;
    }
  });

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'completed':
        return 'bg-green-100 text-green-800';
      case 'active':
        return 'bg-blue-100 text-blue-800';
      case 'paused':
        return 'bg-yellow-100 text-yellow-800';
      default:
        return 'bg-gray-100 text-gray-800';
    }
  };

  const getStatusLabel = (status: string) => {
    switch (status) {
      case 'completed':
        return 'Завершена';
      case 'active':
        return 'Активна';
      case 'paused':
        return 'Приостановлена';
      default:
        return 'Неизвестно';
    }
  };

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleDateString('ru-RU', {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
    });
  };

  const formatTime = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleTimeString('ru-RU', {
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const handleViewSession = (sessionId: string) => {
    if (onViewSession) {
      onViewSession(sessionId);
    }
  };

  const handleExportSession = (sessionId: string) => {
    if (onExportSession) {
      onExportSession(sessionId);
    }
  };

  if (isLoading) {
    return (
      <div className="card">
        <div className="card-header">
          <h3 className="card-title">История сессий</h3>
        </div>
        <div className="space-y-4">
          {[1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="border rounded-lg p-4 animate-pulse">
              <div className="flex items-center justify-between mb-2">
                <div className="h-4 bg-gray-200 rounded w-1/3"></div>
                <div className="h-4 bg-gray-200 rounded w-1/4"></div>
              </div>
              <div className="h-3 bg-gray-200 rounded w-full mb-2"></div>
              <div className="h-3 bg-gray-200 rounded w-2/3"></div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (sessions.length === 0) {
    return (
      <div className="card">
        <div className="card-header">
          <h3 className="card-title">История сессий</h3>
        </div>
        <div className="text-center py-8 text-gray-500">
          <ClockIcon className="w-12 h-12 mx-auto mb-4 text-gray-400" />
          <p>История сессий пуста</p>
          <p className="text-sm mt-2">
            Начните новую консультацию, чтобы увидеть ее здесь
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="card">
      <div className="card-header">
        <h3 className="card-title">История сессий ({sessions.length})</h3>
        <p className="card-description">
          Просмотр предыдущих консультаций и их результатов
        </p>
      </div>

      {/* Filters and Search */}
      <div className="mb-6 space-y-4">
        {/* Search */}
        <div className="relative">
          <MagnifyingGlassIcon className="absolute left-3 top-1/2 transform -translate-y-1/2 w-5 h-5 text-gray-400" />
          <input
            type="text"
            placeholder="Поиск по имени пациента или описанию..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="form-input pl-10"
          />
        </div>

        {/* Filters */}
        <div className="flex flex-wrap gap-4">
          {/* Status Filter */}
          <div className="flex items-center space-x-2">
            <FunnelIcon className="w-4 h-4 text-gray-400" />
            <label className="text-sm font-medium text-gray-700">Статус:</label>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="form-input text-sm py-1"
            >
              <option value="all">Все ({sessions.length})</option>
              <option value="completed">Завершенные ({sessions.filter(s => s.status === 'completed').length})</option>
              <option value="active">Активные ({sessions.filter(s => s.status === 'active').length})</option>
              <option value="paused">Приостановленные ({sessions.filter(s => s.status === 'paused').length})</option>
            </select>
          </div>

          {/* Sort */}
          <div className="flex items-center space-x-2">
            <label className="text-sm font-medium text-gray-700">Сортировка:</label>
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value as any)}
              className="form-input text-sm py-1"
            >
              <option value="date">По дате</option>
              <option value="status">По статусу</option>
              <option value="recommendations">По количеству рекомендаций</option>
            </select>
          </div>
        </div>
      </div>

      {/* Sessions List */}
      <div className="space-y-4">
        {sortedSessions.map((session) => (
          <div
            key={session.id}
            className="border rounded-lg p-4 hover:shadow-md transition-shadow duration-200"
          >
            <div className="flex items-start justify-between mb-3">
              <div className="flex-1">
                <div className="flex items-center space-x-2 mb-2">
                  <h4 className="font-semibold text-gray-900">{session.patientName}</h4>
                  <span className={`px-2 py-1 rounded-full text-xs font-medium ${getStatusColor(session.status)}`}>
                    {getStatusLabel(session.status)}
                  </span>
                </div>
                
                <div className="flex items-center space-x-4 text-sm text-gray-600 mb-2">
                  <div className="flex items-center space-x-1">
                    <CalendarIcon className="w-4 h-4" />
                    <span>{formatDate(session.date)}</span>
                  </div>
                  <div className="flex items-center space-x-1">
                    <ClockIcon className="w-4 h-4" />
                    <span>{formatTime(session.date)}</span>
                  </div>
                  <div className="flex items-center space-x-1">
                    <DocumentTextIcon className="w-4 h-4" />
                    <span>{session.recommendationsCount} рекомендаций</span>
                  </div>
                </div>
                
                <p className="text-sm text-gray-700 line-clamp-2">
                  {session.summary}
                </p>
              </div>
            </div>

            {/* Actions */}
            <div className="flex items-center justify-end space-x-2">
              <button
                onClick={() => handleViewSession(session.id)}
                className="btn btn-secondary text-sm px-3 py-1 flex items-center space-x-1"
                type="button"
              >
                <EyeIcon className="w-4 h-4" />
                <span>Просмотр</span>
              </button>
              
              {session.status === 'completed' && (
                <button
                  onClick={() => handleExportSession(session.id)}
                  className="btn btn-outline text-sm px-3 py-1 flex items-center space-x-1"
                >
                  <DocumentTextIcon className="w-4 h-4" />
                  <span>PDF</span>
                </button>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* No Results */}
      {sortedSessions.length === 0 && (
        <div className="text-center py-8 text-gray-500">
          <p>Сессии не найдены</p>
          <button
            onClick={() => {
              setSearchTerm('');
              setStatusFilter('all');
            }}
            className="mt-2 text-medical-blue hover:underline text-sm"
          >
            Сбросить фильтры
          </button>
        </div>
      )}

      {/* Summary Stats */}
      <div className="mt-6 pt-6 border-t border-gray-200">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-center">
          <div>
            <div className="text-2xl font-bold text-gray-900">{sessions.length}</div>
            <div className="text-sm text-gray-600">Всего сессий</div>
          </div>
          <div>
            <div className="text-2xl font-bold text-green-600">
              {sessions.filter(s => s.status === 'completed').length}
            </div>
            <div className="text-sm text-gray-600">Завершено</div>
          </div>
          <div>
            <div className="text-2xl font-bold text-blue-600">
              {sessions.filter(s => s.status === 'active').length}
            </div>
            <div className="text-sm text-gray-600">Активно</div>
          </div>
          <div>
            <div className="text-2xl font-bold text-gray-600">
              {sessions.reduce((sum, s) => sum + s.recommendationsCount, 0)}
            </div>
            <div className="text-sm text-gray-600">Всего рекомендаций</div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default SessionHistoryComponent;