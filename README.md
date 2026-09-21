# IMDS Medical Document Service

Локальный модуль медицинских документов для MIS.

## Что работает

- постоянные DOCX-шаблоны с версиями;
- назначение шаблонов по специальности / врачу / филиалу / типу приема;
- реальный список пациентов из upstream MIS;
- кабинет врача;
- запись разговора через браузерный микрофон;
- реальный внешний/self-hosted STT + speaker diarization pipeline;
- разделение реплик на `doctor` / `patient`;
- AI-черновики полей выбранного протокола осмотра;
- врач вручную принимает или редактирует AI-черновик;
- МКБ-10 и клинические протоколы;
- DOCX → PDF через LibreOffice;
- SHA-256 и signed QR;
- PDF/DOCX скачивание и печать;
- финальный документ не перегенерируется после завершения.

В коде нет фиктивных пациентов и синтетического AI fallback.

## 1. Локальный запуск

```bash
git clone https://github.com/imds-mis/-.git
cd -
git checkout feat/medical-document-service
cp .env.example .env
```

Заполните в `.env` реальные значения:

```env
MIS_UPSTREAM_URL=https://mis.imds.kz
MIS_AUTH_TOKEN=<действующий bearer token>

SPEECH_PIPELINE_URL=http://host.docker.internal:9000

LLM_BASE_URL=http://host.docker.internal:11434/v1
LLM_API_KEY=<ключ вашего real/self-hosted endpoint>
LLM_MODEL=<имя модели>

QR_SIGNING_SECRET=<длинная случайная строка>
```

Затем:

```bash
docker compose up --build
```

Открыть:

- Кабинет врача: http://localhost:5173/doctor
- Настройки шаблонов: http://localhost:5173/settings/templates
- API health: http://localhost:8080/healthz

## 2. Реальный MIS контекст

В верхней панели локального UI указываются реальные:

- Tenant UUID
- User UUID
- Branch UUID
- Practitioner UUID
- Specialty code

Пациенты после этого загружаются из:

```text
GET https://mis.imds.kz/api/products/mis/v1/patients?branch_id=<branch>
```

через backend proxy. `MIS_AUTH_TOKEN` никогда не передается в браузер.

## 3. Настройки → Шаблоны

1. Откройте http://localhost:5173/settings/templates
2. Укажите реальный MIS контекст.
3. Выберите DOCX.
4. Укажите название.
5. Проверьте JSON полей.
6. Нажмите **Загрузить шаблон**.
7. После загрузки нажмите **Опубликовать**.

Исходный DOCX остается сохраненным. Изменения выпускаются новой версией. Старые документы пациентов остаются на старой версии.

### Placeholder-ы DOCX

Пример:

```text
Пациент: {{patient.full_name}}
Жалобы: {{complaints}}
Анамнез: {{anamnesis_morbi}}
Объективный статус: {{objective_status}}
Диагноз: {{diagnosis_text}}
Рекомендации: {{recommendations}}
```

## 4. Кабинет врача

1. Откройте http://localhost:5173/doctor
2. Укажите реальные tenant/user/branch/practitioner UUID.
3. Выберите пациента из MIS.
4. Выберите опубликованный шаблон.
5. Нажмите **Начать прием и включить микрофон**.
6. Разрешите доступ к микрофону.
7. Аудио отправляется чанками в real speech pipeline.
8. На экране появляются реплики **Врач / Пациент**.
9. LLM возвращает предложения только по полям шаблона.
10. Врач нажимает **Принять AI-черновик** либо вводит текст сам.
11. Выбирает МКБ-10 и клинический протокол.
12. Нажимает **Завершить прием и сформировать документ**.
13. После этого доступны PDF, DOCX, печать и QR-проверка.

## 5. Контракт speech pipeline

`SPEECH_PIPELINE_URL` должен предоставлять:

### POST /transcribe

Raw audio body.

Headers:

```text
Content-Type: audio/webm
X-Session-ID: <uuid>
X-Chunk-ID: <unique-id>
```

Ответ:

```json
{
  "turns": [
    {
      "speaker": "doctor",
      "text": "Что вас беспокоит?",
      "confidence": 0.97,
      "started_ms": 0,
      "ended_ms": 2400
    },
    {
      "speaker": "patient",
      "text": "Боль внизу живота два дня.",
      "confidence": 0.95,
      "started_ms": 2600,
      "ended_ms": 6100
    }
  ]
}
```

### POST /finalize

Header:

```text
X-Session-ID: <uuid>
```

Возвращает финальную speaker-separated расшифровку всего приема.

Если speech provider не настроен, сервис возвращает явный 503. Фиктивной расшифровки нет.

## 6. LLM extraction

`LLM_BASE_URL` должен быть OpenAI-compatible и поддерживать:

```text
POST /chat/completions
```

Модель получает:

- разрешенные поля текущего шаблона;
- transcript;
- системные данные пациента;
- инструкции не придумывать отсутствующие сведения.

Результат хранится только как suggestion, пока врач его не примет.

## 7. Безопасность

- upstream MIS token остается только на backend;
- QR не содержит PHI;
- finalized PDF/DOCX immutable;
- tenant/branch фильтрация применяется к медицинским документам и visit sessions;
- raw audio не сохраняется модулем документов;
- публичный QR endpoint проверяет token hash и SHA-256 сохраненного PDF;
- локальные UUID должны быть реальными данными вашей MIS.

## 8. Тесты

Backend:

```bash
PYTHONPATH=. pytest -q
```

Frontend:

```bash
cd web
npm install
npm test
npm run build
```
