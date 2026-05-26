import { useState, useEffect, useCallback } from 'react';
import apiService from '../services/api';
import type { Specialist, SessionHistory } from '../types';

interface UseApiState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
}

interface UseApiReturn<T> extends UseApiState<T> {
  execute: (...args: any[]) => Promise<T | null>;
  reset: () => void;
}

// Generic hook for API calls
export const useApi = <T>(
  apiFunction: (...args: any[]) => Promise<T>,
  immediate = false
): UseApiReturn<T> => {
  const [state, setState] = useState<UseApiState<T>>({
    data: null,
    loading: false,
    error: null,
  });

  const execute = useCallback(
    async (...args: any[]): Promise<T | null> => {
      setState(prev => ({ ...prev, loading: true, error: null }));
      
      try {
        const result = await apiFunction(...args);
        setState({ data: result, loading: false, error: null });
        return result;
      } catch (err) {
        const errorMessage = err instanceof Error ? err.message : 'An error occurred';
        setState(prev => ({ ...prev, loading: false, error: errorMessage }));
        return null;
      }
    },
    [apiFunction]
  );

  const reset = useCallback(() => {
    setState({ data: null, loading: false, error: null });
  }, []);

  useEffect(() => {
    if (immediate) {
      execute();
    }
  }, [immediate, execute]);

  return { ...state, execute, reset };
};

// Specific hooks for common API operations
export const usePatient = (patientId?: string) => {
  return useApi(apiService.getPatient.bind(apiService), !!patientId);
};

export const useCreatePatient = () => {
  return useApi(apiService.createPatient.bind(apiService));
};

export const useChatSession = (sessionId?: string) => {
  return useApi(apiService.getChatSession.bind(apiService), !!sessionId);
};

export const useCreateChatSession = () => {
  return useApi(apiService.createChatSession.bind(apiService));
};

export const useSendMessage = () => {
  return useApi(apiService.sendMessage.bind(apiService));
};

export const useRecommendations = (sessionId?: string) => {
  return useApi(apiService.getRecommendations.bind(apiService), !!sessionId);
};

export const useSessionHistory = (limit: number = 50, offset: number = 0) => {
  const [state, setState] = useState<UseApiState<{ sessions: SessionHistory[], total: number, limit: number, offset: number }>>({
    data: null,
    loading: false,
    error: null,
  });

  const fetchSessions = useCallback(async () => {
    setState(prev => ({ ...prev, loading: true, error: null }));
    
    try {
      const result = await apiService.getSessionsList(limit, offset);
      // Map API response to SessionHistory. API does not provide patient_name or first message.
      const sessions: SessionHistory[] = result.data.sessions.map((s: any) => ({
        id: s.session_id,
        patientName: 'Anonymous',
        date: s.created_at,
        status: s.status as 'completed' | 'paused' | 'active',
        summary: `Сессия от ${new Date(s.created_at).toLocaleDateString('ru-RU')}`,
        recommendationsCount: s.recommendations_count || 0,
      }));
      
      setState({ 
        data: { 
          sessions, 
          total: result.data.total, 
          limit: result.data.limit, 
          offset: result.data.offset 
        }, 
        loading: false, 
        error: null 
      });
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to fetch sessions';
      setState(prev => ({ ...prev, loading: false, error: errorMessage }));
    }
  }, [limit, offset]);

  useEffect(() => {
    fetchSessions();
  }, [fetchSessions]);

  return { ...state, refetch: fetchSessions };
};

export const useSpecialists = (filters?: {
  specialty?: string;
  location?: string;
  availability?: string;
}) => {
  const [state, setState] = useState<UseApiState<Specialist[]>>({
    data: null,
    loading: false,
    error: null,
  });

  const fetchSpecialists = useCallback(async () => {
    setState(prev => ({ ...prev, loading: true, error: null }));
    
    try {
      const result = await apiService.getSpecialists(filters);
      setState({ data: result.data, loading: false, error: null });
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to fetch specialists';
      setState(prev => ({ ...prev, loading: false, error: errorMessage }));
    }
  }, [filters]);

  useEffect(() => {
    fetchSpecialists();
  }, [fetchSpecialists]);

  return {
    ...state,
    refetch: fetchSpecialists,
  };
};

export const useChatHistory = (sessionId?: string) => {
  return useApi(apiService.getChatHistory.bind(apiService), !!sessionId);
};

export const usePdfExport = () => {
  return useApi(apiService.exportToPDF.bind(apiService));
};

export const useHealthCheck = () => {
  return useApi(apiService.healthCheck.bind(apiService), true);
};