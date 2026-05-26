import axios from 'axios';
import type { AxiosInstance, AxiosResponse } from 'axios';
import type {
  ApiResponse,
  Patient,
  ChatSession,
  ChatMessage,
  AgentStatus,
  Recommendation,
  Specialist,
  SessionHistory
} from '../types';

class ApiService {
  private api: AxiosInstance;
  private baseURL: string;

  constructor(baseURL: string = import.meta.env.VITE_API_BASE_URL || '') {
    // В production: если при сборке задан VITE_API_BASE_URL — используем его (деплой на ВМ);
    // иначе пустой baseURL (относительные пути через nginx proxy).
    // В development — полный URL бэкенда.
    const envUrl = (import.meta.env.VITE_API_BASE_URL || '').toString().trim();
    let finalBaseURL = '';
    if (import.meta.env.PROD) {
      finalBaseURL = envUrl || ''; // пустой = тот же origin, nginx проксирует /api/ на backend
    } else {
      finalBaseURL = baseURL || envUrl || 'http://localhost:8000';
    }
    this.baseURL = finalBaseURL;
    console.log('🔗 API Service initialized with baseURL:', this.baseURL || '(relative)');
    console.log('🔗 Environment VITE_API_BASE_URL:', envUrl || '(empty)');
    console.log('🔗 Production mode:', import.meta.env.PROD);
    this.api = axios.create({
      baseURL: finalBaseURL,
      timeout: 90000, // 90 с — создание сессии и первый ответ бэкенда могут быть долгими
      headers: {
        'Content-Type': 'application/json',
      },
    });

    this.setupInterceptors();
  }

