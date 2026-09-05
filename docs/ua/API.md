*Also available in: [English](../en/API.md) | [Українська](API.md) | [Español](../es/API.md)*

# REST API PearlPBX2

Усі ендпоінти доступні під префіксом `/api/v1/`.

## Контроль доступу

Автентифікація використовує токен-автентифікацію DRF. З кожним запитом надсилайте заголовок `Authorization: Token <ключ>`.

Запити без дійсного токена отримують `HTTP 401 Unauthorized`.

Створення токена:
```bash
python manage.py drf_create_token <username>
```

Або через Django admin / shell (`rest_framework.authtoken.models.Token`).

Немає обмежень за сесією чи IP-адресою. CSRF-захист не застосовується (лише токен-автентифікація).

**Виняток:** кожен метод на `/api/v1/sip-users/`, `/api/v1/sip-transports/` та
`/api/v1/sip-peers/`, включно з `GET`, вимагає обліковий запис staff або
superuser — див. [SIP Users](#sip-users), [SIP Transports](#sip-transports)
та [SIP Peers](#sip-peers) нижче. Дійсний токен звичайного користувача отримає
`403 Forbidden` на цих ресурсах.

## Загальний формат відповіді

**Успіх**: JSON-об'єкт або масив із полями ресурсу. GET-ендпоінти списків повертають пагіновані відповіді:

```json
{
  "count": 42,
  "next": "http://host/api/v1/blacklist/?page=2",
  "previous": null,
  "results": [...]
}
```

**Помилки валідації** використовують стандартний формат DRF:
```json
{"field_name": ["message"]}
```

**Коди статусу HTTP**:
- `200` — OK (читання або оновлення)
- `201` — Created (новий ресурс)
- `204` — No Content (успішне видалення, порожнє тіло)
- `400` — Bad Request (відсутні або некоректні поля)
- `401` — Unauthorized (відсутній або недійсний токен)
- `404` — Not Found
- `409` — Conflict (буде порушено обмеження унікальності, наприклад перейменування запису так, що він збігається з наявним)

---

## Blacklist (блок-лист)

Керує списком caller ID для блокування в діалплані Asterisk.

POST використовує upsert-логіку: якщо запис з таким самим `callerid` + `destination` уже існує, він оновлюється; інакше створюється новий.

### GET `/api/v1/blacklist/`

Повертає пагіновані записи блок-листа.

**Відповідь:**
```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": "uuid",
      "callerid": "+380501234567",
      "destination": "101",
      "reason": "Spam",
      "expiration_date": "2026-12-31T23:59:59"
    }
  ]
}
```

### POST `/api/v1/blacklist/`

Додати або оновити запис блок-листа.

**Тіло запиту:**
```json
{
  "callerid": "+380501234567",
  "destination": "101",
  "reason": "Spam",
  "expiration_date": "2026-12-31T23:59:59"
}
```

- `callerid` — обов'язкове
- `destination`, `reason`, `expiration_date` — опційні

Унікальність застосовується до пари `callerid` + `destination` (типове значення `destination = ""` для загальносистемного блокування).

**Відповідь:** `201` при створенні, `200` при оновленні. Оновлення `callerid`/`destination` запису (через `PUT`/`PATCH` на `/api/v1/blacklist/<uuid>/`) так, що воно збігається з іншою наявною парою, повертає `409 Conflict`.

### DELETE `/api/v1/blacklist/<uuid>/`

Видалити запис блок-листа за ID.

**Відповідь:** `204 No Content` (порожнє тіло).

---

## Whitelist (дозволені номери)

Керує списком caller ID для дозволу чи маршрутизації в діалплані Asterisk. Ідентичний інтерфейс до Blacklist.

### GET `/api/v1/whitelist/`
### POST `/api/v1/whitelist/`
### DELETE `/api/v1/whitelist/<uuid>/`

Той самий формат запиту/відповіді, що й Blacklist.

---

## Contacts (контакти)

Довідник caller ID з іменами для відображення. Використовується для визначення Caller ID Name.

POST використовує upsert-логіку за ключем `callerid`.

### GET `/api/v1/contacts/`

Повертає пагіновані контакти.

**Відповідь:**
```json
{
  "count": 1,
  "results": [
    {
      "id": "uuid",
      "callerid": "+380501234567",
      "name": "Іван Петренко"
    }
  ]
}
```

### POST `/api/v1/contacts/`

Додати або оновити контакт.

**Тіло запиту:**
```json
{
  "callerid": "+380501234567",
  "name": "Іван Петренко"
}
```

Обидва поля обов'язкові.

**Відповідь:** `201` при створенні, `200` при оновленні.

### DELETE `/api/v1/contacts/<uuid>/`

Видалити контакт за ID. Повертає `204 No Content`.

---

## Custom Lists (іменовані списки)

Іменовані списки із записами. Корисно для динамічних пошуків у діалплані (наприклад, VIP-абоненти, групи маршрутизації).

Кожен список має назву й містить записи з `callerid`, опційними `destination`, `reason` і `expiration_date`.

### GET `/api/v1/lists/`

Повертає всі іменовані списки.

**Відповідь:**
```json
{
  "count": 1,
  "results": [
    {"id": "uuid", "name": "VIP"}
  ]
}
```

### POST `/api/v1/lists/`

Створити новий список.

**Тіло запиту:**
```json
{"name": "VIP"}
```

**Відповідь:** `HTTP 201` зі створеним об'єктом списку.

### PATCH `/api/v1/lists/<uuid>/`

Перейменувати список.

**Тіло запиту:**
```json
{"name": "New Name"}
```

`name` має бути непорожнім рядком. Порожнє або відсутнє `name` повертає `400` з тілом `{"error": "Missing \"name\""}`.

### DELETE `/api/v1/lists/<uuid>/`

Видалити список і всі його записи. Повертає `204 No Content`.

---

### GET `/api/v1/lists/<uuid>/entries/`

Повертає пагіновані записи конкретного списку.

**Відповідь:**
```json
{
  "count": 1,
  "results": [
    {
      "id": "uuid",
      "callerid": "+380501234567",
      "destination": "101",
      "reason": "VIP caller",
      "expiration_date": null
    }
  ]
}
```

### POST `/api/v1/lists/<uuid>/entries/`

Додати запис у список.

**Тіло запиту:**
```json
{
  "callerid": "+380501234567",
  "destination": "101",
  "reason": "VIP caller",
  "expiration_date": "2026-12-31T23:59:59"
}
```

- `callerid` — обов'язкове
- `destination`, `reason`, `expiration_date` — опційні

**Відповідь:** `HTTP 201` зі створеним об'єктом запису.

### DELETE `/api/v1/lists/<uuid>/entries/<entry_uuid>/`

Видалити конкретний запис зі списку. Повертає `204 No Content`.

---

## SIP Users

Керує SIP-обліковими записами (extensions). На відміну від решти цього API,
**кожен метод цього ресурсу — включно з `GET` — вимагає обліковий запис
staff або superuser**; дійсний токен звичайного користувача отримає
`403 Forbidden`. Цей ресурс надає доступ до облікових даних для дзвінків,
тож звичайного автентифікованого токена недостатньо.

Запис тут лише оновлює базу даних. Зміни доходять до Asterisk лише після
того, як superuser натисне "Apply Changes" в адмін-панелі — див.
[посібник адміністратора](admin-guide.md). Користувач, збережений без
`transport` або без `routing_table`, буде мовчки пропущений при генерації
конфігурації, тому обидва поля тут обов'язкові.

Видалення SIP-користувача каскадно видаляє будь-який пов'язаний `PhoneDevice`.

### GET `/api/v1/sip-users/`

Повертає SIP-користувачів зі пагінацією. Підтримує:
- `?username=<точне значення>` — фільтр за точним username
- `?extension=<точне значення>` — фільтр за точним extension
- `?search=<текст>` — пошук без урахування регістру за `name`, `username`, `extension`

**Відповідь:**
```json
{
  "count": 1,
  "results": [
    {
      "id": 12,
      "name": "John Doe",
      "username": "101",
      "secret": "s3cret123",
      "transport": 1,
      "transport_name": "transport-udp",
      "nat": false,
      "extension": "101",
      "routing_table": 1,
      "routing_table_name": "PEARLPBX",
      "auth_type": "userpass",
      "custom_extension": "",
      "custom_settings": "",
      "custom_auth_settings": "",
      "custom_aor_settings": "",
      "pjsip_endpoint": "PJSIP/101",
      "is_webrtc": false,
      "realm": "udp-101",
      "md5_cred": "a1b2c3...",
      "created_at": "2026-09-01T10:00:00Z",
      "created_by": 1,
      "modified_at": "2026-09-01T10:00:00Z",
      "modified_by": 1
    }
  ]
}
```

`realm` та `md5_cred` — це облікові дані RFC 2617 HA1, обчислені з
`username`/`transport`/`secret`. WebRTC (`wss`) endpoint-и завжди
автентифікуються як MD5 у згенерованій конфігурації незалежно від
`auth_type`, тож WebRTC-клієнту слід використовувати `md5_cred`/`realm`,
а не відкритий `secret`. Обидва поля — `null` для користувача без
`transport`. `is_webrtc` дорівнює `true`, коли протокол транспорту
користувача — `wss`.

### POST `/api/v1/sip-users/`

Створити SIP-користувача.

**Тіло запиту:**
```json
{
  "name": "John Doe",
  "username": "101",
  "secret": "s3cret123",
  "extension": "101",
  "transport": 1,
  "routing_table": 1,
  "auth_type": "userpass"
}
```

| Поле | Обов'язкове | Примітки |
|---|---|---|
| `name` | так | мінімум 3 символи |
| `username` | так | 3+ символи, лише літери/цифри, унікальний |
| `secret` | так | пароль SIP у відкритому вигляді |
| `transport` | так | ID існуючого `SIPTransport` |
| `routing_table` | так | ID існуючого `RoutingTable` |
| `extension` | так | лише літери/цифри, унікальний |
| `nat` | ні | за замовчуванням `false` |
| `auth_type` | ні | `userpass` (за замовчуванням) або `md5` |
| `custom_extension`, `custom_settings`, `custom_auth_settings`, `custom_aor_settings` | ні | сирі фрагменти `pjsip.conf`/dialplan, записуються дослівно |

**Відповідь:** `HTTP 201` зі створеним об'єктом користувача, або `400`, якщо
`username`/`extension` вже зайняті чи не пройшли валідацію.

### PATCH `/api/v1/sip-users/<id>/`

Часткове оновлення SIP-користувача. Ті самі правила полів, що й у `POST`.

### DELETE `/api/v1/sip-users/<id>/`

Видалити SIP-користувача. Повертає `204 No Content`. Каскадно видаляє будь-який
пов'язаний `PhoneDevice`.

---

## SIP Transports

Керує PJSIP-транспортами. Як і [SIP Users](#sip-users), **кожен метод цього
ресурсу — включно з `GET` — вимагає обліковий запис staff або superuser**;
`cert_file` та `priv_key_file` містять матеріал TLS-сертифіката/приватного
ключа у відкритому вигляді.

Запис тут лише оновлює базу даних. Зміни доходять до Asterisk лише після
того, як superuser натисне "Apply Changes" в адмін-панелі. `cert_file`,
`priv_key_file` та `ca_list_file` містять **вміст** PEM, а не шляхи до
файлів — вони записуються на диск у каталог сертифікатів Asterisk лише під
час "Apply Changes", і лише для транспорту з `protocol` `"tls"`.

Зміна `protocol` у транспорту, який вже використовується, перегенеровує
конфігурацію кожного приєднаного `SIPUser` і робить недійсним його
`md5_cred` (він обчислюється з `protocol-username`). Видалення останнього
`wss`-транспорту вимикає шаблони WebRTC-конфігурації для кожного
WebRTC-користувача. Видалення транспорту, на який ще посилається `SIPUser`
або `SIPPeer`, повертає `409 Conflict` замість помилки на рівні бази даних.

### GET `/api/v1/sip-transports/`

Повертає транспорти зі пагінацією. Підтримує:
- `?name=<точне значення>` — фільтр за точним іменем
- `?protocol=<udp|tcp|tls|wss>` — фільтр за протоколом
- `?search=<текст>` — пошук без урахування регістру за `name`, `description`

**Відповідь:**
```json
{
  "count": 1,
  "results": [
    {
      "id": 1,
      "name": "transport-udp",
      "description": "UDP transport",
      "protocol": "udp",
      "bind": "0.0.0.0:5060",
      "local_nets": "10.0.0.0/16, 192.168.0.0/24",
      "external_media_address": null,
      "external_signaling_address": null,
      "method": "default",
      "verify_server": false,
      "allow_reload": true,
      "cert_file": "",
      "priv_key_file": "",
      "ca_list_file": "",
      "has_tls_material": false,
      "sip_users_count": 3,
      "sip_peers_count": 0,
      "created_at": "2026-09-01T10:00:00Z",
      "created_by": 1,
      "modified_at": "2026-09-01T10:00:00Z",
      "modified_by": 1
    }
  ]
}
```

`sip_users_count`/`sip_peers_count` — це кількість рядків `SIPUser`/`SIPPeer`
на цьому транспорті (ті самі рядки, що блокують `DELETE`). `has_tls_material`
дорівнює `true`, якщо заповнено хоча б одне з трьох полів сертифіката.

### POST `/api/v1/sip-transports/`

Створити транспорт.

**Тіло запиту:**
```json
{
  "name": "transport-udp-nat",
  "protocol": "udp",
  "bind": "0.0.0.0:5060",
  "description": "UDP + NAT for remote users"
}
```

| Поле | Обов'язкове | Примітки |
|---|---|---|
| `name` | так | літери/цифри/підкреслення/дефіси, унікальне, використовується як назва секції в `pjsip.conf` |
| `protocol` | ні | `udp` (за замовчуванням), `tcp`, `tls`, `wss` |
| `bind` | ні | `<ipv4>` або `<ipv4>:<port>`, за замовчуванням `0.0.0.0`; порт має бути 1024-65535 |
| `description` | ні | один рядок, без `\n`/`\r` — записується як коментар у `pjsip.conf` |
| `local_nets` | ні | мережі CIDR через кому, напр. `10.0.0.0/16, 192.168.0.0/24`; порожнє значення зберігається як `null` |
| `external_media_address`, `external_signaling_address` | ні | IP-адреси |
| `method`, `verify_server`, `allow_reload`, `cert_file`, `priv_key_file`, `ca_list_file` | ні | діють лише коли `protocol` дорівнює `tls` |

**Відповідь:** `HTTP 201` зі створеним об'єктом транспорту, або `400`, якщо
`name` вже зайняте чи не пройшло валідацію.

### PATCH `/api/v1/sip-transports/<id>/`

Часткове оновлення транспорту. Ті самі правила полів, що й у `POST`.

### DELETE `/api/v1/sip-transports/<id>/`

Видалити транспорт. Повертає `204 No Content`, або `409 Conflict` із
переліком рядків `SIPUser`/`SIPPeer`, що досі використовують цей транспорт.

---

## SIP Peers

Керує SIP-транками/аплінками. Як і [SIP Users](#sip-users), **кожен метод
цього ресурсу — включно з `GET` — вимагає обліковий запис staff або
superuser**; цей ресурс надає доступ до облікових даних для дзвінків
(відкритий `secret` та обчислений `md5_cred`).

Запис тут лише оновлює базу даних. Зміни доходять до Asterisk лише після
того, як superuser натисне "Apply Changes" в адмін-панелі. Пір, збережений
без `transport` або без `routing_table`, згенерує неповний запис у
`pjsip.conf` (секція `[auth]` без `[endpoint]`/`[aor]`), тому обидва поля тут
обов'язкові. Якщо встановлено `registration_there`, `registration_uri` та
`username` також обов'язкові.

Видалення піра, що досі належить до `TrunkGroup`, повертає `409 Conflict`
замість мовчазного зменшення групи.

### GET `/api/v1/sip-peers/`

Повертає піри зі пагінацією. Підтримує:
- `?name=<точне значення>` — фільтр за точним іменем
- `?routing_table=<id>` — фільтр за таблицею маршрутизації
- `?search=<текст>` — пошук без урахування регістру за `name`, `description`, `username`

**Відповідь:**
```json
{
  "count": 1,
  "results": [
    {
      "id": 5,
      "name": "myprovider",
      "description": "SIP trunk provider",
      "username": "trunkuser",
      "contact_user": "",
      "auth_type": "userpass",
      "secret": "s3cret123",
      "transport": 1,
      "transport_name": "transport-udp",
      "routing_table": 1,
      "routing_table_name": "PEARLPBX",
      "registration_uri": "reg.provider.com:5060",
      "contact_uri": "",
      "match_hosts": "",
      "registration_here": false,
      "registration_there": true,
      "nat": false,
      "custom_auth_settings": "",
      "custom_aor_settings": "",
      "custom_identify_settings": "",
      "auth_realm": "reg.provider.com",
      "md5_cred": "a1b2c3...",
      "trunk_groups": ["main-trunks"],
      "created_at": "2026-09-01T10:00:00Z",
      "created_by": 1,
      "modified_at": "2026-09-01T10:00:00Z",
      "modified_by": 1
    }
  ]
}
```

`registration_here`/`registration_there` відповідають полям моделі
`registrationHere`/`registrationThere`. `auth_realm` та `md5_cred` — це
облікові дані RFC 2617 HA1, обчислені з `username`/`auth_realm`/`secret` —
`auth_realm` це хост-частина `registration_uri`, або `"asterisk"`, якщо його
не вказано. `trunk_groups` містить назви `TrunkGroup`, до яких належить цей
пір; видалення піра, що належить хоча б до однієї групи, буде відхилено
(див. вище).

### POST `/api/v1/sip-peers/`

Створити пір.

**Тіло запиту:**
```json
{
  "name": "myprovider",
  "description": "SIP trunk provider",
  "username": "trunkuser",
  "secret": "s3cret123",
  "auth_type": "userpass",
  "transport": 1,
  "routing_table": 1,
  "registration_there": true,
  "registration_uri": "reg.provider.com:5060"
}
```

| Поле | Обов'язкове | Примітки |
|---|---|---|
| `name` | так | 3+ символи, лише літери/цифри, унікальне, використовується як назва секції в `pjsip.conf` |
| `description` | так | один рядок, без `\n`/`\r` |
| `transport` | так | ID існуючого `SIPTransport` |
| `routing_table` | так | ID існуючого `RoutingTable` |
| `username`, `contact_user` | ні | літери/цифри/дефіси/крапки/підкреслення |
| `auth_type` | ні | `userpass` (за замовчуванням) або `md5` |
| `secret` | ні | пароль SIP у відкритому вигляді |
| `registration_uri`, `contact_uri` | ні | `host[:port]`; обов'язкові, якщо `registration_there` дорівнює `true` |
| `match_hosts` | ні | хости/IP через кому, без портів |
| `registration_here` | ні | за замовчуванням `false` — пір реєструється у нас (шлюзи GSM/E1/T1/FXS/FXO) |
| `registration_there` | ні | за замовчуванням `false` — ми реєструємось у піра (провайдери); вимагає `registration_uri` та `username` |
| `nat` | ні | за замовчуванням `false` |
| `custom_auth_settings`, `custom_aor_settings`, `custom_identify_settings` | ні | сирі фрагменти `pjsip.conf`, записуються дослівно |

**Відповідь:** `HTTP 201` зі створеним об'єктом піра, або `400`, якщо `name`
вже зайняте чи не пройшло валідацію.

### PATCH `/api/v1/sip-peers/<id>/`

Часткове оновлення піра. Ті самі правила полів, що й у `POST`.

### DELETE `/api/v1/sip-peers/<id>/`

Видалити пір. Повертає `204 No Content`, або `409 Conflict` із переліком
`TrunkGroup`, до яких він досі належить.

---

## Ініціювання дзвінка (Originate)

**`POST /api/v1/calls/originate/`**

Ініціює дзвінок через Asterisk AMI. Заміняє прямі HTTP-виклики до Asterisk `rawman` — секрет AMI ніколи не передається клієнтом.

**Тіло запиту:**

| Поле | Тип | Обов'язкове | За замовчуванням | Опис |
|-------|------|----------|---------|-------------|
| `channel` | рядок | так | — | Перше плече для набору, наприклад `"Local/0441231231@Outgoing"` або `"PJSIP/2101"` |
| `exten` | рядок | так | — | Зовнішній номер, з яким з'єднується перше плече, наприклад `"0123123123"` |
| `context` | рядок | так | `"Outgoing"` | Таблиця маршрутизації, яка має доступ до зовнішніх дзвінків |
| `priority` | ціле число | так | `1` | Пріоритет діалплану (залиште: 1) |
| `callerid` | рядок | так | — | Caller ID у форматі `ім'я<номер>`, наприклад `"PearlPBX2 Auto Call<номер_куди_ви_телефонуєте>"` |
| `variable` | об'єкт | ні | — | Канальні змінні як пари ключ-значення, наприклад `{"userId": "0"}` |
| `timeout_ms` | ціле число | так | `30000` | Таймаут Originate на боці Asterisk у мс (1000–120000). Це також бюджет очікування на сервері: воркер API не блокуватиметься в очікуванні відповіді AMI довше, ніж `timeout_ms + 5с` |

**Відповіді:**

| Статус | Значення |
|--------|---------|
| `200` | Дзвінок успішно ініційовано. Тіло: `{"status": "originated", "message": "..."}` |
| `400` | Некоректне тіло запиту (відсутні обов'язкові поля, помилки валідації) |
| `401` | Не надано облікові дані автентифікації |
| `502` | Помилка AMI або Asterisk недоступний |
| `503` | Asterisk вимкнений у цьому DEVMODE |

**Приклад:**

```bash
curl -k -X 'POST' \
  'https://<ваш-сервер>/api/v1/calls/originate/' \
  -H 'accept: */*' \
  -H 'Authorization: Token <ваш-токен>' \
  -H 'Content-Type: application/json' \
  -H 'X-CSRFTOKEN: <ваш-csrf-токен>' \
  -d '{
  "callerid": "0504139380",
  "timeout_ms": 30000,
  "channel": "PJSIP/2101",
  "exten": "0504139380",
  "context": "Outgoing",
  "priority": 1
}'
```

> **Примітки:**
> - `timeout_ms` вказується у **мілісекундах** і обмежує лише час на створення **першого плеча** дзвінка — каналу `channel` (у прикладі `PJSIP/2101`, внутрішній номер). До того, скільки дзвонитиме друге плече (`exten`), це поле відношення не має.
> - Якщо у відповіді прийде `Originate failed`, це означає, що Asterisk не зміг створити перший канал. Найчастіші причини: внутрішнього номера (`PJSIP/2101`) не існує / він не зареєстрований, оператор не відповів на дзвінок, або оператор скинув його, не піднявши слухавку.

**Відповідність старих параметрів rawman:**

| параметр rawman | поле API |
|---|---|
| `channel` | `channel` |
| `exten` | `exten` |
| `context` | `context` |
| `priority` | `priority` |
| `Variable` | `variable` (dict) |
| `callerId` | `callerid` |

---

## Queue Members (члени черги)

Постановка на паузу/зняття з паузи члена черги та читання живого статусу члена черги через Asterisk AMI.
Тут немає постійного ресурсу «член черги» — ці ендпоінти звертаються напряму до
Asterisk, тож вони відображають (і змінюють) живий runtime-стан, а не
записи `QueueMember`, якими керують у Django admin.

### POST `/api/v1/queues/members/pause/`

Поставити на паузу або зняти з паузи члена черги.

**Тіло запиту:**

| Поле | Тип | Обов'язкове | За замовчуванням | Опис |
|-------|------|----------|---------|-------------|
| `interface` | рядок | так | — | Інтерфейс члена черги, наприклад `"PJSIP/101"` |
| `paused` | булеве | так | — | `true` — поставити на паузу, `false` — зняти з паузи |
| `queue` | рядок | ні | — | Обмежити зміну однією чергою. Якщо не вказано, застосовується до члена в кожній черзі, до якої він належить |

**Відповіді:**

| Статус | Значення |
|--------|---------|
| `200` | Стан паузи оновлено. Тіло: `{"status": "paused"}` або `{"status": "unpaused"}` |
| `400` | Некоректне тіло запиту |
| `401` | Не надано облікові дані автентифікації |
| `404` | Інтерфейс не є членом вказаної(их) черги(черг) |
| `502` | Помилка AMI або Asterisk недоступний |
| `503` | Asterisk вимкнений у цьому DEVMODE |

**Приклад:**

```bash
curl -X POST http://127.0.0.1:8000/api/v1/queues/members/pause/ \
  -H "Authorization: Token <ваш-токен>" \
  -H "Content-Type: application/json" \
  -d '{"interface": "PJSIP/101", "paused": true}'
```

### GET `/api/v1/queues/members/`

Перелік членів черги та їх поточного статусу. Опційний query-параметр
`?queue=<name>` обмежує результати однією чергою; без нього перелічуються члени всіх черг.

**Відповідь:**

```json
{
  "members": [
    {
      "queue": "support",
      "name": "PJSIP/101",
      "location": "PJSIP/101",
      "state_interface": "PJSIP/101",
      "membership": "static",
      "penalty": 0,
      "calls_taken": 3,
      "last_call": 0,
      "in_call": false,
      "status": "1",
      "paused": true
    }
  ]
}
```

`status` — це сирий код стану пристрою Asterisk (`AST_DEVICE_*`), переданий
без перекладу.

**Відповіді:**

| Статус | Значення |
|--------|---------|
| `200` | Перелік членів (можливо порожній) |
| `401` | Не надано облікові дані автентифікації |
| `502` | Помилка AMI або Asterisk недоступний |
| `503` | Asterisk вимкнений у цьому DEVMODE |

---

## Call Recordings (записи розмов)

**`GET /api/v1/recordings/<uniqueid>/`**

Отримати аудіо записаного дзвінка за uniqueid Asterisk. Це той самий ендпоінт, на який
посилається `recording_url` у payload веб-хуків CRM — див.
[гайд з інтеграції CRM](crm-integration.md) для повного довідника з веб-хуків. Підтримує HTTP-запити
`Range` для стрімінгу/перемотки та query-параметр
`?download=1`, що форсує відповідь `Content-Disposition: attachment`.

**Відповіді:**

| Статус | Значення |
|--------|---------|
| `200` / `206` | Аудіофайл (`audio/wav` або `audio/mpeg`), повний або частковий (Range) |
| `401` | Не надано облікові дані автентифікації |
| `404` | Запис для цього uniqueid не існує (не записувався, або ще не записаний на диск) |

**Приклад:**

```bash
curl -H "Authorization: Token <ваш-токен>" \
  http://127.0.0.1:8000/api/v1/recordings/1753000000.42/ \
  -o call.wav
```

Доступ не деталізований далі — будь-який дійсний токен API може отримати будь-який
запис, так само як і решта цього API.

---

## Відомі обмеження

- Немає фільтрації чи пошуку на GET-ендпоінтах, окрім `/api/v1/sip-users/`
  (`?username=`, `?extension=`, `?search=`), `/api/v1/sip-transports/`
  (`?name=`, `?protocol=`, `?search=`) та `/api/v1/sip-peers/`
  (`?name=`, `?routing_table=`, `?search=`).

---

## Документація API

Доступна інтерактивна, автоматично згенерована документація OpenAPI 3.0 (на основі
drf-spectacular). Усі три ендпоінти вимагають автентифікації (дійсний токен або
автентифіковану сесію), так само як і решта API.

- **Сира схема (OpenAPI 3.0, YAML):** `GET /api/v1/schema/`
- **Swagger UI:** `GET /api/v1/docs/`
- **ReDoc UI:** `GET /api/v1/redoc/`

> **Примітка:** Ці три ендпоінти вимагають автентифікації (`Authorization: Token <ключ>`),
> так само як і решта API. Відкриття їх напряму в браузері без токена
> повертає `401`. Це навмисно — документація не є публічно доступною.

Схема генерується напряму з DRF ViewSets і серіалізаторів, тож вона завжди
відповідає коду, що виконується.
