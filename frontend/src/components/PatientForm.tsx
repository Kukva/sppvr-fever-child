import React, { useState } from 'react';
import { useForm } from 'react-hook-form';
import { yupResolver } from '@hookform/resolvers/yup';
import * as yup from 'yup';
import type { PatientForm as PatientFormData } from '../types';

const patientSchema = yup.object().shape({
  name: yup
    .string()
    .required('Имя пациента обязательно')
    .min(2, 'Имя должно содержать минимум 2 символа')
    .max(50, 'Имя не должно превышать 50 символов'),
  gender: yup
    .string()
    .oneOf(['male', 'female'], 'Выберите пол')
    .optional(),
  age: yup
    .string()
    .required('Возраст обязателен')
    .matches(/^\d+$/, 'Возраст должен быть числом')
    .test('age-range', 'Возраст должен быть корректным', function(value) {
      const ageUnit = this.parent.ageUnit;
      const age = parseInt(value);
      
      if (ageUnit === 'years') {
        return age >= 0 && age <= 18;
      } else if (ageUnit === 'months') {
        return age >= 0 && age <= 216; // 18 лет * 12 месяцев
      } else if (ageUnit === 'days') {
        return age >= 0 && age <= 6570; // 18 лет * 365 дней
      }
      return false;
    }),
  ageUnit: yup
    .string()
    .oneOf(['years', 'months', 'days'], 'Выберите единицу измерения возраста')
    .required('Единица измерения возраста обязательна'),
  weight: yup
    .string()
    .required('Вес обязателен')
    .matches(/^\d+(\.\d{1})?$/, 'Вес должен быть числом с одним знаком после запятой')
    .test('weight-range', 'Вес должен быть от 1 до 100 кг', (value) => {
      const weight = parseFloat(value);
      return weight >= 1 && weight <= 100;
    }),
  height: yup
    .string()
    .required('Рост обязателен')
    .matches(/^\d+$/, 'Рост должен быть числом')
    .test('height-range', 'Рост должен быть от 30 до 200 см', (value) => {
      const height = parseInt(value);
      return height >= 30 && height <= 200;
    }),
  temperature: yup
    .string()
    .required('Температура обязательна')
    .matches(/^\d+(\.\d{1})?$/, 'Температура должна быть числом с одним знаком после запятой')
    .test('temp-range', 'Температура должна быть от 35 до 42°C', (value) => {
      const temp = parseFloat(value);
      return temp >= 35 && temp <= 42;
    }),
  symptoms: yup
    .array()
    .of(yup.string())
    .min(1, 'Выберите хотя бы один симптом')
    .required('Симптомы обязательны'),
  additionalInfo: yup
    .string()
    .max(500, 'Дополнительная информация не должна превышать 500 символов'),
});

interface PatientFormProps {
  onSubmit: (patient: PatientFormData) => void;
  initialData?: Partial<PatientFormData>;
  isLoading?: boolean;
}

const commonSymptoms = [
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
];

