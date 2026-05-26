import React, { createContext, useContext, useEffect, useRef, useState, useCallback } from 'react';
import webSocketService from '../services/websocket';
import type { AgentStatus, ChatMessage, Recommendation, AgentWorkflowStep, ClinicalSource, AgentProgressStep } from '../types';

export interface WebSocketContextType {
  isConnected: boolean;
  sessionId: string | null;
  messages: ChatMessage[];
  sendMessage: (content: string) => void;
  agentStatus: AgentStatus | null;
  recommendations: Recommendation[];
  /** Цепочка шагов агентов и их решений (объяснимость) */
  agentWorkflow: AgentWorkflowStep[];
  /** Ссылки на клинические рекомендации */
  clinicalSources: ClinicalSource[];
  /** Текущие шаги агентов во время обработки (real-time) */
  agentProgressSteps: AgentProgressStep[];
  connect: (sessionId: string) => void;
  disconnect: () => void;
  clearMessages: () => void;
  setInitialMessages: (messages: ChatMessage[]) => void;
  error: string | null;
  /** Ожидание ответа ассистента после отправки сообщения (для индикатора «печатает»). */
  awaitingAssistantResponse: boolean;
}

// Создаем контекст
const WebSocketContext = createContext<WebSocketContextType | null>(null);

