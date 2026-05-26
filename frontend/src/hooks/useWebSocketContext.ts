import { useWebSocketContext } from '../contexts/WebSocketContext';
import type { ChatMessage, AgentStatus } from '../types';

/**
 * Custom hook for accessing WebSocket context with additional utilities
 * This provides a clean interface for components to interact with WebSocket functionality
 */
export const useWebSocket = () => {
  const context = useWebSocketContext();

  // Additional utility functions can be added here
  const utilities = {
    // Check if there are any messages
    hasMessages: (): boolean => context.messages.length > 0,
    
    // Get last message
    getLastMessage: (): ChatMessage | null => {
      return context.messages.length > 0 ? context.messages[context.messages.length - 1] : null;
    },
    
    // Get messages by sender
    getMessagesBySender: (sender: 'user' | 'assistant'): ChatMessage[] => {
      return context.messages.filter(msg => msg.sender === sender);
    },
    
    // Пока ждём ответ сервера после отправки сообщения (не по current_step — иначе «печатает» зависает на triage_completed и т.п.)
    isAgentProcessing: (): boolean => context.awaitingAssistantResponse,
    
    // Get current agent progress
    getAgentProgress: (): number => {
      return context.agentStatus?.overallProgress || 0;
    },
    
    // Get current step name
    getCurrentStep: (): string => {
      return context.agentStatus?.currentStep || 'Unknown';
    }
  };

  return {
    ...context,
    ...utilities
  };
};

/**
 * Hook for accessing only WebSocket connection status
 * Useful for components that only need to know connection state
 */
export const useWebSocketConnection = () => {
  const { isConnected, sessionId, error, connect, disconnect } = useWebSocketContext();
  
  return {
    isConnected,
    sessionId,
    error,
    connect,
    disconnect,
    isConnecting: !isConnected && !error,
    hasError: !!error
  };
};

/**
 * Hook for accessing only chat messages
 * Useful for components that only need to display messages
 */
export const useChatMessages = () => {
  const { messages, sendMessage, clearMessages } = useWebSocketContext();
  
  return {
    messages,
    sendMessage,
    clearMessages,
    messageCount: messages.length,
    hasMessages: messages.length > 0,
    lastMessage: messages.length > 0 ? messages[messages.length - 1] : null
  };
};

/**
 * Hook for accessing only agent status
 * Useful for components that only need to display agent status
 */
export const useAgentStatus = () => {
  const { agentStatus, awaitingAssistantResponse } = useWebSocketContext();
  
  return {
    agentStatus,
    isProcessing: () => awaitingAssistantResponse,
    progress: agentStatus?.overallProgress || 0,
    currentStep: agentStatus?.currentStep || 'Unknown',
    agents: agentStatus?.agents || []
  };
};

// Export the main hook as default for convenience
export default useWebSocket;