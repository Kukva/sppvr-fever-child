import React from 'react';
import { CpuChipIcon, ChevronRightIcon } from '@heroicons/react/24/outline';
import type { AgentWorkflowStep } from '../types';

interface AgentWorkflowPanelProps {
  workflow: AgentWorkflowStep[];
}

const STEP_LABELS: Record<string, string> = {
  intake: 'Приём данных',
  data_completeness_checker: 'Проверка полноты данных',
  triage: 'Триаж',
  hypothesis_generator: 'Гипотезы',
  question: 'Уточняющие вопросы',
  infection: 'Инфекционист',
  immune: 'Иммунолог',
  oncology: 'Онколог',
  rare_disease: 'Редкие заболевания',
  synthesis: 'Синтез',
};

export const AgentWorkflowPanel: React.FC<AgentWorkflowPanelProps> = ({ workflow }) => {
  if (!workflow || workflow.length === 0) {
    return (
      <div className="rounded-xl border border-gray-200 bg-gray-50/50 p-6 text-center text-gray-500">
        <CpuChipIcon className="w-10 h-10 mx-auto mb-2 text-gray-400" />
        <p className="text-sm">Логика работы агентов появится после завершения анализа.</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <h3 className="text-sm font-semibold text-gray-700 flex items-center gap-2">
        <CpuChipIcon className="w-4 h-4" />
        Как работала система
      </h3>
      <div className="space-y-3">
        {workflow.map((step) => (
          <div
            key={`${step.step}-${step.agent_key}`}
            className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm"
          >
            <div className="flex items-start gap-3">
              <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[#2A9FFF] text-xs font-medium text-white">
                {step.step}
              </span>
              <div className="min-w-0 flex-1">
                <p className="font-medium text-gray-900">
                  {step.title || STEP_LABELS[step.agent_key] || step.agent_key}
                </p>
                {step.role && (
                  <p className="mt-0.5 text-xs text-gray-500">Роль: {step.role}</p>
                )}
                <p className="mt-1 text-sm text-gray-600 leading-relaxed">
                  {step.reasoning}
                </p>
                {(step.confidence != null || step.execution_time_ms != null) && (
                  <p className="mt-2 text-xs text-gray-500">
                    {step.confidence != null && (
                      <span>Уверенность: {(step.confidence * 100).toFixed(0)}%</span>
                    )}
                    {step.execution_time_ms != null && (
                      <span className={step.confidence != null ? ' ml-3' : ''}>
                        Время: {step.execution_time_ms} мс
                      </span>
                    )}
                  </p>
                )}
              </div>
              <ChevronRightIcon className="w-5 h-5 text-gray-400 shrink-0 mt-0.5" />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default AgentWorkflowPanel;
