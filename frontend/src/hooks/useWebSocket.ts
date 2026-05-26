import { useEffect, useRef, useState, useCallback, useMemo } from 'react';
import webSocketService from '../services/websocket';
import type { AgentStatus, ChatMessage, Recommendation } from '../types';

interface UseWebSocketReturn {
  isConnected: boolean;
  connectionState: string;
  agentStatus: AgentStatus | null;
  messages: ChatMessage[];
  recommendations: Recommendation[];
  error: string | null;
  connectionEstablished: boolean;
  commandResponse: any;
  reconnectAttempts: number;
  lastConnectedTime: Date | null;
  connectionQuality: 'good' | 'poor' | 'disconnected';
  connect: (sessionId: string) => Promise<void>;
  disconnect: () => void;
  sendMessage: (message: string) => void;
  sendAgentCommand: (command: string, data?: any) => void;
  clearError: () => void;
  onConnectionEstablished: (callback: (data: any) => void) => void;
  onCommandResponse: (callback: (data: any) => void) => void;
  onMessage: (callback: (message: ChatMessage) => void) => void;
  onRecommendation: (callback: (recommendation: Recommendation) => void) => void;
}

export const useWebSocket = (): UseWebSocketReturn => {
  const [isConnected, setIsConnected] = useState(false);
  const [connectionState, setConnectionState] = useState('disconnected');
  const [agentStatus, setAgentStatus] = useState<AgentStatus | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [connectionEstablished, setConnectionEstablished] = useState(false);
  const [commandResponse, setCommandResponse] = useState<any>(null);
  const [reconnectAttempts, setReconnectAttempts] = useState(0);
  const [lastConnectedTime, setLastConnectedTime] = useState<Date | null>(null);
  const [connectionQuality, setConnectionQuality] = useState<'good' | 'poor' | 'disconnected'>('disconnected');

  // Внешние callback'и для прямого взаимодействия
  const messageCallbackRef = useRef<((message: ChatMessage) => void) | null>(null);
  const recommendationCallbackRef = useRef<((recommendation: Recommendation) => void) | null>(null);
  const connectionEstablishedCallbackRef = useRef<((data: any) => void) | null>(null);
  const commandResponseCallbackRef = useRef<((data: any) => void) | null>(null);

  const onAgentStatusCallback = useCallback((status: AgentStatus) => {
    console.log('🎯 onAgentStatus callback triggered:', status);
    setAgentStatus(status);
  }, []);

  const onChatMessageCallback = useCallback((message: ChatMessage) => {
    console.log('💬 onChatMessage callback triggered:', message);
    // Вызываем внешний callback, если он установлен
    if (messageCallbackRef.current) {
      console.log('💬 Calling external message callback');
      messageCallbackRef.current(message);
    }
  }, []);

  const onRecommendationCallback = useCallback((recommendation: Recommendation) => {
    console.log('💡 onRecommendation callback triggered:', recommendation);
    // Добавляем в локальное состояние для совместимости
    setRecommendations(prev => [...prev, recommendation]);
    // Вызываем внешний callback, если он установлен
    if (recommendationCallbackRef.current) {
      console.log('💡 Calling external recommendation callback');
      recommendationCallbackRef.current(recommendation);
    }
  }, []);

  const onErrorCallback = useCallback((err: any) => {
    console.log('❌ onError callback triggered:', err);
    setError(err.message || 'WebSocket error occurred');
    
    // Обработка специфических ошибок подключения
    if (err.message.includes('Network connection lost')) {
      setConnectionQuality('disconnected');
    } else if (err.message.includes('Connection issues detected')) {
      setConnectionQuality('poor');
    }
  }, []);

  const onConnectionEstablishedCallback = useCallback((data: any) => {
    console.log('✅ onConnectionEstablished callback triggered:', data);
    setConnectionEstablished(true);
    setLastConnectedTime(new Date());
    setConnectionQuality('good');
    setReconnectAttempts(0);
    
    // Вызываем внешний callback, если он установлен
    if (connectionEstablishedCallbackRef.current) {
      connectionEstablishedCallbackRef.current(data);
    }
  }, []);

  const onCommandResponseCallback = useCallback((data: any) => {
    console.log('🎯 onCommandResponse callback triggered:', data);
    setCommandResponse(data);
    
    // Вызываем внешний callback, если он установлен
    if (commandResponseCallbackRef.current) {
      commandResponseCallbackRef.current(data);
    }
  }, []);

  const connect = useCallback(async (sessionId: string) => {
    try {
      setError(null);
      setConnectionState('connecting');
      await webSocketService.connect(sessionId);
      setIsConnected(true);
      setConnectionState('connected');
      setLastConnectedTime(new Date());
      setConnectionQuality('good');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to connect');
      setConnectionState('error');
      setIsConnected(false);
      setConnectionQuality('disconnected');
    }
  }, []);

  const disconnect = useCallback(() => {
    webSocketService.disconnect();
    setIsConnected(false);
    setConnectionState('disconnected');
    setConnectionQuality('disconnected');
    setAgentStatus(null);
    setMessages([]);
    setRecommendations([]);
    setLastConnectedTime(null);
    setReconnectAttempts(0);
  }, []);

  const sendMessage = useCallback((message: string) => {
    try {
      // Проверяем состояние подключения перед отправкой
      if (!webSocketService.isConnected()) {
        setError('Нет подключения к серверу. Сообщение будет отправлено при восстановлении соединения.');
      }
      webSocketService.sendMessage(message);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to send message');
    }
  }, []);

  const sendAgentCommand = useCallback((command: string, data?: any) => {
    try {
      // Проверяем состояние подключения перед отправкой
      if (!webSocketService.isConnected()) {
        setError('Нет подключения к серверу. Команда будет отправлена при восстановлении соединения.');
      }
      webSocketService.sendAgentCommand(command, data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to send command');
    }
  }, []);

  const clearError = useCallback(() => {
    setError(null);
  }, []);

  useEffect(() => {
    console.log('🔧 Setting up WebSocket event listeners...');
    
    // Подписываемся на события всегда, а не только при isConnected
    webSocketService.onAgentStatus(onAgentStatusCallback);
    webSocketService.onChatMessage(onChatMessageCallback);
    webSocketService.onRecommendation(onRecommendationCallback);
    webSocketService.onError(onErrorCallback);
    webSocketService.onConnectionEstablished(onConnectionEstablishedCallback);
    webSocketService.onCommandResponse(onCommandResponseCallback);
    
    console.log('🔧 WebSocket event listeners set up successfully');

    return () => {
      console.log('🔧 Cleaning up WebSocket event listeners...');
      webSocketService.offAgentStatus(onAgentStatusCallback);
      webSocketService.offChatMessage(onChatMessageCallback);
      webSocketService.offRecommendation(onRecommendationCallback);
      webSocketService.offError(onErrorCallback);
      webSocketService.offConnectionEstablished(onConnectionEstablishedCallback);
      webSocketService.offCommandResponse(onCommandResponseCallback);
      console.log('🔧 WebSocket event listeners cleaned up');
    };
  }, [onAgentStatusCallback, onChatMessageCallback, onRecommendationCallback, onErrorCallback, onConnectionEstablishedCallback, onCommandResponseCallback]);

  // УБРАЛИ ненужный useEffect для переподписки - теперь callback'и устанавливаются напрямую
  // и не требуют переподписки, так как они вызываются внутри основных callback'ов

  useEffect(() => {
    // Оптимизированная периодическая проверка состояния подключения
    let intervalId: number;
    let checkCount = 0;
    
    const checkConnection = () => {
      const newState = webSocketService.getConnectionState();
      const newConnected = webSocketService.isConnected();
      
      // Обновляем состояние только если оно изменилось
      setConnectionState(prev => {
        if (prev !== newState) {
          console.log(`Connection state changed: ${prev} -> ${newState}`);
          return newState;
        }
        return prev;
      });
      
      setIsConnected(prev => {
        if (prev !== newConnected) {
          console.log(`Connection status changed: ${prev} -> ${newConnected}`);
          
          // Обновляем качество подключения
          if (newConnected) {
            setConnectionQuality('good');
            setLastConnectedTime(new Date());
            setReconnectAttempts(0);
          } else {
            setConnectionQuality('disconnected');
          }
          
          return newConnected;
        }
        return prev;
      });
      
      // Увеличиваем счетчик проверок
      checkCount++;
      
      // После 10 проверок увеличиваем интервал до 5 секунд
      if (checkCount === 10) {
        clearInterval(intervalId);
        intervalId = window.setInterval(checkConnection, 5000);
      }
    };
    
    // Начинаем с частой проверки (каждую секунду)
    intervalId = window.setInterval(checkConnection, 1000);

    return () => {
      if (intervalId) clearInterval(intervalId);
    };
  }, []);
  
  // Обработка внезапных разрывов соединения
  useEffect(() => {
    const handleOnline = () => {
      console.log('Network connection restored');
      // Пытаемся переподключиться при восстановлении сети
      if (!isConnected && connectionState === 'disconnected') {
        // Здесь можно добавить логику автоматического переподключения
        console.log('Attempting to reconnect after network restore');
      }
    };
    
    const handleOffline = () => {
      console.log('Network connection lost');
      setError('Потеряно сетевое соединение');
      setConnectionQuality('disconnected');
    };
    
    const handleVisibilityChange = () => {
      // При возвращении на страницу проверяем состояние подключения
      if (!document.hidden && connectionState === 'connected' && !webSocketService.isConnected()) {
        console.log('Page became visible, checking connection');
        setError('Подключение потеряно, пытаемся восстановить...');
        // Здесь можно добавить логику переподключения
      }
    };
    
    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);
    document.addEventListener('visibilitychange', handleVisibilityChange);
    
    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, [isConnected, connectionState]);

  const onConnectionEstablished = useCallback((callback: (data: any) => void) => {
    connectionEstablishedCallbackRef.current = callback;
  }, []);

  const onCommandResponse = useCallback((callback: (data: any) => void) => {
    commandResponseCallbackRef.current = callback;
  }, []);

  const onMessage = useCallback((callback: (message: ChatMessage) => void) => {
    messageCallbackRef.current = callback;
  }, []);

  const onRecommendation = useCallback((callback: (recommendation: Recommendation) => void) => {
    recommendationCallbackRef.current = callback;
  }, []);

  return {
    isConnected,
    connectionState,
    agentStatus,
    messages,
    recommendations,
    error,
    connectionEstablished,
    commandResponse,
    reconnectAttempts,
    lastConnectedTime,
    connectionQuality,
    connect,
    disconnect,
    sendMessage,
    sendAgentCommand,
    clearError,
    onConnectionEstablished,
    onCommandResponse,
    onMessage,
    onRecommendation,
  };
};