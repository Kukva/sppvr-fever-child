import React, { useState, useCallback, useEffect, useRef } from 'react';
import { PaperAirplaneIcon, MicrophoneIcon } from '@heroicons/react/24/outline';
import { MicrophoneIcon as MicrophoneIconSolid } from '@heroicons/react/24/solid';
import toast from 'react-hot-toast';
import { getMicErrorMessage, logMicDiagnostic } from '../utils/micDiagnostics';
import { Header } from '../components/Header';
import {
  PatientDataForm,
  type PatientData,
} from '../components/PatientDataForm';
import ChatInterface from '../components/ChatInterface';
import { PageDoodleBackground } from '../components/PageDoodleBackground';
import { useWebSocket } from '../hooks/useWebSocketContext';
import { useCreateChatSession } from '../hooks/useApi';
import type { Patient, ChatSession } from '../types';

/** Парсит строку возраста "3 года", "6 мес" в годы и месяцы */
function parseAge(ageStr: string): { years: number; months: number } {
  const s = (ageStr || '').trim().toLowerCase();
  if (!s) return { years: 1, months: 0 };
  const numMatch = s.match(/(\d+)/);
  const num = numMatch ? parseInt(numMatch[1], 10) : 1;
  if (/\b(мес|месяц|месяцев)\b/.test(s))
    return { years: 0, months: Math.min(num, 11) };
  return { years: Math.min(num, 18), months: 0 };
}

function formatPatientData(data: PatientData): string {
  const parts: string[] = [];
  if (data.gender === 'boy') parts.push('Мальчик');
  if (data.gender === 'girl') parts.push('Девочка');
  if (data.age) parts.push(data.age);
  if (data.temperature) parts.push(`температура ${data.temperature}°C`);
  if (data.symptoms.length > 0) parts.push(data.symptoms.join(', '));
  if (data.comments?.trim()) parts.push(data.comments.trim());
  return parts.join(', ');
}

/** Для бэкенда: из PatientData в формат сессии (age_years, age_months) и хранение */
function patientDataToStorage(data: PatientData) {
  const { years, months } = parseAge(data.age);
  return {
    name: 'Пациент',
    gender: data.gender === 'girl' ? 'female' : 'male',
    age: years,
    ageMonths: months,
    ageDays: undefined,
    weight: 15,
    height: 85,
    temperature: parseFloat(data.temperature) || 38,
    symptoms: data.symptoms.length ? data.symptoms : ['Лихорадка'],
    additionalInfo: data.comments?.trim() || '',
  };
}

