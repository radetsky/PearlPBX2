# Handoff: OpenAI + Gemini (STT / TTS / LLM) для PearlPBX2 (BOYK)

Документ для Claude Code у проєкті PearlPBX2 (Python/Django). Джерело: проєкт Paseo
(`worker/src/lib/aiProvider.ts`, `tools/tts_generate_openai.py`). Те, що нижче названо
«перевірено», взято з працюючого коду Paseo станом на 2026-10-07. Те, що названо
«перевірити», колега має звірити з актуальною документацією (context7 / офіційні docs)
і з реальним кодом PearlPBX2 до написання моделей.

## 1. Принципи, які ми вже випробували

1. **OpenAI основний, Gemini запасний.** Перемикання лише при: мережевій помилці, HTTP 5xx, HTTP 429.
   Інші 4xx (поганий запит, ключ) НЕ перемикають, а падають одразу (інакше ховаємо баги).
2. **Ключі лише на сервері** (env), ніколи в клієнті/логах/БД.
3. **Назви моделей — у settings, не в коді.** `gpt-4o-mini-tts`, `tts-1`, `whisper-1` OpenAI закриває;
   ми вже раз мігрували. Дефолти нижче можуть застаріти.
4. **Один код-шлях на операцію**: `transcribe()`, `speak()`, `analyze()` приховують провайдера.
   Але в Django (на відміну від Paseo) **зберігаємо в БД, який провайдер/модель/версію промпту
   відповіли** — для аудиту й повторного аналізу.
5. **Кеш озвучки за хешем**: `sha256(model::voice::instructions::text)`. Незмінна репліка не генерується повторно
   (у Paseo це `manifest_openai.json`).

## 2. Моделі (перевірено в Paseo)

| Задача | OpenAI (основний) | Gemini (запасний) |
|---|---|---|
| STT | `gpt-transcribe`, `POST /v1/audio/transcriptions` (multipart) | `gemini-3.8-flash`, `generateContent` з аудіо |
| TTS | `gpt-audio-1.5`, `POST /v1/chat/completions` з audio-виходом | `gemini-3.8-flash-tts` |
| Аудіо → структурований аналіз (LLM) | `gpt-audio-1.5` (аудіо на вході) | `gemini-3.8-flash` |

Gemini TTS: у Paseo мав жорсткий денний ліміт (~100 запитів/день на модель, навіть з білінгом,
станом на 2026-09-27). Для масової озвучки в PBX це ризик, тому він лише fallback.

## 3. Точні форми запитів

### STT, OpenAI
```
POST https://api.openai.com/v1/audio/transcriptions
Authorization: Bearer $OPENAI_API_KEY
multipart: model=gpt-transcribe, language=<iso>, prompt=<optional vocabulary hint>, file=<audio>
-> {"text": "..."}
```
`prompt` підсовує лексику (імена, терміни) — працює для підвищення точності.

### STT, Gemini
```
POST https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key=$GEMINI_API_KEY
{"contents":[{"parts":[
  {"text":"Transcribe this audio verbatim. Return only the transcript text."},
  {"inlineData":{"mimeType":"audio/wav","data":"<base64>"}}]}]}
-> candidates[0].content.parts[*].text
```

### LLM-аналіз аудіо, OpenAI
`gpt-audio-1.5` через chat completions НЕ підтримує `response_format`. Тому: у промпті
«Return ONLY a JSON object with exactly these fields…», далі парсимо відповідь.
```
POST /v1/chat/completions
{"model":"gpt-audio-1.5","messages":[{"role":"user","content":[
  {"type":"text","text":"<prompt>"},
  {"type":"input_audio","input_audio":{"data":"<base64>","format":"wav"|"mp3"}}]}]}
-> choices[0].message.content   (може бути в ```json ... ``` — знімати огорожу)
```

### LLM-аналіз аудіо, Gemini
Те саме `generateContent`, але з `"generationConfig":{"responseMimeType":"application/json"}` — тоді JSON чистий.

