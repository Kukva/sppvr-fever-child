import type { AgentStatus, ChatMessage, Recommendation, AgentWorkflowStep, ClinicalSource } from '../types';

/** Если модель вернула пустой/пробельный ответ — показываем явную подсказку врачу вместо «молчания». */
const EMPTY_ASSISTANT_RESPONSE_FALLBACK =
  'По этому запросу не удалось сформулировать развёрнутый ответ. Уточните клиническую картину, переформулируйте вопрос или используйте блок «Логика агентов» и рекомендации ниже, если они отображаются.';

/** Шаги, после которых граф уже не «крутится» в фоне (для статуса в UI). */
function isPipelineStepIdle(currentStep: string | undefined): boolean {
  if (!currentStep) return false;
  return (
    currentStep === 'completed' ||
    currentStep === 'feedback_requested' ||
    currentStep === 'triage_completed' ||
    currentStep === 'synthesis_completed' ||
    currentStep === 'hypothesis_generation_completed' ||
    currentStep === 'questions_completed' ||
    currentStep === 'questions_generated' ||
    currentStep === 'waiting_for_user' ||
    currentStep === 'awaiting_input'
  );
}

class WebSocketService {
  private ws: WebSocket | null = null;
  private wsUrl: string;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectDelay = 1000;
  private maxReconnectDelay = 30000; // Максимальная задержка 30 секунд
  private isConnecting = false;
  private sessionId: string = '';
  private messageQueue: any[] = [];
  private eventListeners: Map<string, Function[]> = new Map();
  private responseTimeouts: Map<string, number> = new Map();
  private isOnline = navigator.onLine;
  private connectionNotificationShown = false;
  private reconnectTimeoutId: number | null = null;
  private lastDisconnectTime: number = 0;
  private consecutiveFailures = 0;
  private backoffMultiplier = 1.5; // Множитель для экспоненциальной задержки
  private processedResponses = new Set<string>(); // Отслеживание обработанных ответов
  /** При переключении сессии — не запускать handleReconnect */
  private closingForSwitch = false;
  /** Закрытие по disconnect/closeSocketOnly — не логировать и не пробрасывать Event в reject */
  private abortingConnect = false;

