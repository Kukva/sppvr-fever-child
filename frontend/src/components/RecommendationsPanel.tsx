import React from 'react';
import { 
  ExclamationTriangleIcon,
  CheckCircleIcon,
  InformationCircleIcon,
  ShieldCheckIcon,
  DocumentTextIcon,
  LinkIcon
} from '@heroicons/react/24/outline';
import type { Recommendation, Diagnosis } from '../types';

interface RecommendationsPanelProps {
  recommendations: Recommendation[];
  isLoading?: boolean;
}

export const RecommendationsPanel: React.FC<RecommendationsPanelProps> = ({
  recommendations,
  isLoading = false,
}) => {
  const getPriorityIcon = (priority: string) => {
    switch (priority) {
      case 'urgent':
        return <ExclamationTriangleIcon className="w-5 h-5 text-red-500" />;
      case 'high':
        return <ExclamationTriangleIcon className="w-5 h-5 text-orange-500" />;
      case 'medium':
        return <InformationCircleIcon className="w-5 h-5 text-yellow-500" />;
      case 'low':
        return <CheckCircleIcon className="w-5 h-5 text-green-500" />;
      default:
        return <InformationCircleIcon className="w-5 h-5 text-gray-500" />;
    }
  };

  const getCategoryIcon = (category: string) => {
    switch (category) {
      case 'emergency':
        return <ExclamationTriangleIcon className="w-5 h-5 text-red-500" />;
      case 'medication':
        return <ShieldCheckIcon className="w-5 h-5 text-blue-500" />;
      case 'observation':
        return <InformationCircleIcon className="w-5 h-5 text-yellow-500" />;
      case 'consultation':
        return <CheckCircleIcon className="w-5 h-5 text-green-500" />;
      default:
        return <InformationCircleIcon className="w-5 h-5 text-gray-500" />;
    }
  };

  const getPriorityColor = (priority: string) => {
    switch (priority) {
      case 'urgent':
        return 'border-red-300 bg-red-50';
      case 'high':
        return 'border-orange-300 bg-orange-50';
      case 'medium':
        return 'border-yellow-300 bg-yellow-50';
      case 'low':
        return 'border-green-300 bg-green-50';
      default:
        return 'border-gray-300 bg-gray-50';
    }
  };

  const getCategoryColor = (category: string) => {
    switch (category) {
      case 'emergency':
        return 'bg-red-100 text-red-800';
      case 'medication':
        return 'bg-blue-100 text-blue-800';
      case 'observation':
        return 'bg-yellow-100 text-yellow-800';
      case 'consultation':
        return 'bg-green-100 text-green-800';
      default:
        return 'bg-gray-100 text-gray-800';
    }
  };

  const getPriorityLabel = (priority: string) => {
    switch (priority) {
      case 'urgent':
        return 'Срочно';
      case 'high':
        return 'Высокий';
      case 'medium':
        return 'Средний';
      case 'low':
        return 'Низкий';
      default:
        return 'Обычный';
    }
  };

  const getCategoryLabel = (category: string) => {
    switch (category) {
      case 'emergency':
        return 'Экстренная помощь';
      case 'medication':
        return 'Лекарства';
      case 'observation':
        return 'Наблюдение';
      case 'consultation':
        return 'Консультация';
      default:
        return 'Общее';
    }
  };

  const formatTimestamp = (timestamp: string) => {
    return new Date(timestamp).toLocaleString('ru-RU', {
      day: 'numeric',
      month: 'short',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const getConfidenceColor = (confidence: 'high' | 'medium' | 'low') => {
    switch (confidence) {
      case 'high':
        return 'bg-green-100 text-green-800 border-green-300';
      case 'medium':
        return 'bg-yellow-100 text-yellow-800 border-yellow-300';
      case 'low':
        return 'bg-gray-100 text-gray-800 border-gray-300';
      default:
        return 'bg-gray-100 text-gray-800 border-gray-300';
    }
  };

  const getConfidenceLabel = (confidence: 'high' | 'medium' | 'low') => {
    switch (confidence) {
      case 'high':
        return 'Высокая';
      case 'medium':
        return 'Средняя';
      case 'low':
        return 'Низкая';
      default:
        return 'Неизвестно';
    }
  };

  // Извлекаем все диагнозы из рекомендаций
  const allDiagnoses: Diagnosis[] = [];
  recommendations.forEach(rec => {
    if (rec.possible_diagnoses && rec.possible_diagnoses.length > 0) {
      allDiagnoses.push(...rec.possible_diagnoses);
    }
  });

  const sortedRecommendations = [...recommendations].sort((a, b) => {
    const priorityOrder = { urgent: 0, high: 1, medium: 2, low: 3 };
    const aPriority = priorityOrder[a.priority as keyof typeof priorityOrder] || 4;
    const bPriority = priorityOrder[b.priority as keyof typeof priorityOrder] || 4;
    return aPriority - bPriority;
  });

  if (isLoading) {
    return (
      <div className="card">
        <div className="card-header">
          <h3 className="card-title">Рекомендации</h3>
        </div>
        <div className="flex items-center justify-center py-8">
          <div className="loading-spinner w-8 h-8"></div>
          <span className="ml-2 text-gray-600">Загрузка рекомендаций...</span>
        </div>
      </div>
    );
  }

  if (recommendations.length === 0) {
    return (
      <div className="card">
        <div className="card-header">
          <h3 className="card-title">Рекомендации</h3>
        </div>
        <div className="text-center py-8 text-gray-500">
          <InformationCircleIcon className="w-12 h-12 mx-auto mb-4 text-gray-400" />
          <p>Рекомендации пока не доступны</p>
          <p className="text-sm mt-2">
            Заполните информацию о пациенте и начните чат для получения рекомендаций
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="card">
      <div className="card-header">
        <h3 className="card-title">Рекомендации ({recommendations.length})</h3>
        <p className="card-description">
          Медицинские рекомендации на основе анализа симптомов
        </p>
      </div>

      <div className="space-y-4">
        {/* Секция возможных диагнозов */}
        {allDiagnoses.length > 0 && (
          <div className="mb-6">
            <h4 className="text-lg font-semibold text-gray-900 mb-4 flex items-center">
              <DocumentTextIcon className="w-5 h-5 mr-2 text-blue-600" />
              Возможные диагнозы
            </h4>
            <div className="space-y-4">
              {allDiagnoses.map((diagnosis, index) => (
                <div
                  key={index}
                  className="border rounded-lg p-4 bg-white shadow-sm hover:shadow-md transition-shadow"
                >
                  <div className="flex items-start justify-between mb-3">
                    <h5 className="font-semibold text-gray-900 text-base">
                      {diagnosis.diagnosis}
                    </h5>
                    <span className={`px-3 py-1 rounded-full text-xs font-medium border ${getConfidenceColor(diagnosis.confidence)}`}>
                      {getConfidenceLabel(diagnosis.confidence)} уверенность
                    </span>
                  </div>

                  <div className="mb-3">
                    <p className="text-sm text-gray-700 leading-relaxed">
                      <span className="font-medium text-gray-900">Обоснование: </span>
                      {diagnosis.reasoning}
                    </p>
                  </div>

                  {diagnosis.clinical_recommendation_url && (
                    <div className="mb-3">
                      <a
                        href={diagnosis.clinical_recommendation_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center text-sm text-blue-600 hover:text-blue-800 hover:underline"
                      >
                        <LinkIcon className="w-4 h-4 mr-1" />
                        Клиническая рекомендация
                      </a>
                    </div>
                  )}

                  {diagnosis.required_tests && diagnosis.required_tests.length > 0 && (
                    <div className="mt-3 pt-3 border-t border-gray-200">
                      <p className="text-sm font-medium text-gray-900 mb-2">
                        Необходимые обследования:
                      </p>
                      <ul className="list-disc list-inside space-y-1">
                        {diagnosis.required_tests.map((test, testIndex) => (
                          <li key={testIndex} className="text-sm text-gray-700">
                            {test}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Секция рекомендаций */}
        {sortedRecommendations.length > 0 && (
          <div>
            <h4 className="text-lg font-semibold text-gray-900 mb-4">
              Рекомендации ({sortedRecommendations.length})
            </h4>
            <div className="space-y-4">
              {sortedRecommendations.map((recommendation) => (
                <div
                  key={recommendation.id}
                  className={`border rounded-lg p-4 transition-all duration-200 hover:shadow-md ${getPriorityColor(
                    recommendation.priority
                  )}`}
                >
                  <div className="flex items-start justify-between mb-3">
                    <div className="flex items-center space-x-2">
                      {getPriorityIcon(recommendation.priority)}
                      <h4 className="font-semibold text-gray-900">
                        {recommendation.title}
                      </h4>
                    </div>
                    
                    <div className="flex items-center space-x-2">
                      <span className={`px-2 py-1 rounded-full text-xs font-medium ${getCategoryColor(
                        recommendation.category
                      )}`}>
                        {getCategoryLabel(recommendation.category)}
                      </span>
                      <span className="text-xs text-gray-500">
                        {getPriorityLabel(recommendation.priority)}
                      </span>
                    </div>
                  </div>

                  <div className="flex items-start space-x-2 mb-3">
                    {getCategoryIcon(recommendation.category)}
                    <p className="text-gray-700 text-sm leading-relaxed">
                      {recommendation.description}
                    </p>
                  </div>

                  <div className="flex items-center justify-between text-xs text-gray-500">
                    <span>
                      Агент: {recommendation.agentId}
                    </span>
                    <span>
                      {formatTimestamp(recommendation.timestamp)}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Summary Section */}
      <div className="mt-6 p-4 bg-blue-50 rounded-lg border border-blue-200">
        <div className="flex items-start space-x-2">
          <InformationCircleIcon className="w-5 h-5 text-blue-600 mt-0.5" />
          <div>
            <h4 className="font-medium text-blue-900 mb-1">Важная информация</h4>
            <p className="text-sm text-blue-800">
              Рекомендации сформированы ИИ-системой для поддержки клинического решения и не заменяют осмотр пациента,
              действующие протоколы и суждение врача. Тяжесть и срочность оценивайте по клиническим критериям и стандартам вашего учреждения.
            </p>
          </div>
        </div>
      </div>

      {/* Emergency Warning */}
      {recommendations.some(r => r.category === 'emergency') && (
        <div className="mt-4 p-4 bg-red-50 rounded-lg border border-red-200">
          <div className="flex items-start space-x-2">
            <ExclamationTriangleIcon className="w-5 h-5 text-red-600 mt-0.5" />
            <div>
              <h4 className="font-medium text-red-900 mb-1">⚠️ Требуется срочная помощь</h4>
              <p className="text-sm text-red-800">
                Обнаружены признаки, требующие немедленного клинического вмешательства.
                Рассмотрите немедленную госпитализацию или вызов бригады неотложной помощи по протоколам вашего учреждения.
              </p>
              <p className="text-sm text-red-800 mt-2">
                Вне стационара при показаниях — телефоны экстренных служб 103 / 112.
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default RecommendationsPanel;