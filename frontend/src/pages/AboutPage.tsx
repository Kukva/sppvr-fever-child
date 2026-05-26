import React from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ArrowLeftIcon,
  InformationCircleIcon,
  ShieldCheckIcon,
  CpuChipIcon,
} from '@heroicons/react/24/outline';
import { Header } from '../components/Header';
import { PageDoodleBackground } from '../components/PageDoodleBackground';
import marinaSiteLogo from '../assets/marina-site-logo.svg';

const sectionClass =
  'rounded-[24px] sm:rounded-[30px] border border-figma-accentBorder bg-white/85 shadow-figma-card backdrop-blur-sm p-6 sm:p-8';
const sectionTitleClass =
  'text-lg font-semibold text-figma-ink border-b border-gray-200/80 pb-3 mb-4';

export const AboutPage: React.FC = () => {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-gradient-to-b from-[#F0F4F8] to-white flex flex-col relative overflow-hidden">
      <PageDoodleBackground />
      <Header />

      <div className="relative z-10 border-b border-gray-200/80 bg-white/80 backdrop-blur-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 py-3 sm:py-4 flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={() => navigate('/')}
            className="inline-flex items-center gap-2 rounded-xl border-2 border-figma-accentSoft bg-white/90 px-3 py-2 text-sm font-medium text-figma-ink hover:bg-white hover:border-figma-accent transition-colors"
          >
            <ArrowLeftIcon className="w-5 h-5 shrink-0" />
            На главную
          </button>
          <div className="flex flex-wrap items-center gap-3 sm:gap-4 min-w-0">
            <img
              src={marinaSiteLogo}
              alt=""
              className="h-8 sm:h-9 w-auto max-w-[min(260px,50vw)] object-contain object-left shrink-0"
              decoding="async"
              aria-hidden
            />
            <div className="min-w-0">
              <h1 className="text-lg sm:text-xl font-semibold text-figma-ink">
                О системе
              </h1>
              <p className="text-sm text-gray-600">
                Мультиагентная ИИ-система для врачей
              </p>
            </div>
          </div>
        </div>
      </div>

      <main className="relative z-10 flex-1 max-w-4xl w-full mx-auto px-4 sm:px-6 py-8 space-y-8">
        <section className={sectionClass}>
          <div className={sectionTitleClass}>
            <h2 className="inline">Описание системы</h2>
          </div>
          <div className="space-y-4 text-gray-700 text-[15px] sm:text-base leading-relaxed">
            <p>
              <strong className="text-figma-ink">
                ИИ-ассистент для оценки лихорадки у детей
              </strong>{' '}
              — мультиагентная система для врачей-педиатров и детских
              специалистов: помогает структурировать оценку, дифференциальную
              диагностику и маршрутизацию сложных случаев. Интерфейс ассистента
              «Марина Ивановна» задаёт тон дружелюбного клинического диалога.
            </p>
            <p>
              Инфраструктура и модели — в экосистеме{' '}
              <strong className="text-figma-ink">Yandex Cloud</strong> (в т.ч.
              YandexGPT); логика агентов реализована как цепочка
              специализированных шагов с последующим синтезом рекомендаций для
              врача.
            </p>
            <p>
              Несколько ИИ-агентов анализируют разные аспекты клинической
              картины; итог объединяется так, чтобы поддержать врача в
              диагностике и выборе тактики, а не заменить клиническое решение.
            </p>
          </div>
        </section>

        <section className={sectionClass}>
          <div
            className={`${sectionTitleClass} flex items-center gap-2 border-0 pb-0 mb-4`}
          >
            <CpuChipIcon className="w-6 h-6 text-figma-accent shrink-0" />
            <h2 className="text-lg font-semibold text-figma-ink">
              Мультиагентная архитектура
            </h2>
          </div>
          <div className="space-y-4 border-t border-gray-200/80 pt-4">
            <p className="text-gray-700">
              Система включает следующие роли агентов:
            </p>
            <ul className="space-y-3 list-disc list-inside text-gray-700 marker:text-figma-accent">
              <li>
                <strong className="text-figma-ink">Агент сбора данных</strong>{' '}
                (Intake) — собирает и структурирует информацию о пациенте,
                симптомах и анамнезе
              </li>
              <li>
                <strong className="text-figma-ink">Агент триажа</strong>{' '}
                (Triage) — оценивает срочность и приоритет обращения
              </li>
              <li>
                <strong className="text-figma-ink">
                  Специализированные диагностические агенты
                </strong>{' '}
                — разбор по направлениям:
                <ul className="ml-6 mt-2 space-y-1 list-disc text-gray-600">
                  <li>инфекционные заболевания</li>
                  <li>иммунологические состояния</li>
                  <li>онкологические заболевания</li>
                  <li>редкие заболевания</li>
                </ul>
              </li>
              <li>
                <strong className="text-figma-ink">Агент синтеза</strong>{' '}
                (Synthesis) — объединяет выводы и формирует итоговые
                рекомендации
              </li>
              <li>
                <strong className="text-figma-ink">Агент маршрутизации</strong>{' '}
                (Routing) — предлагает вовлечение специалистов и варианты
                предварительной трактовки
              </li>
            </ul>
          </div>
        </section>

        <section className={sectionClass}>
          <div className={sectionTitleClass}>
            <h2>Возможности системы</h2>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {[
              {
                title: 'Быстрая оценка',
                body: 'Многокритериальный разбор симптомов и данных для ориентира по тяжести состояния.',
              },
              {
                title: 'Клинические ориентиры',
                body: 'Формулировки с опорой на распространённые протоколы и стандарты помощи; требуют верификации врачом.',
              },
              {
                title: 'Маршрутизация',
                body: 'Подсказки по специалистам и логике различения диагнозов — с объяснением хода рассуждения.',
              },
              {
                title: 'Диалог',
                body: 'Уточняющие вопросы для сбора недостающей информации и повышения полноты картины.',
              },
            ].map((item) => (
              <div
                key={item.title}
                className="rounded-2xl border border-gray-200/90 bg-white/70 p-4 shadow-sm"
              >
                <h3 className="font-semibold text-figma-ink mb-2">
                  {item.title}
                </h3>
                <p className="text-sm text-gray-700 leading-relaxed">
                  {item.body}
                </p>
              </div>
            ))}
          </div>
        </section>

        <section className={`${sectionClass} border-red-200/80 bg-red-50/35`}>
          <div
            className={`${sectionTitleClass} border-red-200/50 flex items-center gap-2`}
          >
            <ShieldCheckIcon className="w-6 h-6 text-red-600 shrink-0" />
            <h2 className="text-red-900">Важная информация</h2>
          </div>
          <div className="space-y-4 text-gray-800">
            <div className="rounded-xl border border-red-200/80 bg-white/90 p-4">
              <h3 className="font-semibold text-red-900 mb-2">
                Ограничения системы
              </h3>
              <ul className="space-y-2 list-disc list-inside text-sm text-gray-800">
                <li>
                  Сервис — <strong>вспомогательный инструмент</strong>, не
                  заменяет очный приём, осмотр и очную консультацию.
                </li>
                <li>
                  Решения о диагностике и лечении принимает врач на основе
                  полной клинической оценки.
                </li>
                <li>
                  Система не подменяет клиническое мышление, опыт и суждение
                  специалиста.
                </li>
                <li>
                  Рекомендации опираются на введённые данные и могут требовать
                  уточнения и проверки.
                </li>
              </ul>
            </div>

            <div className="rounded-xl border border-red-200/80 bg-white/90 p-4">
              <h3 className="font-semibold text-red-900 mb-2">
                Зона ответственности
              </h3>
              <ul className="space-y-2 list-disc list-inside text-sm text-gray-800">
                <li>
                  Врач несёт ответственность за клинические решения в отношении
                  пациента.
                </li>
                <li>
                  Разработчики не отвечают за решения, принятые только на основе
                  вывода системы без независимой клинической оценки.
                </li>
                <li>
                  При сомнениях или ухудшении состояния руководствуйтесь
                  протоколами учреждения, показаниями к госпитализации и
                  неотложной помощи.
                </li>
                <li>
                  Система предназначена для квалифицированных медицинских
                  работников, не для самодиагностики или самолечения.
                </li>
              </ul>
            </div>
          </div>
        </section>

        <section className={sectionClass}>
          <div
            className={`${sectionTitleClass} flex items-center gap-2 border-0 pb-0 mb-4`}
          >
            <InformationCircleIcon className="w-6 h-6 text-figma-accent shrink-0" />
            <h2 className="text-lg font-semibold text-figma-ink">
              Техническая информация
            </h2>
          </div>
          <div className="space-y-2 text-sm text-gray-700 border-t border-gray-200/80 pt-4">
            <p>
              <strong className="text-figma-ink">Версия:</strong> 1.0.0
            </p>
            <p>
              <strong className="text-figma-ink">Архитектура:</strong>{' '}
              мультиагентная система (LangGraph)
            </p>
            <p>
              <strong className="text-figma-ink">Модели:</strong> YandexGPT
              (Yandex AI Studio), инфраструктура Yandex Cloud
            </p>
            <p>
              <strong className="text-figma-ink">Доступность:</strong>{' '}
              круглосуточно (при работе сервиса)
            </p>
            <p>
              <strong className="text-figma-ink">Аудитория:</strong>{' '}
              врачи-педиатры и детские специалисты
            </p>
          </div>
        </section>

        <section className={sectionClass}>
          <div className={sectionTitleClass}>
            <h2>Контакты и поддержка</h2>
          </div>
          <div className="text-gray-700 text-[15px] sm:text-base leading-relaxed">
            <p className="mb-2">
              Вопросы по работе сервиса, предложения по улучшению и сообщения об
              ошибках направляйте администратору развёртывания.
            </p>
            <p className="text-sm text-gray-600">
              Продукт развивается; обратная связь помогает приоритизировать
              доработки интерфейса и логики агентов.
            </p>
          </div>
        </section>
      </main>

      <footer className="relative z-10 py-5 border-t border-gray-200/80 bg-white/60 backdrop-blur-sm mt-auto">
        <p className="text-xs text-gray-500 text-center max-w-3xl mx-auto px-4">
          Вспомогательный инструмент. Не заменяет очный приём и осмотр врача.
        </p>
      </footer>
    </div>
  );
};

export default AboutPage;