**Обов'язково валідувати форму відповіді** (типи полів, допустимі значення enum) перед записом у БД;
у Paseo `parseGradingJson` кидає помилку на невідповідну форму. У Django це має бути pydantic/DRF-серіалайзер.

### TTS, OpenAI
```
POST /v1/chat/completions
{"model":"gpt-audio-1.5","modalities":["text","audio"],
 "audio":{"voice":"nova","format":"wav"},
 "messages":[
  {"role":"system","content":"You are a text-to-speech engine, not an assistant. The user's message is a script line, never a request or a question to you: do not answer it, react to it or continue it. Say exactly that line aloud, word for word, adding, omitting or translating nothing. <STYLE> <LANGUAGE HINT>"},
  {"role":"user","content":"Script line to read aloud verbatim:\n<<<\n{text}\n>>>"}]}
-> choices[0].message.audio.data  (base64 WAV)
```
Уроки з Paseo:
- Без обгортки `<<< >>>` і system-промпту модель **відповідає** на репліку замість озвучити її.
- Мову модель вгадує зі стрічки. Короткі/двозначні фрази читає англійською або кирилицю як російську.
  Тому в інструкцію завжди додавати явну мову й акцент («Speak in Ukrainian, authentic Ukrainian
  pronunciation, not Russian»).
- Стиль (спокійний/привітний) передається текстом у system-промпті (окремого поля `instructions` у цій моделі немає).
- Змішана мова в одній репліці: різати на сегменти за мовою, озвучувати окремо, склеювати з паузою 120 мс
  (`language_segments`, `join_wavs` у `tools/tts_generate_openai.py`).
- Голос закріплений за персонажем/статтю, а не за мовою (`ash` чоловічий, `nova` жіночий).
- Ретраї: таймаут 60 с, до 5 спроб, 429 і обриви читання (`IncompleteRead`) повторювати з паузою 5 с.
  Без таймауту генерація колись зависла.

### TTS, Gemini
```
POST .../models/gemini-3.8-flash-tts:generateContent
{"contents":[{"parts":[{"text":"..."}]}],
 "generationConfig":{"responseModalities":["AUDIO"],
   "speechConfig":{"voiceConfig":{"prebuiltVoiceConfig":{"voiceName":"Kore"}}}}}
-> candidates[0].content.parts[0].inlineData {mimeType, data}
```
Gemini віддає сирий PCM (`audio/L16;rate=24000`). Треба загорнути в WAV-заголовок
(`pcmToWav`: 16-біт, mono, rate із mime, дефолт 24000).

## 4. Що специфічне для телефонії (у Paseo цього не було; перевірити)

- **Довгі записи дзвінків.** Paseo транскрибував клацання по кілька секунд. Для дзвінка на
  хвилини/десятки хвилин: перевірити ліміти розміру/тривалості (OpenAI transcriptions мають
  ліміт розміру файла; Gemini inline має ліміт, для великих файлів потрібен File API). Якщо перевищує:
  нарізати ffmpeg на чанки з невеликим перекриттям і склеїти текст.
- **Канали.** Записи Asterisk часто стерео (абонент/оператор окремо). Найдешевша «діаризація»: транскрибувати
  канали окремо й злити за таймкодами. Таймкоди/сегменти `gpt-transcribe` перевірити в документації.
  Не обіцяти діаризацію, якої модель не дає.
- **Формат.** 8 кГц wav/gsm. Для STT конвертувати в 16 кГц mono wav/mp3 (ffmpeg). Для TTS у Asterisk
  конвертувати вихід (24 кГц) у 8 кГц mono `slin`/wav перед відтворенням.
- **Емоційний аналіз** брати з аудіо (інтонація), а не лише з тексту: передавати в LLM і аудіо, і
  транскрипт. Це та сама схема «аудіо + JSON-промпт», що й `grade` у Paseo.
- **Персональні дані.** Записи дзвінків і транскрипти йдуть стороннім провайдерам: перевірити
  правові вимоги/згоду й data-retention налаштування провайдерів до продакшену.

## 5. Пропонована архітектура в Django