export const PatientFormComponent: React.FC<PatientFormProps> = ({
  onSubmit,
  initialData,
  isLoading = false,
}) => {
  const [selectedSymptoms, setSelectedSymptoms] = useState<string[]>(
    initialData?.symptoms || []
  );
  const [ageUnit, setAgeUnit] = useState<'years' | 'months' | 'days'>(
    initialData?.ageUnit || 'years'
  );

  const {
    register,
    handleSubmit,
    formState: { errors },
    setValue,
    watch,
  } = useForm<PatientFormData>({
    resolver: yupResolver(patientSchema) as any,
    defaultValues: {
      ...initialData,
      ageUnit: initialData?.ageUnit || 'years',
    },
  });

  const currentAgeUnit = watch('ageUnit') || ageUnit;

  const handleSymptomToggle = (symptom: string) => {
    const newSymptoms = selectedSymptoms.includes(symptom)
      ? selectedSymptoms.filter(s => s !== symptom)
      : [...selectedSymptoms, symptom];
    
    setSelectedSymptoms(newSymptoms);
    setValue('symptoms', newSymptoms);
  };

  const onFormSubmit = (data: PatientFormData) => {
    onSubmit(data);
  };

  return (
    <div className="card max-w-2xl mx-auto">
      <div className="card-header">
        <h2 className="card-title">Информация о пациенте</h2>
        <p className="card-description">
          Заполните данные о пациенте для формирования запроса к ассистенту
        </p>
      </div>

      <form onSubmit={handleSubmit(onFormSubmit as any)} className="space-y-6">
        {/* Basic Information */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="form-group">
            <label className="form-label" htmlFor="name">
              Имя пациента *
            </label>
            <input
              id="name"
              type="text"
              className={`form-input ${errors.name ? 'form-input-error' : ''}`}
              placeholder="Введите имя или условное обозначение"
              {...register('name')}
              disabled={isLoading}
            />
            {errors.name && (
              <p className="form-error">{errors.name.message}</p>
            )}
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor="gender">
              Пол
            </label>
            <select
              id="gender"
              className={`form-input ${errors.gender ? 'form-input-error' : ''}`}
              {...register('gender')}
              disabled={isLoading}
            >
              <option value="">Не указан</option>
              <option value="male">Мужской</option>
              <option value="female">Женский</option>
            </select>
            {errors.gender && (
              <p className="form-error">{errors.gender.message}</p>
            )}
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor="age">
              Возраст *
            </label>
            <div className="flex gap-2">
              <input
                id="age"
                type="text"
                className={`form-input flex-1 ${errors.age ? 'form-input-error' : ''}`}
                placeholder={
                  currentAgeUnit === 'years' ? '0-18' :
                  currentAgeUnit === 'months' ? '0-216' : '0-6570'
                }
                {...register('age')}
                disabled={isLoading}
              />
              <select
                className={`form-input w-32 ${errors.ageUnit ? 'form-input-error' : ''}`}
                {...register('ageUnit')}
                onChange={(e) => {
                  setAgeUnit(e.target.value as 'years' | 'months' | 'days');
                  setValue('ageUnit', e.target.value as 'years' | 'months' | 'days');
                }}
                disabled={isLoading}
              >
                <option value="years">лет</option>
                <option value="months">месяцев</option>
                <option value="days">дней</option>
              </select>
            </div>
            {errors.age && (
              <p className="form-error">{errors.age.message}</p>
            )}
            {errors.ageUnit && (
              <p className="form-error">{errors.ageUnit.message}</p>
            )}
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor="weight">
              Вес (кг) *
            </label>
            <input
              id="weight"
              type="text"
              className={`form-input ${errors.weight ? 'form-input-error' : ''}`}
              placeholder="10.5"
              {...register('weight')}
              disabled={isLoading}
            />
            {errors.weight && (
              <p className="form-error">{errors.weight.message}</p>
            )}
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor="height">
              Рост (см) *
            </label>
            <input
              id="height"
              type="text"
              className={`form-input ${errors.height ? 'form-input-error' : ''}`}
              placeholder="120"
              {...register('height')}
              disabled={isLoading}
            />
            {errors.height && (
              <p className="form-error">{errors.height.message}</p>
            )}
          </div>
        </div>

        {/* Temperature */}
        <div className="form-group">
          <label className="form-label" htmlFor="temperature">
            Температура (°C) *
          </label>
          <input
            id="temperature"
            type="text"
            className={`form-input ${errors.temperature ? 'form-input-error' : ''}`}
            placeholder="38.5"
            {...register('temperature')}
            disabled={isLoading}
          />
          {errors.temperature && (
            <p className="form-error">{errors.temperature.message}</p>
          )}
        </div>

        {/* Symptoms */}
        <div className="form-group">
          <label className="form-label">
            Симптомы * (выберите все подходящие)
          </label>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
            {commonSymptoms.map((symptom) => (
              <label
                key={symptom}
                className="flex items-center space-x-2 cursor-pointer p-2 rounded hover:bg-gray-50"
              >
                <input
                  type="checkbox"
                  className="rounded border-gray-300 text-medical-blue focus:ring-medical-blue"
                  checked={selectedSymptoms.includes(symptom)}
                  onChange={() => handleSymptomToggle(symptom)}
                  disabled={isLoading}
                />
                <span className="text-sm">{symptom}</span>
              </label>
            ))}
          </div>
          {errors.symptoms && (
            <p className="form-error">{errors.symptoms.message}</p>
          )}
        </div>

        {/* Additional Information */}
        <div className="form-group">
          <label className="form-label" htmlFor="additionalInfo">
            Дополнительная информация
          </label>
          <textarea
            id="additionalInfo"
            rows={4}
            className={`form-input ${errors.additionalInfo ? 'form-input-error' : ''}`}
            placeholder="Опишите дополнительные симптомы, длительность заболевания, принятые лекарства и т.д."
            {...register('additionalInfo')}
            disabled={isLoading}
          />
          {errors.additionalInfo && (
            <p className="form-error">{errors.additionalInfo.message}</p>
          )}
        </div>

        {/* Submit Button */}
        <div className="flex justify-end space-x-3">
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => window.history.back()}
            disabled={isLoading}
          >
            Отмена
          </button>
          <button
            type="submit"
            className="btn btn-primary"
            disabled={isLoading}
          >
            {isLoading ? (
              <span className="flex items-center">
                <div className="loading-spinner w-4 h-4 mr-2"></div>
                Сохранение...
              </span>
            ) : (
              'Продолжить'
            )}
          </button>
        </div>
      </form>
    </div>
  );
};

export default PatientFormComponent;