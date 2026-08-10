# Посібник адміністратора PearlPBX2

**Версія:** 2.7.0

---

## Зміст

1. [Вступ](#1-вступ)
2. [Архітектура системи](#2-архітектура-системи)
3. [Встановлення (огляд)](#3-встановлення-огляд)
4. [Конфігурація через змінні середовища](#4-конфігурація-через-змінні-середовища)
5. [Користувачі та ролі](#5-користувачі-та-ролі)
6. [SIP-транспорти](#6-sip-транспорти)
7. [SIP-користувачі](#7-sip-користувачі)
8. [SIP-піри (транки)](#8-sip-піри-транки)
9. [Групи транків](#9-групи-транків)
10. [Діалплан (Dialplan)](#10-діалплан-dialplan)
11. [Маршрутизація дзвінків](#11-маршрутизація-дзвінків)
12. [Черги](#12-черги)
13. [Музика на утриманні (MOH)](#13-музика-на-утриманні-moh)
14. [Звукові файли](#14-звукові-файли)
15. [Apply Changes](#15-apply-changes)
16. [Служби (Services)](#16-служби-services)
17. [Веб-хуки (CRM)](#17-веб-хуки-crm)
18. [REST API](#18-rest-api)
19. [Провізіонінг телефонів](#19-провізіонінг-телефонів)
20. [Обслуговування](#20-обслуговування)

---

## 1. Вступ

PearlPBX2 — це веб-інтерфейс для керування Asterisk PBX, побудований на Django. Система дозволяє керувати SIP-абонентами, транками, діалпланом, маршрутизацією, чергами та іншими об'єктами Asterisk через веб-інтерфейс, автоматично генеруючи конфігураційні файли Asterisk з бази даних.

### Ключові можливості

- Управління PJSIP транспортами, абонентами та транками
- Редактор діалплану з підтримкою синтаксису AEL та валідацією
- Префіксна маршрутизація дзвінків
- Черги з підтримкою ескалації, анонсів, глобальних налаштувань
- Дашборд оператора в реальному часі (WebSocket)
- CDR, записи розмов, журнали черг
- Аналітика з графіками (Chart.js)
- Автоматичні зворотні дзвінки (callback)
- Провізіонінг телефонів (TFTP)
- REST API для зовнішньої інтеграції
- Apply Changes — генерація конфігів та перезавантаження Asterisk одним кліком

### Хто є адміністратором

Адміністратор — це користувач із правами **superuser** (is_superuser=True). Тільки superuser може:

- застосовувати зміни конфігурації до Asterisk (`/admin/apply`);
- керувати всіма об'єктами PBX через адмін-панель;
- створювати та редагувати інших користувачів.

Користувачі з правами **staff** (is_staff=True) можуть переглядати адмін-панель, але без доступу до Apply Changes.

---

## 2. Архітектура системи

### Загальна схема

```
Browser ──WebSocket──► Django Channels ◄── Redis ◄── Dashboard Listener ◄── Asterisk AMI
Browser ──HTTP──────► Django (ASGI) ◄──── PostgreSQL
                            │
                            └──► /etc/asterisk/*.conf  (генерація конфігів)

Asterisk FastAGI ◄──────────► FastAGI Service (port 4573)
Callback daemon ─────────────► Asterisk AMI (вихідні дзвінки)
```

### Компоненти

| Компонент | Призначення |
|-----------|-------------|
| **Django (ASGI)** | Веб-додаток, HTTP + WebSocket, порт 8000 |
| **PostgreSQL** | База даних для всіх об'єктів PBX |
| **Redis** | Канал обміну повідомленнями для WebSocket, зберігання стану черг/каналів |
| **Dashboard Listener** | Служба, яка слухає події AMI Asterisk та публікує їх у Redis |
| **Callback Daemon** | Служба, яка моніторить чергу колбеків у БД та ініціює дзвінки через AMI |
| **FastAGI Server** | Служба FastAGI для обробки діалплану (перевірка списків, запис розмов, маршрутизація, паркування) |

### Потік даних

1. **Конфігурація:** Admin UI → Django Models → `core/conf.py` → файли `/etc/asterisk/*.conf` → перезавантаження Asterisk
2. **Дашборд:** Події Asterisk AMI → Dashboard Listener → Redis Pub/Sub → Django Channels → WebSocket → Браузер
3. **Callback:** Запит у БД → Callback Daemon (SELECT FOR UPDATE) → AMI Originate → вихідний дзвінок
4. **FastAGI:** Asterisk діалплан → AGI(agi://localhost:4573/handler) → FastAGI сервер → змінні каналу

### Компоненти Django

| Модуль | Призначення |
|--------|-------------|
| `core/` | Центральні моделі, генератор конфігів, валідатори, адмін-інтерфейс |
| `apps/dashboard/` | WebSocket дашборд оператора |
| `apps/reports/` | CDR, записи, журнали, аналітика |
| `apps/lists/` | CRUD для списків номерів |
| `apps/callback/` | Моделі та представлення для колбеків |
| `apps/provision/` | Провізіонінг телефонів |
| `apps/api/` | REST API |
| `apps/webhooks/` | Веб-хуки для CRM-інтеграції (події дзвінків) |

---

## 3. Встановлення (огляд)

### Вимоги до системи

- **Python** 3.10+
- **Django** 5.2
- **PostgreSQL** 14+
- **Redis** 7+
- **Asterisk** 22+ (з модулями `res_pjsip`, `res_agi`, `cdr_pgsql`)

### Швидкий старт (розробка)

```bash
# Створення віртуального середовища
python3 -m venv .python-venv
source .python-venv/bin/activate

# Встановлення залежностей
pip install -r requirements.txt

# Налаштування змінних середовища
cp env.sample .env
# Відредагуйте .env — DB, AMI, DEVMODE тощо

# Ініціалізація бази даних
python manage.py migrate
python manage.py createsuperuser

# Запуск сервера розробки
python manage.py runserver
```

### Продуктивне середовище

```bash
# Через uvicorn (ASGI + WebSocket)
uvicorn pbx.asgi:application --host 0.0.0.0 --port 8000 --workers 3
```

**Важливо:** Django має працювати від користувача `asterisk` для доступу до `/etc/asterisk`.

### Докладна інструкція

- Повна інструкція зі встановлення Asterisk: [docs/en/install_asterisk.md](../en/install_asterisk.md)
- Загальні вимоги та налаштування: [docs/en/INSTALL.md](../en/INSTALL.md)
- Docker-розгортання: `docker-compose.yml` (django, asterisk, postgres, redis)
- Ansible-розгортання: `ansible/` (9 ролей: system, postgres, redis, asterisk, pearlpbx2, services, nginx, tftp, firewall)

### Режими роботи (DEVMODE)

| Режим | Значення | Опис |
|-------|----------|------|
| Production | `Production` | Безпечні cookies, без debug |
| Staging | `Staging` | Тестовий сервер |
| Development | `Development` | Debug режим, розробка на VPS |
| without_asterisk_on_localhost | `without_asterisk_on_localhost` | Локальна розробка без Asterisk |

---

## 4. Конфігурація через змінні середовища

Всі налаштування задаються через змінні середовища. Приклад: [env.sample](../../env.sample).

### Обов'язкові змінні

| Змінна | Опис | Типове значення |
|--------|------|-----------------|
| `DEVMODE` | Режим роботи | `Development` |
| `DJANGO_SECRET_KEY` | Секретний ключ Django (обов'язковий у Production) | — |
| `DB_HOST` | Хост PostgreSQL | `localhost` |
| `DB_NAME` | Назва бази даних | `pearlpbx2` |
| `DB_USER` | Користувач БД | `pearlpbx2` |
| `DB_PASS` | Пароль БД | — |
| `ASTERISK_MANAGER_HOST` | Хост AMI Asterisk | `127.0.0.1` |
| `ASTERISK_MANAGER_USERNAME` | Ім'я користувача AMI | `django` |
| `ASTERISK_MANAGER_SECRET` | Пароль AMI | — |

### Опціональні змінні

| Змінна | Опис | Типове значення |
|--------|------|-----------------|
| `ALLOWED_HOSTS` | Дозволені хости (comma-separated) | `127.0.0.1` |
| `CSRF_TRUSTED_ORIGINS` | Довірені джерела CSRF | — |
| `ASTERISK_ROOT_DIR` | Коренева директорія Asterisk | `/tmp` |
| `ASTERISK_CONFIG_DIR` | Директорія конфігів Asterisk | `/etc/asterisk` |
| `ASTERISK_BACKUP_DIR` | Директорія бекапів | `/tmp/backup/asterisk` |
| `ASTERISK_MONITOR_DIR` | Директорія записів розмов | `/var/spool/asterisk/monitor` |
| `ASTERISK_BACKUP_MONITOR_DIR` | Резервна директорія записів (iSCSI) | — |
| `REDIS_URL` | URL підключення до Redis | `redis://localhost:6379` |
| `TFTP_DIR` | Директорія TFTP для провізіонінгу | `/var/lib/tftpboot` |
| `DASHBOARD_MISSED_CALL_WINDOW_MINUTES` | Вікно пропущених дзвінків | `0` (поточна доба) |
| `PHONE_COUNTRY_CODE` | Код країни для нормалізації | `380` |
| `PHONE_LOCAL_CODE` | Міський код | `044` |
| `PHONE_REQUIRED_LEN` | Очікувана довжина повного номера при нормалізації | `10` |
| `PHONE_CITYCODE_LEN` | Довжина міського коду при нормалізації | `7` |
| `PEARLPBX_PUBLIC_URL` | Публічний базовий URL веб-інтерфейсу (використовується для посилань на записи розмов у веб-хуках CRM) | `http://localhost:8000` |

---

## 5. Користувачі та ролі

### Групи користувачів

Система використовує стандартну модель користувачів Django.

#### Група "Report Viewer"

Користувачі в цій групі мають доступ до:

- Dashboard (`/dashboard/`)
- Parking (моніторинг ULINE, `/dashboard/ulines/`)
- Reports (`/reports/`)
- Lists (`/lists/`)

Створення групи:

1. Адмін-панель → Authentication and Authorization → Groups → Add Group.
2. Назва: `Report Viewer`.
3. Призначте необхідні права (або жодних — доступ контролюється через код у `HEADER_MENU_PAGES`).

#### Рівні доступу в Django

| Рівень | `is_superuser` | `is_staff` | Доступ |
|--------|---------------|------------|--------|
| Superuser | true | true | Повний доступ, включаючи Apply Changes |
| Staff | false | true | Адмін-панель (перегляд/редагування об'єктів) |
| Report Viewer | false | false | Dashboard, Reports, Lists |
| Звичайний | false | false | Тільки homepage (якщо увійшов) |

### Створення користувача

1. Перейдіть до `/admin/auth/user/add/`.
2. Заповніть **Username**, **Password**.
3. Натисніть **Save and continue editing**.
4. На вкладці **Permissions**:
   - **Superuser status** — поставте галочку для повного доступу.
   - **Staff status** — поставте для доступу до адмін-панелі.
5. На вкладці **Groups** додайте користувача до групи "Report Viewer" (якщо потрібно).

### Навігаційне меню (HEADER_MENU_PAGES)

У `settings.py` визначено пункти меню з прив'язкою до ролей:

| Пункт | Роль | URL |
|-------|------|-----|
| Dashboard | admin, superuser, Report Viewer | `/dashboard/` |
| Parking (ULINE) | admin, superuser, Report Viewer | `/dashboard/ulines/` |
| Reports | admin, superuser, Report Viewer | `/reports/` |
| Lists | admin, superuser, Report Viewer | `/lists/` |
| Admin panel | superuser | `/admin` |

---

## 6. SIP-транспорти

SIP-транспорти визначають, як Asterisk слухає та передає SIP-трафік. Відповідає моделі `SIPTransport`.

### Створення транспорту

1. Адмін-панель → PBX Setup → SIP Transports → Add SIP Transport.
2. Поля:

| Поле | Опис |
|------|------|
| **Description** | Опис (наприклад, "UDP для віддалених користувачів") |
| **Name** | Унікальне ім'я (наприклад, `transport-udp-nat`). Валідується як контекст Asterisk |
| **Protocol** | `UDP`, `TCP`, `TLS`, `WSS` |
| **Bind** | IP-адреса для прослуховування (наприклад, `0.0.0.0:5060`) |
| **Local Nets** | Локальні мережі (comma-separated, наприклад, `192.168.0.0/16,10.0.0.0/8`) |
| **External Media Address** | Зовнішня IP-адреса для медіа (NAT) |
| **External Signaling Address** | Зовнішня IP-адреса для сигналізації (NAT) |

#### TLS-налаштування (тільки для протоколу TLS)

| Поле | Опис |
|------|------|
| **Method** | Метод TLS (default, tlsv1, tlsv1_1, tlsv1_2, sslv2, sslv3, sslv23) |
| **Verify Server** | Перевірка сервера |
| **Allow Reload** | Дозвіл перезавантаження сертифіката |
| **Cert File** | Вміст сертифіката (зберігається в `ASTERISK_CONFIG_DIR/certificate/`) |
| **Priv Key File** | Вміст приватного ключа |
| **CA List File** | CA ланцюжок |

### Рекомендації

- Для звичайного використання створіть UDP-транспорт на порту 5060.
- Для підтримки WebRTC створіть WSS-транспорт.
- При роботі через NAT заповніть `External Media/Signaling Address`.

---

## 7. SIP-користувачі

SIP-користувачі — це внутрішні абоненти телефонної мережі. Відповідає моделі `SIPUser`.

### Створення абонента

1. Адмін-панель → PBX Setup → SIP Users → Add SIP User.
2. Поля:

| Поле | Опис |
|------|------|
| **Name** | Ім'я абонента (відображається в системі) |
| **Username** | Ім'я для автентифікації на SIP-телефоні |
| **Extension** | Внутрішній номер. Якщо залишити порожнім, буде згенеровано автоматично |
| **Secret** | Пароль для SIP-автентифікації |
| **Transport** | Транспорт PJSIP, який використовує абонент |
| **Routing Table** | Таблиця маршрутизації для вихідних дзвінків |
| **NAT** | Увімкнення обробки NAT для абонента (boolean) |
| **Auth Type** | Тип автентифікації: `userpass` або `md5` |
| **Allowed Extension** | Обмеження, з якого extension дозволено реєструватись цьому абоненту |
| **Custom Settings** | Додаткові налаштування для секцій `endpoint`, `auth`, `aor` |

### Автоматична генерація extension

Якщо поле **Extension** залишити порожнім, система автоматично згенерує наступний вільний номер у форматі `2XX`. Діапазон пошуку визначається налаштуваннями маршрутизації (`PEARLPBX_DEFAULT_ROUTING_PREFIX`).

### Поля Custom Settings

Для налаштування параметрів PJSIP, яких немає в основній формі, використовуйте поля:

- **Custom Endpoint Settings** — додаткові параметри секції `[endpoint]`.
- **Custom Auth Settings** — додаткові параметри секції `[auth]`.
- **Custom AOR Settings** — додаткові параметри секції `[aor]`.

Кожне поле приймає текст у форматі `parameter = value`, по одному на рядок. Ці значення дописуються у відповідні секції згенерованого `pjsip.conf`.

---

## 8. SIP-піри (транки)

SIP-піри — це зовнішні з'єднання з телефонними операторами або іншими АТС. Відповідає моделі `SIPPeer`.

### Створення транку

1. Адмін-панель → PBX Setup → SIP Peers → Add SIP Peer.
2. Поля:

#### Generic

| Поле | Опис |
|------|------|
| **Name** | Унікальне ім'я транку |
| **Description** | Опис (наприклад, "Оператор Київстар") |
| **Transport** | Транспорт для з'єднання |
| **Routing Table** | Таблиця маршрутизації для вихідних дзвінків |

#### Authentication

| Поле | Опис |
|------|------|
| **Username** | Ім'я для автентифікації на стороні оператора |
| **Contact User** | Contact user для автентифікації |
| **Auth Type** | `userpass` або `md5` |
| **Secret** | Пароль |
| **Custom Auth Settings** | Додаткові параметри auth |

#### Connection

| Поле | Опис |
|------|------|
| **Registration URI** | URI для реєстрації у оператора (`sip:operator.ua:5060`) |
| **Contact URI** | URI, на який направляти дзвінки (`sip:operator.ua:5060`) |
| **Match Hosts** | IP-адреси оператора для співставлення вхідних дзвінків (comma-separated) |

**Формування AOR contact:** якщо **Contact URI** не заповнено, система підставляє **Registration URI** як контакт AOR (з попередженням у логах — це може бути некоректно, якщо реєстратор і медіа-хост відрізняються). Якщо не заповнено жодного з полів, AOR лишається без статичного контакту.

Коли **Registration There** увімкнено, AOR транку одразу отримує "bootstrap"-контакт (`max_contacts=1`, `remove_existing=yes`), навіть до першої вдалої реєстрації — інакше вихідні дзвінки не мають куди йти в проміжку до REGISTER. Після успішного REGISTER цей контакт замінюється на той, що реально прислав оператор.

#### Registration

| Поле | Опис |
|------|------|
| **Registration Here** | Реєструвати на стороні Asterisk (`True/False`) |
| **Registration There** | Реєструвати на стороні оператора (`True/False`) |

#### Advanced (collapsed)

| Поле | Опис |
|------|------|
| **NAT** | Увімкнення обробки NAT для транку (boolean) |
| **Custom AOR Settings** | Додаткові параметри AOR |

### Групи транків

Див. розділ [Групи транків](#9-групи-транків).

---

## 9. Групи транків

Дозволяють об'єднати кілька транків у групу для failover — при недоступності першого транку дзвінок автоматично направляється на наступний. Відповідає моделі `TrunkGroup`.

### Створення групи

1. Адмін-панель → PBX Setup → Trunk Groups → Add Trunk Group.
2. Поля:
   - **Name** — назва групи.
   - **SIP Peers** — виберіть транки зі списку. Порядок має значення: перший транк є пріоритетним.

Обробка групи здійснюється через FastAGI-сервер (handler `dial-trunk-group`).

---

## 10. Діалплан (Dialplan)

Система використовує синтаксис AEL (Asterisk Extension Language) для діалплану.

### Контексти (DialplanContext)

Контекст — це логічна група розширень (extensions) у діалплані Asterisk.

**Створення контексту:**

1. Адмін-панель → PBX Setup → Dialplan Contexts → Add Dialplan Context.
2. Поля:
   - **Name** — унікальне ім'я контексту. Назви контекстів та таблиць маршрутизації є спільним простором імен.
   - **Description** — опис.

**Примітка:** Контексти та таблиці маршрутизації не можуть мати однакових імен.

### Розширення (DialplanExtension)

Розширення — це окремі номери або шаблони в контексті з визначеним діалпланом на мові AEL.

**Створення розширення:**

1. З контексту (inline) або напряму: PBX Setup → Dialplan Extensions → Add.
2. Поля:

| Поле | Опис |
|------|------|
| **Context** | Батьківський контекст |
| **Ext** | Номер або шаблон (AEL-валідація) |
| **Dialplan** | Тіло розширення на мові AEL |
| **Description** | Опис |

**Валідація:** Поле `ext` проходить валідацію через `validate_asterisk_extension_prefix`. Діалплан проходить валідацію через `AsteriskDialplanValidator` для перевірки синтаксису AEL.

**Приклад діалплану:**

```ael
{
    Answer();
    Wait(1);
    Playback(hello);
    Hangup();
}
```

### Макроси (DialplanMacro)

Макроси AEL — це багаторазово використовувані блоки діалплану.

**Створення макросу:**

1. Адмін-панель → PBX Setup → Dialplan Macros → Add.
2. Поля: **Name**, **Description**, **Macro** (тіло макросу на AEL).

### Глобальні змінні (DialplanGlobalVariable)

Дозволяють визначити іменовані записи, що потрапляють у блок `globals { }` на початку
згенерованого `extensions.ael`.

1. Адмін-панель → PBX Setup → Dialplan Global Variables → Add.
2. Поля: **Name**, **Value**.
3. Ім'я перевіряється на коректний синтаксис ідентифікатора; значення не може містити `;`
   або переноси рядків.

### Примітка щодо імен

Оскільки `DialplanContext` і `RoutingTable` мають спільний простір імен, неможливо створити контекст і таблицю маршрутизації з однаковою назвою. Адмін-форма контексту перевіряє унікальність через `DialplanContextAdminForm`.

---

## 11. Маршрутизація дзвінків

Маршрутизація дзвінків визначає, як обробляються вихідні дзвінки на основі префікса номера.

### Таблиці маршрутизації (RoutingTable)

Таблиця маршрутизації групує записи маршрутизації. Назви таблиць поділяють простір імен із Dialplan-контекстами.

**Створення:**

1. PBX Setup → Routing Tables → Add Routing Table.
2. **Name** — назва таблиці (унікальна, не може співпадати з контекстом).

### Записи маршрутизації (RoutingRecord)

Кожен запис визначає, в який контекст направити дзвінок залежно від префікса номера.

| Поле | Опис |
|------|------|
| **Prefix** | Префікс номера (наприклад, `_2XX` — внутрішні, `_380` — Україна) |
| **Name** | Назва запису |
| **Context** | Контекст діалплану для обробки |
| **Routing Table** | Таблиця маршрутизації |

**Сортування:** Записи обробляються в порядку, визначеному полем `name`. Система також підтримує AEL-синтаксис для префіксів (знак `_` на початку означає шаблон).

**Типові записи:**

| Prefix | Призначення |
|--------|-------------|
| `_2XX` | Внутрішні номери |
| `_0[1-9]X.` | Міські дзвінки |
| `_380` | Дзвінки по Україні |
| `_X.` | Всі інші (catch-all) |

---

## 12. Черги

### Створення черги

1. Адмін-панель → PBX Setup → Queues → Add Queue.
2. Основні поля:

| Поле | Опис |
|------|------|
| **Name** | Унікальне ім'я черги |
| **Strategy** | Стратегія розподілу дзвінків (`ringall`, `leastrecent`, `fewestcalls`, `random`, `rrmemory`, `rrordered`, `linear`, `wrandom`) |
| **Music Class** | Клас MOH для музики в черзі |

### Додавання членів черги

**Масове додавання через форму:**

1. У формі черги знайдіть секцію **Add Members**.
2. Виберіть SIP-користувачів зі списку `Add SIP Users`.
3. При збереженні для кожного вибраного користувача буде створено запис `QueueMember` з інтерфейсом `PJSIP/{username}`.
4. Існуючі члени черги не змінюються.

**Індивідуальне додавання:**

- Використовуйте inline-форму **Queue members** на сторінці черги.
- Або створіть запис напряму: PBX Setup → Queue Members → Add.

Поля члена черги:

| Поле | Опис |
|------|------|
| **Member Name** | Ім'я агента (відображається в дашборді) |
| **Interface** | Інтерфейс агента (наприклад, `PJSIP/101`) |
| **State Interface** | Інтерфейс для відстеження стану |
| **Queue** | Черга |
| **Penalty** | Штраф (визначає пріоритет) |
| **Ring In Use** | Дзвонити агенту, навіть якщо його інтерфейс вже зайнятий іншим викликом |
| **Wrapuptime** | Індивідуальний час "після дзвінка" для цього агента (перекриває значення черги) |

### Правила черг (Queue Rules)

Правила визначають зміну пріоритетів (penalty) агентів залежно від часу очікування дзвінка в черзі.

**Створення правила:**

1. Адмін-панель → PBX Setup → Queue Rules → Add Queue Rule.
2. Додайте кроки ескалації (Penalty Changes):
   - **Seconds** — через скільки секунд застосувати правило.
   - **Max Penalty** — максимальний штраф.
   - **Min Penalty** — мінімальний штраф.
   - **Raise Penalty** — збільшення штрафу.
   - **Order** — порядок застосування.

**Прив'язка правила до черги:**

У формі черги, секція **Queue Rules**, виберіть правило зі списку `Default Rule`. Посилання `Edit Rule` відкриває сторінку редагування правила в новій вкладці.

### Анонси черг (Queue Announcements)

Налаштовуються в секції **Announcements** форми черги:

- **Announce** — звуковий файл для оголошення.
- **Queue Announce** — оголошення назви черги.
- **Queue Announcement** — вибір типу оголошення.
- **Announce Frequency** — частота оголошень (сек).
- **Announce Holdtime** — оголошення часу очікування.
- **Announce Position** — оголошення позиції в черзі.

### Додаткові налаштування (секція Advanced)

У згорнутій секції **Advanced** доступні всі параметри черг Asterisk:

- timeout, retry, maxlen, wrapuptime
- autopause, autopausedelay
- context, service_level, weight, autofill, ringinuse
- joinempty, leavewhenempty
- monitor_format
- timeoutpriority, timeoutrestart
- periodic_announce, random_periodic_announce
- setqueuevar
- та інші.

### Глобальні налаштування черг (CallQueueGlobalSettings)

Доступно через адмін-панель: PBX Setup → Call Queue Global Settings. Тут можна задати глобальні параметри, які застосовуються до всіх черг, зокрема `shared_lastcall`, `setvar`, `persistent_members`, `autofill`, `monitor_type`, `negative_penalty_invalid`, `force_longest_waiting_caller`.

---

## 13. Музика на утриманні (MOH)

### Класи MOH (MusicOnHold)

1. Адмін-панель → PBX Setup → Music On Hold → Add Music On Hold.
2. Поля:

| Поле | Опис |
|------|------|
| **Name** | Назва класу MOH |
| **Mode** | Режим: `files` (відтворення файлів), `playlist` (плейлист), `custom` |
| **Directory** | Директорія з файлами |
| **Sort** | Сортування файлів: `alpha`, `random`, `randstart` |

### Плейлисти MOH (MusicOnHoldPlaylistEntry)

Додаються inline у формі класу MOH:

| Поле | Опис |
|------|------|
| **File** | Ім'я файлу |
| **URL** | Адреса потоку (якщо режим playlist) |
| **MOH Class** | Клас MOH |

---

## 14. Звукові файли

Система дозволяє завантажувати звукові файли для використання в діалплані через модель `SoundFile`.

1. Адмін-панель → PBX Setup → Sound Files → Add Sound File.
2. Поля:

| Поле | Опис |
|------|------|
| **Language** | Мова файлу (наприклад, `uk`, `en`) |
| **Name** | Назва файлу (без розширення) |
| **File** | Аудіофайл для завантаження |

Файли зберігаються через кастомне сховище `SoundsFileSystemStorage`, яке копіює файли у відповідну директорію Asterisk.

---

## 15. Apply Changes

**Apply Changes** — це ключовий механізм системи, який генерує конфігураційні файли Asterisk з даних у базі даних, створює бекап та перезавантажує Asterisk.

### Доступ

Apply Changes доступний тільки для **superuser**. Шлях: `/admin/apply`.

### Процес

1. **Перегляд змін:** На сторінці `/admin/apply` показано всі конфігураційні файли, які будуть згенеровані, з їхнім вмістом.
2. **Застосування:** Позначте галочку "Apply Changes" та натисніть кнопку.
3. **Бекап:** Система створює архів `tar.gz` поточної конфігурації в `ASTERISK_BACKUP_DIR`.
4. **Генерація файлів:** Записує файли в `ASTERISK_ROOT_DIR + ASTERISK_CONFIG_DIR`.
5. **TLS-сертифікати:** Якщо є TLS-транспорти, сертифікати записуються в `{CONFIG_DIR}/certificate/`.
6. **Версіонування:** Кожен файл зберігається в БД (`ConfigurationFile`) з версією. Якщо вміст не змінився, версія не збільшується.
7. **SystemConfiguration:** Створюється знімок поточної конфігурації з посиланнями на всі `ConfigurationFile`.
8. **Перезавантаження Asterisk:** Виконується AMI-команда:
   - **Soft reload** — перезавантаження модулів (`module reload`).
   - **Hard restart** — повний перезапуск Asterisk (`restart gracefully`).

### Які файли генеруються

| Файл | Функція генерації | Опис |
|------|-------------------|------|
| `/etc/asterisk/pjsip.conf` | `make_pjsip_conf()` | Транспорти, ендпоінти, auth, AOR, реєстрації |
| `/etc/asterisk/extensions.ael` | `make_extensions_ael()` | Діалплан, макроси, маршрутизація |
| `/etc/asterisk/queues.conf` | `make_queues_conf()` | Черги та глобальні налаштування |
| `/etc/asterisk/queuerules.conf` | `make_queuerules_conf()` | Правила ескалації черг |
| `/etc/asterisk/manager.conf` | `make_manager_conf()` | AMI-користувачі (менеджери) |
| `/etc/asterisk/musiconhold.conf` | `make_musiconhold_conf()` | Класи MOH та плейлисти |
| Додаткові файли | Користувацькі | Через модель `ConfigurationFile` |

### Користувацькі конфігураційні файли (ConfigurationFile)

Модель `ConfigurationFile` дозволяє додавати довільні файли конфігурації Asterisk:

1. Адмін-панель → PBX Setup → Configuration Files → Add.
2. Поля: **Name**, **Description**, **Path** (шлях відносно `ASTERISK_ROOT_DIR`), **Content**.
3. При кожному Apply Changes файли з найновішою версією включаються в набір конфігурацій.

Це дозволяє керувати файлами, які не генеруються автоматично (наприклад, `features.conf`, `cdr.conf`, `logger.conf`).

### Перегляд історії

Моделі `ConfigurationFile` та `SystemConfiguration` зберігають історію змін. Кожен SystemConfiguration — це знімок стану конфігурації на момент Apply, що дозволяє відстежити, які файли і в яких версіях були застосовані. Знімок також включає посилання на бінарні файли (модель `BinaryFile`, наприклад TLS-сертифікати), застосовані разом із текстовими конфігами.

---

## 16. Служби (Services)

Система включає кілька окремих служб, кожна з яких працює як окремий процес. Всі служби мають власне віртуальне середовище та systemd unit.

### Загальна інформація

Всі служби запускаються від користувача `asterisk`.

| Служба | systemd unit | Порт | Призначення |
|--------|-------------|------|-------------|
| Django | `PearlPBX2.service` | 8000 | Веб-додаток |
| Dashboard Listener | `pearlpbx2-dashboard.service` | — | AMI → Redis |
| Callback Daemon | `pearlpbx2-callback.service` | — | Колбеки |
| FastAGI Server | `pearlpbx2-fastagi.service` | 4573 | AGI-обробники |

**Примітка:** юніти встановлюються та керуються через Ansible (`ansible/roles/services/`); шаблони `.service`-файлів у `services/` у корені репозиторію застаріли й не відповідають назвам, що реально розгортаються.

### Dashboard Listener

**Директорія:** `services/dashboard/`

Служба підключається до Asterisk через AMI та слухає всі події, публікуючи їх у Redis Pub/Sub на каналі `asterisk:events`.

**Дані в Redis:**

| Ключ | Опис |
|------|------|
| `asterisk:channels:*` | Активні канали |
| `asterisk:channels:all` | Всі канали (JSON) |
| `asterisk:queue:{name}` | Стан черги (агенти, дзвінки) |
| `parking:uline:*` | Стан паркувальних слотів |
| `statistics:*` | Статистика дзвінків |

**Запуск:**

```bash
cd services/dashboard
source .python-venv/bin/activate
python dashboard_listener.py
```

**Перевірка роботи:**

```bash
systemctl status pearlpbx2-dashboard.service
journalctl -u pearlpbx2-dashboard.service -f
```

**Залежності:** `redis`, `asterisk-ami`

**Сповіщення в Slack про пропущені дзвінки (опціонально):** служба може надсилати агреговане повідомлення в Slack, коли абоненти залишають чергу без відповіді. Всі пропущені дзвінки в межах вікна debounce групуються в одне повідомлення на чергу. Налаштовується через змінні в `services/dashboard/env`:

| Змінна | Опис | Типове значення |
|--------|------|-----------------|
| `SLACK_MISSED_CALL_WEBHOOK_URL` | Slack incoming webhook URL. Порожнє значення вимикає функцію | — (вимкнено) |
| `MISSED_CALL_DEBOUNCE_SECONDS` | Вікно групування пропущених дзвінків в одне повідомлення | `60` |

### Callback Daemon

**Директорія:** `services/callback/`

Служба моніторить таблицю `callback_number` у базі даних. Коли з'являється запис зі статусом `NEW`, служба:

1. Блокує запис через `SELECT FOR UPDATE SKIP LOCKED` (запобігання race condition при multiprocessing).
2. Викликає AMI `Originate` для створення вихідного дзвінка.
3. Оновлює статус на `PENDING`, `ANSWERED` або `BUSY`.

**Запуск:**

```bash
cd services/callback
source .python-venv/bin/activate
python callback.py
```

**Параметри:**

```bash
python callback.py --db_host=localhost --ami_user=admin --ami_pass=secret
python callback.py --process_count=4   # багатопроцесорний режим
python callback.py --dump_config      # перегляд конфігурації
```

**Залежності:** `psycopg2-binary`, `asterisk-ami`, `requests`

### FastAGI Server

**Директорія:** `services/fastagi/`

Сервер FastAGI на базі Twisted + StarPy. Слухає порт 4573 та обробляє AGI-запити від Asterisk.

**Обробники (handlers):**

| Handler | Призначення | Змінна, що встановлюється |
|---------|-------------|--------------------------|
| `blacklist` | Перевірка номера в блок-листі | `BLACKLISTED` (0/1) |
| `whitelist` | Перевірка номера в дозволеному списку | `WHITELISTED` (0/1) |
| `customlist` | Перевірка в іменованому списку | `CUSTOM_LISTED` (0/1) |
| `dial-trunk-group` | Дзвінок через групу транків (failover) | `TRUNK_GROUP_DIALLED` (0/1) |
| `mixmonitor` | Запуск запису розмови | `MIXMONITOR` (0/1) |
| `add-callback` | Додавання запиту на колбек | `CALLBACK_ADDED` (0/1) |
| `queue-status` | Перевірка доступності черги | `READYTORECEIVE`, `QUEUECALLERS` |
| `parking-uline` | Розподіл паркувального слоту | `ULINE` (номер слоту або 0) |

**ULINE Redis Manager** — керує паркувальними слотами (1–199) через атомарний Lua-скрипт у Redis.

**Запуск:**

```bash
cd services/fastagi
source venv/bin/activate
python fastagi.py
```

**Залежності:** `twisted`, `starpy`, `psycopg2-binary`, `redis`

### Класичні AGI-скрипти (Slack-сповіщення)

**Директорія:** `services/agi/`

На відміну від FastAGI Server (окрема служба на порту 4573), це класичні AGI-скрипти (`missed_call.py`, `unmatched_call.py`), які Asterisk запускає напряму з діалплану для точкових Slack-сповіщень про пропущені та невідповідні дзвінки. Спільний функціонал (зокрема `notify_slack()`) винесено в `agi_common.py`.

**Конфігурація:** `/etc/PearlPBX/AGI/env`.

### Приклад використання FastAGI в діалплані

```ael
context check_blacklist {
    _X. => {
        AGI(agi://127.0.0.1:4573/blacklist);
        if ("${BLACKLISTED}" = "1") {
            Hangup();
        }
    }
}
```

---

## 17. Веб-хуки (CRM)

Веб-хуки дозволяють автоматично надсилати CRM-системі JSON POST-запити про події дзвінків (початок, відповідь оператора, завершення, пропущений дзвінок у черзі). Реалізовано в `apps/webhooks/` — доставку обробляє Dashboard Listener на основі подій AMI.

**Докладний опис форматів payload, перевірки підпису та прикладів обробника** — в окремому гайді [docs/ua/crm-integration.md](crm-integration.md) (а також спрощена версія для розробників CRM: [docs/ua/crm-integrator-guide.md](crm-integrator-guide.md)). Цей розділ описує лише налаштування веб-хука в адмін-панелі.

### Створення веб-хука

1. Адмін-панель → Webhooks → Add Webhook.
2. Поля:

| Поле | Опис |
|------|------|
| **Name** | Унікальна назва веб-хука |
| **Description** | Опис (для власної навігації) |
| **Is Active** | Увімкнути/вимкнути надсилання без видалення налаштування |
| **URL** | Ендпоінт на боці CRM, куди надсилається JSON POST |
| **Send Incoming** | Надсилати подію на початок вхідного дзвінка |
| **Send Ended** | Надсилати подію на завершення дзвінка (потребує ввімкненого Send Incoming, інакше дзвінок не буде "анонсовано") |
| **Send Missed** | Надсилати подію при пропущеному дзвінку в черзі (потребує вибору хоча б однієї черги) |
| **Send Answered** | Надсилати подію, коли оператор черги відповів на дзвінок (потребує вибору хоча б однієї черги) |
| **Contexts** | Контексти діалплану, вхідні дзвінки в яких запускають веб-хук |
| **Queues** | Черги, приєднання до яких запускає веб-хук |
| **Headers** | Додаткові HTTP-заголовки у форматі JSON (наприклад, `{"Authorization": "Bearer ..."}`) |
| **Secret** | Спільний секрет для HMAC-SHA256 підпису тіла запиту (заголовок `X-PearlPBX-Signature`) |
| **Timeout** | Таймаут HTTP-запиту в секундах (за замовчуванням 5) |
| **Retries** | Кількість повторних спроб доставки після невдачі (за замовчуванням 1) |
| **Payload Template** | Кастомний JSON-шаблон тіла запиту з підстановками `${placeholder}`; якщо очистити поле — використовується вбудований шаблон за замовчуванням для кожного типу події |

**Примітка:** якщо для веб-хука не вибрано жодного контексту чи черги, форма адміна вимагає вказати принаймні один з них (інакше незрозуміло, які дзвінки мають запускати доставку).

---

## 18. REST API

Система надає REST API для зовнішньої інтеграції. Докладна документація: [docs/en/API.md](../en/API.md), а також живий Swagger UI на `/api/v1/docs/` і OpenAPI-схема на `/api/v1/schema/`.

Для інтеграції з CRM-системами (веб-хуки про дзвінки, розділ 17 вище) та доступ до записів розмов через API див. окремий гайд: [docs/ua/crm-integration.md](crm-integration.md).

### Короткий огляд

API побудовано на Django REST Framework (`DefaultRouter` + `ViewSet`-и, `apps/api/`).

**Базовий URL:** `/api/v1/`

**Автентифікація:** token-based через DRF `TokenAuthentication` (заголовок `Authorization: Token <key>`). IP-адресних обмежень більше немає. Токен створюється командою:

```bash
python manage.py drf_create_token <username>
```

Без валідного токена запити повертають `401 Unauthorized`.

**Ендпоінти:**

| Ендпоінт | Методи | Призначення |
|----------|--------|-------------|
| `/api/v1/blacklist/` | GET, POST | Список / створення записів блок-листа |
| `/api/v1/blacklist/<uuid>/` | GET, PUT, PATCH, DELETE | Перегляд / зміна / видалення запису |
| `/api/v1/whitelist/` | GET, POST | Список / створення дозволених номерів |
| `/api/v1/whitelist/<uuid>/` | GET, PUT, PATCH, DELETE | Перегляд / зміна / видалення запису |
| `/api/v1/contacts/` | GET, POST | Список / створення контактів |
| `/api/v1/contacts/<uuid>/` | GET, PUT, PATCH, DELETE | Перегляд / зміна / видалення контакту |
| `/api/v1/lists/` | GET, POST | Список іменованих списків / створення нового |
| `/api/v1/lists/<uuid>/` | GET, PATCH, DELETE | Вміст / перейменування / видалення списку |
| `/api/v1/lists/<uuid>/entries/` | GET, POST | Перегляд / додавання записів до списку |
| `/api/v1/lists/<uuid>/entries/<uuid>/` | DELETE | Видалення запису зі списку |
| `/api/v1/calls/originate/` | POST | Ініціювати вихідний дзвінок через AMI (повертає 503, якщо `DEVMODE=without_asterisk_on_localhost`) |
| `/api/v1/recordings/<uniqueid>/` | GET | Отримати аудіофайл запису розмови (підтримка Range-запитів) |
| `/api/v1/docs/`, `/api/v1/redoc/`, `/api/v1/schema/` | GET | Swagger/Redoc UI та OpenAPI-схема |

**Коди статусу:** 200, 201, 204, 400, 401, 404, 409.

**Формат відповіді:** JSON.

---

## 19. Провізіонінг телефонів

Система підтримує автоматичне налаштування SIP-телефонів через TFTP.

### Модель PhoneDevice

| Поле | Опис |
|------|------|
| **MAC Address** | MAC-адреса телефону (унікальна) |
| **SIP User** | Прив'язаний SIP-користувач |
| **Telephone Type** | Тип телефону: `spa502g`, `spa504g`, `gxp1200`, `softphone`, `webrtc`, `other` |
| **SIP Server** | Адреса SIP-сервера, яку отримає пристрій у своїй конфігурації |

### Процес провізіонінгу

1. Зареєструйте телефон у системі (додайте PhoneDevice).
2. Прив'яжіть до існуючого SIP-користувача.
3. Конфігураційні файли генеруються в директорію `TFTP_DIR`.
4. Телефон отримує конфігурацію через TFTP при завантаженні.

---

## 20. Обслуговування

### Резервне копіювання

Система автоматично створює бекап при кожному Apply Changes:

- Архів `tar.gz` зберігається в `ASTERISK_BACKUP_DIR`.
- Формат імені: `asterisk-{timestamp}.tar.gz`.
- Бекап включає всю поточну конфігурацію Asterisk.

Крім того, Ansible-інсталяція налаштовує два щоденні cron-завдання:

- **Бекап PostgreSQL** (`bin/pg_backup_pearlpbx2.sh`) — щодня о 01:30.
- **Бекап `/etc/asterisk`** (`bin/backup_asterisk.sh`) — щодня о 02:30. Архівує `/etc/asterisk`
  у `tar.gz` та зберігає в `BACKUP_DIR` (типово `/var/backups/asterisk-etc`) з ретенцією
  `RETENTION_DAYS` (типово 14 днів). Конфігурація — `/etc/PearlPBX/backup_asterisk/env`
  (шаблон `backup_asterisk.env.j2`); опційно можна вказати `SLACK_WEBHOOK_URL` для сповіщення
  про збій.

### Міграція з PearlPBX1

Директорія `migrate_from_PearlPBX1/` містить скрипти та інструкції для міграції з першої версії системи.

### Оновлення системи

Для оновлення використовуйте `update.sh` або `git pull` з наступним застосуванням міграцій:

```bash
git pull
source .python-venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic
systemctl restart PearlPBX2
```

### Логування

Система логує події через стандартний механізм Django logging:

- **core** логгер — INFO рівень (навмисно знижено з DEBUG, щоб уникнути потрапляння payload'ів подій AMI, які містять caller ID/PII, у journald).
- **django** логгер — INFO рівень.
- **apps** логгер — INFO рівень, `propagate=False`.
- **\_\_main\_\_** логгер — INFO рівень.

Логи виводяться в консоль (stdout). Для продакшну рекомендується налаштувати запис у файл або систему централізованого логування.

### Моніторинг служб

```bash
# Перевірка статусу всіх служб
systemctl status PearlPBX2.service pearlpbx2-dashboard.service pearlpbx2-callback.service pearlpbx2-fastagi.service asterisk.service

# Перегляд логів
journalctl -u PearlPBX2.service -f
journalctl -u pearlpbx2-dashboard.service -f
journalctl -u pearlpbx2-callback.service -f
journalctl -u pearlpbx2-fastagi.service -f
```

---

*Документ створено для PearlPBX2 v2.7.0. Інтерфейс системи та шляхи можуть відрізнятися залежно від конфігурації.*
