import React from 'react';
import { 
  CpuChipIcon,
  CheckCircleIcon,
  ExclamationTriangleIcon,
  ClockIcon,
  PlayIcon,
  PauseIcon
} from '@heroicons/react/24/outline';
import type { AgentStatus } from '../types';

interface AgentStatusProps {
  agentStatus: AgentStatus | null;
  isLoading?: boolean;
  onStartProcessing?: () => void;
  onPauseProcessing?: () => void;
}

export const AgentStatusComponent: React.FC<AgentStatusProps> = ({
  agentStatus,
  isLoading = false,
  onStartProcessing,
  onPauseProcessing,
}) => {
  const getAgentIcon = (type: string) => {
    switch (type) {
      case 'triage':
        return <CpuChipIcon className="w-5 h-5" />;
      case 'specialist':
        return <CheckCircleIcon className="w-5 h-5" />;
      case 'coordinator':
        return <ClockIcon className="w-5 h-5" />;
      default:
        return <CpuChipIcon className="w-5 h-5" />;
    }
  };

  const getAgentTypeLabel = (type: string) => {
    switch (type) {
      case 'triage':
        return 'Сортировщик';
      case 'specialist':
        return 'Специалист';
      case 'coordinator':
        return 'Координатор';
      default:
        return 'Агент';
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'idle':
        return 'agent-card-idle';
      case 'processing':
        return 'agent-card-processing';
      case 'completed':
        return 'agent-card-completed';
      case 'error':
        return 'agent-card-error';
      default:
        return 'agent-card-idle';
    }
  };

  const getStatusIndicator = (status: string) => {
    switch (status) {
      case 'idle':
        return 'agent-status-idle';
      case 'processing':
        return 'agent-status-processing';
      case 'completed':
        return 'agent-status-completed';
      case 'error':
        return 'agent-status-error';
      default:
        return 'agent-status-idle';
    }
  };

  const getStatusLabel = (status: string) => {
    switch (status) {
      case 'idle':
        return 'Ожидает';
      case 'processing':
        return 'Обрабатывает';
      case 'completed':
        return 'Завершен';
      case 'error':
        return 'Ошибка';
      default:
        return 'Неизвестно';
    }
  };

  const getOverallProgressColor = (progress: number) => {
    if (progress === 100) return 'bg-green-500';
    if (progress >= 75) return 'bg-blue-500';
    if (progress >= 50) return 'bg-yellow-500';
    if (progress >= 25) return 'bg-orange-500';
    return 'bg-red-500';
  };

  const isAnyAgentProcessing = agentStatus?.agents.some(agent => agent.status === 'processing') || false;
  const allAgentsCompleted = agentStatus?.agents.every(agent => agent.status === 'completed') || false;

  if (isLoading) {
    return (
      <div className="card">
        <div className="card-header">
          <h3 className="card-title">Статус агентов</h3>
        </div>
        <div className="flex items-center justify-center py-8">
          <div className="loading-spinner w-8 h-8"></div>
          <span className="ml-2 text-gray-600">Загрузка статуса...</span>
        </div>
      </div>
    );
  }

  if (!agentStatus) {
    return (
      <div className="card">
        <div className="card-header">
          <h3 className="card-title">Статус агентов</h3>
        </div>
        <div className="text-center py-8 text-gray-500">
          <CpuChipIcon className="w-12 h-12 mx-auto mb-4 text-gray-400" />
          <p>Статус агентов недоступен</p>
          <p className="text-sm mt-2">
            Начните консультацию для активации мультиагентной системы
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="card">
      <div className="card-header">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="card-title">Статус агентов</h3>
            <p className="card-description">
              Мультиагентная система анализа симптомов
            </p>
          </div>
          
          {/* Control Buttons */}
          <div className="flex space-x-2">
            {!isAnyAgentProcessing && !allAgentsCompleted && onStartProcessing && (
              <button
                onClick={onStartProcessing}
                className="btn btn-primary flex items-center space-x-1"
              >
                <PlayIcon className="w-4 h-4" />
                <span>Запустить</span>
              </button>
            )}
            
            {isAnyAgentProcessing && onPauseProcessing && (
              <button
                onClick={onPauseProcessing}
                className="btn btn-secondary flex items-center space-x-1"
              >
                <PauseIcon className="w-4 h-4" />
                <span>Пауза</span>
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Overall Progress */}
      <div className="mb-6">
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm font-medium text-gray-700">Общий прогресс</span>
          <span className="text-sm text-gray-600">{agentStatus.overallProgress}%</span>
        </div>
        <div className="progress-bar">
          <div
            className={`progress-fill ${getOverallProgressColor(agentStatus.overallProgress)}`}
            style={{ width: `${agentStatus.overallProgress}%` }}
          ></div>
        </div>
        <div className="mt-2 text-sm text-gray-600">
          Текущий шаг: {agentStatus.currentStep === 'feedback_requested' ? 'ожидание обратной связи' : agentStatus.currentStep}
        </div>
      </div>

      {/* Individual Agents */}
      <div className="space-y-4">
        {agentStatus.agents.map((agent) => (
          <div key={agent.id} className={`agent-card ${getStatusColor(agent.status)}`}>
            <div className="flex items-start justify-between mb-3">
              <div className="flex items-center space-x-3">
                <div className={`agent-status-indicator ${getStatusIndicator(agent.status)}`}></div>
                <div>
                  <h4 className="font-semibold text-gray-900 flex items-center space-x-2">
                    <span>{getAgentIcon(agent.type)}</span>
                    <span>{agent.name}</span>
                  </h4>
                  <p className="text-sm text-gray-600">
                    {getAgentTypeLabel(agent.type)}
                  </p>
                </div>
              </div>
              
              <div className="text-right">
                <span className={`px-2 py-1 rounded-full text-xs font-medium ${
                  agent.status === 'processing' ? 'bg-blue-100 text-blue-800' :
                  agent.status === 'completed' ? 'bg-green-100 text-green-800' :
                  agent.status === 'error' ? 'bg-red-100 text-red-800' :
                  'bg-gray-100 text-gray-800'
                }`}>
                  {getStatusLabel(agent.status)}
                </span>
              </div>
            </div>

            {/* Agent Progress */}
            <div className="mb-3">
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs text-gray-600">Прогресс</span>
                <span className="text-xs text-gray-600">{agent.progress}%</span>
              </div>
              <div className="progress-bar h-1">
                <div
                  className={`progress-fill h-1 ${getOverallProgressColor(agent.progress)}`}
                  style={{ width: `${agent.progress}%` }}
                ></div>
              </div>
            </div>

            {/* Current Task */}
            {agent.currentTask && (
              <div className="text-sm text-gray-700 mb-2">
                <span className="font-medium">Текущая задача:</span>{' '}
                {agent.currentTask === 'feedback_requested' ? 'ожидание обратной связи' : agent.currentTask}
              </div>
            )}

            {/* Agent Result (if completed) */}
            {agent.status === 'completed' && agent.result && (
              <div className="mt-3 p-3 bg-green-50 rounded border border-green-200">
                <div className="flex items-start space-x-2">
                  <CheckCircleIcon className="w-4 h-4 text-green-600 mt-0.5" />
                  <div className="text-sm text-green-800">
                    <div className="font-medium mb-1">Результат:</div>
                    <div>{typeof agent.result === 'string' ? agent.result : JSON.stringify(agent.result)}</div>
                  </div>
                </div>
              </div>
            )}

            {/* Error (if any) */}
            {agent.status === 'error' && (
              <div className="mt-3 p-3 bg-red-50 rounded border border-red-200">
                <div className="flex items-start space-x-2">
                  <ExclamationTriangleIcon className="w-4 h-4 text-red-600 mt-0.5" />
                  <div className="text-sm text-red-800">
                    <div className="font-medium mb-1">Ошибка:</div>
                    <div>Произошла ошибка при обработке запроса</div>
                  </div>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>

      {/* System Status */}
      <div className="mt-6 p-4 bg-blue-50 rounded-lg border border-blue-200">
        <div className="flex items-start space-x-2">
          <CpuChipIcon className="w-5 h-5 text-blue-600 mt-0.5" />
          <div>
            <h4 className="font-medium text-blue-900 mb-1">Статус системы</h4>
            <p className="text-sm text-blue-800">
              {agentStatus.currentStep === 'feedback_requested'
                ? 'Рекомендации готовы. Ответьте на вопросы обратной связи в чате.'
                : allAgentsCompleted 
                ? 'Все агенты завершили работу. Рекомендации готовы.'
                : isAnyAgentProcessing 
                ? 'Система анализирует симптомы. Это может занять несколько минут.'
                : 'Система готова к работе. Нажмите "Запустить" для начала анализа.'
              }
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default AgentStatusComponent;