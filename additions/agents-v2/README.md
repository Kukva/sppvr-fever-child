# СППВР «Лихорадящий ребёнок» — пакет для ML

## ⚠️ Статус: ЧЕРНОВИК, не провалидирован

Все SKILL.md написаны на основе российских КР (Союз педиатров России, Минздрав РФ) и открытых клинических источников. **Клиническая валидация педиатром ещё не проведена.** Не использовать на реальных пациентах до завершения валидации.

---

## Что здесь есть

```
sppvr_package/
├── README.md               ← этот файл
├── test_cases.md           ← 10 тестовых кейсов с ожидаемыми ответами
└── skills/
    ├── intake/             ← сбор данных пациента
    ├── triage/             ← маршрутизация по 4 зонам
    ├── data_completeness_checker/  ← достаточность данных
    ├── hypothesis_generator/       ← дифференциальные гипотезы
    ├── infection/          ← инфекционные причины
    ├── immune/             ← ревматология / иммунология
    ├── rare_disease/       ← аутовоспалительные синдромы
    ├── oncology/           ← онкогематология
    ├── synthesis/          ← итоговое заключение
    └── question/           ← уточняющие вопросы
```

---

## Как встроить в граф (Fever Routing / fiber)

### Шаг 1 — скопировать SKILL.md
Положить каждую папку из `skills/` в `backend/skills/` репозитория. Структура уже совпадает с форматом `REGISTERED_AGENT_NAMES` в `config.py`.

```bash
cp -r skills/* /path/to/fiber/backend/skills/
```

### Шаг 2 — проверить config.py
Убедиться что все 10 агентов присутствуют в `REGISTERED_AGENT_NAMES`:
```python
REGISTERED_AGENT_NAMES = [
    "intake",
    "data_completeness_checker",
    "triage",
    "hypothesis_generator",
    "question",
    "infection",
    "immune",
    "oncology",
    "rare_disease",
    "synthesis",
]
```

### Шаг 3 — первый запуск только на 5 агентах
Для начала запустить только базовую цепочку (ЛБОИ-сценарий):
```
intake → data_completeness_checker → triage → infection → synthesis
```
Остальные агенты (immune, oncology, rare_disease, hypothesis_generator) добавить после того как базовая цепочка проходит тестовые кейсы 1–5 из test_cases.md.

### Шаг 4 — прогнать тестовые кейсы
Файл `test_cases.md` содержит 10 кейсов с ожидаемыми ответами.

**Критический минимум перед выходом на врачей:**
- Кейс 2 (петехии → скорая) — нулевая толерантность
- Кейс 4 (ребёнок 7 недель → госпитализация) — нулевая толерантность  
- Кейс 7 (цитопения → онкология) — нулевая толерантность

Если хотя бы один из трёх не проходит — на врачей не выходим.

---

## Формат входных данных (для intake)

Система принимает свободный текст или структурированный JSON:

```json
{
  "age_months": 18,
  "weight_kg": 11,
  "sex": "М",
  "fever": {
    "max_temp": 39.4,
    "duration_days": 2,
    "responds_to_antipyretics": true,
    "pattern": "constant"
  },
  "symptoms": {
    "catarrhal": false,
    "rash": "no",
    "gi": false,
    "dysuria": false,
    "lymphadenopathy": false,
    "hepatosplenomegaly": false,
    "altered_consciousness": false,
    "refuses_fluids": false
  },
  "history": {
    "vaccination_status": "complete",
    "immunodeficiency": false,
    "chronic_disease": "нет",
    "prior_similar_episodes": false,
    "recent_travel": false,
    "contact_sick": false,
    "antibiotics_taken": false
  }
}
```

---

## Что НЕ входит в этот пакет

- Интерфейс для врача — делается отдельно
- Интеграция с МИС — следующий этап
- Валидированные промпты — нужна проверка педиатром
- Агент `rheumatology_deep` — запланирован, материал есть (PDF + PPT от ревматологов), пишется после валидации базовой цепочки

---

## Дедлайн

Массовое тестирование на врачах — **15 мая 2026**.

Контакт по клинической части — [имя клинического продакта].
