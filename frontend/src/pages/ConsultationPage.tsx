import React, {
  useState,
  useEffect,
  useRef,
  useCallback,
  useMemo,
} from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { ArrowLeftIcon } from '@heroicons/react/24/outline';
import toast from 'react-hot-toast';

import ChatInterface from '../components/ChatInterface';
import RecommendationsPanel from '../components/RecommendationsPanel';
import SpecialistCards from '../components/SpecialistCards';
import AgentStatusComponent from '../components/AgentStatus';
import AgentWorkflowPanel from '../components/AgentWorkflowPanel';
import ClinicalSourcesPanel from '../components/ClinicalSourcesPanel';
import PDFExport from '../components/PDFExport';
import { Header } from '../components/Header';
import { BackgroundShapes } from '../components/BackgroundShapes';

import { useWebSocket } from '../hooks/useWebSocketContext';
import { useCreateChatSession, useSendMessage } from '../hooks/useApi';
import apiService from '../services/api';

import type {
  Patient,
  ChatSession,
  ChatMessage,
  Recommendation,
  Specialist,
  AgentStatus,
} from '../types';

/** Узлы графа после сбора данных / уточняющих вопросов — дольше по времени, нужна явная коммуникация */
const DEEP_ANALYSIS_AGENT_KEYS = new Set([
  'triage',
  'hypothesis_generator',
  'route_to_specialists',
  'infection',
  'immune',
  'oncology',
  'rare_disease',
  'synthesis',
  'feedback_request',
]);