  private setupInterceptors() {
    // Request interceptor
    this.api.interceptors.request.use(
      (config) => {
        // Add auth token if available
        const token = localStorage.getItem('auth_token');
        if (token) {
          config.headers.Authorization = `Bearer ${token}`;
        }
        
        if (import.meta.env.VITE_ENABLE_DEBUG === 'true') {
          console.log('API Request:', config);
        }
        
        return config;
      },
      (error) => {
        console.error('API Request Error:', error);
        return Promise.reject(error);
      }
    );

    // Response interceptor
    this.api.interceptors.response.use(
      (response: AxiosResponse) => {
        if (import.meta.env.VITE_ENABLE_DEBUG === 'true') {
          console.log('API Response:', response);
        }
        return response;
      },
      (error) => {
        console.error('API Response Error:', error);
        const status = error.response?.status;
        const reqUrl = (error as { config?: { url?: string } }).config?.url ?? '';
        // #region agent log
        {
          const hasResp = !!error.response;
          const hid = !hasResp ? 'H2' : status && [502, 503, 504].includes(status) ? 'H1' : 'H4';
          fetch('http://127.0.0.1:7242/ingest/a6d48fc0-72b0-4b37-8e7d-b68b0bd7fd73', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-Debug-Session-Id': '9fcf1d' },
            body: JSON.stringify({
              sessionId: '9fcf1d',
              location: 'api.ts:responseInterceptor',
              message: 'API response error',
              data: {
                hasResponse: hasResp,
                status: status ?? null,
                code: (error as { code?: string }).code,
                reqUrl,
                baseURL: this.baseURL || '(relative)',
              },
              timestamp: Date.now(),
              hypothesisId: hid,
              runId: 'vm-debug',
            }),
          }).catch(() => {});
        }
        // #endregion
        if (status === 502 || status === 503 || status === 504) {
          (error as any).userMessage = 'Сервис временно недоступен. Проверьте, что backend запущен (или попробуйте позже).';
        }
        if (status === 401) {
          localStorage.removeItem('auth_token');
          window.location.href = '/login';
        }
        return Promise.reject(error);
      }
    );
  }

  // Patient endpoints
  async createPatient(patientData: Omit<Patient, 'id' | 'createdAt' | 'updatedAt'>): Promise<ApiResponse<Patient>> {
    const response = await this.api.post('/api/patients', patientData);
    return response.data;
  }

  async getPatient(id: string): Promise<ApiResponse<Patient>> {
    const response = await this.api.get(`/api/patients/${id}`);
    return response.data;
  }

  async updatePatient(id: string, patientData: Partial<Patient>): Promise<ApiResponse<Patient>> {
    const response = await this.api.put(`/api/patients/${id}`, patientData);
    return response.data;
  }

  // Chat session endpoints
  async getSessionsList(limit: number = 50, offset: number = 0): Promise<ApiResponse<{ sessions: SessionHistory[], total: number, limit: number, offset: number }>> {
    const response = await this.api.get(`/api/v1/sessions?limit=${limit}&offset=${offset}`);
    return response.data;
  }

  async createChatSession(patientData: any): Promise<ApiResponse<ChatSession>> {
    const response = await this.api.post('/api/v1/sessions', {
      doctor_id: null,
      patient_initial_data: {
        age_years: patientData.age_years,
        age_months: patientData.age_months || 0
      }
    });
    // #region agent log
    {
      const d = response.data as { data?: { session_id?: string }; session_id?: string };
      const sid = d?.data?.session_id ?? d?.session_id;
      fetch('http://127.0.0.1:7242/ingest/a6d48fc0-72b0-4b37-8e7d-b68b0bd7fd73', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Debug-Session-Id': '9fcf1d' },
        body: JSON.stringify({
          sessionId: '9fcf1d',
          location: 'api.ts:createChatSession',
          message: 'createChatSession ok',
          data: { sessionId: sid ?? null, baseURL: this.baseURL || '(relative)' },
          timestamp: Date.now(),
          hypothesisId: 'H3',
          runId: 'vm-debug',
        }),
      }).catch(() => {});
    }
    // #endregion
    return response.data;
  }

  async getChatSession(sessionId: string): Promise<ApiResponse<ChatSession>> {
    const response = await this.api.get(`/api/v1/sessions/${sessionId}`);
    return response.data;
  }

  async sendMessage(sessionId: string, message: string): Promise<ApiResponse<ChatMessage>> {
    const response = await this.api.post('/api/v1/chat/message', {
      session_id: sessionId,
      content: message
    });
    return response.data;
  }

  async getChatHistory(sessionId: string): Promise<ApiResponse<SessionHistory[]>> {
    const response = await this.api.get(`/api/v1/sessions/${sessionId}/history`);
    return response.data;
  }

  // Agent endpoints - временно заглушки, так как эти эндпоинты не реализованы в бэкенде
  async getAgentStatus(sessionId: string): Promise<ApiResponse<AgentStatus>> {
    // Временно возвращаем пустой статус, так как эндпоинт не реализован
    return Promise.resolve({
      status: 'success',
      data: {
        agents: [],
        overallProgress: 0,
        currentStep: 'idle'
      }
    } as unknown as ApiResponse<AgentStatus>);
  }

  async startAgentProcessing(sessionId: string): Promise<ApiResponse<{ message: string }>> {
    // Временно заглушка, так как эндпоинт не реализован
    return Promise.resolve({
      status: 'success',
      data: { message: 'Processing started' }
    } as unknown as ApiResponse<{ message: string }>);
  }

  async pauseAgentProcessing(sessionId: string): Promise<ApiResponse<{ message: string }>> {
    // Временно заглушка, так как эндпоинт не реализован
    return Promise.resolve({
      status: 'success',
      data: { message: 'Processing paused' }
    } as unknown as ApiResponse<{ message: string }>);
  }

  // Recommendation endpoints
  async getRecommendations(sessionId: string): Promise<ApiResponse<Recommendation[]>> {
    const response = await this.api.get(`/api/v1/sessions/${sessionId}/recommendations`);
    return response.data;
  }

  async createRecommendation(sessionId: string, recommendation: Omit<Recommendation, 'id' | 'timestamp'>): Promise<ApiResponse<Recommendation>> {
    // Временно заглушка, так как эндпоинт не реализован
    return Promise.resolve({
      status: 'success',
      data: recommendation as Recommendation
    } as unknown as ApiResponse<Recommendation>);
  }

  // Specialist endpoints - временно заглушки
  async getSpecialists(filters?: {
    specialty?: string;
    location?: string;
    availability?: string;
  }): Promise<ApiResponse<Specialist[]>> {
    // Временно возвращаем пустой массив, так как эндпоинт не реализован
    return Promise.resolve({
      status: 'success',
      data: []
    } as unknown as ApiResponse<Specialist[]>);
  }

  async getSpecialist(id: string): Promise<ApiResponse<Specialist>> {
    // Временно заглушка, так как эндпоинт не реализован
    return Promise.reject(new Error('Specialist endpoint not implemented'));
  }

  // PDF export endpoint
  async exportToPDF(sessionId: string): Promise<ApiResponse<{ downloadUrl: string }>> {
    const response = await this.api.post(`/api/v1/export/pdf/${sessionId}`);
    return response.data;
  }

  // Health check
  async healthCheck(): Promise<ApiResponse<{ status: string; timestamp: string }>> {
    const response = await this.api.get('/health');
    return response.data;
  }

  // Utility methods
  getBaseURL(): string {
    return this.baseURL;
  }

  setAuthToken(token: string) {
    localStorage.setItem('auth_token', token);
  }

  removeAuthToken() {
    localStorage.removeItem('auth_token');
  }

  isAuthenticated(): boolean {
    return !!localStorage.getItem('auth_token');
  }
}

// Create singleton instance
const apiService = new ApiService();

export default apiService;