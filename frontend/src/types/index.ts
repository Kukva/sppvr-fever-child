// Базовые типы для API
export interface ApiResponse<T> {
  data: T;
  message?: string;
  status: number;
}

// Типы для пациента
export interface Patient {
  id: string;
  name: string;
  gender?: 'male' | 'female';
  age: number;
  ageMonths?: number;
  ageDays?: number;
  weight: number;
  height: number;
  temperature: number;
  symptoms: string[];
  additionalInfo?: string;
  createdAt: string;
  updatedAt: string;
}

export interface PatientForm {
  name: string;
  gender?: 'male' | 'female';
  age: string;
  ageUnit: 'years' | 'months' | 'days';
  weight: string;
  height: string;
  temperature: string;
  symptoms: string[];
  additionalInfo?: string;
}

// Типы для чата
export interface ChatMessage {
  id: string;
  content: string;
  sender: 'user' | 'assistant';
  timestamp: string;
  type?: 'text' | 'recommendation' | 'specialist';
  /** Ссылки на КР и источники, пришедшие с этим ответом (WebSocket response) */
  clinicalSources?: ClinicalSource[];
}

export interface ChatSession {
  id: string;
  patientId: string;
  messages: ChatMessage[];
  status: 'active' | 'completed' | 'paused';
  createdAt: string;
  updatedAt: string;
}

// Типы для агентов
export interface Agent {
  id: string;
  name: string;
  type: 'triage' | 'specialist' | 'coordinator';
  status: 'idle' | 'processing' | 'completed' | 'error';
  progress: number;
  currentTask?: string;
  result?: any;
}

export interface AgentStatus {
  agents: Agent[];
  overallProgress: number;
  currentStep: string;
}

// Типы для диагнозов
export interface Diagnosis {
  diagnosis: string;
  confidence: 'high' | 'medium' | 'low';
  reasoning: string;
  clinical_recommendation_url: string;
  required_tests: string[];
}

// Типы для рекомендаций
export interface Recommendation {
  id: string;
  title: string;
  description: string;
  priority: 'low' | 'medium' | 'high' | 'urgent';
  category: 'medication' | 'observation' | 'emergency' | 'consultation';
  agentId: string;
  timestamp: string;
  possible_diagnoses?: Diagnosis[];
}

// Типы для специалистов
export interface Specialist {
  id: string;
  name: string;
  specialty: string;
  experience: string;
  rating: number;
  availability: 'available' | 'busy' | 'offline';
  location: string;
  contactInfo: {
    phone?: string;
    email?: string;
    address?: string;
  };
}

// Логика работы агентов (объяснимость)
export interface AgentWorkflowStep {
  step: number;
  agent_key: string;
  title: string;
  /** Краткое описание роли агента (что делает этот шаг) */
  role?: string;
  reasoning: string;
  confidence?: number;
  execution_time_ms?: number;
}

// Шаг прогресса агента (real-time во время обработки)
export interface AgentProgressStep {
  agent_key: string;
  title: string;
  description: string;
  status?: string;
}

// Ссылки на клинические рекомендации
export interface ClinicalSource {
  title: string;
  url: string;
  description: string;
  /** Раздел или абзац, на который ссылается рекомендация */
  section_or_paragraph?: string;
  /** Дословный фрагмент из КР для сверки с первоисточником */
  verbatim_excerpt?: string;
  /** Какое утверждение в выводе системы подкрепляет этот источник */
  supports_claim?: string;
}

// Типы для WebSocket событий
export interface WebSocketMessage {
  type: 'agent_status' | 'chat_message' | 'recommendation' | 'error' | 'session_update';
  payload: any;
  timestamp: string;
}

// Типы для PDF экспорта
export interface PDFExportData {
  patient: Patient;
  session: ChatSession;
  recommendations: Recommendation[];
  specialists: Specialist[];
  agentStatus: AgentStatus;
}

// Типы для уведомлений
export interface Notification {
  id: string;
  type: 'success' | 'error' | 'warning' | 'info';
  title: string;
  message: string;
  duration?: number;
  timestamp: string;
}

// Типы для истории сессий
export interface SessionHistory {
  id: string;
  patientName: string;
  date: string;
  status: 'completed' | 'paused' | 'active';
  summary: string;
  recommendationsCount: number;
}

// Типы для форм
export interface FormField {
  name: string;
  label: string;
  type: 'text' | 'number' | 'select' | 'textarea' | 'checkbox';
  required?: boolean;
  placeholder?: string;
  options?: { value: string; label: string }[];
  validation?: {
    min?: number;
    max?: number;
    pattern?: RegExp;
    message?: string;
  };
}

// Типы для конфигурации приложения
export interface AppConfig {
  apiBaseUrl: string;
  wsUrl: string;
  maxRetries: number;
  timeout: number;
  enableDebug: boolean;
}