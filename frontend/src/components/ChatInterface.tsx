import React, { useState, useRef, useEffect, memo, useCallback } from 'react';
import { PaperAirplaneIcon, ExclamationTriangleIcon, WifiIcon, SignalSlashIcon, ArrowPathIcon, MicrophoneIcon } from '@heroicons/react/24/outline';
import { MicrophoneIcon as MicrophoneIconSolid } from '@heroicons/react/24/solid';
import toast from 'react-hot-toast';
import type { ChatMessage } from '../types';
import { InlineClinicalSources } from './InlineClinicalSources';
import { ChatMessageMarkdown } from './ChatMessageMarkdown';
import { getMicErrorMessage, logMicDiagnostic } from '../utils/micDiagnostics';

const SpeechRecognitionAPI = typeof window !== 'undefined' && ((window as unknown as { SpeechRecognition?: unknown }).SpeechRecognition ?? (window as unknown as { webkitSpeechRecognition?: unknown }).webkitSpeechRecognition);
const canUseMicrophoneGlobal = typeof window !== 'undefined' && (window as unknown as { isSecureContext?: boolean }).isSecureContext !== false && !!SpeechRecognitionAPI;

interface ChatInterfaceProps {
  sessionId: string;
  messages: ChatMessage[];
  onSendMessage: (message: string) => void;
  isLoading?: boolean;
  connectionStatus?: 'connected' | 'connecting' | 'disconnected' | 'error';
  connectionQuality?: 'good' | 'poor' | 'disconnected';
  onManualReconnect?: () => void;
}

