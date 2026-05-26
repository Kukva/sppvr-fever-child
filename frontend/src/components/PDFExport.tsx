import React, { useState } from 'react';
import { 
  DocumentArrowDownIcon,
  CheckCircleIcon,
  ExclamationTriangleIcon 
} from '@heroicons/react/24/outline';
import jsPDF from 'jspdf';
import type { PDFExportData } from '../types';

interface PDFExportProps {
  data: PDFExportData;
  onExportComplete?: (success: boolean) => void;
}

export const PDFExport: React.FC<PDFExportProps> = ({
  data,
  onExportComplete,
}) => {
  const [isExporting, setIsExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);

  const generatePDF = async () => {
    setIsExporting(true);
    setExportError(null);

    try {
      // Validate data
      if (!data || !data.patient) {
        throw new Error('Отсутствуют данные о пациенте');
      }

      // Create a new PDF document
      const pdf = new jsPDF('p', 'mm', 'a4');
      const pageWidth = pdf.internal.pageSize.getWidth();
      const pageHeight = pdf.internal.pageSize.getHeight();
      let yPosition = 20;

      // Helper function to add new page if needed
      const checkPageBreak = (requiredHeight: number) => {
        if (yPosition + requiredHeight > pageHeight - 20) {
          pdf.addPage();
          yPosition = 20;
        }
      };

      // Add header
      pdf.setFontSize(20);
      pdf.setFont('helvetica', 'bold');
      pdf.text('Медицинская консультация', pageWidth / 2, yPosition, { align: 'center' });
      yPosition += 15;

      pdf.setFontSize(12);
      pdf.setFont('helvetica', 'normal');
      pdf.text(`Дата: ${new Date().toLocaleDateString('ru-RU')}`, pageWidth / 2, yPosition, { align: 'center' });
      yPosition += 15;

      // Patient Information Section
      checkPageBreak(40);
      pdf.setFontSize(16);
      pdf.setFont('helvetica', 'bold');
      pdf.text('Информация о пациенте', 20, yPosition);
      yPosition += 10;

      pdf.setFontSize(11);
      pdf.setFont('helvetica', 'normal');
      
      // Name
      const nameText = `Имя: ${data.patient.name || 'Не указано'}`;
      pdf.text(nameText, 20, yPosition);
      yPosition += 7;
      
      // Gender
      if (data.patient.gender) {
        const genderText = `Пол: ${data.patient.gender === 'male' ? 'Мужской' : 'Женский'}`;
        pdf.text(genderText, 20, yPosition);
        yPosition += 7;
      }
      
      // Age with detailed info
      let ageText = `Возраст: ${data.patient.age || 0} лет`;
      if (data.patient.ageMonths) {
        ageText += ` (${data.patient.ageMonths} месяцев)`;
      } else if (data.patient.ageDays) {
        ageText += ` (${data.patient.ageDays} дней)`;
      }
      pdf.text(ageText, 20, yPosition);
      yPosition += 7;
      
      // Weight
      const weightText = `Вес: ${data.patient.weight || 'Не указан'} кг`;
      pdf.text(weightText, 20, yPosition);
      yPosition += 7;
      
      // Height
      const heightText = `Рост: ${data.patient.height || 'Не указан'} см`;
      pdf.text(heightText, 20, yPosition);
      yPosition += 7;
      
      // Temperature
      const tempText = `Температура: ${data.patient.temperature || 'Не указана'}°C`;
      pdf.text(tempText, 20, yPosition);
      yPosition += 7;
      
      // Symptoms
      const symptomsText = `Симптомы: ${data.patient.symptoms && data.patient.symptoms.length > 0 
        ? data.patient.symptoms.join(', ') 
        : 'Не указаны'}`;
      const symptomsLines = pdf.splitTextToSize(symptomsText, pageWidth - 40);
      pdf.text(symptomsLines, 20, yPosition);
      yPosition += symptomsLines.length * 7 + 3;

      if (data.patient.additionalInfo) {
        checkPageBreak(20);
        pdf.text('Дополнительная информация:', 20, yPosition);
        yPosition += 7;
        const lines = pdf.splitTextToSize(data.patient.additionalInfo, pageWidth - 40);
        pdf.text(lines, 20, yPosition);
        yPosition += lines.length * 7 + 10;
      }

      // Recommendations Section
      if (data.recommendations && data.recommendations.length > 0) {
        checkPageBreak(30);
        pdf.setFontSize(16);
        pdf.setFont('helvetica', 'bold');
        pdf.text('Рекомендации', 20, yPosition);
        yPosition += 10;

        data.recommendations.forEach((recommendation, index) => {
        checkPageBreak(40);
        
        pdf.setFontSize(12);
        pdf.setFont('helvetica', 'bold');
        pdf.text(`${index + 1}. ${recommendation.title}`, 20, yPosition);
        yPosition += 8;

        pdf.setFontSize(10);
        pdf.setFont('helvetica', 'normal');
        
        // Priority and Category
        const priorityText = `Приоритет: ${getPriorityLabel(recommendation.priority)}`;
        const categoryText = `Категория: ${getCategoryLabel(recommendation.category)}`;
        pdf.text(priorityText, 20, yPosition);
        yPosition += 6;
        pdf.text(categoryText, 20, yPosition);
        yPosition += 8;

        // Description
        const descriptionText = recommendation.description || 'Описание отсутствует';
        const lines = pdf.splitTextToSize(descriptionText, pageWidth - 40);
        pdf.text(lines, 20, yPosition);
        yPosition += lines.length * 7 + 10;
        });
      } else {
        checkPageBreak(20);
        pdf.setFontSize(16);
        pdf.setFont('helvetica', 'bold');
        pdf.text('Рекомендации', 20, yPosition);
        yPosition += 10;
        pdf.setFontSize(11);
        pdf.setFont('helvetica', 'normal');
        pdf.text('Рекомендации пока не доступны', 20, yPosition);
        yPosition += 10;
      }

      // Specialists Section
      if (data.specialists.length > 0) {
        checkPageBreak(30);
        pdf.setFontSize(16);
        pdf.setFont('helvetica', 'bold');
        pdf.text('Рекомендуемые специалисты', 20, yPosition);
        yPosition += 10;

        data.specialists.forEach((specialist, index) => {
          checkPageBreak(35);
          
          pdf.setFontSize(12);
          pdf.setFont('helvetica', 'bold');
          pdf.text(`${index + 1}. ${specialist.name}`, 20, yPosition);
          yPosition += 7;

          pdf.setFontSize(10);
          pdf.setFont('helvetica', 'normal');
          pdf.text(`Специальность: ${specialist.specialty}`, 20, yPosition);
          yPosition += 6;
          pdf.text(`Опыт: ${specialist.experience}`, 20, yPosition);
          yPosition += 6;
          pdf.text(`Рейтинг: ${specialist.rating}/5`, 20, yPosition);
          yPosition += 6;
          pdf.text(`Локация: ${specialist.location}`, 20, yPosition);
          yPosition += 6;

          if (specialist.contactInfo.phone) {
            pdf.text(`Телефон: ${specialist.contactInfo.phone}`, 20, yPosition);
            yPosition += 6;
          }

          yPosition += 5;
        });
      }

      // Agent Status Section
      if (data.agentStatus) {
        checkPageBreak(30);
        pdf.setFontSize(16);
        pdf.setFont('helvetica', 'bold');
        pdf.text('Статус анализа', 20, yPosition);
        yPosition += 10;

        pdf.setFontSize(10);
        pdf.setFont('helvetica', 'normal');
        pdf.text(`Общий прогресс: ${data.agentStatus.overallProgress || 0}%`, 20, yPosition);
        yPosition += 7;
        pdf.text(`Текущий шаг: ${data.agentStatus.currentStep || 'Неизвестно'}`, 20, yPosition);
        yPosition += 10;

        if (data.agentStatus.agents && data.agentStatus.agents.length > 0) {
          data.agentStatus.agents.forEach((agent) => {
            checkPageBreak(20);
            pdf.text(`Агент ${agent.name || 'Неизвестный'}: ${getStatusLabel(agent.status)}`, 20, yPosition);
            yPosition += 6;
            if (agent.currentTask) {
              pdf.text(`  Задача: ${agent.currentTask}`, 20, yPosition);
              yPosition += 6;
            }
          });
        }
      }

      // Chat History Section (if available)
      if (data.session && data.session.messages && data.session.messages.length > 0) {
        checkPageBreak(30);
        pdf.setFontSize(16);
        pdf.setFont('helvetica', 'bold');
        pdf.text('История чата', 20, yPosition);
        yPosition += 10;

        pdf.setFontSize(10);
        pdf.setFont('helvetica', 'normal');
        
        data.session.messages.forEach((message, index) => {
          checkPageBreak(25);
          const senderLabel = message.sender === 'user' ? 'Пациент/Врач' : 'Ассистент';
          pdf.setFont('helvetica', 'bold');
          pdf.text(`${index + 1}. ${senderLabel}:`, 20, yPosition);
          yPosition += 6;
          
          pdf.setFont('helvetica', 'normal');
          const messageLines = pdf.splitTextToSize(message.content || '', pageWidth - 40);
          pdf.text(messageLines, 25, yPosition);
          yPosition += messageLines.length * 5 + 5;
        });
      }

      // Footer
      pdf.setFontSize(8);
      pdf.setFont('helvetica', 'italic');
      const footerDisclaimer =
        'Документ сгенерирован ИИ-системой для врачебного использования; не заменяет клиническое решение и документацию по случаю';
      const footerLines = pdf.splitTextToSize(footerDisclaimer, pageWidth - 30);
      const lineH = 4;
      let footerY = pageHeight - 12 - (footerLines.length - 1) * lineH;
      footerLines.forEach((line: string, i: number) => {
        pdf.text(line, pageWidth / 2, footerY + i * lineH, { align: 'center' });
      });

      // Save the PDF
      const fileName = `medical_consultation_${data.patient.name}_${new Date().toISOString().split('T')[0]}.pdf`;
      pdf.save(fileName);

      onExportComplete?.(true);
    } catch (error) {
      console.error('Error generating PDF:', error);
      setExportError('Ошибка при создании PDF. Попробуйте еще раз.');
      onExportComplete?.(false);
    } finally {
      setIsExporting(false);
    }
  };

  const getPriorityLabel = (priority: string) => {
    switch (priority) {
      case 'urgent': return 'Срочно';
      case 'high': return 'Высокий';
      case 'medium': return 'Средний';
      case 'low': return 'Низкий';
      default: return 'Обычный';
    }
  };

  const getCategoryLabel = (category: string) => {
    switch (category) {
      case 'emergency': return 'Экстренная помощь';
      case 'medication': return 'Лекарства';
      case 'observation': return 'Наблюдение';
      case 'consultation': return 'Консультация';
      default: return 'Общее';
    }
  };

  const getStatusLabel = (status: string) => {
    switch (status) {
      case 'idle': return 'Ожидает';
      case 'processing': return 'Обрабатывает';
      case 'completed': return 'Завершен';
      case 'error': return 'Ошибка';
      default: return 'Неизвестно';
    }
  };

  return (
    <div className="card">
      <div className="card-header">
        <h3 className="card-title">Экспорт в PDF</h3>
        <p className="card-description">
          Сохраните всю информацию о консультации в PDF файл
        </p>
      </div>

      <div className="space-y-4">
        {/* Export Info */}
        <div className="p-4 bg-blue-50 rounded-lg border border-blue-200">
          <div className="flex items-start space-x-2">
            <DocumentArrowDownIcon className="w-5 h-5 text-blue-600 mt-0.5" />
            <div>
              <h4 className="font-medium text-blue-900 mb-1">Что будет включено в PDF:</h4>
              <ul className="text-sm text-blue-800 space-y-1">
                <li>• Информация о пациенте</li>
                <li>• Все рекомендации ({data.recommendations.length})</li>
                <li>• Рекомендуемые специалисты ({data.specialists.length})</li>
                <li>• Статус работы агентов</li>
                <li>• История чата</li>
              </ul>
            </div>
          </div>
        </div>

        {/* Export Button */}
        <button
          onClick={generatePDF}
          disabled={isExporting}
          className="w-full btn btn-primary flex items-center justify-center"
        >
          {isExporting ? (
            <>
              <div className="loading-spinner w-4 h-4 mr-2"></div>
              Создание PDF...
            </>
          ) : (
            <>
              <DocumentArrowDownIcon className="w-5 h-5 mr-2" />
              Скачать PDF
            </>
          )}
        </button>

        {/* Error Message */}
        {exportError && (
          <div className="p-4 bg-red-50 rounded-lg border border-red-200">
            <div className="flex items-start space-x-2">
              <ExclamationTriangleIcon className="w-5 h-5 text-red-600 mt-0.5" />
              <div>
                <h4 className="font-medium text-red-900 mb-1">Ошибка экспорта</h4>
                <p className="text-sm text-red-800">{exportError}</p>
              </div>
            </div>
          </div>
        )}

        {/* Success Message (shown after successful export) */}
        {!isExporting && !exportError && (
          <div className="p-4 bg-green-50 rounded-lg border border-green-200">
            <div className="flex items-start space-x-2">
              <CheckCircleIcon className="w-5 h-5 text-green-600 mt-0.5" />
              <div>
                <h4 className="font-medium text-green-900 mb-1">Готово к экспорту</h4>
                <p className="text-sm text-green-800">
                  Нажмите кнопку выше, чтобы создать PDF документ со всей информацией о консультации.
                </p>
              </div>
            </div>
          </div>
        )}

        {/* Additional Info */}
        <div className="text-xs text-gray-500 text-center">
          PDF предназначен для служебного использования и передачи в медицинскую документацию по решению врача.
          Файл будет загружен в папку загрузок браузера.
        </div>
      </div>
    </div>
  );
};

export default PDFExport;