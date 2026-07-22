# Інтеграція з CRM

PearlPBX2 повідомляє зовнішні CRM-системи про дзвінки двома способами:

- **веб-хуки** — сервіс dashboard сам надсилає `POST`-запит на URL, вказаний у CRM, коли відбувається вхідний дзвінок, оператор відповідає на дзвінок, дзвінок завершується, або дзвінок пропущено в черзі;
- **REST API** — CRM за токеном забирає файл запису розмови за детермінованим посиланням, яке приходить у тілі веб-хука.

Функціонал повністю опціональний: поки в адмінці не створено жодного активного запису `Webhook`, нічого не надсилається і ніякого навантаження на систему немає.

## Зміст

1. [Як це працює](#1-як-це-працює)
2. [Налаштування веб-хука в адмінці](#2-налаштування-веб-хука-в-адмінці)
3. [Формати повідомлень (payload)](#3-формати-повідомлень-payload)
4. [Записи розмов: посилання та завантаження через API](#4-записи-розмов-посилання-та-завантаження-через-api)
5. [Перевірка підпису запиту](#5-перевірка-підпису-запиту)
6. [Кастомний шаблон тіла запиту](#6-кастомний-шаблон-тіла-запиту)
7. [Поведінка при збоях доставки](#7-поведінка-при-збоях-доставки)
8. [Приклад: мінімальний обробник веб-хуків](#8-приклад-мінімальний-обробник-веб-хуків)

---

## 1. Як це працює

Джерелом істини про стан дзвінків є сервіс `services/dashboard/dashboard_listener.py` — він слухає події Asterisk AMI в реальному часі. Саме він і надсилає веб-хуки, у чотирьох випадках:

| Подія          | Коли спрацьовує | Умова |
|----------------|------------------|-------|
| `call.incoming` | новий дзвінок заходить у налаштований контекст, або приєднується до налаштованої черги | контекст/черга дзвінка збігається з фільтром веб-хука |
| `call.answered` | оператор підняв слухавку дзвінка з черги (AMI-подія `AgentConnect`) | черга дзвінка збігається з фільтром веб-хука, і в ньому увімкнено «Send answered» |
| `call.missed`   | абонент поклав слухавку, не дочекавшись оператора в черзі | черга дзвінка збігається з фільтром веб-хука, і в ньому увімкнено «Send missed» |
| `call.ended`    | канал завершує роботу (hangup) | **лише для дзвінків, про які раніше було надіслано `call.incoming`** |

Важливий нюанс: `call.ended` навмисно надсилається **тільки** для дзвінків, про які CRM вже було проінформовано подією `call.incoming`. Система запам'ятовує в Redis (`webhook:notified:{uniqueid}`, TTL 2 години), яким веб-хукам було повідомлено про початок дзвінка, і при завершенні дзвінка перевіряє цей запис. Це гарантує:
- CRM ніколи не отримає «дзвінок завершено» для дзвінка, про який їй не повідомляли;
- CRM ніколи не отримає цю подію двічі.

Події `call.missed` і `call.answered`, навпаки, **не** вимагають попереднього `call.incoming` — і пропущений, і відповілий дзвінок вартий окремого запису в CRM, навіть якщо цей веб-хук не підписаний на вхідні дзвінки. Якщо дзвінок усе ж було анонсовано (`call.incoming` для нього надсилався), обидві події додатково позначають внутрішній маркер: пропуск ставить `missed: true`, а відповідь оператора записує, хто саме відповів (`answered_by_member`, `answered_by_interface`). Подальший `call.ended` буде містити всі ці поля — так CRM може пов'язати всі події одного дзвінка без додаткових запитів.

Подія `call.answered` існує лише для дзвінків через чергу — вона відповідає AMI-події Asterisk `AgentConnect`, яка не виникає поза чергами. Тому увімкнути «Send answered» можна лише за наявності хоча б однієї вибраної черги (так само, як і для `send_missed`).

## 2. Налаштування веб-хука в адмінці

Веб-хуки налаштовуються в Django admin, модель **Webhooks** (доступно тільки суперкористувачу). Кожен рядок — окрема незалежна інтеграція, тож можна одночасно підключити кілька різних CRM.

Поля форми:

| Поле | Опис |
|------|------|
| `is_active` | вкл/викл цього веб-хука без видалення налаштувань |
| `url` | адреса, куди CRM приймає `POST`-запити |
| `send_incoming` / `send_ended` / `send_missed` / `send_answered` | на які події підписаний цей веб-хук. `send_ended` вимагає увімкненого `send_incoming` (див. п.1). `send_missed` і `send_answered` кожен вимагає вибрану хоча б одну чергу |
| `contexts` | список контекстів діалплану — вхідні дзвінки в ці контексти запускають веб-хук |
| `queues` | список черг — дзвінки, що приєднались до цих черг, запускають веб-хук |
| `headers` | додаткові HTTP-заголовки у форматі JSON, наприклад `{"X-Api-Key": "..."}` |
| `secret` | опціональний спільний секрет для підпису тіла запиту (HMAC-SHA256), див. п.5 |
| `timeout` | таймаут одної спроби доставки, секунди (за замовчуванням 5) |
| `retries` | скільки додаткових спроб робити після невдачі (за замовчуванням 1) |
| `payload_template` | кастомний JSON-шаблон тіла запиту, див. п.6. При створенні нового веб-хука форма адмінки автоматично заповнює це поле повним прикладом з усіма доступними плейсхолдерами — можна прибрати зайве або очистити поле повністю, щоб повернутись до вбудованого стандартного payload |

**Обов'язково** потрібно вибрати хоча б один контекст або чергу — інакше форма не збережеться: саме це визначає, для яких «сценаріїв» дзвінків спрацьовує веб-хук.

Зміни в адмінці застосовуються **без перезапуску сервісу**: при кожному збереженні Django серіалізує активні веб-хуки в Redis-ключ `webhooks:config`, а `dashboard_listener` перечитує цей ключ при старті й на кожному циклі перевірки здоров'я (кожні 30 секунд). Якщо потрібно примусово синхронізувати конфіг вручну (наприклад, після втрати даних Redis):

```bash
python manage.py sync_webhooks
```

## 3. Формати повідомлень (payload)

Усі запити — `POST` з тілом `application/json`.

### `call.incoming` — початок дзвінка

```json
{
  "event": "call.incoming",
  "uniqueid": "1753000000.42",
  "caller_id_num": "380501234567",
  "caller_id_name": "Customer",
  "exten": "s",
  "context": "incoming",
  "queue": null,
  "timestamp": "2026-07-21T18:58:51.811673",
  "recording_expected": null,
  "recording_url": "https://pbx.example.com/api/v1/recordings/1753000000.42/"
}
```

### `call.answered` — оператор відповів на дзвінок у черзі

```json
{
  "event": "call.answered",
  "uniqueid": "1753000000.42",
  "caller_id_num": "380501234567",
  "caller_id_name": "Customer",
  "queue": "support",
  "member_name": "Оператор Петренко",
  "member_interface": "PJSIP/101",
  "member_number": "101",
  "ringtime": "3500",
  "holdtime": "18",
  "timestamp": "2026-07-21T18:58:51.812900"
}
```

`ringtime` (мілісекунди) і `holdtime` (секунди) — прямо з AMI-події Asterisk `AgentConnect`: скільки дзвонило оператору і скільки клієнт чекав у черзі до з'єднання.

### `call.ended` — завершення дзвінка

```json
{
  "event": "call.ended",
  "uniqueid": "1753000000.42",
  "caller_id_num": "380501234567",
  "caller_id_name": "Customer",
  "exten": "s",
  "context": "incoming",
  "queue": null,
  "timestamp": "2026-07-21T18:58:51.814936",
  "duration": 42,
  "cause": "16",
  "cause_txt": "Normal Clearing",
  "answered_time": "38",
  "billsec": "38",
  "missed": false,
  "answered_by_member": "Оператор Петренко",
  "answered_by_interface": "PJSIP/101",
  "recorded": true,
  "recording_url": "https://pbx.example.com/api/v1/recordings/1753000000.42/",
  "recording_file": "/var/spool/asterisk/monitor/2026/07/21/x.wav"
}
```

`answered_by_member` / `answered_by_interface` заповнюються, якщо для цього дзвінка перед завершенням прийшла подія `call.answered` — інакше обидва поля `null` (наприклад, дзвінок був пропущений, або взагалі не проходив через чергу).

### `call.missed` — пропущений дзвінок у черзі

```json
{
  "event": "call.missed",
  "uniqueid": "1753000000.42",
  "caller_id_num": "380501234567",
  "queue": "support",
  "wait_time": 21,
  "timestamp": "2026-07-21T18:58:51.813698"
}
```

Поля, не застосовні до конкретної події, приходять як `null` (наприклад, `queue` для дзвінка, класифікованого за контекстом, а не за чергою).

## 4. Записи розмов: посилання та завантаження через API

`recording_url` у кожному payload — це **детерміноване** посилання, побудоване з `uniqueid` дзвінка. Його можна обчислити ще до завершення дзвінка, тому воно є вже в `call.incoming` — як прогноз:

- `recording_expected` — очікування, чи буде дзвінок записаний, зняте зі значення змінної Asterisk `MIXMONITOR` у момент події. Для дзвінків, класифікованих за чергою, це значення зазвичай уже відоме (AGI, що приймає рішення про запис, виконується до `Queue()`). Для дзвінків, класифікованих лише за контекстом, подія `call.incoming` летить раніше за цей AGI, тому значення — `null` (невідомо).
- У `call.ended` поле `recorded` — уже підтверджений факт (`true`/`false`, або `null`, якщо інформація була втрачена, наприклад через переперепідключення AMI посеред дзвінка). `recording_url` заповнюється лише коли `recorded: true`.

Сам файл CRM забирає окремим запитом до REST API (не з веб-хука):

```bash
curl -H "Authorization: Token <ваш-токен>" \
  https://pbx.example.com/api/v1/recordings/1753000000.42/ \
  -o call.wav
```

Деталі ендпоінта:

| | |
|---|---|
| Метод | `GET /api/v1/recordings/<uniqueid>/` |
| Автентифікація | токен DRF (`Authorization: Token <ключ>`), як і решта REST API PearlPBX2 |
| Права доступу | без деталізації — будь-який дійсний токен API має доступ до будь-якого запису (так само, як до інших ендпоінтів API) |
| `200` / `206` | аудіофайл (`audio/wav` або `audio/mpeg`); підтримуються `Range`-запити для потокового відтворення |
| `?download=1` | форсує завантаження файлу (`Content-Disposition: attachment`) замість inline-відповіді |
| `401` | токен не передано або він недійсний |
| `404` | запису ще немає (дзвінок не записувався, або файл ще не встиг з'явитись на диску) |

Токен видається так само, як і для решти API — через Django admin (`Auth Token`) або командою:

```bash
python manage.py drf_create_token <username>
```

> Людям (не CRM) для прослуховування в браузері доступне окреме, захищене сесією посилання `/reports/audio/uid/{uniqueid}/` у веб-інтерфейсі PearlPBX2 — це той самий файл, інший спосіб автентифікації.

## 5. Перевірка підпису запиту

Якщо у веб-хука заповнено поле `secret`, кожен запит додатково містить заголовок:

```
X-PearlPBX-Signature: sha256=<hex-підпис HMAC-SHA256 сирого тіла запиту>
```

Приклад перевірки підпису (Python):

```python
import hashlib
import hmac

def verify(secret: str, body: bytes, header_value: str) -> bool:
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header_value)
```

Приклад на Node.js:

```javascript
const crypto = require("crypto");

function verify(secret, rawBody, headerValue) {
  const expected =
    "sha256=" + crypto.createHmac("sha256", secret).update(rawBody).digest("hex");
  return crypto.timingSafeEqual(Buffer.from(expected), Buffer.from(headerValue));
}
```

**Важливо:** підпис рахується від сирих байтів тіла запиту — перевіряйте його до будь-якого парсингу JSON.

## 6. Кастомний шаблон тіла запиту

За замовчуванням надсилається стандартний payload (див. п.3). Якщо CRM очікує інший формат полів, у полі `payload_template` можна задати власний JSON-об'єкт. Рядкові значення можуть містити плейсхолдери `${назва_змінної}`:

При створенні нового веб-хука в адмінці поле **Payload template** уже заповнене — там повний приклад з усіма доступними плейсхолдерами (по одному на кожне поле). Це зроблено навмисно, щоб одразу бачити весь набір опцій, а не звірятися з документацією. Просто видаліть непотрібні рядки, або залиште все як є — для полів, не притаманних конкретній події (наприклад, `${ringtime}` у `call.incoming`), система підставить порожній рядок, а не покаже буквальний текст плейсхолдера. Якщо кастомний формат не потрібен узагалі — очистіть поле повністю (порожньо/`null`), і надсилатиметься стандартний payload, наведений у розділі 3.

```json
{
  "call_id": "${uniqueid}",
  "from": "${caller_id_num}",
  "direction": "inbound",
  "recording": "${recording_url}"
}
```

Доступні плейсхолдери: `event`, `uniqueid`, `caller_id_num`, `caller_id_name`, `exten`, `context`, `queue`, `timestamp`, `duration`, `cause`, `cause_txt`, `answered_time`, `billsec`, `recorded`, `recording_expected`, `recording_url`, `recording_file`, `missed`, `wait_time`, `member_name`, `member_interface`, `member_number`, `ringtime`, `holdtime`, `answered_by_member`, `answered_by_interface`.

Використання невідомого плейсхолдера викликає помилку валідації форми — адмінка не дасть зберегти такий шаблон. Якщо поле лишити порожнім, надсилається стандартний payload для кожної події.

## 7. Поведінка при збоях доставки

Доставка веб-хуків — це best-effort (найкраще зусилля), без гарантій «рівно один раз» і без черги повторної доставки:

- запит виконується асинхронно й ніколи не блокує обробку дзвінка — навіть якщо CRM-сервер недоступний або відповідає повільно, це не вплине на роботу Asterisk чи дашборду;
- кожна спроба обмежена таймаутом `timeout` із налаштувань веб-хука;
- у разі невдачі виконується до `retries` додаткових спроб з невеликою паузою між ними;
- якщо всі спроби провалились, подія просто логується на сервері й більше не повторюється.

Тому рекомендується, щоб приймальний ендпоінт CRM:
- відповідав швидко (в межах пари секунд) — довга обробка на боці CRM підвищує ризик таймауту;
- був ідемпотентним за `uniqueid` — про всяк випадок, якщо CRM-система сама повторює обробку вхідних запитів.

## 8. Приклад: мінімальний обробник веб-хуків

Спрощений приклад на Python (Flask) — приймає всі три типи подій, перевіряє підпис і за потреби забирає запис розмови:

```python
import hashlib
import hmac
import os

import requests
from flask import Flask, request, abort

app = Flask(__name__)

WEBHOOK_SECRET = os.environ["PEARLPBX_WEBHOOK_SECRET"]
API_TOKEN = os.environ["PEARLPBX_API_TOKEN"]


def verify_signature(body: bytes, header_value: str | None) -> bool:
    if not header_value:
        return False
    expected = "sha256=" + hmac.new(
        WEBHOOK_SECRET.encode(), body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, header_value)


@app.post("/pearlpbx/webhook")
def handle_webhook():
    raw_body = request.get_data()
    if not verify_signature(raw_body, request.headers.get("X-PearlPBX-Signature")):
        abort(401)

    payload = request.get_json()
    event = payload["event"]

    if event == "call.incoming":
        create_or_update_call_card(payload)
    elif event == "call.answered":
        mark_call_card_answered(payload["uniqueid"], payload["member_name"])
    elif event == "call.missed":
        create_missed_call_task(payload)
    elif event == "call.ended":
        close_call_card(payload)
        if payload.get("recorded"):
            fetch_recording(payload["uniqueid"], payload["recording_url"])

    return "", 200


def fetch_recording(uniqueid: str, recording_url: str) -> None:
    response = requests.get(
        recording_url,
        headers={"Authorization": f"Token {API_TOKEN}"},
        timeout=10,
    )
    response.raise_for_status()
    with open(f"/data/recordings/{uniqueid}.wav", "wb") as f:
        f.write(response.content)
```

---

Пов'язана документація:
- [docs/en/API.md](../en/API.md) — повний довідник REST API PearlPBX2 (англійською)
- [services/dashboard/README.md](../../services/dashboard/README.md) — технічні деталі роботи сервісу dashboard і формату Redis-подій (англійською)