  // Простой хеш-метод для создания уникальных ID
  private hashString(str: string): string {
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
      const char = str.charCodeAt(i);
      hash = ((hash << 5) - hash) + char;
      hash = hash & hash; // Convert to 32bit integer
    }
    return Math.abs(hash).toString(36);
  }

  constructor(wsUrl: string = import.meta.env.VITE_WS_URL || '') {
    // В production используем относительные пути, в development - полный URL
    if (import.meta.env.PROD) {
      // В production используем текущий протокол и хост
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const host = window.location.host;
      const apiBase = (import.meta.env.VITE_API_BASE_URL || '').toString().trim();
      this.wsUrl = apiBase ? apiBase.replace(/^http/, 'ws').replace(/\/+$/, '') : `${protocol}//${host}`;
    } else {
      // В режиме разработки используем прямой URL к бэкенду
      this.wsUrl = wsUrl || 'ws://localhost:8000';
    }
    
    // Отслеживаем состояние сети
    window.addEventListener('online', this.handleOnlineStatusChange.bind(this));
    window.addEventListener('offline', this.handleOnlineStatusChange.bind(this));
  }

  /** Закрывает сокет и сбрасывает состояние без очистки listeners (для смены сессии). */
  private closeSocketOnly(): void {
    this.abortingConnect = true;
    this.closingForSwitch = true;
    this.responseTimeouts.forEach(id => clearTimeout(id));
    this.responseTimeouts.clear();
    if (this.reconnectTimeoutId) {
      clearTimeout(this.reconnectTimeoutId);
      this.reconnectTimeoutId = null;
    }
    if (this.ws) {
      this.ws.onclose = null;
      this.ws.onerror = null;
      this.ws.onopen = null;
      this.ws.onmessage = null;
      this.ws.close();
      this.ws = null;
    }
    this.isConnecting = false;
  }

  connect(sessionId: string): Promise<void> {
    return new Promise((resolve, reject) => {
      if (this.ws && this.ws.readyState === WebSocket.OPEN && this.sessionId === sessionId) {
        resolve();
        return;
      }

      if (this.isConnecting || (this.ws && this.sessionId !== sessionId)) {
        this.closeSocketOnly();
      }

      this.closingForSwitch = false;
      this.abortingConnect = false;
      this.isConnecting = true;
      this.sessionId = sessionId;
      this.messageQueue = []; // очередь для старой сессии сбрасываем

      try {
        const fullUrl = `${this.wsUrl}/api/v1/chat/stream/${sessionId}`;
        console.log('Connecting to WebSocket:', fullUrl);

        this.ws = new WebSocket(fullUrl);

        this.ws.onopen = () => {
          console.log('WebSocket connected');
          this.isConnecting = false;
          this.reconnectAttempts = 0;

          this.flushMessageQueue();

          resolve();
        };

        this.ws.onmessage = (event) => {
          try {
            // Проверка на пустые или некорректные данные
            if (!event.data || typeof event.data !== 'string') {
              console.warn('Received empty or invalid WebSocket data');
              return;
            }
            
            // Проверка на malformed JSON
            let data;
            try {
              data = JSON.parse(event.data);
            } catch (parseError) {
              console.error('Error parsing WebSocket message (malformed JSON):', parseError);
              console.error('Raw data:', event.data);
              this.emit('error', new Error('Received malformed JSON from server'));
              return;
            }
            
            // Проверка структуры сообщения
            if (!data || typeof data !== 'object') {
              console.warn('Received invalid message structure:', data);
              return;
            }
            
            this.handleMessage(data);
          } catch (error) {
            console.error('Unexpected error processing WebSocket message:', error);
            this.emit('error', new Error('Failed to process WebSocket message'));
          }
        };

        this.ws.onclose = (event) => {
          console.log('WebSocket disconnected:', event.code, event.reason);
          this.isConnecting = false;
          this.handleReconnect();
        };

        this.ws.onerror = (error) => {
          if (this.abortingConnect) {
            this.abortingConnect = false;
            this.isConnecting = false;
            reject(new Error('Connection aborted'));
            return;
          }
          console.error('WebSocket error:', error);
          this.isConnecting = false;
          reject(error);
        };
      } catch (error) {
        this.isConnecting = false;
        reject(error);
      }
    });
  }

  private handleMessage(data: any) {
    console.log('🔥 WebSocket message received:', data);
    console.log('🔥 Message type:', data.type);
    console.log('🔥 Full data structure:', JSON.stringify(data, null, 2));
    
    const { type, message, status, current_step, urgency_level, needs_more_info, questions_to_ask } = data;
    
    switch (type) {
      case 'connection_established':
        console.log('✅ WebSocket connection established:', data);
        this.emit('connection_established', data);
        break;
        
      case 'message_received':
        console.log('✅ Message received confirmation:', data);
        // Очищаем таймаут для этого сообщения
        this.clearResponseTimeout(data.message_id);
        this.emit('message_received', data);
        break;
        
      case 'message':
        console.log('💬 Chat message received:', message);
        this.emit('chat_message', message);
        break;
        
      case 'status':
        console.log('📊 Status update received:', { current_step, urgency_level, needs_more_info, questions_to_ask });
        const done = isPipelineStepIdle(current_step);
        const agentStatus = {
          agents: [{
            id: 'main',
            name: 'Main Agent',
            type: 'coordinator',
            status: done ? 'completed' : 'processing',
            progress: done ? 100 : 50,
            currentTask: current_step,
            result: status
          }],
          overallProgress: done ? 100 : 50,
          currentStep: current_step || 'Processing'
        };
        console.log('📊 Emitting agent status:', agentStatus);
        this.emit('agent_status', agentStatus);
        break;
        
      case 'response':
        console.log('📝 Response received:', data);
        console.log('📝 Response data:', data.data);
        console.log('📝 Response data keys:', data.data ? Object.keys(data.data) : 'undefined');
        console.log('📝 Response data.response:', data.data?.response);
        
        const rawResponse = data.data?.response;
        const trimmed =
          typeof rawResponse === 'string' ? rawResponse.trim() : String(rawResponse ?? '').trim();
        const hasText = trimmed.length > 0;
        const displayContent = hasText ? trimmed : EMPTY_ASSISTANT_RESPONSE_FALLBACK;

        // Создаем уникальный ID: пустые ответы не дедуплицируем по хешу пустой строки
        const responseId = hasText
          ? `response_${this.hashString(trimmed + (data.data?.session_id || '') + (data.data?.timestamp || ''))}`
          : `response_empty_${Date.now()}_${Math.random().toString(36).slice(2, 11)}`;

        if (!hasText) {
          console.warn('⚠️ Empty assistant response from server; showing fallback');
        }

        // Проверяем, не обрабатывали ли мы уже этот ответ (только для непустых — иначе каждый раз новый id)
        if (hasText && this.processedResponses.has(responseId)) {
          console.log('🔄 Response already processed, skipping:', responseId);
          this.emit('assistant_response_complete');
          return;
        }

        if (hasText) {
          this.processedResponses.add(responseId);
        }

        // Очищаем старые обработанные ответы (оставляем только последние 50)
        if (this.processedResponses.size > 50) {
          const oldestResponse = this.processedResponses.values().next().value;
          if (oldestResponse) {
            this.processedResponses.delete(oldestResponse);
          }
        }
        
        // Сначала отправляем статус, если он есть в ответе
        if (data.data && data.data.current_step) {
          console.log('📊 Emitting agent status from response:', data.data.current_step);
          const isDone = isPipelineStepIdle(data.data.current_step);
          const responseAgentStatus = {
            agents: [{
              id: 'main',
              name: 'Main Agent',
              type: 'coordinator',
              status: isDone ? 'completed' : 'processing',
              progress: isDone ? 100 : 50,
              currentTask: data.data.current_step,
              result: data.data.urgency_level || 'processing'
            }],
            overallProgress: isDone ? 100 : 50,
            currentStep: data.data.current_step || 'Processing'
          };
          console.log('📊 Agent status from response:', responseAgentStatus);
          this.emit('agent_status', responseAgentStatus);
        }
        
        // Всегда показываем сообщение в чате, если есть data.data (пустой ответ — fallback)
        if (data.data) {
          console.log('💬 Emitting chat message:', displayContent.substring(0, 120));
          const rawSources = data.data.clinical_sources;
          const clinicalSources =
            Array.isArray(rawSources) && rawSources.length > 0 ? rawSources : undefined;
          const chatMessage = {
            id: responseId,
            content: displayContent,
            sender: 'assistant' as const,
            timestamp: new Date().toISOString(),
            ...(clinicalSources ? { clinicalSources } : {}),
          };
          this.emit('chat_message', chatMessage);
        } else {
          console.warn('⚠️ Response payload missing data.data:', data);
        }
        
        // Отправляем рекомендации, если они есть
        if (data.data && data.data.recommendations) {
          console.log('💡 Emitting recommendations:', data.data.recommendations);
          this.emit('recommendation', data.data.recommendations);
        }
        // Логика работы агентов и клинические источники
        if (data.data && data.data.agent_workflow && data.data.agent_workflow.length > 0) {
          this.emit('agent_workflow', data.data.agent_workflow);
        }
        if (data.data && data.data.clinical_sources && data.data.clinical_sources.length > 0) {
          this.emit('clinical_sources', data.data.clinical_sources);
        }
        this.emit('assistant_response_complete');
        break;
        
      case 'command_response':
        // Обработка ответа на команду
        console.log('🎯 Command response received:', data);
        this.emit('command_response', data);
        break;
        
      case 'error':
        // Обработка ошибки
        console.error('❌ WebSocket error from server:', data.message);
        this.emit('assistant_response_complete');
        this.emit('error', new Error(data.message || 'Unknown WebSocket error'));
        break;
        
      case 'agent_progress':
        this.emit('agent_progress', {
          agent_key: data.agent_key,
          title: data.title,
          description: data.description,
          status: data.status || 'completed',
        });
        break;

      case 'pong':
        // Ответ на ping-запрос
        console.log('🏓 Received pong from server');
        break;
        
      case 'ping':
        // Ответ на ping-запрос от сервера
        console.log('🏓 Received ping from server');
        break;
        
      default:
        console.warn('❓ Unknown message type:', type, data);
    }
  }

  private emit(event: string, data: any) {
    const listeners = this.eventListeners.get(event) || [];
    console.log(`📢 Emitting event "${event}" to ${listeners.length} listeners:`, data);
    listeners.forEach((callback, index) => {
      console.log(`📢 Calling listener ${index + 1} for event "${event}"`);
      callback(data);
    });
  }

  private flushMessageQueue() {
    while (this.messageQueue.length > 0 && this.ws && this.ws.readyState === WebSocket.OPEN) {
      const message = this.messageQueue.shift();
      try {
        // Проверка сообщения перед отправкой
        if (!message || typeof message !== 'object') {
          console.warn('Invalid message in queue, skipping:', message);
          continue;
        }
        
        const messageStr = JSON.stringify(message);
        this.ws.send(messageStr);
        
        // Устанавливаем таймаут для ответа (если это сообщение с ожиданием ответа)
        if (message.expectResponse) {
          const timeoutId = setTimeout(() => {
            console.warn(`No response received for message: ${message.type}`);
            this.emit('error', new Error('Response timeout'));
          }, 30000); // 30 секунд таймаут
          
          this.responseTimeouts.set(message.id || message.type, timeoutId);
        }
      } catch (error) {
        console.error('Error sending message from queue:', error);
        this.emit('error', new Error('Failed to send message'));
        
        // Возвращаем сообщение в очередь при ошибке
        this.messageQueue.unshift(message);
        break;
      }
    }
  }

  private handleReconnect() {
    if (this.closingForSwitch) {
      this.closingForSwitch = false;
      return;
    }
    // Проверяем состояние сети перед попыткой переподключения
    if (!this.isOnline) {
      console.log('Offline detected, postponing reconnection');
      this.emit('error', new Error('Network connection lost'));
      return;
    }
    
    // Проверяем, не было ли слишком частых отключений
    const now = Date.now();
    const timeSinceLastDisconnect = now - this.lastDisconnectTime;
    
    // Если отключения происходят слишком часто, увеличиваем множитель
    if (timeSinceLastDisconnect < 5000) { // Меньше 5 секунд
      this.consecutiveFailures++;
    } else {
      this.consecutiveFailures = Math.max(0, this.consecutiveFailures - 1);
    }
    
    this.lastDisconnectTime = now;
    
    if (this.reconnectAttempts < this.maxReconnectAttempts) {
      this.reconnectAttempts++;
      
      // Экспоненциальная задержка с учетом множителя для частых отключений
      const baseDelay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1);
      const adjustedDelay = Math.min(
        baseDelay * Math.pow(this.backoffMultiplier, this.consecutiveFailures),
        this.maxReconnectDelay
      );
      
      console.log(`Attempting to reconnect in ${adjustedDelay}ms (attempt ${this.reconnectAttempts}, consecutive failures: ${this.consecutiveFailures})`);
      
      // Показываем уведомление о проблемах с подключением
      if (this.reconnectAttempts > 2 && !this.connectionNotificationShown) {
        this.connectionNotificationShown = true;
        this.emit('error', new Error(`Connection issues detected, attempting to reconnect (${this.reconnectAttempts}/${this.maxReconnectAttempts})...`));
      }
      
      // Очищаем предыдущий таймаут, если есть
      if (this.reconnectTimeoutId) {
        clearTimeout(this.reconnectTimeoutId);
      }
      
      this.reconnectTimeoutId = window.setTimeout(() => {
        if (this.sessionId) {
          this.connect(this.sessionId).catch(error => {
            console.error('Reconnection failed:', error);
            this.consecutiveFailures++;
            
            if (this.reconnectAttempts >= this.maxReconnectAttempts) {
              this.emit('error', new Error(`Failed to reconnect after ${this.maxReconnectAttempts} attempts. Please refresh the page or check your connection.`));
            }
          });
        }
      }, adjustedDelay);
    } else {
      console.error(`Max reconnection attempts (${this.maxReconnectAttempts}) reached`);
      this.emit('error', new Error(`Connection failed after ${this.maxReconnectAttempts} attempts. Please refresh the page or check your internet connection.`));
      
      // Предлагаем ручное переподключение через некоторое время
      setTimeout(() => {
        this.emit('error', new Error('You can try to reconnect manually or refresh the page.'));
      }, 10000);
    }
  }

  disconnect() {
    this.abortingConnect = true;
    this.closingForSwitch = true;
    // Очищаем все таймауты
    this.responseTimeouts.forEach(timeoutId => clearTimeout(timeoutId));
    this.responseTimeouts.clear();

    if (this.reconnectTimeoutId) {
      clearTimeout(this.reconnectTimeoutId);
      this.reconnectTimeoutId = null;
    }

    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    this.isConnecting = false;
    this.eventListeners.clear();
    this.messageQueue = [];
    this.connectionNotificationShown = false;
    this.reconnectAttempts = 0;
    this.consecutiveFailures = 0;
    this.lastDisconnectTime = 0;
    
    // Очищаем обработанные ответы при отключении
    this.processedResponses.clear();
  }

  // Event subscription methods
  onAgentStatus(callback: (status: AgentStatus) => void) {
    const listeners = this.eventListeners.get('agent_status') || [];
    // Проверяем, не добавлен ли уже этот callback
    if (!listeners.includes(callback)) {
      listeners.push(callback);
      this.eventListeners.set('agent_status', listeners);
      console.log('✅ Agent status callback registered');
    } else {
      console.log('⚠️ Agent status callback already registered, skipping');
    }
  }

  onChatMessage(callback: (message: ChatMessage) => void) {
    const listeners = this.eventListeners.get('chat_message') || [];
    // Проверяем, не добавлен ли уже этот callback
    if (!listeners.includes(callback)) {
      listeners.push(callback);
      this.eventListeners.set('chat_message', listeners);
      console.log('✅ Chat message callback registered');
    } else {
      console.log('⚠️ Chat message callback already registered, skipping');
    }
  }

  onRecommendation(callback: (recommendation: Recommendation) => void) {
    const listeners = this.eventListeners.get('recommendation') || [];
    if (!listeners.includes(callback)) {
      listeners.push(callback);
      this.eventListeners.set('recommendation', listeners);
      console.log('✅ Recommendation callback registered');
    } else {
      console.log('⚠️ Recommendation callback already registered, skipping');
    }
  }

  onAgentWorkflow(callback: (workflow: AgentWorkflowStep[]) => void) {
    const listeners = this.eventListeners.get('agent_workflow') || [];
    if (!listeners.includes(callback)) {
      listeners.push(callback);
      this.eventListeners.set('agent_workflow', listeners);
    }
  }

  onClinicalSources(callback: (sources: ClinicalSource[]) => void) {
    const listeners = this.eventListeners.get('clinical_sources') || [];
    if (!listeners.includes(callback)) {
      listeners.push(callback);
      this.eventListeners.set('clinical_sources', listeners);
    }
  }

  onAgentProgress(callback: (step: { agent_key: string; title: string; description: string; status?: string }) => void) {
    const listeners = this.eventListeners.get('agent_progress') || [];
    if (!listeners.includes(callback)) {
      listeners.push(callback);
      this.eventListeners.set('agent_progress', listeners);
    }
  }

  /** Завершение обработки сообщения на сервере (ответ или ошибка) — для сброса индикатора «печатает». */
  onAssistantResponseComplete(callback: () => void) {
    const listeners = this.eventListeners.get('assistant_response_complete') || [];
    if (!listeners.includes(callback)) {
      listeners.push(callback);
      this.eventListeners.set('assistant_response_complete', listeners);
    }
  }

  offAgentProgress(callback: (step: { agent_key: string; title: string; description: string; status?: string }) => void) {
    const listeners = this.eventListeners.get('agent_progress') || [];
    const next = listeners.filter((cb) => cb !== callback);
    this.eventListeners.set('agent_progress', next);
  }

  onError(callback: (error: any) => void) {
    const listeners = this.eventListeners.get('error') || [];
    // Проверяем, не добавлен ли уже этот callback
    if (!listeners.includes(callback)) {
      listeners.push(callback);
      this.eventListeners.set('error', listeners);
      console.log('✅ Error callback registered');
    } else {
      console.log('⚠️ Error callback already registered, skipping');
    }
  }

  onSessionUpdate(callback: (update: any) => void) {
    const listeners = this.eventListeners.get('session_update') || [];
    // Проверяем, не добавлен ли уже этот callback
    if (!listeners.includes(callback)) {
      listeners.push(callback);
      this.eventListeners.set('session_update', listeners);
      console.log('✅ Session update callback registered');
    } else {
      console.log('⚠️ Session update callback already registered, skipping');
    }
  }

  onConnectionEstablished(callback: (data: any) => void) {
    const listeners = this.eventListeners.get('connection_established') || [];
    // Проверяем, не добавлен ли уже этот callback
    if (!listeners.includes(callback)) {
      listeners.push(callback);
      this.eventListeners.set('connection_established', listeners);
      console.log('✅ Connection established callback registered');
    } else {
      console.log('⚠️ Connection established callback already registered, skipping');
    }
  }

  onCommandResponse(callback: (data: any) => void) {
    const listeners = this.eventListeners.get('command_response') || [];
    // Проверяем, не добавлен ли уже этот callback
    if (!listeners.includes(callback)) {
      listeners.push(callback);
      this.eventListeners.set('command_response', listeners);
      console.log('✅ Command response callback registered');
    } else {
      console.log('⚠️ Command response callback already registered, skipping');
    }
  }

  // Event unsubscription methods
  offAgentStatus(callback: (status: AgentStatus) => void) {
    const listeners = this.eventListeners.get('agent_status') || [];
    const index = listeners.indexOf(callback);
    if (index > -1) {
      listeners.splice(index, 1);
      this.eventListeners.set('agent_status', listeners);
    }
  }

  offChatMessage(callback: (message: ChatMessage) => void) {
    const listeners = this.eventListeners.get('chat_message') || [];
    const index = listeners.indexOf(callback);
    if (index > -1) {
      listeners.splice(index, 1);
      this.eventListeners.set('chat_message', listeners);
    }
  }

  offRecommendation(callback: (recommendation: Recommendation) => void) {
    const listeners = this.eventListeners.get('recommendation') || [];
    const index = listeners.indexOf(callback);
    if (index > -1) {
      listeners.splice(index, 1);
      this.eventListeners.set('recommendation', listeners);
    }
  }

  offError(callback: (error: any) => void) {
    const listeners = this.eventListeners.get('error') || [];
    const index = listeners.indexOf(callback);
    if (index > -1) {
      listeners.splice(index, 1);
      this.eventListeners.set('error', listeners);
    }
  }

  offSessionUpdate(callback: (update: any) => void) {
    const listeners = this.eventListeners.get('session_update') || [];
    const index = listeners.indexOf(callback);
    if (index > -1) {
      listeners.splice(index, 1);
      this.eventListeners.set('session_update', listeners);
    }
  }

  offConnectionEstablished(callback: (data: any) => void) {
    const listeners = this.eventListeners.get('connection_established') || [];
    const index = listeners.indexOf(callback);
    if (index > -1) {
      listeners.splice(index, 1);
      this.eventListeners.set('connection_established', listeners);
    }
  }

  offCommandResponse(callback: (data: any) => void) {
    const listeners = this.eventListeners.get('command_response') || [];
    const index = listeners.indexOf(callback);
    if (index > -1) {
      listeners.splice(index, 1);
      this.eventListeners.set('command_response', listeners);
    }
  }

  // Send messages
  sendMessage(message: string) {
    // Проверка на пустое сообщение
    if (!message || typeof message !== 'string' || message.trim() === '') {
      console.warn('Attempted to send empty message');
      return;
    }
    
    const data = {
      id: `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
      type: 'message',
      content: message.trim(),
      timestamp: new Date().toISOString(),
      expectResponse: true
    };

    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      try {
        this.ws.send(JSON.stringify(data));
        
        // Устанавливаем таймаут для ответа
        const timeoutId = setTimeout(() => {
          console.warn(`No response received for message: ${data.id}`);
          this.emit('error', new Error('Response timeout for message'));
        }, 30000);
        
        this.responseTimeouts.set(data.id, timeoutId);
      } catch (error) {
        console.error('Error sending message:', error);
        this.emit('error', new Error('Failed to send message'));
        // Добавляем в очередь при ошибке
        this.messageQueue.push(data);
      }
    } else {
      // Добавляем в очередь, если соединение еще не установлено
      this.messageQueue.push(data);
    }
  }

  sendAgentCommand(command: string, data?: any) {
    // Проверка команды
    if (!command || typeof command !== 'string') {
      console.warn('Attempted to send invalid command');
      return;
    }
    
    const message = {
      id: `cmd_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
      type: 'command',
      command,
      data,
      timestamp: new Date().toISOString(),
      expectResponse: true
    };

    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      try {
        this.ws.send(JSON.stringify(message));
        
        // Устанавливаем таймаут для ответа
        const timeoutId = setTimeout(() => {
          console.warn(`No response received for command: ${message.id}`);
          this.emit('error', new Error('Response timeout for command'));
        }, 30000);
        
        this.responseTimeouts.set(message.id, timeoutId);
      } catch (error) {
        console.error('Error sending command:', error);
        this.emit('error', new Error('Failed to send command'));
        // Добавляем в очередь при ошибке
        this.messageQueue.push(message);
      }
    } else {
      // Добавляем в очередь, если соединение еще не установлено
      this.messageQueue.push(message);
    }
  }

  // Utility methods
  isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN || false;
  }

  getConnectionState(): string {
    if (!this.ws) return 'disconnected';
    
    switch (this.ws.readyState) {
      case WebSocket.CONNECTING:
        return 'connecting';
      case WebSocket.OPEN:
        return 'connected';
      case WebSocket.CLOSING:
        return 'closing';
      case WebSocket.CLOSED:
        return 'disconnected';
      default:
        return 'unknown';
    }
  }

  getSocketId(): string | undefined {
    return undefined; // Нативный WebSocket не имеет ID
  }

  // Метод для отправки ping-запроса
  ping() {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      try {
        this.ws.send(JSON.stringify({ type: 'ping', timestamp: new Date().toISOString() }));
      } catch (error) {
        console.error('Error sending ping:', error);
        this.emit('error', new Error('Failed to send ping'));
      }
    }
  }
  
  // Обработчик изменения состояния сети
  private handleOnlineStatusChange() {
    const wasOnline = this.isOnline;
    this.isOnline = navigator.onLine;
    
    if (!wasOnline && this.isOnline) {
      console.log('Network connection restored');
      this.connectionNotificationShown = false;
      this.consecutiveFailures = 0; // Сбрасываем счетчик при восстановлении сети
      
      // Пытаемся переподключиться при восстановлении сети с небольшой задержкой
      if (this.sessionId && !this.isConnected()) {
        this.reconnectAttempts = 0;
        
        // Небольшая задержка перед переподключением после восстановления сети
        setTimeout(() => {
          if (this.isOnline && !this.isConnected()) {
            this.connect(this.sessionId).catch(error => {
              console.error('Reconnection after network restore failed:', error);
              this.emit('error', new Error('Failed to reconnect after network restoration'));
            });
          }
        }, 1000);
      }
    } else if (wasOnline && !this.isOnline) {
      console.log('Network connection lost');
      this.emit('error', new Error('Network connection lost'));
      
      // Очищаем таймаут переподключения при потере сети
      if (this.reconnectTimeoutId) {
        clearTimeout(this.reconnectTimeoutId);
        this.reconnectTimeoutId = null;
      }
    }
  }
  
  // Метод для ручного переподключения
  public manualReconnect(): Promise<void> {
    if (this.isConnecting) {
      return Promise.reject(new Error('Connection already in progress'));
    }
    
    // Сбрасываем счетчики при ручном переподключении
    this.reconnectAttempts = 0;
    this.consecutiveFailures = 0;
    this.connectionNotificationShown = false;
    
    if (this.reconnectTimeoutId) {
      clearTimeout(this.reconnectTimeoutId);
      this.reconnectTimeoutId = null;
    }
    
    if (!this.sessionId) {
      return Promise.reject(new Error('No session ID available for reconnection'));
    }
    
    return this.connect(this.sessionId);
  }
  
  // Метод для получения информации о состоянии подключения
  public getConnectionInfo() {
    return {
      isConnected: this.isConnected(),
      connectionState: this.getConnectionState(),
      reconnectAttempts: this.reconnectAttempts,
      maxReconnectAttempts: this.maxReconnectAttempts,
      isOnline: this.isOnline,
      consecutiveFailures: this.consecutiveFailures,
      queuedMessages: this.messageQueue.length
    };
  }
  
  // Метод для очистки таймаута ответа
  private clearResponseTimeout(messageId: string) {
    const timeoutId = this.responseTimeouts.get(messageId);
    if (timeoutId) {
      clearTimeout(timeoutId);
      this.responseTimeouts.delete(messageId);
    }
  }
}

// Create singleton instance
const webSocketService = new WebSocketService();

export default webSocketService;