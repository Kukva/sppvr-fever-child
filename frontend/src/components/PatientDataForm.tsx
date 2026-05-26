import React, { useState, useEffect } from 'react';
import { ChevronDownIcon, ChevronUpIcon } from '@heroicons/react/24/outline';

export interface PatientData {
  gender: 'boy' | 'girl' | null;
  age: string;
  temperature: string;
  symptoms: string[];
  comments: string;
}

const COMMON_SYMPTOMS = [
  'Лихорадка',
  'Головная боль',
  'Боль в горле',
  'Кашель',
  'Насморк',
  'Тошнота',
  'Рвота',
  'Диарея',
  'Боль в животе',
  'Сыпь',
  'Усталость',
  'Потеря аппетита',
  'Затрудненное дыхание',
  'Боль в ушах',
  'Озноб',
  'Боль в мышцах',
  'Светобоязнь',
  'Увеличение лимфоузлов',
  'Боль при глотании',
  'Хрипы',
  'Одышка',
  'Цианоз',
  'Судороги',
  'Сонливость',
  'Беспокойство',
  'Плач',
  'Отказ от питья',
  'Сухость во рту',
  'Редкое мочеиспускание',
  'Боль при мочеиспускании',
];

const AGE_QUICK_OPTIONS = ['1 год', '3 года', '6 лет', '10 лет', '15 лет'];
const TEMP_QUICK_OPTIONS = ['37', '37.5', '38', '38.5', '39', '39.5', '40'];

interface PatientDataFormProps {
  onDataChange: (data: PatientData) => void;
  /** Макет Figma: верхняя строка-аккордеон внутри стеклянной карточки */
  variant?: 'default' | 'figma';
}