// Provider компонент
export const WebSocketProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  // Состояние
  const [isConnected, setIsConnected] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [agentStatus, setAgentStatus] = useState<AgentStatus | null>(null);
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [agentWorkflow, setAgentWorkflow] = useState<AgentWorkflowStep[]>([]);
  const [clinicalSources, setClinicalSources] = useState<ClinicalSource[]>([]);
  const [agentProgressSteps, setAgentProgressSteps] = useState<AgentProgressStep[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [awaitingAssistantResponse, setAwaitingAssistantResponse] = useState(false);
  
  // Refs для отслеживания состояния
  const messagesRef = useRef<Set<string>>(new Set()); // Для дедупликации
  const recommendationsRef = useRef<Set<string>>(new Set()); // Для дедупликации рекомендаций
  const currentSessionRef = useRef<string | null>(null);

  // Инициализация WebSocket сервиса
  useEffect(() => {
    console.log('🔧 WebSocket Service initialized in Context (using singleton)');

    // Устанавливаем единственные listeners
    const setupListeners = () => {
      // Connection established
      webSocketService.onConnectionEstablished((data: any) => {
        console.log('📡 Context: Connection established', data);
        setIsConnected(true);
        setError(null);
      });

      // Chat messages
      webSocketService.onChatMessage((message: ChatMessage) => {
        console.log('💬 Context: Chat message received', message);
        console.log('💬 Context: Message structure:', {
          id: message.id,
          content: message.content?.substring(0, 50) + '...',
          sender: message.sender,
          timestamp: message.timestamp,
          type: message.type
        });
        
        // Дедупликация по ID
        if (message.id && !messagesRef.current.has(message.id)) {
          messagesRef.current.add(message.id);
          setMessages(prev => {
            // Проверяем, что сообщения еще нет в массиве (двойная защита)
            if (prev.some(m => m.id === message.id)) {
              console.log('🔄 Context: Message already exists in array, skipping', message.id);
              return prev;
            }
            const newMessages = [...prev, message];
            console.log('✅ Context: Message added to state', message.id);
            console.log('✅ Context: Total messages count:', newMessages.length);
            console.log('✅ Context: All message IDs:', newMessages.map(m => m.id));
            return newMessages;
          });
        } else if (message.id) {
          console.log('🔄 Context: Duplicate message ignored', message.id);
        } else {
          console.warn('⚠️ Context: Message without ID received', message);
          // Добавляем сообщение без ID с временным ID
          const tempId = `temp_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
          const messageWithId = { ...message, id: tempId };
          setMessages(prev => {
            // Проверяем, что сообщения еще нет в массиве
            if (prev.some(m => m.id === tempId)) {
              console.log('🔄 Context: Temp message already exists in array, skipping', tempId);
              return prev;
            }
            const newMessages = [...prev, messageWithId];
            console.log('✅ Context: Message without ID added with temp ID', tempId);
            console.log('✅ Context: Total messages count:', newMessages.length);
            return newMessages;
          });
        }
      });

      // Agent status
      webSocketService.onAgentStatus((status: AgentStatus) => {
        console.log('🤖 Context: Agent status updated', status);
        setAgentStatus(status);
      });

      // Логика работы агентов (финальная после ответа)
      webSocketService.onAgentWorkflow((workflow: AgentWorkflowStep[]) => {
        setAgentWorkflow(workflow);
        setAgentProgressSteps([]); // сбрасываем live-прогресс при получении финального workflow
      });
      // Прогресс агентов в реальном времени (во время обработки)
      webSocketService.onAgentProgress((step: AgentProgressStep) => {
        setAgentProgressSteps((prev) => [...prev, { ...step, status: step.status || 'completed' }]);
      });
      // Клинические источники
      webSocketService.onClinicalSources((sources: ClinicalSource[]) => {
        setClinicalSources(sources);
      });

      // Recommendations
      webSocketService.onRecommendation((recommendationsData: any) => {
        console.log('💡 Context: Recommendations received', recommendationsData);
        
        // Recommendations can come as array or single object
        let recommendationsArray: Recommendation[] = [];
        
        if (Array.isArray(recommendationsData)) {
          recommendationsArray = recommendationsData;
        } else if (recommendationsData && typeof recommendationsData === 'object') {
          // Check if it's a recommendations object with possible_diagnoses
          if (recommendationsData.possible_diagnoses || recommendationsData.recommendations_text) {
            // This is a recommendations object from backend
            // Create a single recommendation entry that includes possible_diagnoses
            recommendationsArray = [{
              id: `rec_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
              title: 'Клинические рекомендации',
              description: recommendationsData.recommendations_text || '',
              priority: 'high' as const,
              category: 'consultation' as const,
              agentId: 'synthesis',
              timestamp: new Date().toISOString(),
              possible_diagnoses: recommendationsData.possible_diagnoses || []
            }];
          } else {
            // Single recommendation object
            recommendationsArray = [recommendationsData];
          }
        }
        
        if (recommendationsArray.length > 0) {
          setRecommendations(prev => {
            const existingIds = new Set(prev.map(r => r.id));
            const newRecs = recommendationsArray
              .map((rec: any) => ({
                id: rec.id || `rec_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
                title: rec.title || 'Рекомендация',
                description: rec.description || rec.content || '',
                priority: rec.priority || 'medium',
                category: rec.category || 'consultation',
                agentId: rec.agentId || rec.agent_id || 'system',
                timestamp: rec.timestamp || new Date().toISOString(),
                possible_diagnoses: rec.possible_diagnoses || undefined
              }))
              .filter((rec: Recommendation) => !existingIds.has(rec.id));
            
            console.log('💡 Context: Adding recommendations', newRecs.length);
            if (newRecs.some(r => r.possible_diagnoses && r.possible_diagnoses.length > 0)) {
              console.log('💡 Context: Recommendations include diagnoses', 
                newRecs.find(r => r.possible_diagnoses)?.possible_diagnoses?.length);
            }
            return [...prev, ...newRecs];
          });
        }
      });

      // Errors
      webSocketService.onError((errorData: any) => {
        console.error('❌ Context: WebSocket error', errorData);
        setAwaitingAssistantResponse(false);
        setError(errorData.message || 'WebSocket error occurred');
      });

      webSocketService.onAssistantResponseComplete(() => {
        setAwaitingAssistantResponse(false);
      });

      console.log('🎯 Context: All WebSocket listeners set up');
    };

    setupListeners();

    // Очистка при размонтировании
    return () => {
      webSocketService.disconnect();
      console.log('🧹 Context: WebSocket service cleaned up');
    };
  }, []);

  // Функция подключения
  const connect = useCallback((newSessionId: string) => {
    console.log('🔗 Context: Connecting to session', newSessionId);
    
    // Если сессия изменилась, очищаем сообщения
    if (currentSessionRef.current && currentSessionRef.current !== newSessionId) {
      console.log('🔄 Context: Session changed, clearing messages');
      clearMessages();
    }
    
    currentSessionRef.current = newSessionId;
    setSessionId(newSessionId);
    
    webSocketService.connect(newSessionId).catch(() => {
      // Ожидаемо при смене сессии или unmount — соединение закрыто до установки
    });
  }, []);

  // Функция отключения
  const disconnect = useCallback(() => {
    console.log('🔌 Context: Disconnecting');
    webSocketService.disconnect();
    setIsConnected(false);
    setSessionId(null);
    setAwaitingAssistantResponse(false);
  }, []);

  // Функция отправки сообщения
  const sendMessage = useCallback((content: string) => {
    console.log('📤 Context: Sending message', content);
    if (sessionId) {
      setAwaitingAssistantResponse(true);
      setAgentProgressSteps([]); // сброс live-прогресса перед новым запросом
      // Добавляем сообщение пользователя сразу в состояние
      const userMessage: ChatMessage = {
        id: `user_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
        content,
        sender: 'user',
        timestamp: new Date().toISOString()
      };
      
      setMessages(prev => [...prev, userMessage]);
      webSocketService.sendMessage(content);
    } else {
      console.warn('⚠️ Context: Cannot send message - not connected');
      setError('Cannot send message - not connected to WebSocket');
    }
  }, [sessionId]);

  // Функция очистки сообщений
  const clearMessages = useCallback(() => {
    console.log('🧹 Context: Clearing messages');
    setMessages([]);
    messagesRef.current.clear();
    setRecommendations([]);
    recommendationsRef.current.clear();
    setAgentWorkflow([]);
    setClinicalSources([]);
    setAgentProgressSteps([]);
    setAgentStatus(null);
    setError(null);
    setAwaitingAssistantResponse(false);
  }, []);

  // Установка начальных сообщений (например, при открытии существующей сессии)
  const setInitialMessages = useCallback((newMessages: ChatMessage[]) => {
    setMessages(newMessages);
    newMessages.forEach(m => m.id && messagesRef.current.add(m.id));
  }, []);

  // Значение контекста
  const contextValue: WebSocketContextType = {
    isConnected,
    sessionId,
    messages,
    sendMessage,
    agentStatus,
    recommendations,
    agentWorkflow,
    clinicalSources,
    agentProgressSteps,
    connect,
    disconnect,
    clearMessages,
    setInitialMessages,
    error,
    awaitingAssistantResponse
  };

  return (
    <WebSocketContext.Provider value={contextValue}>
      {children}
    </WebSocketContext.Provider>
  );
};

// Hook для использования контекста
export const useWebSocketContext = (): WebSocketContextType => {
  const context = useContext(WebSocketContext);
  
  if (!context) {
    throw new Error('useWebSocketContext must be used within a WebSocketProvider');
  }
  
  return context;
};

// Экспорт контекста для тестирования
export { WebSocketContext };