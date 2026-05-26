# Соответствие агентов и Yandex AI Studio (prompt IDs)

В проекте используются те же **prompt ID** агентов, что и в интерфейсе Yandex AI Studio. Ниже — соответствие и примеры вызова через **Responses API** (prompt по id).

**Два варианта API Yandex:**

| API | URL | Использование в проекте |
|-----|-----|--------------------------|
| **LLM API** (Chat Completions) | `https://llm.api.cloud.yandex.net/v1` | Да — вызовы через `chat.completions.create()` с системным промптом из SKILL.md / встроенным |
| **Responses API** (prompt по id) | `https://ai.api.cloud.yandex.net/v1` | Нет — промпты хранятся в облаке, вызов по id |

ID агентов в `app/config.py` совпадают с prompt ID в Yandex AI Studio. При необходимости можно перейти на Responses API и вызывать агентов по id.

---

## Prompt ID агентов (config → Yandex)

| Агент в проекте | Prompt ID (config) | Переменная в config |
|-----------------|--------------------|----------------------|
| HYPOTHESIS_GENERATOR | `YOUR_HYPOTHESIS_AGENT_ID` | `hypothesis_generator_agent_id` |
| DATA_COMPLETENESS_CHECKER | `YOUR_DATA_COMPLETENESS_AGENT_ID` | `data_completeness_checker_agent_id` |
| SYNTHESIS | `YOUR_SYNTHESIS_AGENT_ID` | `synthesis_agent_id` |
| INTAKE | `YOUR_INTAKE_AGENT_ID` | `intake_agent_id` |
| TRIAGE | `YOUR_TRIAGE_AGENT_ID` | `triage_agent_id` |
| QUESTION | `YOUR_QUESTION_AGENT_ID` | `question_agent_id` |
| INFECTION | `YOUR_INFECTION_AGENT_ID` | `infection_agent_id` |
| IMMUNE | `YOUR_IMMUNE_AGENT_ID` | `immune_agent_id` |
| ONCOLOGY | `YOUR_ONCOLOGY_AGENT_ID` | `oncology_agent_id` |
| RARE_DISEASE | `YOUR_RARE_DISEASE_AGENT_ID` | `rare_disease_agent_id` |

---

## Примеры вызова через Responses API (Yandex)

Базовые настройки: **base_url** `https://ai.api.cloud.yandex.net/v1`, **project** `YOUR_FOLDER_ID`, аутентификация по API-ключу.

### HYPOTHESIS_GENERATOR

```python
import openai

client = openai.OpenAI(
    api_key="<API_key_value>",
    base_url="https://ai.api.cloud.yandex.net/v1",
    project="YOUR_FOLDER_ID"
)

response = client.responses.create(
    prompt={"id": "YOUR_HYPOTHESIS_AGENT_ID"},
    input="some message",
)
print(response.output_text)
```

### DATA_COMPLETENESS_CHECKER

```python
import openai

client = openai.OpenAI(
    api_key="<API_key_value>",
    base_url="https://ai.api.cloud.yandex.net/v1",
    project="YOUR_FOLDER_ID"
)

response = client.responses.create(
    prompt={"id": "YOUR_DATA_COMPLETENESS_AGENT_ID"},
    input="some message",
)
print(response.output_text)
```

### SYNTHESIS

```python
import openai

client = openai.OpenAI(
    api_key="<API_key_value>",
    base_url="https://ai.api.cloud.yandex.net/v1",
    project="YOUR_FOLDER_ID"
)

response = client.responses.create(
    prompt={"id": "YOUR_SYNTHESIS_AGENT_ID"},
    input="some message",
)
print(response.output_text)
```

### QUESTION AGENT

```python
import openai

client = openai.OpenAI(
    api_key="<API_key_value>",
    base_url="https://ai.api.cloud.yandex.net/v1",
    project="YOUR_FOLDER_ID"
)

response = client.responses.create(
    prompt={"id": "YOUR_QUESTION_AGENT_ID"},
    input="some message",
)
print(response.output_text)
```

### RARE DISEASE AGENT

```python
import openai

client = openai.OpenAI(
    api_key="<API_key_value>",
    base_url="https://ai.api.cloud.yandex.net/v1",
    project="YOUR_FOLDER_ID"
)

response = client.responses.create(
    prompt={"id": "YOUR_RARE_DISEASE_AGENT_ID"},
    input="some message",
)
print(response.output_text)
```

### ONCOLOGY AGENT

```python
import openai

client = openai.OpenAI(
    api_key="<API_key_value>",
    base_url="https://ai.api.cloud.yandex.net/v1",
    project="YOUR_FOLDER_ID"
)

response = client.responses.create(
    prompt={"id": "YOUR_ONCOLOGY_AGENT_ID"},
    input="some message",
)
print(response.output_text)
```

### IMMUNE AGENT

```python
import openai

client = openai.OpenAI(
    api_key="<API_key_value>",
    base_url="https://ai.api.cloud.yandex.net/v1",
    project="YOUR_FOLDER_ID"
)

response = client.responses.create(
    prompt={"id": "YOUR_IMMUNE_AGENT_ID"},
    input="some message",
)
print(response.output_text)
```

---

В текущей реализации (`app/core/ai_studio.py`) используется **LLM API** (`https://llm.api.cloud.yandex.net/v1`) и `chat.completions.create()` с системным промптом из SKILL.md или встроенным. Чтобы вызывать агентов через **Responses API** по prompt id, нужно добавить отдельный путь в `YandexAIStudioClient` и при необходимости переключать его через конфиг.
