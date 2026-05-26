"""Сервис генерации PDF отчетов"""

import os
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

from app.config import settings
from app.db.models import Session, Message
import logging

logger = logging.getLogger(__name__)


class PDFReportGenerator:
    """Генератор PDF отчетов с рекомендациями"""

    _FALLBACK_DIR = Path("/tmp/fiber-pdf-exports")

    def __init__(self, output_dir: str = None):
        self.output_dir = Path(output_dir or settings.pdf_export_dir)
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            logger.warning(
                "Cannot create PDF export dir %s (permission denied), using fallback %s",
                self.output_dir,
                self._FALLBACK_DIR,
            )
            self.output_dir = self._FALLBACK_DIR
            self.output_dir.mkdir(parents=True, exist_ok=True)

        # Попытка регистрации шрифтов с поддержкой кириллицы
        self._setup_fonts()
    
    def _setup_fonts(self):
        """Настройка шрифтов с поддержкой кириллицы (DejaVu). Ищем в системе (Docker) и в fonts/."""
        candidates = [
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
            Path("/usr/share/fonts/truetype/dejavu-core/DejaVuSans.ttf"),
            Path(__file__).resolve().parent.parent.parent / "fonts" / "DejaVuSans.ttf",
            Path("fonts") / "DejaVuSans.ttf",
        ]
        bold_candidates = [
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
            Path("/usr/share/fonts/truetype/dejavu-core/DejaVuSans-Bold.ttf"),
            Path(__file__).resolve().parent.parent.parent / "fonts" / "DejaVuSans-Bold.ttf",
            Path("fonts") / "DejaVuSans-Bold.ttf",
        ]
        try:
            dejavu_sans = next((p for p in candidates if p.exists()), None)
            dejavu_sans_bold = next((p for p in bold_candidates if p.exists()), None)
            if dejavu_sans:
                pdfmetrics.registerFont(TTFont('DejaVuSans', str(dejavu_sans)))
                self.font_normal = 'DejaVuSans'
            else:
                self.font_normal = 'Helvetica'
                logger.warning("DejaVu Sans not found, Cyrillic may render incorrectly")
            if dejavu_sans_bold:
                pdfmetrics.registerFont(TTFont('DejaVuSans-Bold', str(dejavu_sans_bold)))
                self.font_bold = 'DejaVuSans-Bold'
            else:
                self.font_bold = 'Helvetica-Bold'
        except Exception as e:
            logger.error(f"Error setting up fonts: {str(e)}")
            self.font_normal = 'Helvetica'
            self.font_bold = 'Helvetica-Bold'
    
    async def generate_report(
        self,
        session_id: str,
        patient_data: Dict[str, Any],
        recommendations: Dict[str, Any],
        session_data: Optional[Session] = None,
        messages: Optional[List[Message]] = None
    ) -> str:
        """Генерация PDF отчета"""
        
        try:
            # Генерация имени файла
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"recommendation_{session_id}_{timestamp}.pdf"
            filepath = self.output_dir / filename
            
            # Создание PDF документа
            doc = SimpleDocTemplate(
                str(filepath),
                pagesize=A4,
                rightMargin=2*cm,
                leftMargin=2*cm,
                topMargin=2*cm,
                bottomMargin=2*cm
            )
            
            # Сбор контента
            story = self._build_report_content(
                session_id,
                patient_data,
                recommendations,
                session_data,
                messages
            )
            
            # Генерация PDF
            doc.build(story)
            
            logger.info(f"PDF report generated: {filepath}")
            return str(filepath)
            
        except Exception as e:
            logger.error(f"Error generating PDF report: {str(e)}")
            raise
    
    def _build_report_content(
        self,
        session_id: str,
        patient_data: Dict[str, Any],
        recommendations: Dict[str, Any],
        session_data: Optional[Session] = None,
        messages: Optional[List[Message]] = None
    ) -> List:
        """Построение контента отчета"""
        
        story = []
        
        # Стили
        styles = self._get_styles()
        
        # Заголовок
        story.extend(self._create_header(styles))
        
        # Информация о пациенте
        story.extend(self._create_patient_section(patient_data, styles))
        
        # Оценка срочности
        story.extend(self._create_urgency_section(recommendations, styles))
        
        # Маршрутизация к специалистам
        story.extend(self._create_routing_section(recommendations, styles))
        
        # Рекомендуемые обследования
        story.extend(self._create_tests_section(recommendations, styles))
        
        # Красные флаги
        if recommendations.get('red_flags'):
            story.extend(self._create_red_flags_section(recommendations['red_flags'], styles))
        
        # История диалога
        if messages:
            story.extend(self._create_chat_history_section(messages, styles))
        
        # Футер
        story.extend(self._create_footer(session_id, styles))
        
        return story
    
    def _get_styles(self) -> Dict[str, ParagraphStyle]:
        """Получение стилей документа"""
        
        styles = getSampleStyleSheet()
        
        # Кастомные стили
        custom_styles = {
            'title': ParagraphStyle(
                'CustomTitle',
                parent=styles['Heading1'],
                fontName=self.font_bold,
                fontSize=18,
                textColor=colors.HexColor('#1a237e'),
                spaceAfter=20,
                alignment=TA_CENTER,
                leading=22
            ),
            
            'subtitle': ParagraphStyle(
                'CustomSubtitle',
                parent=styles['Heading2'],
                fontName=self.font_bold,
                fontSize=14,
                textColor=colors.HexColor('#283593'),
                spaceAfter=12,
                spaceBefore=20,
                leading=18
            ),
            
            'normal': ParagraphStyle(
                'CustomNormal',
                parent=styles['Normal'],
                fontName=self.font_normal,
                fontSize=11,
                leading=14,
                spaceAfter=6
            ),
            
            'urgent': ParagraphStyle(
                'Urgent',
                parent=styles['Normal'],
                fontName=self.font_bold,
                fontSize=13,
                leading=16,
                spaceAfter=8
            ),
            
            'footer': ParagraphStyle(
                'Footer',
                parent=styles['Normal'],
                fontName=self.font_normal,
                fontSize=9,
                textColor=colors.grey,
                leading=12
            )
        }
        
        return custom_styles
    
    def _create_header(self, styles: Dict[str, ParagraphStyle]) -> List:
        """Создание заголовка документа"""
        
        content = []
        
        # Основной заголовок
        content.append(Paragraph("МЕДИЦИНСКОЕ ЗАКЛЮЧЕНИЕ", styles['title']))
        content.append(Paragraph("Система маршрутизации детей с лихорадкой", styles['normal']))
        content.append(Spacer(1, 0.5*cm))
        
        return content
    
    def _create_patient_section(self, patient_data: Dict[str, Any], styles: Dict[str, ParagraphStyle]) -> List:
        """Создание раздела с информацией о пациенте"""
        
        content = []
        content.append(Paragraph("1. ИНФОРМАЦИЯ О ПАЦИЕНТЕ", styles['subtitle']))
        
        # Формирование таблицы с данными
        patient_info = []
        
        # Возраст
        age_years = patient_data.get('age_years')
        age_months = patient_data.get('age_months')
        if age_years is not None:
            age_text = f"{age_years} лет"
            if age_months and age_months > 0:
                age_text += f" {age_months} мес"
            patient_info.append(["Возраст:", age_text])
        
        # Температура
        temp_current = patient_data.get('temperature_current')
        temp_max = patient_data.get('temperature_max')
        if temp_current is not None:
            temp_text = f"{temp_current}°C"
            if temp_max is not None:
                temp_text += f" (макс: {temp_max}°C)"
            patient_info.append(["Температура:", temp_text])
        
        # Длительность
        duration = patient_data.get('duration_days')
        if duration is not None:
            patient_info.append(["Длительность лихорадки:", f"{duration} дней"])
        
        # Паттерн температуры
        pattern = patient_data.get('temperature_pattern')
        if pattern:
            patient_info.append(["Паттерн температуры:", pattern])
        
        # Симптомы
        symptoms = patient_data.get('symptoms', [])
        if symptoms:
            patient_info.append(["Симптомы:", ", ".join(symptoms[:5])])
            if len(symptoms) > 5:
                patient_info.append(["", f"... и еще {len(symptoms) - 5} симптомов"])
        
        # Создание таблицы
        if patient_info:
            patient_table = Table(patient_info, colWidths=[5*cm, 10*cm])
            patient_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#e3f2fd')),
                ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (0, -1), self.font_bold),
                ('FONTNAME', (1, 0), (1, -1), self.font_normal),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('LEFTPADDING', (0, 0), (-1, -1), 8),
                ('RIGHTPADDING', (0, 0), (-1, -1), 8),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ]))
            
            content.append(patient_table)
        
        content.append(Spacer(1, 0.5*cm))
        return content
    
    def _create_urgency_section(self, recommendations: Dict[str, Any], styles: Dict[str, ParagraphStyle]) -> List:
        """Создание раздела оценки срочности"""
        
        content = []
        content.append(Paragraph("2. ОЦЕНКА СРОЧНОСТИ", styles['subtitle']))
        
        urgency_level = recommendations.get('urgency_level', 'routine')
        
        # Цвета для уровней срочности
        urgency_colors = {
            'emergency': colors.red,
            'urgent': colors.orange,
            'routine': colors.green
        }
        
        # Метки для уровней срочности
        urgency_labels = {
            'emergency': '🔴 ЭКСТРЕННЫЙ',
            'urgent': '🟡 СРОЧНЫЙ',
            'routine': '🟢 ПЛАНОВЫЙ'
        }
        
        # Описание уровней
        urgency_descriptions = {
            'emergency': 'Требуется немедленная госпитализация',
            'urgent': 'Консультация специалиста в течение 24 часов',
            'routine': 'Плановая консультация в течение 3-7 дней'
        }
        
        # Создание стиля для уровня срочности
        urgency_style = ParagraphStyle(
            'UrgencyLevel',
            parent=styles['urgent'],
            textColor=urgency_colors.get(urgency_level, colors.black)
        )
        
        content.append(Paragraph(urgency_labels.get(urgency_level, urgency_level.upper()), urgency_style))
        content.append(Paragraph(urgency_descriptions.get(urgency_level, ''), styles['normal']))
        content.append(Spacer(1, 0.5*cm))
        
        return content
    
    def _create_routing_section(self, recommendations: Dict[str, Any], styles: Dict[str, ParagraphStyle]) -> List:
        """Создание раздела маршрутизации к специалистам"""
        
        content = []
        content.append(Paragraph("3. РЕКОМЕНДУЕМАЯ МАРШРУТИЗАЦИЯ", styles['subtitle']))
        
        # Основной специалист
        primary_specialist = recommendations.get('primary_specialist')
        if primary_specialist:
            content.append(Paragraph("<b>📋 ОСНОВНОЕ НАПРАВЛЕНИЕ:</b>", styles['normal']))
            
            # Карточка специалиста
            specialist_info = [
                ["<b>Специалист:</b>", primary_specialist.get('name', 'Не указан')],
                ["<b>Приоритет:</b>", primary_specialist.get('priority', 'средний')],
                ["<b>Сроки:</b>", primary_specialist.get('timeframe', 'Не указаны')],
                ["<b>Цель консультации:</b>", primary_specialist.get('purpose', 'Не указана')]
            ]
            
            specialist_table = Table(specialist_info, colWidths=[4*cm, 11*cm])
            specialist_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f3e5f5')),
                ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (0, -1), self.font_bold),
                ('FONTNAME', (1, 0), (1, -1), self.font_normal),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('LEFTPADDING', (0, 0), (-1, -1), 8),
                ('RIGHTPADDING', (0, 0), (-1, -1), 8),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ]))
            
            content.append(specialist_table)
            
            # Причины направления
            reasons = primary_specialist.get('reasons', [])
            if reasons:
                content.append(Spacer(1, 0.3*cm))
                content.append(Paragraph("<b>📌 Обоснование направления:</b>", styles['normal']))
                for reason in reasons:
                    content.append(Paragraph(f"• {reason}", styles['normal']))
        
        # Дополнительные специалисты
        additional_specialists = recommendations.get('additional_specialists', [])
        if additional_specialists:
            content.append(Spacer(1, 0.5*cm))
            content.append(Paragraph("<b>👥 ДОПОЛНИТЕЛЬНЫЕ КОНСУЛЬТАЦИИ:</b>", styles['normal']))
            
            for spec in additional_specialists:
                spec_text = f"• {spec.get('name', 'Не указан')} ({spec.get('priority', 'средний')} приоритет)"
                if spec.get('timeframe'):
                    spec_text += f" - {spec['timeframe']}"
                content.append(Paragraph(spec_text, styles['normal']))
        
        content.append(Spacer(1, 0.5*cm))
        return content
    
    def _create_tests_section(self, recommendations: Dict[str, Any], styles: Dict[str, ParagraphStyle]) -> List:
        """Создание раздела рекомендуемых обследований"""
        
        content = []
        content.append(Paragraph("4. РЕКОМЕНДУЕМЫЕ ОБСЛЕДОВАНИЯ", styles['subtitle']))
        
        required_tests = recommendations.get('required_tests', [])
        if required_tests:
            for test in required_tests:
                content.append(Paragraph(f"□ {test}", styles['normal']))
        else:
            content.append(Paragraph("Обследования будут определены специалистом", styles['normal']))
        
        content.append(Spacer(1, 0.5*cm))
        return content
    
    def _create_red_flags_section(self, red_flags: List[str], styles: Dict[str, ParagraphStyle]) -> List:
        """Создание раздела красных флагов"""
        
        content = []
        content.append(Paragraph("5. ТРЕВОЖНЫЕ ПРИЗНАКИ", styles['subtitle']))
        
        for flag in red_flags:
            content.append(Paragraph(f"⚠️ {flag}", styles['normal']))
        
        content.append(Spacer(1, 0.5*cm))
        return content
    
    def _create_chat_history_section(self, messages: List[Message], styles: Dict[str, ParagraphStyle]) -> List:
        """Создание раздела истории диалога"""
        
        content = []
        content.append(PageBreak())
        content.append(Paragraph("6. ИСТОРИЯ КОНСУЛЬТАЦИИ", styles['subtitle']))
        
        # Ограничение количества сообщений
        recent_messages = messages[-20:]  # Последние 20 сообщений
        
        for msg in recent_messages:
            timestamp = (msg.created_at.strftime("%H:%M:%S") if msg.created_at else "")
            role_label = {
                "user": "👨‍⚕️ Врач",
                "assistant": "🤖 Ассистент",
                "system": "🔧 Система",
            }.get(msg.role or "", (msg.role or "").upper())
            
            # Заголовок сообщения
            header = f"<b>{role_label}</b> ({timestamp})"
            content.append(Paragraph(header, styles["normal"]))
            
            # Текст сообщения: защита от None и невалидных символов для ReportLab (например <, >, &)
            raw = (msg.content or "").strip()
            safe_text = raw.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;") if raw else "—"
            content.append(Paragraph(safe_text, styles["normal"]))
            content.append(Spacer(1, 0.2*cm))
        
        return content
    
    def _create_footer(self, session_id: str, styles: Dict[str, ParagraphStyle]) -> List:
        """Создание футера документа"""
        
        content = []
        content.append(Spacer(1, 1*cm))
        
        footer_text = f"""
Дата формирования: {datetime.now().strftime('%d.%m.%Y %H:%M')}<br/>
ID сессии: {session_id}<br/><br/>
<b>ВАЖНЫЕ НАПОМИНАНИЯ:</b><br/>
⚕️ Данное заключение носит рекомендательный характер и не заменяет консультацию специалиста.<br/>
📞 При любых сомнениях или ухудшении состояния — немедленное обращение за медицинской помощью.<br/>
🔄 Клиническая картина может меняться — важно динамическое наблюдение.
        """
        
        content.append(Paragraph(footer_text, styles['footer']))
        
        return content