export const ConsultationPage: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const sessionIdFromUrl = searchParams.get('session');

  // State
  const [patient, setPatient] = useState<Patient | null>(null);
  const [chatSession, setChatSession] = useState<ChatSession | null>(null);
  const [loadingExistingSession, setLoadingExistingSession] =
    useState(!!sessionIdFromUrl);
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [specialists, setSpecialists] = useState<Specialist[]>([]);
  const [activeTab, setActiveTab] = useState<
    | 'chat'
    | 'recommendations'
    | 'specialists'
    | 'status'
    | 'workflow'
    | 'export'
  >('chat');
  const hasSentInitialMessage = useRef(false);

  // API hooks
  const createChatSession = useCreateChatSession();
  const sendMessage = useSendMessage();

  // WebSocket hook - using new Context
  const {
    isConnected,
    sessionId,
    messages,
    sendMessage: wsSendMessage,
    agentStatus: wsAgentStatus,
    recommendations: wsRecommendations,
    agentWorkflow,
    clinicalSources,
    agentProgressSteps,
    error: wsError,
    connect,
    disconnect,
    clearMessages,
    setInitialMessages,
    isAgentProcessing,
  } = useWebSocket();

  const deepAnalysisActive = useMemo(
    () =>
      (agentProgressSteps ?? []).some((s) =>
        DEEP_ANALYSIS_AGENT_KEYS.has(s.agent_key)
      ),
    [agentProgressSteps]
  );

  // Логирование получения сообщений из Context
  useEffect(() => {
    console.log('📄 ConsultationPage: Messages from Context updated', {
      count: messages.length,
      messageIds: messages.map((m) => m.id),
      messageSenders: messages.map((m) => m.sender),
      isConnected,
      sessionId,
    });
  }, [messages, isConnected, sessionId]);

  // Update recommendations from WebSocket context
  useEffect(() => {
    if (wsRecommendations && wsRecommendations.length > 0) {
      console.log(
        '💡 ConsultationPage: Updating recommendations from context',
        wsRecommendations.length
      );
      setRecommendations(wsRecommendations);
    }
  }, [wsRecommendations]);

  // Extract specialists from agent status and messages
  useEffect(() => {
    const newSpecialists: Specialist[] = [];

    // Check agent status for specialist information
    if (wsAgentStatus) {
      wsAgentStatus.agents.forEach((agent) => {
        if (agent.result && typeof agent.result === 'object') {
          // Check for primary_specialist
          if (agent.result.primary_specialist) {
            const primary = agent.result.primary_specialist;
            newSpecialists.push({
              id: `primary_${agent.id}_${Date.now()}`,
              name: primary.name || 'Специалист',
              specialty:
                primary.specialty ||
                primary.speciality ||
                agent.name ||
                'Неизвестно',
              experience: primary.experience || 'Опытный специалист',
              rating: primary.rating || 4.5,
              availability: 'available' as const,
              location: primary.location || 'Не указано',
              contactInfo: {
                phone: primary.phone || primary.contactInfo?.phone,
                email: primary.email || primary.contactInfo?.email,
                address: primary.address || primary.contactInfo?.address,
              },
            });
          }

          // Check for additional_specialists
          if (
            agent.result.additional_specialists &&
            Array.isArray(agent.result.additional_specialists)
          ) {
            agent.result.additional_specialists.forEach(
              (spec: any, index: number) => {
                newSpecialists.push({
                  id: `additional_${agent.id}_${index}_${Date.now()}`,
                  name: spec.name || 'Специалист',
                  specialty: spec.specialty || spec.speciality || 'Неизвестно',
                  experience: spec.experience || 'Опытный специалист',
                  rating: spec.rating || 4.5,
                  availability: 'available' as const,
                  location: spec.location || 'Не указано',
                  contactInfo: {
                    phone: spec.phone || spec.contactInfo?.phone,
                    email: spec.email || spec.contactInfo?.email,
                    address: spec.address || spec.contactInfo?.address,
                  },
                });
              }
            );
          }

          // Check for activated_specialists (list of specialist types)
          if (
            agent.result.activated_specialists &&
            Array.isArray(agent.result.activated_specialists)
          ) {
            const specialistTypeMap: Record<string, string> = {
              INFECTION: 'Инфекционист',
              IMMUNE: 'Иммунолог',
              ONCOLOGY: 'Онколог',
              RARE_DISEASE: 'Специалист по редким заболеваниям',
              PEDIATRICIAN: 'Педиатр',
              NEONATOLOGIST: 'Неонатолог',
              GASTROENTEROLOGIST: 'Гастроэнтеролог',
              RHEUMATOLOGIST: 'Ревматолог',
              HEMATOLOGIST: 'Гематолог',
              PULMONOLOGIST: 'Пульмонолог',
              ENT: 'ЛОР',
            };

            agent.result.activated_specialists.forEach(
              (specType: string, index: number) => {
                const specialtyName = specialistTypeMap[specType] || specType;
                // Check if we already have this specialist
                if (
                  !newSpecialists.some((s) => s.specialty === specialtyName)
                ) {
                  newSpecialists.push({
                    id: `activated_${specType}_${index}_${Date.now()}`,
                    name: `Врач-${specialtyName.toLowerCase()}`,
                    specialty: specialtyName,
                    experience: 'Опытный специалист',
                    rating: 4.5,
                    availability: 'available' as const,
                    location: 'Не указано',
                    contactInfo: {},
                  });
                }
              }
            );
          }
        }
      });
    }

    // Also check messages for specialist information
    messages.forEach((msg) => {
      if (msg.type === 'specialist' && msg.content) {
        try {
          const specData =
            typeof msg.content === 'string'
              ? JSON.parse(msg.content)
              : msg.content;
          if (specData && !newSpecialists.some((s) => s.id === specData.id)) {
            newSpecialists.push({
              id: specData.id || `msg_spec_${Date.now()}`,
              name: specData.name || 'Специалист',
              specialty: specData.specialty || 'Неизвестно',
              experience: specData.experience || 'Опытный специалист',
              rating: specData.rating || 4.5,
              availability: (specData.availability || 'available') as const,
              location: specData.location || 'Не указано',
              contactInfo: specData.contactInfo || {},
            });
          }
        } catch (e) {
          // Not JSON, skip
        }
      }
    });

    if (newSpecialists.length > 0) {
      console.log(
        '👨‍⚕️ ConsultationPage: Updating specialists',
        newSpecialists.length
      );
      setSpecialists((prev) => {
        // Merge with existing, avoiding duplicates by specialty and name
        const existingKeys = new Set(
          prev.map((s) => `${s.specialty}_${s.name}`)
        );
        const unique = newSpecialists.filter(
          (s) => !existingKeys.has(`${s.specialty}_${s.name}`)
        );
        return [...prev, ...unique];
      });
    }
  }, [wsAgentStatus, messages]);

  // Initialize: either from sessionStorage (new consultation) or from URL ?session= (existing)
  useEffect(() => {
    if (!sessionIdFromUrl) {
      // Новая консультация: сбрасываем старую сессию, чтобы не подключаться к ней и не переключаться потом
      setChatSession(null);
    }
    if (sessionIdFromUrl) {
      (async () => {
        try {
          const [sessionRes, historyRes] = await Promise.all([
            apiService.getChatSession(sessionIdFromUrl),
            apiService.getChatHistory(sessionIdFromUrl),
          ]);
          const sessionData = sessionRes?.data ?? sessionRes;
          const historyData = historyRes?.data ?? historyRes;
          if (!sessionData?.session_id) {
            toast.error('Сессия не найдена');
            navigate('/history');
            return;
          }
          const session: ChatSession = {
            id: sessionData.session_id,
            patientId: 'anonymous',
            messages: [],
            status: (sessionData.status || 'active') as
              | 'active'
              | 'completed'
              | 'paused',
            createdAt: sessionData.created_at || new Date().toISOString(),
            updatedAt: sessionData.updated_at || new Date().toISOString(),
          };
          const anonymousPatient: Patient = {
            id: 'anonymous',
            name: 'Anonymous',
            age: 0,
            weight: 0,
            height: 0,
            temperature: 0,
            symptoms: [],
            createdAt: session.createdAt,
            updatedAt: session.updatedAt,
          };
          setChatSession(session);
          setPatient(anonymousPatient);
          const list = historyData?.messages ?? historyData ?? [];
          const chatMessages: ChatMessage[] = Array.isArray(list)
            ? list.map((m: any, i: number) => ({
                id: m.message_id || m.id || `msg_${i}_${Date.now()}`,
                content: m.content || '',
                sender: (m.role === 'user' ? 'user' : 'assistant') as
                  | 'user'
                  | 'assistant',
                timestamp: m.timestamp || new Date().toISOString(),
              }))
            : [];
          clearMessages();
          setInitialMessages(chatMessages);
          connect(session.id);
          hasSentInitialMessage.current = true;
        } catch (e) {
          console.error('Error loading session:', e);
          toast.error('Не удалось загрузить сессию');
          navigate('/history');
        } finally {
          setLoadingExistingSession(false);
        }
      })();
      return;
    }

    const patientData = sessionStorage.getItem('patientData');
    if (patientData) {
      try {
        const parsed = JSON.parse(patientData);
        // Convert form data to patient format
        const ageValue = parseInt(parsed.age);
        const ageUnit = parsed.ageUnit || 'years';

        // Convert age to years for display
        let ageInYears = ageValue;
        if (ageUnit === 'months') {
          ageInYears = Math.floor(ageValue / 12);
        } else if (ageUnit === 'days') {
          ageInYears = Math.floor(ageValue / 365);
        }

        const patient: Patient = {
          id: Date.now().toString(),
          name: parsed.name,
          gender: parsed.gender,
          age: ageInYears,
          ageMonths: ageUnit === 'months' ? ageValue : undefined,
          ageDays: ageUnit === 'days' ? ageValue : undefined,
          weight: parseFloat(parsed.weight),
          height: parseInt(parsed.height),
          temperature: parseFloat(parsed.temperature),
          symptoms: parsed.symptoms,
          additionalInfo: parsed.additionalInfo,
          createdAt: new Date().toISOString(),
          updatedAt: new Date().toISOString(),
        };
        setPatient(patient);
      } catch (error) {
        console.error('Error parsing patient data:', error);
        toast.error('Ошибка загрузки данных пациента');
        navigate('/');
      }
    } else {
      navigate('/');
    }
  }, [navigate, sessionIdFromUrl, connect, clearMessages, setInitialMessages]);

  // Create chat session when patient is loaded (only for new consultation, not when opening by session ID)
  useEffect(() => {
    if (patient && !chatSession && !sessionIdFromUrl) {
      initializeChatSession();
    }
  }, [patient, sessionIdFromUrl]);

  // Initialize WebSocket when chat session is created; switch session without full disconnect (service closes old socket and connects to new)
  useEffect(() => {
    if (chatSession && chatSession.id) {
      clearMessages();
      connect(chatSession.id);
    }
  }, [chatSession?.id, connect, clearMessages]);

  // Disconnect only when leaving the consultation page
  useEffect(() => {
    return () => {
      disconnect();
    };
  }, [disconnect]);

  // Handle WebSocket connection established — отправка первого сообщения только один раз
  useEffect(() => {
    if (
      !isConnected ||
      !sessionId ||
      !patient ||
      !chatSession ||
      hasSentInitialMessage.current
    )
      return;

    hasSentInitialMessage.current = true;
    toast.success('Соединение с чатом установлено');

    const initialQuestion = sessionStorage.getItem('initialQuestion');
    if (initialQuestion && initialQuestion.trim()) {
      sessionStorage.removeItem('initialQuestion');
      console.log(
        '🚀 Sending initial question from home page:',
        initialQuestion
      );
      wsSendMessage(initialQuestion.trim());
    } else {
      const initialMessage = createInitialPatientMessage(patient);
      console.log('🚀 Sending initial patient message:', initialMessage);
      wsSendMessage(initialMessage);
    }
  }, [isConnected, sessionId, patient, chatSession, wsSendMessage]);

  // Handle WebSocket errors
  useEffect(() => {
    if (wsError) {
      console.error('WebSocket error:', wsError);
      toast.error(`Ошибка WebSocket: ${wsError}`);
    }
  }, [wsError]);

  const initializeChatSession = async () => {
    if (!patient) return;

    try {
      // Создаем данные пациента в формате, который ожидает бэкенд
      const patientData = {
        patient_id: patient.id,
        age_years: patient.age,
        age_months: patient.ageMonths || 0,
        age_days: patient.ageDays || 0,
        gender: patient.gender,
        name: patient.name,
        temperature: patient.temperature,
        symptoms: patient.symptoms,
        weight: patient.weight,
        height: patient.height,
        additional_info: patient.additionalInfo,
      };

      // Используем patientData для создания сессии
      const result = await createChatSession.execute(patientData);
      console.log('📝 Session creation result:', result);

      if (result) {
        // Проверяем структуру ответа
        let sessionData: any;
        if (result.data) {
          // Если ответ обернут в ApiResponse
          sessionData = result.data;
        } else {
          // Если ответ прямой от бэкенда
          sessionData = result;
        }

        console.log('📝 Session data:', sessionData);

        // Создаем объект сессии в ожидаемом формате
        const session: ChatSession = {
          id: sessionData.session_id,
          patientId: patient.id,
          createdAt: sessionData.created_at,
          updatedAt: sessionData.created_at,
          status: sessionData.status as 'active' | 'completed' | 'paused',
          messages: [], // Инициализируем пустым массивом
        };

        console.log('✅ Chat session created:', session);
        setChatSession(session);

        // Initial message will be handled by the Context when we send it
      }
    } catch (error: any) {
      console.error('Error creating chat session:', error);
      const msg =
        error?.userMessage ||
        error?.response?.data?.detail ||
        'Ошибка создания сессии чата';
      toast.error(msg);
    }
  };

  // Функция для создания начального сообщения с данными пациента
  const createInitialPatientMessage = (patient: Patient): string => {
    const symptomsText = patient.symptoms.join(', ');
    const additionalInfoText = patient.additionalInfo
      ? `\nДополнительная информация: ${patient.additionalInfo}`
      : '';

    return `Здравствуйте! Мне нужна консультация.

Пациент: ${patient.name}
Возраст: ${patient.age} лет
Вес: ${patient.weight} кг
Рост: ${patient.height} см
Температура: ${patient.temperature}°C
Симптомы: ${symptomsText}${additionalInfoText}

Пожалуйста, проведите оценку состояния и дайте рекомендации.`;
  };

  const handleSendMessage = async (message: string) => {
    if (!chatSession) {
      console.error('No chat session available');
      toast.error('Сессия чата не найдена');
      return;
    }

    // User message will be added by the Context automatically

    try {
      // Send via WebSocket if connected
      if (isConnected) {
        wsSendMessage(message);
      } else {
        // Fallback to HTTP API
        const result = await sendMessage.execute(chatSession.id, message);
        if (result) {
          // result уже содержит данные напрямую от бэкенда, а не обернутый ответ
          // Messages are handled by Context now
        }
      }
    } catch (error) {
      console.error('Error sending message:', error);
      toast.error('Ошибка отправки сообщения');
    }
  };

  const handleStartProcessing = async () => {
    if (!chatSession) return;

    try {
      // For now, just show toast - agent commands will be handled differently
      toast.success('Анализ начат');
    } catch (error) {
      console.error('Error starting processing:', error);
      toast.error('Ошибка запуска анализа');
    }
  };

  const handlePauseProcessing = async () => {
    if (!chatSession) return;

    try {
      // For now, just show toast - agent commands will be handled differently
      toast.success('Анализ приостановлен');
    } catch (error) {
      console.error('Error pausing processing:', error);
      toast.error('Ошибка приостановки анализа');
    }
  };

  const handleContactSpecialist = (specialist: Specialist) => {
    toast.success(
      `Информация о специалисте ${specialist.name} добавлена в рекомендации`
    );
  };

  const handleExportPDF = () => {
    if (!patient || !chatSession) return;

    // This would trigger the PDF export component
    setActiveTab('export');
  };

  const handleExportComplete = (success: boolean) => {
    if (success) {
      toast.success('PDF успешно создан и загружен');
    } else {
      toast.error('Ошибка создания PDF');
    }
  };

  const tabs = [
    { id: 'chat', label: 'Чат', icon: '💬' },
    {
      id: 'recommendations',
      label: 'Рекомендации',
      icon: '💡',
      count: recommendations.length,
    },
    {
      id: 'specialists',
      label: 'Специалисты',
      icon: '👨‍⚕️',
      count: specialists.length,
    },
    { id: 'status', label: 'Статус агентов', icon: '🤖' },
    {
      id: 'workflow',
      label: 'Логика и источники',
      icon: '📋',
      count: (agentWorkflow?.length || 0) + (clinicalSources?.length || 0),
    },
  ];

  if (!patient && loadingExistingSession) {
    return (
      <div className="container-medical py-8">
        <div className="flex items-center justify-center">
          <div className="loading-spinner w-8 h-8"></div>
          <span className="ml-2">Загрузка сессии...</span>
        </div>
      </div>
    );
  }

  if (!patient) {
    return (
      <div className="container-medical py-8">
        <div className="flex items-center justify-center">
          <div className="loading-spinner w-8 h-8"></div>
          <span className="ml-2">Загрузка...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-b from-start-blueLight to-white relative overflow-hidden">
      <BackgroundShapes />
      <Header />
      {/* Новый вопрос — возврат на главную */}
      <div className="border-b border-gray-200 bg-white">
        <div className="container-medical py-3 flex items-center justify-between">
          <button
            type="button"
            onClick={() => navigate('/')}
            className="flex items-center gap-2 text-gray-600 hover:text-gray-900 transition-colors"
          >
            <ArrowLeftIcon className="w-5 h-5" />
            <span className="font-medium">Новый вопрос</span>
          </button>
          <span className="text-xs text-gray-500 flex items-center gap-1.5">
            <span
              className={`w-2 h-2 rounded-full ${isConnected ? 'bg-green-500' : 'bg-red-500'}`}
            />
            {isConnected ? 'Подключено' : 'Отключено'}
          </span>
        </div>
      </div>

      {/* Navigation Tabs */}
      <div className="bg-white border-b">
        <div className="container-medical">
          <nav className="flex space-x-8">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id as any)}
                className={`py-4 px-1 border-b-2 font-medium text-sm transition-colors ${
                  activeTab === tab.id
                    ? 'border-medical-blue text-medical-blue'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                }`}
              >
                <span className="flex items-center space-x-2">
                  <span>{tab.icon}</span>
                  <span>{tab.label}</span>
                  {tab.count !== undefined && tab.count > 0 && (
                    <span className="bg-medical-blue text-white text-xs rounded-full px-2 py-0.5">
                      {tab.count}
                    </span>
                  )}
                </span>
              </button>
            ))}
          </nav>
        </div>
      </div>

      {/* Content */}
      <main className="container-medical py-8">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Main Content */}
          <div className="lg:col-span-2">
            {activeTab === 'chat' && (
              <div className="flex flex-col gap-3 h-[600px]">
                {(agentProgressSteps?.length ?? 0) > 0 && (
                  <div
                    className={`rounded-lg border px-4 py-3 text-sm ${
                      deepAnalysisActive
                        ? 'border-amber-200 bg-amber-50/80'
                        : 'border-[#2A9FFF]/30 bg-blue-50/50'
                    }`}
                  >
                    {deepAnalysisActive && (
                      <div className="mb-3 border-b border-amber-200/80 pb-3">
                        <p className="font-semibold text-gray-900">
                          Идёт глубокий анализ
                        </p>
                        <p className="mt-1 text-gray-700 leading-relaxed">
                          Обычно требуется{' '}
                          <span className="font-medium">1–3 минуты</span>:
                          оценка срочности (триаж) → гипотезы → при
                          необходимости узкие специалисты → сводка и
                          рекомендации. Дождитесь ответа; обновлять страницу не
                          нужно.
                        </p>
                      </div>
                    )}
                    <p className="font-medium text-gray-800 mb-1">
                      Сейчас выполняется шаг:
                    </p>
                    <p className="text-gray-700">
                      {agentProgressSteps[agentProgressSteps.length - 1].title}
                      {' — '}
                      {
                        agentProgressSteps[agentProgressSteps.length - 1]
                          .description
                      }
                    </p>
                    {agentProgressSteps.length > 1 && (
                      <p className="mt-2 text-xs text-gray-500">
                        Выполнено шагов в этом запросе:{' '}
                        {agentProgressSteps.length}
                      </p>
                    )}
                  </div>
                )}
                <div className="flex-1 min-h-0">
                  <ChatInterface
                    sessionId={chatSession?.id || ''}
                    messages={messages}
                    onSendMessage={handleSendMessage}
                    isLoading={isAgentProcessing()}
                    connectionStatus={
                      isConnected ? 'connected' : 'disconnected'
                    }
                    connectionQuality={undefined}
                    onManualReconnect={() =>
                      chatSession && connect(chatSession.id)
                    }
                  />
                </div>
              </div>
            )}

            {activeTab === 'recommendations' && (
              <RecommendationsPanel
                recommendations={recommendations}
                isLoading={isAgentProcessing()}
              />
            )}

            {activeTab === 'specialists' && (
              <SpecialistCards
                specialists={specialists}
                isLoading={false}
                onContactSpecialist={handleContactSpecialist}
              />
            )}

            {activeTab === 'status' && (
              <AgentStatusComponent
                agentStatus={wsAgentStatus}
                isLoading={false}
                onStartProcessing={handleStartProcessing}
                onPauseProcessing={handlePauseProcessing}
              />
            )}

            {activeTab === 'workflow' && (
              <div className="space-y-8">
                <AgentWorkflowPanel workflow={agentWorkflow || []} />
                <ClinicalSourcesPanel sources={clinicalSources || []} />
              </div>
            )}

            {activeTab === 'export' && chatSession && (
              <PDFExport
                data={{
                  patient,
                  session: chatSession,
                  recommendations,
                  specialists,
                  agentStatus: wsAgentStatus || {
                    agents: [],
                    overallProgress: 0,
                    currentStep: 'Неизвестно',
                  },
                }}
                onExportComplete={handleExportComplete}
              />
            )}
          </div>

          {/* Sidebar */}
          <div className="space-y-6">
            {/* Quick Actions */}
            <div className="card">
              <h3 className="card-title">Быстрые действия</h3>
              <div className="space-y-3">
                {!isAgentProcessing() && (
                  <button
                    onClick={handleStartProcessing}
                    className="w-full btn btn-primary"
                  >
                    Запустить анализ
                  </button>
                )}

                {isAgentProcessing() && (
                  <button
                    onClick={handlePauseProcessing}
                    className="w-full btn btn-secondary"
                  >
                    Приостановить анализ
                  </button>
                )}

                <button
                  onClick={() => handleExportPDF()}
                  className="w-full btn btn-outline"
                >
                  Экспорт в PDF
                </button>
              </div>
            </div>

            {/* Patient Info */}
            <div className="card">
              <h3 className="card-title">Информация о пациенте</h3>
              <div className="space-y-2 text-sm">
                <div>
                  <strong>Имя:</strong> {patient.name}
                </div>
                <div>
                  <strong>Возраст:</strong> {patient.age} лет
                </div>
                <div>
                  <strong>Вес:</strong> {patient.weight} кг
                </div>
                <div>
                  <strong>Рост:</strong> {patient.height} см
                </div>
                <div>
                  <strong>Температура:</strong> {patient.temperature}°C
                </div>
                <div>
                  <strong>Симптомы:</strong>
                  <ul className="mt-1 ml-4 list-disc">
                    {patient.symptoms.map((symptom, index) => (
                      <li key={index}>{symptom}</li>
                    ))}
                  </ul>
                </div>
                {patient.additionalInfo && (
                  <div>
                    <strong>Доп. информация:</strong>
                    <p className="mt-1">{patient.additionalInfo}</p>
                  </div>
                )}
              </div>
            </div>

            {/* Connection Status */}
            <div className="card">
              <h3 className="card-title">Статус подключения</h3>
              <div className="space-y-2 text-sm">
                <div className="flex items-center justify-between">
                  <span>WebSocket:</span>
                  <span
                    className={`font-medium ${isConnected ? 'text-green-600' : 'text-red-600'}`}
                  >
                    {isConnected ? 'Подключено' : 'Отключено'}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span>Обработка:</span>
                  <span
                    className={`font-medium ${isAgentProcessing() ? 'text-blue-600' : 'text-gray-600'}`}
                  >
                    {isAgentProcessing() ? 'Активна' : 'Неактивна'}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
};

export default ConsultationPage;