export const PatientDataForm: React.FC<PatientDataFormProps> = ({
  onDataChange,
  variant = 'default',
}) => {
  const [open, setOpen] = useState(false);
  const [gender, setGender] = useState<PatientData['gender']>(null);
  const [age, setAge] = useState('');
  const [temperature, setTemperature] = useState('');
  const [symptoms, setSymptoms] = useState<string[]>([]);
  const [comments, setComments] = useState('');

  useEffect(() => {
    onDataChange({ gender, age, temperature, symptoms, comments });
  }, [gender, age, temperature, symptoms, comments]);

  const handleGender = (g: 'boy' | 'girl') => {
    setGender((prev) => (prev === g ? null : g));
  };

  const toggleSymptom = (s: string) => {
    setSymptoms((prev) =>
      prev.includes(s) ? prev.filter((x) => x !== s) : [...prev, s]
    );
  };

  const setTempFromInput = (raw: string) => {
    const v = raw.replace(/[^\d.,]/g, '').replace(',', '.');
    if (
      v === '' ||
      (parseFloat(v) >= 35 && parseFloat(v) <= 42) ||
      v.slice(-1) === '.'
    ) {
      setTemperature(v);
    }
  };

  const accentOn =
    variant === 'figma'
      ? 'bg-figma-accent text-white border-figma-accent'
      : 'bg-[#2A9FFF] text-white border-[#2A9FFF]';
  const accentOff =
    variant === 'figma'
      ? 'bg-white/80 text-gray-900 border-figma-accentSoft hover:border-figma-accent'
      : 'bg-white text-gray-900 border-gray-300 hover:border-[#2A9FFF]';

  const summaryParts = [
    gender === 'boy' ? 'Мальчик' : gender === 'girl' ? 'Девочка' : null,
    age || null,
    temperature ? `${temperature}°C` : null,
    symptoms.length ? symptoms.join(', ') : null,
    comments?.trim() || null,
  ].filter(Boolean);

  const triggerClass =
    variant === 'figma'
      ? 'w-full flex items-center justify-between gap-3 min-h-[49px] px-4 rounded-[20px] border border-figma-accentSoft bg-transparent text-left text-base text-black hover:bg-white/25 transition-colors'
      : 'flex items-center gap-2 text-sm text-gray-700 hover:text-black transition-colors text-left';

  const panelClass =
    variant === 'figma'
      ? 'mt-3 p-4 sm:p-6 rounded-[20px] border border-figma-accentSoft bg-white/45 backdrop-blur-sm space-y-6'
      : 'mt-4 p-6 bg-gray-50 rounded-xl space-y-6 border border-gray-200';

  return (
    <div className="w-full">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className={triggerClass}
      >
        <span className={variant === 'figma' ? 'font-normal pr-2' : ''}>
          Указать данные пациента (пол, возраст, температура, симптомы)
        </span>
        {variant === 'figma' ? (
          open ? (
            <ChevronUpIcon className="w-5 h-5 text-figma-accent shrink-0" />
          ) : (
            <ChevronDownIcon className="w-5 h-5 text-figma-accent shrink-0" />
          )
        ) : open ? (
          <ChevronUpIcon className="w-4 h-4 flex-shrink-0" />
        ) : (
          <ChevronDownIcon className="w-4 h-4 flex-shrink-0" />
        )}
      </button>

      {open && (
        <div className={panelClass}>
          <p className="text-xs text-gray-600">
            Напишите в поле выше или выберите варианты ниже — данные попадут в
            первое сообщение к ассистенту.
          </p>

          <div>
            <label className="block text-sm font-medium text-gray-900 mb-3">
              Пол
            </label>
            <div className="flex gap-3">
              <button
                type="button"
                onClick={() => handleGender('boy')}
                className={`px-5 py-2.5 rounded-lg border-2 transition-all font-medium text-sm ${
                  gender === 'boy' ? accentOn : accentOff
                }`}
              >
                Мальчик
              </button>
              <button
                type="button"
                onClick={() => handleGender('girl')}
                className={`px-5 py-2.5 rounded-lg border-2 transition-all font-medium text-sm ${
                  gender === 'girl' ? accentOn : accentOff
                }`}
              >
                Девочка
              </button>
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-900 mb-3">
              Возраст (мес или лет)
            </label>
            <div className="flex flex-wrap gap-2 mb-3">
              {AGE_QUICK_OPTIONS.map((a) => (
                <button
                  key={a}
                  type="button"
                  onClick={() => setAge(a)}
                  className={`px-4 py-2 text-sm rounded-lg border-2 transition-all font-medium ${
                    age === a ? accentOn : accentOff
                  }`}
                >
                  {a}
                </button>
              ))}
            </div>
            <input
              type="text"
              placeholder="или введите возраст (например: 6 мес)"
              value={age}
              onChange={(e) => setAge(e.target.value)}
              className={`w-full px-4 py-2.5 border-2 rounded-lg focus:outline-none ${
                variant === 'figma'
                  ? 'border-figma-accentSoft focus:border-figma-accent bg-white/60'
                  : 'border-gray-300 focus:border-[#2A9FFF]'
              }`}
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-900 mb-3">
              Температура (°C)
            </label>
            <div className="flex flex-wrap gap-2 mb-3">
              {TEMP_QUICK_OPTIONS.map((t) => (
                <button
                  key={t}
                  type="button"
                  onClick={() => setTemperature(t)}
                  className={`px-4 py-2 text-sm rounded-lg border-2 transition-all font-medium ${
                    temperature === t ? accentOn : accentOff
                  }`}
                >
                  {t}
                </button>
              ))}
            </div>
            <input
              type="text"
              placeholder="или введите температуру"
              value={temperature}
              onChange={(e) => setTempFromInput(e.target.value)}
              className={`w-full px-4 py-2.5 border-2 rounded-lg focus:outline-none ${
                variant === 'figma'
                  ? 'border-figma-accentSoft focus:border-figma-accent bg-white/60'
                  : 'border-gray-300 focus:border-[#2A9FFF]'
              }`}
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-900 mb-3">
              Симптомы
            </label>
            <div className="flex flex-wrap gap-2 max-h-48 overflow-y-auto pr-1">
              {COMMON_SYMPTOMS.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => toggleSymptom(s)}
                  className={`px-4 py-2 text-sm rounded-lg border-2 transition-all font-medium ${
                    symptoms.includes(s) ? accentOn : accentOff
                  }`}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-900 mb-3">
              Комментарии
            </label>
            <textarea
              placeholder="Дополнительная информация, свои формулировки симптомов..."
              value={comments}
              onChange={(e) => setComments(e.target.value)}
              rows={2}
              className={`w-full px-4 py-2.5 border-2 rounded-lg text-sm resize-none focus:outline-none ${
                variant === 'figma'
                  ? 'border-figma-accentSoft focus:border-figma-accent bg-white/60'
                  : 'border-gray-300 focus:border-[#2A9FFF]'
              }`}
            />
          </div>

          {summaryParts.length > 0 && (
            <div
              className={`pt-4 border-t ${variant === 'figma' ? 'border-figma-accentSoft' : 'border-gray-300'}`}
            >
              <p className="text-sm text-gray-700">
                <strong className="text-gray-900">Выбрано:</strong>{' '}
                {summaryParts.join(', ')}
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