export const HomePage: React.FC = () => {
  const [query, setQuery] = useState('');
  const [patientData, setPatientData] = useState<PatientData>({
    gender: null,
    age: '',
    temperature: '',
    symptoms: [],
    comments: '',
  });

  const [chatSession, setChatSession] = useState<ChatSession | null>(null);
  const [patient, setPatient] = useState<Patient | null>(null);
  const [pendingInitialMessage, setPendingInitialMessage] = useState<
    string | null
  >(null);
  const hasSentInitialMessage = useRef(false);
  const [isListening, setIsListening] = useState(false);
  const recognitionRef = useRef<unknown>(null);

  const SpeechRecognitionAPI =
    typeof window !== 'undefined' &&
    ((window as unknown as { SpeechRecognition?: unknown }).SpeechRecognition ??
      (window as unknown as { webkitSpeechRecognition?: unknown })
        .webkitSpeechRecognition);
  // Браузер даёт доступ к микрофону только в безопасном контексте (HTTPS или localhost)
  const canUseMicrophone =
    typeof window !== 'undefined' &&
    (window as unknown as { isSecureContext?: boolean }).isSecureContext !==
      false &&
    !!SpeechRecognitionAPI;

  const createChatSessionApi = useCreateChatSession();
  const {
    isConnected,
    sessionId,
    messages,
    sendMessage: wsSendMessage,
    connect,
    disconnect,
    clearMessages,
    isAgentProcessing,
    error: wsError,
  } = useWebSocket();

  const handleSubmit = useCallback(() => {
    const patientInfo = formatPatientData(patientData);
    const fullQuery = patientInfo
      ? `${patientInfo}. ${query}`.trim()
      : query.trim();

    if (!fullQuery) return;

    if (chatSession && patient) {
      wsSendMessage(fullQuery);
      setQuery('');
      return;
    }

    const storage = patientDataToStorage(patientData);
    const patientObj: Patient = {
      id: `patient_${Date.now()}`,
      name: storage.name,
      gender: storage.gender as 'male' | 'female',
      age: storage.age,
      ageMonths: storage.ageMonths,
      weight: storage.weight,
      height: storage.height,
      temperature: storage.temperature,
      symptoms: storage.symptoms,
      additionalInfo: storage.additionalInfo,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    };

    createChatSessionApi
      .execute({
        age_years: storage.age,
        age_months: storage.ageMonths ?? 0,
      })
      .then((result: any) => {
        const sid = result?.data?.session_id ?? result?.session_id;
        if (!sid) {
          toast.error('Не удалось создать сессию');
          return;
        }
        const session: ChatSession = {
          id: sid,
          patientId: patientObj.id,
          messages: [],
          status: 'active',
          createdAt:
            (result?.data?.created_at ?? result?.created_at) ||
            new Date().toISOString(),
          updatedAt:
            (result?.data?.created_at ?? result?.created_at) ||
            new Date().toISOString(),
        };
        setChatSession(session);
        setPatient(patientObj);
        setPendingInitialMessage(fullQuery);
        setQuery('');
        clearMessages();
        connect(session.id);
      })
      .catch((err: any) => {
        const msg =
          err?.response?.data?.detail ||
          err?.message ||
          'Ошибка создания сессии';
        toast.error(msg);
      });
  }, [
    query,
    patientData,
    chatSession,
    patient,
    createChatSessionApi,
    wsSendMessage,
    connect,
    clearMessages,
  ]);

  useEffect(() => {
    if (
      !isConnected ||
      !sessionId ||
      !chatSession ||
      hasSentInitialMessage.current
    )
      return;
    if (!pendingInitialMessage?.trim()) return;

    hasSentInitialMessage.current = true;
    setPendingInitialMessage(null);
    toast.success('Соединение установлено');
    wsSendMessage(pendingInitialMessage.trim());
  }, [
    isConnected,
    sessionId,
    chatSession,
    pendingInitialMessage,
    wsSendMessage,
  ]);

  useEffect(() => {
    if (wsError) toast.error(`Ошибка: ${wsError}`);
  }, [wsError]);

  useEffect(() => {
    if (!chatSession?.id) return;
    return () => {
      disconnect();
    };
  }, [chatSession?.id, disconnect]);

  // Диагностика микрофона: при ?diagnose=mic в URL вывести в консоль
  useEffect(() => {
    if (
      typeof window !== 'undefined' &&
      new URLSearchParams(window.location.search).get('diagnose') === 'mic'
    ) {
      logMicDiagnostic();
    }
  }, []);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const toggleVoiceInput = useCallback(() => {
    if (!SpeechRecognitionAPI) return;
    const recognition = recognitionRef.current as {
      start: () => void;
      stop: () => void;
      abort: () => void;
    } | null;
    if (isListening && recognition) {
      try {
        recognition.stop();
      } catch {
        recognition.abort?.();
      }
      setIsListening(false);
      return;
    }
    try {
      const Rec = SpeechRecognitionAPI as new () => {
        start: () => void;
        stop: () => void;
        abort: () => void;
        onresult: (e: {
          resultIndex?: number;
          results: {
            length: number;
            [i: number]: {
              [j: number]: { transcript?: string };
              transcript?: string;
            };
          };
        }) => void;
        onerror: () => void;
        onend: () => void;
        continuous: boolean;
        lang: string;
        interimResults: boolean;
      };
      const r = new Rec();
      r.continuous = true;
      r.lang = 'ru-RU';
      r.interimResults = false;
      r.onresult = (e: {
        resultIndex?: number;
        results: {
          length: number;
          [i: number]: {
            [j: number]: { transcript?: string };
            transcript?: string;
          };
        };
      }) => {
        const resultIndex = e.resultIndex ?? 0;
        const parts: string[] = [];
        for (let i = resultIndex; i < e.results.length; i++) {
          const result = e.results[i];
          const first = result?.[0] ?? result;
          const t =
            (first as { transcript?: string } | undefined)?.transcript ?? '';
          if (t) parts.push(t);
        }
        const transcript = parts.join(' ').trim();
        if (transcript)
          setQuery((prev) =>
            (prev ? `${prev} ${transcript}` : transcript).trim().slice(0, 1000)
          );
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

  useEffect(() => {
    return () => {
      const r = recognitionRef.current as {
        stop?: () => void;
        abort?: () => void;
      } | null;
      if (r)
        try {
          r.stop?.();
        } catch {
          r.abort?.();
        }
    };
  }, []);

  const handleSendMessage = useCallback(
    (message: string) => {
      if (!chatSession) return;
      if (isConnected) wsSendMessage(message);
      else toast.error('Нет соединения с сервером');
    },
    [chatSession, isConnected, wsSendMessage]
  );

  const connectionStatus = isConnected
    ? 'connected'
    : sessionId
      ? 'connecting'
      : 'disconnected';

  const hasData = query.trim() !== '' || formatPatientData(patientData) !== '';

  if (chatSession && patient) {
    return (
      <div className="min-h-screen bg-gradient-to-b from-[#F0F4F8] to-white flex flex-col relative overflow-hidden">
        <PageDoodleBackground />
        <Header />
        <main className="flex-1 flex flex-col px-4 sm:px-6 py-6 relative z-10 max-w-4xl mx-auto w-full">
          <div className="mb-4 text-center sm:text-left">
            <h1 className="text-lg sm:text-xl font-medium text-figma-ink">
              ИИ-ассистент для оценки лихорадки у детей
            </h1>
            <p className="text-sm text-gray-600 mt-1">
              Диалог продолжается в этом окне. Уточните клиническую картину или
              задайте вопрос по тактике.
            </p>
          </div>
          <div className="relative flex-1 min-h-0 rounded-[30px] border border-figma-accentBorder shadow-figma-card overflow-hidden flex flex-col">
            <div className="absolute inset-0 rounded-[30px] backdrop-blur-[8px] bg-gradient-to-br from-figma-gradFrom to-figma-gradTo pointer-events-none" />
            <div className="absolute inset-0 rounded-[30px] shadow-figma-card-inset pointer-events-none" />
            <div className="relative z-10 flex-1 min-h-0 flex flex-col bg-white/25">
              <ChatInterface
                sessionId={chatSession.id}
                messages={messages}
                onSendMessage={handleSendMessage}
                isLoading={isAgentProcessing()}
                connectionStatus={connectionStatus}
                connectionQuality={isConnected ? 'good' : 'disconnected'}
              />
            </div>
          </div>
          <p className="text-sm text-figma-hint mt-3 text-center sm:text-left">
            Нажмите Enter для отправки. Срочные состояния оценивайте по
            клиническим протоколам и показаниям к госпитализации.
          </p>
        </main>
        <footer className="py-4 border-t border-gray-200/80 bg-white/60 backdrop-blur-sm relative z-10">
          <p className="text-xs text-gray-500 text-center max-w-3xl mx-auto px-4">
            Вспомогательный инструмент. Не заменяет очный приём и осмотр врача.
          </p>
        </footer>
      </div>
    );
  }

  const figmaActionBtnBase =
    'relative flex h-[60px] w-[60px] shrink-0 items-center justify-center rounded-[10px] backdrop-blur-[8px] transition-opacity';
  const micBtnIdle = `${figmaActionBtnBase} bg-figma-actionGlass shadow-figma-action-inset text-white hover:opacity-90`;
  const sendBtnIdle = `${figmaActionBtnBase} bg-[#2A9FFF] text-white shadow-md hover:bg-[#2290e6]`;
  const figmaActionBtnDisabled = `${figmaActionBtnBase} cursor-not-allowed bg-gray-100/80 text-gray-400 opacity-60 shadow-none`;

  return (
    <div className="min-h-screen bg-gradient-to-b from-[#F0F4F8] to-white flex flex-col relative overflow-hidden">
      <PageDoodleBackground />
      <Header />

      <main className="relative z-10 flex flex-1 items-center justify-center px-4 sm:px-6 py-10 sm:py-16">
        <div className="relative w-full max-w-[994px]">
          <div className="text-center mb-8 sm:mb-10 px-1">
            <h1 className="text-2xl sm:text-3xl md:text-4xl text-figma-ink font-semibold leading-tight mb-3 max-w-3xl mx-auto">
              — Марина Ивановна, подскажите, пожалуйста!
            </h1>
            <p className="text-lg sm:text-xl text-figma-ink font-semibold mb-2">
              ИИ-ассистент для оценки лихорадки у детей
            </p>
            <p className="text-base sm:text-lg text-gray-600 max-w-xl mx-auto">
              Опишите клиническую ситуацию — получите структурированную
              поддержку в оценке и маршрутизации
            </p>
          </div>

          <div className="relative rounded-[30px] border border-figma-accentBorder shadow-figma-card p-5 sm:p-6 md:p-8">
            <div className="absolute inset-0 rounded-[30px] backdrop-blur-[8px] bg-gradient-to-br from-figma-gradFrom to-figma-gradTo pointer-events-none" />
            <div className="absolute inset-0 rounded-[30px] shadow-figma-card-inset pointer-events-none" />
            <div className="relative z-10 space-y-4">
              <PatientDataForm variant="figma" onDataChange={setPatientData} />

              <div className="relative">
                {isListening && (
                  <div className="absolute top-3 left-3 right-3 flex items-center gap-2 bg-red-50/95 px-3 py-2 rounded-[14px] border border-red-200 z-10">
                    <div className="w-3 h-3 bg-red-500 rounded-full animate-pulse flex-shrink-0" />
                    <span className="text-sm text-red-600 font-medium">
                      Идёт распознавание речи…
                    </span>
                  </div>
                )}
                <textarea
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="Например: ребенку 3 года, температура 38.5, капризничает, что делать?"
                  className={`w-full min-h-[160px] sm:min-h-[181px] px-4 py-4 pr-[148px] pb-[88px] border-2 border-figma-accentSoft rounded-[20px] resize-none focus:outline-none focus:border-figma-accent bg-white text-base text-figma-ink placeholder:text-figma-inkMuted transition-colors ${
                    isListening ? 'pt-12' : ''
                  }`}
                  maxLength={1000}
                  disabled={isListening}
                />
                <div className="absolute bottom-4 right-4 flex items-center gap-3">
                  <button
                    type="button"
                    onClick={canUseMicrophone ? toggleVoiceInput : undefined}
                    disabled={!canUseMicrophone}
                    className={
                      !canUseMicrophone
                        ? figmaActionBtnDisabled
                        : isListening
                          ? `${figmaActionBtnBase} bg-red-500 text-white shadow-none hover:bg-red-600`
                          : micBtnIdle
                    }
                    title={
                      !canUseMicrophone
                        ? SpeechRecognitionAPI
                          ? 'Микрофон доступен только по HTTPS или с localhost'
                          : 'Голосовой ввод недоступен в этом браузере'
                        : isListening
                          ? 'Остановить запись'
                          : 'Голосовой ввод'
                    }
                    aria-label={
                      isListening ? 'Остановить запись' : 'Голосовой ввод'
                    }
                  >
                    {isListening ? (
                      <MicrophoneIconSolid className="w-6 h-6 text-white" />
                    ) : (
                      <MicrophoneIcon
                        className={`w-6 h-6 ${!canUseMicrophone ? 'text-gray-400' : 'text-white'}`}
                      />
                    )}
                  </button>
                  <button
                    type="button"
                    onClick={handleSubmit}
                    className={`${sendBtnIdle} text-white disabled:opacity-40 disabled:cursor-not-allowed disabled:bg-gray-200 disabled:text-gray-400 disabled:shadow-none`}
                    disabled={!hasData || isListening}
                    aria-label="Отправить"
                  >
                    <PaperAirplaneIcon className="w-6 h-6 shrink-0" />
                  </button>
                </div>
              </div>

              <p className="text-sm text-figma-hint text-center sm:text-left px-1">
                Нажмите Enter для отправки. Срочные состояния оценивайте по
                клиническим протоколам и показаниям к госпитализации.
              </p>

              {hasData && (
                <p className="text-xs text-gray-600 border-t border-[rgba(29,102,162,0.25)] pt-4">
                  Будет отправлено: {formatPatientData(patientData)}
                  {query.trim() ? `. ${query.trim()}` : ''}
                </p>
              )}
            </div>
          </div>
        </div>
      </main>

      <footer className="py-5 sm:py-6 border-t border-gray-200/80 bg-white/60 backdrop-blur-sm relative z-10">
        <p className="text-xs text-gray-500 text-center max-w-3xl mx-auto px-4">
          Вспомогательный инструмент. Не заменяет очный приём и осмотр врача.
        </p>
      </footer>
    </div>
  );
};

export default HomePage;