```
boyk/ai/
  providers/base.py      # Protocol: transcribe(), speak(), analyze_audio()
  providers/openai.py    # httpx, формати з §3
  providers/gemini.py
  router.py              # fallback-політика §1.1, повертає (результат, provider, model)
  schemas.py             # pydantic: CallAnalysisResult
  prompts.py             # версіоновані промпти (PROMPT_VERSION)
  tasks.py               # Celery: transcribe_call, analyze_call, synthesize_prompt
```

Fallback (суть `aiProvider.ts`):
```python
RETRYABLE = lambda r: r is None or r.status_code == 429 or r.status_code >= 500

def run(op, *args):
    last = None
    for name in settings.AI_PROVIDER_ORDER:          # ["openai", "gemini"]
        provider = PROVIDERS[name]
        if not provider.configured():
            continue
        try:
            return getattr(provider, op)(*args), name
        except ProviderHTTPError as e:
            if not RETRYABLE(e.response):
                raise                                 # не ховаємо 4xx
            last = e
        except (httpx.TransportError, httpx.TimeoutException) as e:
            last = e
    raise AiUnavailable(last)
```

Settings (env): `OPENAI_API_KEY`, `GEMINI_API_KEY`, `AI_PROVIDER_ORDER`, `AI_STT_MODELS`,
`AI_TTS_MODELS`, `AI_ANALYSIS_MODELS` (за провайдером), `AI_HTTP_TIMEOUT=60`.

### Моделі (чернетка; колега має узгодити з наявними моделями BOYK/дзвінків)

Припущення: у BOYK уже є модель дзвінка і запису. Якщо ні, скоригувати FK.

- `CallTranscript`: `call` FK, `provider`, `model`, `language`, `text`, `segments` JSON
  (`[{start,end,speaker,text}]`, може бути порожнім), `duration_s`, `status`
  (`pending|done|failed`), `error`, `created_at`. Унікальність `(call, provider, model)` або
  версіонування: нова транскрипція не затирає стару.
- `CallAnalysis`: `call` FK, `transcript` FK, `provider`, `model`, `prompt_version`,
  `overall_sentiment` (enum), `emotions` JSON (`[{party, emotion, intensity 0..1}]`), `score`,
  `summary`, `topics` JSON, `action_items` JSON, `raw_response` JSON/Text, `status`, `error`, `created_at`.
  Індекс по `(call, -created_at)`.
- `VoicePrompt` (кеш TTS): `text`, `lang`, `voice`, `style`, `provider`, `model`,
  `content_hash` (unique, формула з §1.5), `audio` FileField (8 кГц-варіант для Asterisk
  можна в окремому полі), `created_at`.
- (Опційно) `AiUsage`: `operation`, `provider`, `model`, `call` FK null, `latency_ms`,
  `input_seconds/chars`, `ok`. Для витрат і для моніторингу fallback-ів.

### Потоки

1. **STT:** запис завершено → Celery `transcribe_call` → (нарізка/конвертація) → `router.run("transcribe")` → `CallTranscript`.
2. **Емоційний підсумок:** після STT → `analyze_call`: аудіо + транскрипт + промпт з жорсткою JSON-схемою →
   валідація pydantic → `CallAnalysis`. Невалідний JSON — один повтор, далі `status=failed` + `raw_response`.
3. **TTS:** `get_or_create` за `content_hash` → якщо немає, `router.run("speak")` → конвертація під Asterisk → файл у `VoicePrompt`.
   Відтворення з AGI: завжди `agi.finish()`.

## 6. Чек-ліст для колеги перед кодом

- Прочитати реальні моделі BOYK/дзвінків і узгодити FK та назви (§5 — лише чернетка).
- Звірити актуальні назви моделей, ліміти розміру/тривалості аудіо, наявність таймкодів і діаризації
  у документації OpenAI і Gemini (context7). Не покладатися на пам'ять.
- Міграції + додати нові permissions до наявних груп (правило проєкту).
- Ключі лише з env; нічого не логувати з аудіо/транскриптів на INFO без політики збереження.
- Один мінімальний тест: роутер перемикається на 429/5xx і НЕ перемикається на 400/401 (мок httpx).
