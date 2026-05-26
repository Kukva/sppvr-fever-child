/**
 * Диагностика микрофона (Web Speech API) и понятные сообщения об ошибках.
 * На ВМ микрофон работает только по HTTPS; по HTTP браузер блокирует доступ.
 */

export interface MicDiagnostic {
  isSecureContext: boolean;
  hasSpeechRecognition: boolean;
  origin: string;
  protocol: string;
  recommendation: string;
}

/** Проверка поддержки и безопасного контекста */
export function getMicDiagnostic(): MicDiagnostic {
  if (typeof window === 'undefined') {
    return {
      isSecureContext: false,
      hasSpeechRecognition: false,
      origin: '',
      protocol: '',
      recommendation: 'Запустите в браузере',
    };
  }
  const win = window as unknown as {
    isSecureContext?: boolean;
    SpeechRecognition?: unknown;
    webkitSpeechRecognition?: unknown;
    location?: { origin: string; protocol: string };
  };
  const isSecureContext = win.isSecureContext !== false;
  const hasSpeechRecognition = !!(
    win.SpeechRecognition ?? win.webkitSpeechRecognition
  );
  const origin = win.location?.origin ?? '';
  const protocol = win.location?.protocol ?? '';

  let recommendation = '';
  if (!hasSpeechRecognition) {
    recommendation = 'Голосовой ввод недоступен в этом браузере (Chrome/Edge рекомендуется).';
  } else if (!isSecureContext) {
    recommendation =
      'Микрофон доступен только по HTTPS или с localhost. Откройте приложение по https://IP_ВМ (см. DEPLOY.md, раздел 8).';
  } else {
    recommendation = 'Микрофон должен работать. Если нет — проверьте разрешение в настройках браузера.';
  }

  return {
    isSecureContext,
    hasSpeechRecognition,
    origin,
    protocol,
    recommendation,
  };
}

/** Логировать диагностику в консоль (для отладки на ВМ) */
export function logMicDiagnostic(): void {
  const d = getMicDiagnostic();
  console.log('[Микрофон] Диагностика:', {
    secureContext: d.isSecureContext,
    speechRecognition: d.hasSpeechRecognition,
    origin: d.origin,
    protocol: d.protocol,
    recommendation: d.recommendation,
  });
}

/** Коды ошибок SpeechRecognition: https://developer.mozilla.org/en-US/docs/Web/API/SpeechRecognitionErrorEvent/error */
const ERROR_MESSAGES: Record<string, string> = {
  'not-allowed':
    'Доступ к микрофону запрещён. Разрешите доступ для этого сайта в настройках браузера (иконка замка/ссылки в адресной строке).',
  'service-not-allowed':
    'Микрофон доступен только по HTTPS или с localhost. На ВМ откройте приложение по https://IP (см. инструкцию в DEPLOY.md).',
  'no-speech': 'Речь не распознана. Попробуйте ещё раз.',
  'audio-capture': 'Микрофон не найден или занят другим приложением.',
  'network': 'Проверьте подключение к интернету (распознавание может использовать облачный сервис).',
  'aborted': 'Запись остановлена.',
  'language-not-supported': 'Язык ru-RU не поддерживается в этом браузере.',
};

/**
 * Человекочитаемое сообщение по коду ошибки SpeechRecognition.
 */
export function getMicErrorMessage(errorCode: string): string {
  return (
    ERROR_MESSAGES[errorCode] ??
    `Ошибка микрофона: ${errorCode}. Откройте по HTTPS (https://IP_ВМ) или с localhost.`
  );
}