export const ChatInterface: React.FC<ChatInterfaceProps> = ({
  messages,
  onSendMessage,
  isLoading = false,
  connectionStatus = 'disconnected',
  connectionQuality = 'disconnected',
  onManualReconnect,
}) => {
  const [inputMessage, setInputMessage] = useState('');
  const [errorMessage, setErrorMessage] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [messageDeliveryStatus, setMessageDeliveryStatus] = useState<Map<string, 'sending' | 'sent' | 'failed'>>(new Map());
  const [isAssistantTyping, setIsAssistantTyping] = useState(false);
  const [showConnectionError, setShowConnectionError] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const messagesScrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const recognitionRef = useRef<unknown>(null);

  const scrollMessagesToBottom = useCallback(() => {
    const el = messagesScrollRef.current;
    if (!el) return;
    el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' });
  }, []);

  useEffect(() => {
    console.log('🎨 ChatInterface: Messages updated', {
      count: messages.length,
      messageIds: messages.map(m => m.id),
      messageSenders: messages.map(m => m.sender)
    });
    // Прокрутка только внутри области чата (без scrollIntoView — иначе дёргается вся страница)
    if (messages.length === 0 && !isLoading && !isAssistantTyping) return;
    const t = requestAnimationFrame(() => {
      scrollMessagesToBottom();
    });
    return () => cancelAnimationFrame(t);
  }, [messages, isLoading, isAssistantTyping, scrollMessagesToBottom]);
  
  // Отслеживаем состояние подключения
  useEffect(() => {
    if (connectionStatus === 'disconnected' || connectionStatus === 'error') {
      setShowConnectionError(true);
    } else {
      setShowConnectionError(false);
    }
  }, [connectionStatus]);
  
  // Индикатор «печатает» только пока реально ждём ответ (isLoading — boolean)
  useEffect(() => {
    const loading = Boolean(isLoading);
    console.log('🎨 ChatInterface: isLoading changed', { isLoading: loading, isAssistantTyping });
    if (loading && !isAssistantTyping) {
      setIsAssistantTyping(true);
    } else if (!loading && isAssistantTyping) {
      const id = window.setTimeout(() => setIsAssistantTyping(false), 400);
      return () => clearTimeout(id);
    }
  }, [isLoading, isAssistantTyping]);

  // Голосовой ввод (Web Speech API): запуск/остановка распознавания
  const toggleVoiceInput = useCallback(() => {
    if (!SpeechRecognitionAPI) return;
    const recognition = recognitionRef.current as { start: () => void; stop: () => void; abort: () => void } | null;
    if (isListening && recognition) {
      try { recognition.stop(); } catch { recognition.abort?.(); }
      setIsListening(false);
      return;
    }
    try {
      const Rec = SpeechRecognitionAPI as new () => { start: () => void; stop: () => void; abort: () => void; onresult: (e: { results: { transcript: string }[][] }) => void; onerror: (e: { error: string }) => void; onend: () => void; continuous: boolean; lang: string; interimResults: boolean };
      const r = new Rec();
      r.continuous = true;
      r.lang = 'ru-RU';
      r.interimResults = false;
      r.onresult = (e: { resultIndex?: number; results: { length: number; [i: number]: { [j: number]: { transcript?: string }; transcript?: string } } }) => {
        const resultIndex = e.resultIndex ?? 0;
        const parts: string[] = [];
        for (let i = resultIndex; i < e.results.length; i++) {
          const result = e.results[i];
          const first = result?.[0] ?? result;
          const t = (first as { transcript?: string } | undefined)?.transcript ?? '';
          if (t) parts.push(t);
        }
        const transcript = parts.join(' ').trim();
        if (transcript) setInputMessage((prev) => (prev ? `${prev} ${transcript}` : transcript).trim().slice(0, 1000));
      };
      r.onerror = (e: { error?: string }) => {
        setIsListening(false);
        const code = e?.error ?? 'unknown';
        toast.error(getMicErrorMessage(code));
      };
      r.onend = () => setIsListening(false);
      recognitionRef.current = r;
      r.start();
      setIsListening(true);
    } catch {
      setIsListening(false);
      toast.error(getMicErrorMessage('not-allowed'));
    }
  }, [isListening]);

  // Диагностика микрофона при ?diagnose=mic
  useEffect(() => {
    if (typeof window !== 'undefined' && new URLSearchParams(window.location.search).get('diagnose') === 'mic') {
      logMicDiagnostic();
    }
  }, []);

  // Остановка распознавания при размонтировании
  useEffect(() => {
    return () => {
      const r = recognitionRef.current as { stop?: () => void; abort?: () => void } | null;
      if (r) try { r.stop?.(); } catch { r.abort?.(); }
    };
  }, []);

  // Функция для санитизации HTML для предотвращения XSS
  const sanitizeHtml = (input: string): string => {
    // Удаляем потенциально опасные HTML теги и скрипты
    return input
      .replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, '')
      .replace(/<iframe\b[^<]*(?:(?!<\/iframe>)<[^<]*)*<\/iframe>/gi, '')
      .replace(/<object\b[^<]*(?:(?!<\/object>)<[^<]*)*<\/object>/gi, '')
      .replace(/<embed\b[^<]*(?:(?!<\/embed>)<[^<]*)*<\/embed>/gi, '')
      .replace(/javascript:/gi, '')
      .replace(/on\w+\s*=/gi, '');
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    
    // Очищаем предыдущие ошибки
    setErrorMessage('');
    
    // Проверка на пустое сообщение
    if (!inputMessage || !inputMessage.trim()) {
      setErrorMessage('Пожалуйста, введите сообщение');
      return;
    }
    
    // Проверка длины сообщения
    if (inputMessage.trim().length < 1) {
      setErrorMessage('Сообщение слишком короткое');
      return;
    }
    
    if (inputMessage.trim().length > 1000) {
      setErrorMessage('Сообщение слишком длинное (максимум 1000 символов)');
      return;
    }
    
    // Санитизация сообщения
    const sanitizedMessage = sanitizeHtml(inputMessage.trim());
    
    if (!sanitizedMessage || sanitizedMessage.length === 0) {
      setErrorMessage('Сообщение содержит недопустимые символы');
      return;
    }
    
    // Проверяем состояние подключения перед отправкой
    if (connectionStatus !== 'connected') {
      setErrorMessage('Нет подключения к серверу. Сообщение будет отправлено при восстановлении соединения.');
      return;
    }
    
    // Создаем ID для отслеживания доставки сообщения
    const messageId = `user_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    
    // Устанавливаем статус отправки
    setMessageDeliveryStatus(prev => new Map(prev).set(messageId, 'sending'));
    
    try {
      onSendMessage(sanitizedMessage);
      setInputMessage('');
      
      // Обновляем статус на "отправлено" через небольшую задержку
      setTimeout(() => {
        setMessageDeliveryStatus(prev => {
          const newMap = new Map(prev);
          newMap.set(messageId, 'sent');
          return newMap;
        });
      }, 500);
      
      // Очищаем статус доставки через некоторое время
      setTimeout(() => {
        setMessageDeliveryStatus(prev => {
          const newMap = new Map(prev);
          newMap.delete(messageId);
          return newMap;
        });
      }, 5000);
    } catch (error) {
      // Обновляем статус на "ошибка"
      setMessageDeliveryStatus(prev => {
        const newMap = new Map(prev);
        newMap.set(messageId, 'failed');
        return newMap;
      });
        setErrorMessage('Не удалось отправить сообщение. Попробуйте еще раз.');
        
        // Очищаем статус ошибки через некоторое время
        setTimeout(() => {
          setMessageDeliveryStatus(prev => {
            const newMap = new Map(prev);
            newMap.delete(messageId);
            return newMap;
          });
        }, 5000);
      }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };
  
  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setInputMessage(e.target.value);
    setErrorMessage(''); // Очищаем ошибку при вводе
    
    // Показываем индикатор набора текста
    if (!isTyping && e.target.value.length > 0) {
      setIsTyping(true);
    } else if (isTyping && e.target.value.length === 0) {
      setIsTyping(false);
    }
  };

  const formatTimestamp = (timestamp: string) => {
    return new Date(timestamp).toLocaleTimeString('ru-RU', {
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const DISCLAIMER =
    'Информация носит вспомогательный характер и не заменяет клинический осмотр и действующие стандарты помощи.';

  const renderMessage = useCallback((message: ChatMessage) => {
    const isUser = message.sender === 'user';
    const deliveryStatus = messageDeliveryStatus.get(message.id);

    return (
      <div
        key={message.id}
        className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-4 fade-in`}
      >
        {!isUser && (
          <div className="flex flex-col items-center mr-2 shrink-0">
            <div className="w-9 h-9 rounded-full bg-[#2A9FFF] flex items-center justify-center text-white text-xs font-semibold">
              AI
            </div>
          </div>
        )}
        <div className={`flex flex-col ${isUser ? 'items-end' : 'items-start'} max-w-[85%] lg:max-w-md`}>
          {!isUser && (
            <span className="text-xs font-medium text-gray-600 mb-1">Мария Ивановна</span>
          )}
          <div className={`message ${isUser ? 'message-user' : 'message-assistant'} px-4 py-3 relative rounded-2xl ${isUser ? 'rounded-br-sm' : 'rounded-bl-sm'}`}>
            {message.type === 'recommendation' && (
              <div className="mb-2 p-2 bg-yellow-100 rounded text-yellow-800 text-xs">
                💡 Рекомендация
              </div>
            )}
            {message.type === 'specialist' && (
              <div className="mb-2 p-2 bg-blue-100 rounded text-blue-800 text-xs">
                👨‍⚕️ Специалист
              </div>
            )}
            <ChatMessageMarkdown content={message.content ?? ''} />
            {!isUser && message.clinicalSources && message.clinicalSources.length > 0 && (
              <InlineClinicalSources sources={message.clinicalSources} />
            )}
            {!isUser && (
              <div className="mt-3 pt-3 border-t border-gray-200 flex items-start gap-2">
                <ExclamationTriangleIcon className="w-4 h-4 text-amber-500 shrink-0 mt-0.5" />
                <p className="text-xs font-semibold text-gray-700">{DISCLAIMER}</p>
              </div>
            )}
          </div>
          <div className={`text-xs mt-1 flex items-center gap-2 ${isUser ? 'text-gray-500' : 'text-gray-400'}`}>
            <span>{formatTimestamp(message.timestamp)}</span>
            {isUser && deliveryStatus === 'sending' && (
              <span className="text-amber-600">Отправка...</span>
            )}
            {isUser && deliveryStatus === 'sent' && (
              <span className="text-green-600">✓</span>
            )}
            {isUser && deliveryStatus === 'failed' && (
              <span className="text-red-600">✗ Ошибка</span>
            )}
          </div>
        </div>
      </div>
    );
  }, [messageDeliveryStatus]);

  return (
    <div className="chat-container h-full flex flex-col">
      {/* Chat Header — минимальный, только статус подключения */}
      <div className="chat-header py-2">
        <div className="flex items-center justify-end space-x-2">
            {/* Индикатор состояния подключения */}
            <div className="flex items-center space-x-1">
              {connectionStatus === 'connected' ? (
                <>
                  <WifiIcon className="w-4 h-4 text-green-500" />
                  <div className={`w-2 h-2 rounded-full ${connectionQuality === 'good' ? 'bg-green-500' : 'bg-yellow-500'} ${connectionQuality === 'good' ? '' : 'animate-pulse'}`}></div>
                </>
              ) : connectionStatus === 'connecting' ? (
                <>
                  <ArrowPathIcon className="w-4 h-4 text-yellow-500 animate-spin" />
                  <div className="w-2 h-2 rounded-full bg-yellow-500 animate-pulse"></div>
                </>
              ) : (
                <>
                  <SignalSlashIcon className="w-4 h-4 text-red-500" />
                  <div className="w-2 h-2 rounded-full bg-red-500"></div>
                </>
              )}
            </div>
            
            <span className="text-sm text-gray-600">
              {connectionStatus === 'connected'
                ? (isLoading ? 'Анализирует...' : 'Готов к ответу')
                : connectionStatus === 'connecting'
                ? 'Подключение...'
                : 'Нет подключения'
              }
            </span>
            
            {isTyping && (
              <span className="text-xs text-gray-500 italic">Набирает сообщение...</span>
            )}
            {connectionStatus !== 'connected' && onManualReconnect && (
              <button
                onClick={onManualReconnect}
                className="text-xs text-blue-600 hover:text-blue-800 flex items-center space-x-1"
                title="Переподключиться"
              >
                <ArrowPathIcon className="w-3 h-3" />
                <span>Переподключиться</span>
              </button>
            )}
        </div>
      </div>

      {/* Messages Container */}
      <div className="chat-messages" ref={messagesScrollRef}>
        {messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-gray-500">
            <div className="text-center mb-4">
              <div className="w-16 h-16 bg-medical-lightblue rounded-full flex items-center justify-center mx-auto mb-4">
                <PaperAirplaneIcon className="w-8 h-8 text-medical-blue" />
              </div>
              <h3 className="text-lg font-medium text-gray-900 mb-2">
                Начните консультацию
              </h3>
              <p className="text-sm">
                Опишите кейс пациента — помогу структурировать оценку и маршрутизацию.
              </p>
            </div>
            
            <div className="text-left max-w-md">
              <p className="text-sm font-medium text-gray-700 mb-2">
                Примеры запросов:
              </p>
              <ul className="text-sm space-y-1 text-gray-600">
                <li>• «Пациент 3 лет, t 38.5 °C, нарастающая вялость — дифференциал и срочность?»</li>
                <li>• «Какие красные флаги при лихорадке у данного контингента учитывать в первую очередь?»</li>
                <li>• «Показания к госпитализации против амбулаторного наблюдения по текущей картине?»</li>
                <li>• «Кого из специалистов включить в маршрут при подозрении на …?»</li>
              </ul>
            </div>
          </div>
        ) : (
          messages.map(renderMessage)
        )}
        
        {/* Индикатор набора текста ассистентом */}
        {isAssistantTyping && (
          <div className="flex justify-start mb-4">
            <div className="message message-assistant px-4 py-2">
              <div className="flex items-center space-x-2">
                <div className="loading-spinner w-4 h-4"></div>
                <span className="text-sm">Ассистент печатает...</span>
              </div>
              <div className="mt-2">
                <div className="flex space-x-1">
                  <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }}></div>
                  <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></div>
                  <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></div>
                </div>
              </div>
            </div>
          </div>
        )}
        
        {/* Уведомление об ошибке подключения */}
        {showConnectionError && (
          <div className="flex justify-center mb-4">
            <div className="bg-red-50 border border-red-200 rounded-lg p-3 max-w-md">
              <div className="flex items-center space-x-2">
                <SignalSlashIcon className="w-5 h-5 text-red-500" />
                <div>
                  <p className="text-sm font-medium text-red-800">
                    {connectionStatus === 'error' ? 'Ошибка подключения' : 'Соединение потеряно'}
                  </p>
                  <p className="text-xs text-red-600 mt-1">
                    {connectionStatus === 'error'
                      ? 'Не удалось подключиться к серверу. Проверьте интернет-соединение.'
                      : 'Пытаемся восстановить соединение...'}
                  </p>
                  {onManualReconnect && (
                    <button
                      onClick={onManualReconnect}
                      className="mt-2 text-xs text-red-700 hover:text-red-900 underline"
                    >
                      Попробовать переподключиться
                    </button>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}
        
        <div ref={messagesEndRef} />
      </div>

      {/* Input Container */}
      <div className="chat-input-container">
        <form onSubmit={handleSubmit} className="flex space-x-2 items-center">
          {SpeechRecognitionAPI && (
            <button
              type="button"
              onClick={canUseMicrophoneGlobal ? toggleVoiceInput : undefined}
              disabled={!canUseMicrophoneGlobal}
              className={`btn px-3 py-2 shrink-0 ${!canUseMicrophoneGlobal ? 'bg-gray-100 text-gray-400 cursor-not-allowed' : isListening ? 'bg-red-500 hover:bg-red-600 text-white' : 'bg-gray-100 hover:bg-gray-200 text-gray-700'} rounded-lg transition-colors`}
              title={
                !canUseMicrophoneGlobal
                  ? SpeechRecognitionAPI
                    ? 'Микрофон доступен только по HTTPS или с localhost'
                    : 'Голосовой ввод недоступен в этом браузере'
                  : isListening
                    ? 'Остановить запись'
                    : 'Голосовой ввод'
              }
              aria-label={isListening ? 'Остановить запись' : 'Голосовой ввод'}
            >
              {isListening ? (
                <MicrophoneIconSolid className="w-5 h-5" />
              ) : (
                <MicrophoneIcon className="w-5 h-5" />
              )}
            </button>
          )}
          <div className="flex-1 relative">
            <input
              ref={inputRef}
              type="text"
              value={inputMessage}
              onChange={handleInputChange}
              onKeyPress={handleKeyPress}
              placeholder="Введите ваш вопрос..."
              className={`form-input pr-12 ${errorMessage ? 'border-red-500 focus:border-red-500' : ''}`}
              maxLength={1000}
            />
            <div className="absolute right-2 top-1/2 transform -translate-y-1/2 text-xs text-gray-400">
              {inputMessage.length}/1000
            </div>
          </div>
          
          <button
            type="submit"
            className={`btn px-4 py-2 ${
              connectionStatus !== 'connected'
                ? 'btn-disabled bg-gray-300 text-gray-500 cursor-not-allowed'
                : 'btn-primary'
            }`}
            disabled={!inputMessage.trim() || inputMessage.trim().length < 1 || connectionStatus !== 'connected'}
            title={connectionStatus !== 'connected' ? 'Нет подключения к серверу' : 'Отправить сообщение'}
          >
            <PaperAirplaneIcon className="w-5 h-5" />
          </button>
        </form>
        
        {errorMessage && (
          <div className="mt-2 p-2 bg-red-100 border border-red-400 text-red-700 rounded flex items-center justify-between">
            <div className="flex items-center">
              <ExclamationTriangleIcon className="w-4 h-4 mr-2" />
              <span className="text-sm">{errorMessage}</span>
            </div>
            <button
              onClick={() => setErrorMessage('')}
              className="text-red-500 hover:text-red-700"
              title="Закрыть"
            >
              ×
            </button>
          </div>
        )}
        
        <div className="mt-2 text-xs text-gray-500 text-center flex items-center justify-center space-x-2">
          <span>Нажмите Enter для отправки сообщения.</span>
          <span>•</span>
          <span>Ассистент использует ИИ для анализа симптомов.</span>
          {connectionQuality === 'poor' && (
            <>
              <span>•</span>
              <span className="text-yellow-600">Нестабильное соединение</span>
            </>
          )}
        </div>
      </div>
    </div>
  );
};

// Оптимизируем компонент с memo чтобы избежать лишних ререндеров
const OptimizedChatInterface = memo(ChatInterface);
OptimizedChatInterface.displayName = 'ChatInterface';

export default OptimizedChatInterface;