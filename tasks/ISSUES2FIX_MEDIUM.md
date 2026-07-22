# ISSUES2FIX (MEDIUM) — покроковий план фіксу M1–M16

Джерело: `tasks/ISSUES.md`, розділ MEDIUM. Verified against the current code on
`extend/api_v1` before writing this plan — every item below is confirmed still
present (M7 and L6 already got fixed as a side effect of the API DRF migration and
are NOT in this file).

Виконуй пункти по порядку. Після кожного пункту запускай тести з розділу
"Перевірка" в кінці. Не змінюй файли, не згадані в пункті. Коментарі в коді — лише
англійською.

## Виключено з цього раунду (рішення користувача)
- **M5** (FastAGI blocks the Twisted reactor) — async refactor of a Twisted service,
  найризикованіше, окремий раунд.
- **M13** (dashboard listener robustness gaps) — async refactor of the asyncio
  service, той самий ризик, окремий раунд.

## Вже виправлено раніше (не займатись)
- M7 — DRF migration replaced the leaky `except Exception → JsonResponse(500)`
  pattern entirely.
- L6 — `Whitelist` already inherits `AuditFields` (migration `0075`).

---

## M1 — CDR CSV: header/row mismatch (`apps/reports/views.py`)

**Проблема:** `export_cdr_csv` (рядок ~679) пише заголовок з 7 колонок, а кожен рядок
має 8 значень (`cdr.channel`, `cdr.dstchannel`) — зсув усіх колонок для будь-якого
споживача CSV.

### Фікс

Знайди `writer.writerow([...])` заголовок (7 елементів, закінчується `"Channel"`) і
додай восьму колонку `"Dest. Channel"`:

```python
        writer.writerow(
            [
                "Date/Time",
                "Source",
                "Destination",
                "Duration",
                "Billed Duration",
                "Status",
                "Channel",
                "Dest. Channel",
            ]
        )
```

Тіло циклу (`cdr.channel`, `cdr.dstchannel`) НЕ чіпати — воно вже коректне, це
заголовок був неповний.

---

## M2 — N+1 у `AnalyticsMissedCallsView` (`apps/reports/views.py`)

**Проблема:** на кожен abandoned call (рядок ~966, цикл `for row in abandon_events`)
робиться до 3 додаткових запитів (`QueueLog` lucky-check, 2×`CDR` exists). При сотнях
abandon-подій на день — тисячі запитів на один page view.

**Підхід:** замінити 3 per-call `.exists()`-запити на 3 batch-запити **на рівні
черги** (один раз на `queuename`, а не на кожен callid), і перевіряти членство в
Python-множинах. Логіка пріоритету (lucky > called_back > done, взаємовиключно)
залишається ідентичною.

### Фікс

Знайди блок усередині `for queuename in queue_names:` (рядок ~939), одразу після
побудови `callerid_by_callid` (рядок ~954-960) і ПЕРЕД циклом
`for row in abandon_events:` (рядок ~966). Встав туди batch-запити:

```python
                callerid_by_callid = {
                    row["callid"]: row["data2"]
                    for row in QueueLog.objects.filter(
                        event="ENTERQUEUE",
                        callid__in=[e["callid"] for e in abandon_events],
                    ).values("callid", "data2")
                }

                all_callids = list(callerid_by_callid.keys())
                all_callerids = list(set(callerid_by_callid.values()))

                # Batch (once per queue, not per abandoned call) the three checks
                # that used to run per-call inside the loop below.
                lucky_new_callids = QueueLog.objects.filter(
                    time__lte=date_to,
                    queuename=queuename,
                    event="ENTERQUEUE",
                    data2__in=all_callerids,
                ).exclude(callid__in=all_callids).values_list("callid", "time", "data2")

                completed_callids = set(
                    QueueLog.objects.filter(
                        callid__in=[c for c, _t, _d in lucky_new_callids],
                        event__in=["COMPLETECALLER", "COMPLETEAGENT"],
                    ).values_list("callid", flat=True)
                )
                lucky_callerids_by_time = {}
                for callid, entry_time, callerid in lucky_new_callids:
                    if callid in completed_callids:
                        lucky_callerids_by_time.setdefault(callerid, []).append(entry_time)

                called_back_callerids = set(
                    CDR.objects.filter(
                        start__lte=date_to,
                        disposition="ANSWERED",
                        src__in=all_callerids,
                    ).values_list("src", "start")
                )
                operator_callerids = set(
                    CDR.objects.filter(
                        start__lte=date_to,
                        disposition="ANSWERED",
                        dst__in=all_callerids,
                    ).values_list("dst", "start")
                )
```

Далі заміни тіло циклу `for row in abandon_events:` (рядок ~966-1010) на версію,
що перевіряє членство в підготовлених множинах замість запитів:

```python
                called_back = 0
                operators = 0

                for row in abandon_events:
                    callid = row["callid"]
                    abandon_time = row["time"]
                    callerid = callerid_by_callid.get(callid)
                    if not callerid:
                        continue

                    # Lucky: re-entered the same queue after abandon_time and completed.
                    if any(
                        t >= abandon_time
                        for t in lucky_callerids_by_time.get(callerid, [])
                    ):
                        called_back += 1
                        continue

                    # Called back: caller dialed in via CDR after abandon_time.
                    if any(
                        src == callerid and start >= abandon_time
                        for src, start in called_back_callerids
                    ):
                        called_back += 1
                        continue

                    # Done: operator dialed the caller after abandon_time.
                    if any(
                        dst == callerid and start >= abandon_time
                        for dst, start in operator_callerids
                    ):
                        operators += 1
```

Це вже 3 batch-запити на чергу замість до 3×N per-call запитів. НЕ намагайся
переписати на єдиний SQL-агрегат — залишайся точно на цій батч-структурі, вона
безпечна і легко перевіряється.

---

## M3 — `ConfigurationFileAdmin.save_model` тихо втрачає правки (`core/admin.py`)

**Проблема:** рядок ~255-267 — якщо `content` не змінився, метод повертається без
`save()`, тому правки `name`/`description`/`path` губляться без жодного
повідомлення користувачу.

### Фікс

Заміни метод `save_model` класу `ConfigurationFileAdmin` (рядок ~255):

```python
    def save_model(self, request, obj, form, change):
        last_instance = (
            ConfigurationFile.objects.filter(name=obj.name).order_by("-version").first()
        )
        if not last_instance:
            obj.save()
            return
        if last_instance.content != obj.content:
            # Create new ConfigurationFile instance with incremented version
            obj.pk = None
            obj.version = last_instance.version + 1
            obj.created = timezone.now()
            obj.save()
        else:
            # Content unchanged: still persist name/description/path edits on the
            # existing row instead of silently discarding them.
            obj.save()
            messages.info(
                request,
                _(
                    "Content unchanged — no new version created; other field "
                    "edits were saved."
                ),
            )
```

Перевір, чи в `core/admin.py` вже є імпорт `from django.contrib import messages` і
`from django.utils.translation import gettext_lazy as _` — якщо немає, додай на
початку файлу.

---

## M4 — `HomepageStatusView` витікання AMI-з'єднань (`core/views/base_views.py`)

**Проблема:** рядок ~148-169 — `logoff()` викликається лише всередині callback
`on_version`, який спрацьовує тільки якщо AMI відповість вчасно. При таймауті
(`done.wait(3)`) з'єднання/потік/сокет лишаються висіти назавжди.

### Фікс

Заміни `try/except` блок (рядок ~155-169) так, щоб `logoff()` гарантовано
викликався і при таймауті:

```python
        client = None
        try:
            client = AMIClient(
                address=settings.ASTERISK_MANAGER_HOST,
                port=int(settings.ASTERISK_MANAGER_PORT),
            )
            client.login(
                username=settings.ASTERISK_MANAGER_USERNAME,
                secret=settings.ASTERISK_MANAGER_SECRET,
                callback=on_login,
            )
            done.wait(timeout=3)
            if ami_result:
                result["asterisk"] = ami_result
        except Exception as e:
            logger.warning("AMI unavailable in HomepageStatusView: %s", e)
        finally:
            if client is not None:
                try:
                    client.logoff()
                except Exception:
                    pass
```

У колбеку `on_version` (рядок ~145-153) прибери дублюючий `client.logoff()` — тепер
про це дбає `finally`:

```python
        def on_version(response, **kwargs):
            output = response.keys.get("Output", "")
            m = re.match(r"(Asterisk\s+[\d.]+)", output)
            ami_result["version"] = m.group(1) if m else output.split(" built")[0]
            done.set()
```

(Прибрано внутрішній `try: client.logoff() except: pass` — залишився лише зовнішній
`finally`, який тепер спрацьовує завжди, включно з таймаутом.)

---

## M6 — Monitor filename з caller-controlled даних (`services/fastagi/fastagi.py`)

**Проблема:** `get_monitor_filename` (рядок ~141) будує
`f"{date_path}/{time_str}_{src}_{dst}"`, де `src`/`dst` — caller ID з мережі.
Символи `/`, `..`, `,` потрапляють у `mkdir_p` і в аргументи `MixMonitor`
(рядок ~471) — path traversal / injection зайвих опцій.

### Фікс

На початку `services/fastagi/fastagi.py`, поруч з іншими module-level константами
(шукай `import re` — він вже є), додай:

```python
_SAFE_CALLERID_RE = re.compile(r"[^0-9A-Za-z+_-]")


def _sanitize_for_path(value: str) -> str:
    """Strip anything but digits/letters/+/_/- so a crafted caller ID cannot
    inject path separators or MixMonitor option delimiters."""
    return _SAFE_CALLERID_RE.sub("", value or "")
```

У методі `get_monitor_filename` (рядок ~141-147) заміни:

```python
    def get_monitor_filename(self, src: str, dst: str, cdr_uniqueid: str) -> str:
        """Generate a unique monitor filename based on current date + UUIDv4."""
        now = datetime.now()
        date_path = now.strftime("%Y/%m/%d")
        uuid_str = str(uuid.uuid4())
        time_str = now.strftime("%H_%M_%S")
        safe_src = _sanitize_for_path(src)
        safe_dst = _sanitize_for_path(dst)
        filename = f"{date_path}/{time_str}_{safe_src}_{safe_dst}"
```

(Далі тіло методу без змін — `uuid_str` вже був згенерований, але перевір, чи він
використовується нижче; якщо ні, залиш як є, не видаляй рядок.)

---

## M8 — MOH віддається без автентифікації (`pbx/urls.py`)

**Рішення користувача:** додати `login_required`.

### Фікс

`pbx/urls.py` — заміни блок реєстрації MOH-роуту (рядок ~21-30):

```python
from django.contrib.auth.decorators import login_required

# ... (залиш решту імпортів як є)

# Serve MOH files (authenticated users only — same tree is writable by admins)
MOH_ROOT = (
    "/var/lib/asterisk/moh/"
    if settings.DEVMODE != settings.DEVMODE_WITHOUT_ASTERISK
    else "moh/"
)
urlpatterns += [
    path("moh/<path:path>", login_required(serve), {"document_root": MOH_ROOT}),
]
```

Додай імпорт `from django.contrib.auth.decorators import login_required` на
початку файлу (поруч з іншими `django.contrib`/`django.views` імпортами).

---

## M9 — Queue-опції, які генератор ігнорує (`core/conf.py`)

**Проблема:** `maxlen`, `weight`, `setqueuevar`, `random_periodic_announce` (на
`Queue`) та `force_longest_waiting_caller` (на `CallQueueGlobalSettings`) є в моделі,
але `_make_single_queue_config()` / `make_queues_conf()` їх не емітять — адмін
міняє значення, які нічого не роблять.

### Фікс

У `core/conf.py`, у функції `_make_single_queue_config` (рядок ~571), знайди місце
одразу після рядка `output.append(f"strategy={queue.strategy}")` і додай:

```python
    output.append(f"strategy={queue.strategy}")
    output.append(_opt("maxlen", queue.maxlen, "0"))
    output.append(f"weight={queue.weight}")
    output.append(_bool_opt("setqueuevar", queue.setqueuevar))
    output.append(_bool_opt("random-periodic-announce", queue.random_periodic_announce))
```

(Використовуй `_opt`/`_bool_opt` — вони вже імпортовані/визначені у файлі та
використовуються поруч для аналогічних полів; подивись на сусідні рядки для
точного стилю виклику.)

Знайди `make_queues_conf()` (рядок ~639) — там, де формується глобальна секція
`[general]` (шукай, де емітяться інші `CallQueueGlobalSettings` поля), додай:

```python
    output.append(
        _bool_opt(
            "force_longest_waiting_caller",
            global_settings.force_longest_waiting_caller,
        )
    )
```

Онов'ляй за тим самим патерном, за яким сусідні global-settings поля вже
емітяться в тій самій функції — знайди змінну, яка тримає
`CallQueueGlobalSettings`-інстанс, і онови ім'я за аналогією.

---

## M10 — `MusicOnHold.mode`/`sort` мають невалідні дефолти (`core/models.py`)

**Проблема:** рядки ~836 (`mode`) і ~853 (`sort`) — `default=1` (int) при
`TextChoices` зі string-значеннями (`"files"`, `"random"`, ...). Об'єкт, створений
програмно без явного значення, отримує `mode="1"`, що не збігається з жодною
гілкою в `make_musiconhold_conf()`.

### Фікс

Знайди `class MusicOnHoldModes(models.TextChoices)` (рядок ~815) і
`class MusicOnHoldSortModes(models.TextChoices)` (рядок ~821) — визначи перше
значення кожного (наприклад `FILES = "files"` і аналогічний перший член сортування).

У полі `mode` (рядок ~836):

```python
    mode = models.CharField(
        max_length=32,
        default=MusicOnHoldModes.FILES,
        choices=MusicOnHoldModes.choices,
        null=True,
        blank=False,
    )
```

У полі `sort` (рядок ~853), використай перший член `MusicOnHoldSortModes`
(подивись точну назву в class-визначенні, наприклад `RANDOM` чи як він там
називається):

```python
    sort = models.CharField(
        max_length=32,
        default=MusicOnHoldSortModes.<ПЕРШИЙ_ЧЛЕН>,
        choices=MusicOnHoldSortModes.choices,
        null=True,
        blank=False,
    )
```

Заміни `<ПЕРШИЙ_ЧЛЕН>` на реальну назву константи з `MusicOnHoldSortModes`.

Після зміни — обов'язково згенеруй міграцію (це `AlterField`, не потребує
backfill, бо `null=True` вже дозволяє старі рядки).

---

## M11 — Cisco TFTP: підкаталог моделі ніколи не створюється + dead stub

**Проблема (реальний баг):** `apps/provision/provisioning_manager.py`,
`save_config_file` (рядок ~92) робить лише `open(filepath, "wb")`. Для Cisco
`filename = f"{model}/{mac}.xml"` (рядок ~83) — підкаталог `{model}/` ніколи не
створюється, тільки базовий `config_directory` (в `__init__`, рядок ~31). Кожен
Cisco-телефон падає з `FileNotFoundError`.

**Друга знахідка (важливо повідомити користувачу, не мовчати):** сам ISSUES.md
пункт M11 також описує `apps/provision/views.py::apply_all_configurations` як
"stub, що симулює й нічого не пише". Перевірка показала: ця функція **НЕ
підключена до жодного urls.py** (`apps/provision` не має власного `urls.py`, і
`pbx/urls.py` не інклюдить `apps.provision`) — вона повністю мертвий, недосяжний
код. Реальна робоча реалізація вже існує в
`apps/provision/admin.py::PhoneDeviceAdmin.apply_all_configurations_view`
(маршрут `admin:provision_phonedevice_apply_all`), яка коректно викликає
`PhoneProvisioningManager(settings.TFTP_DIR).provision_device(device)` для кожного
пристрою з нормальним success/failure звітом.

Тому "реалізувати справжню generate+save" для мертвого коду означало б дублювати
те, що вже правильно зроблено в admin — порушення DRY. **Правильний фікс: видалити
мертвий stub**, а не реалізовувати другий шлях виконання тієї самої дії.

### Фікс 1 — Cisco-директорія (реальний баг)

`apps/provision/provisioning_manager.py`, метод `save_config_file` (рядок ~92):

```python
    def save_config_file(self, config_data, filename):
        """Save configuration file"""
        filepath = os.path.join(self.config_directory, filename)
        os.makedirs(os.path.dirname(filepath), exist_ok=True)

        with open(filepath, "wb") as f:
            f.write(config_data)

        return filepath
```

(Додано лише `os.makedirs(os.path.dirname(filepath), exist_ok=True)` перед
`open()` — покриває і Grandstream (без підкаталогу — `os.path.dirname` поверне
`config_directory`, `makedirs` на існуючу директорію з `exist_ok=True` нешкідливий).

### Фікс 2 — видалення мертвого stub

Видали функцію `apply_all_configurations` цілком з `apps/provision/views.py`. Якщо
після видалення файл `apps/provision/views.py` стає порожнім (лише імпорти без
використання) — залиш файл як є (не видаляй файл, тільки функцію), щоб не зламати
потенційні `from apps.provision import views` десь ще. Перевір grep-ом:

```bash
grep -rn "from apps.provision import views\|apps.provision.views" --include="*.py" .
```

Якщо є інші посилання на цей модуль — не видаляй файл, лише функцію.

---

## M12 — `SIPUser` side-effects і `save()`-time ValidationError

Дві незалежні проблеми в `core/models.py`:

### 12.1 — Model-level `clean()` для `DialplanContext`/`RoutingTable`

**Проблема:** `DialplanContext.save()` (рядок ~190) і `RoutingTable.save()`
(рядок ~255) кидають `ValidationError` прямо із `save()`. Поза формою (скрипт,
management command, `objects.create()`) це стає непіймано́ю 500-помилкою, а не
акуратною формою-помилкою.

**Фікс:** додай `clean()` з тією ж перевіркою в обидва класи (адитивно — існуючу
перевірку в `save()` НЕ видаляй, вона й далі захищає прямі виклики поза формою).

У `DialplanContext` (рядок ~163-190), перед методом `save`:

```python
    def clean(self):
        super().clean()
        if (
            RoutingTable.objects.filter(name=self.name)
            .exclude(pk=self.pk if self.pk else None)
            .exists()
        ):
            raise ValidationError(
                {"name": _('Context name "%(name)s" already exists in RoutingTable.') % {"name": self.name}}
            )
```

У `RoutingTable` (рядок ~218-255), перед методом `save`:

```python
    def clean(self):
        super().clean()
        if (
            DialplanContext.objects.filter(name=self.name)
            .exclude(pk=self.pk if self.pk else None)
            .exists()
        ):
            raise ValidationError(
                {"name": _('Context name "%(name)s" already exists in DialplanContext.') % {"name": self.name}}
            )
```

Перевір, що `from django.utils.translation import gettext_lazy as _` вже
імпортовано у `core/models.py` (майже напевно так, бо він використовується всюди
у файлі).

### 12.2 — `SIPUser.delete()` лишає `DialplanExtension` після видалення

**Проблема:** `SIPUser.save()` (рядок ~392) автоматично створює/оновлює
`DialplanExtension`, але видалення `SIPUser` не чіпає цей extension — сирота
лишається в dialplan назавжди.

**Фікс:** додай `delete()` override у `SIPUser` (десь після методу `save`, рядок
~392-430):

```python
    def delete(self, *args, **kwargs):
        default_users_context = DialplanContext.getUsersOrCreateUsers()
        DialplanExtension.objects.filter(
            context=default_users_context, ext=self.extension
        ).delete()
        return super().delete(*args, **kwargs)
```

Не намагайся виправляти "hijack" сценарій із двох користувачів на одному
`previous_extension` в цьому раунді — це складніша структурна зміна (потребує
явного FK замість пошуку за текстовим `ext`), винеси її окремим TODO-пунктом у
`tasks/backlog.md`, а не переписуй `save()` зараз.

---

## M14 — `callback.py`: docs vs behaviour + SQL identifier (`services/callback/callback.py`, `services/callback/CLAUDE.md`)

### 14.1 — Документація неправдива

`services/callback/CLAUDE.md` стверджує "AMI reconnection: automatic on disconnect
via `on_disconnect()`", але коду, що реєструє такий callback, немає — health-check
робить `os._exit(1)` (рядки ~110, ~114) і покладається на `systemd Restart=`.

**Фікс:** виправ документацію, а не код (реалізація через systemd — це правильний
підхід для цього сервісу, вигадувати `on_disconnect()` немає сенсу). У
`services/callback/CLAUDE.md` знайди фразу про "automatic on disconnect via
`on_disconnect()`" і заміни на:

```markdown
AMI reconnection: not automatic. A background health-check thread calls
`os._exit(1)` when the AMI connection is lost; the process is expected to be
supervised by systemd with `Restart=always` (see the provided unit file).
```

### 14.2 — SQL identifier interpolation

`update_call_status` (рядок ~264) і `update_uniqueid` (рядок ~271) інтерполюють
`self.dbtable` у SQL через f-string. Значення конфіг-джерельне (не з мережі), але
безпечніше використати `psycopg2.sql.Identifier`.

**Фікс:** на початку `services/callback/callback.py` додай імпорт (якщо ще немає):

```python
from psycopg2 import sql
```

Заміни обидва методи:

```python
    def update_call_status(self, id: int, dst: str, status: str):
        self.ensure_db_connected()
        dt = datetime.now(timezone.utc)
        cursor = self.conn.cursor()

        query = sql.SQL(
            "update {table} set updated=%s, dial_status=%s where dst=%s and id=%s"
        ).format(table=sql.Identifier(self.dbtable))
        cursor.execute(query, (dt, status, dst, id))
        self.conn.commit()

    def update_uniqueid(self, id: int, uniqueid: str):
        self.ensure_db_connected()
        cursor = self.conn.cursor()
        query = sql.SQL("update {table} set uniqueid=%s where id=%s").format(
            table=sql.Identifier(self.dbtable)
        )
        cursor.execute(query, (uniqueid, id))
        self.conn.commit()
```

Перевір інші місця у файлі, що так само роблять `f"...{self.dbtable}..."` (grep
`self.dbtable` у файлі) — застосуй той самий патерн скрізь, де `dbtable`
інтерполюється в SQL-текст.

---

## M15 — `get_all_queues` блокуючий `KEYS` (`apps/dashboard/views.py`)

**Проблема:** рядок ~91 — `r.keys("asterisk:queue:*")` блокує Redis; решта коду
файлу вже використовує `scan_iter` (рядки ~192, ~289).

### Фікс

Знайди рядок:

```python
        queue_keys = r.keys("asterisk:queue:*")
```

Заміни на:

```python
        queue_keys = list(r.scan_iter("asterisk:queue:*"))
```

(Обгортання в `list(...)` — бо `scan_iter` повертає генератор, а решта коду під
цим рядком, ймовірно, очікує список/ітерований об'єкт кілька разів; якщо код нижче
ітерує лише один раз, `list()` все одно безпечний і не ламає нічого.)

---

## M16 — Дубльована HTTP-Range логіка (`apps/reports/views.py`)

**Проблема:** `AudioFileView` (рядок ~369) і `AudioFileByUniqueidView`
(рядок ~425) дублюють однакові ~30 рядків Range/206-логіки.

### Фікс

Додай module-level helper-функцію у `apps/reports/views.py`, ПЕРЕД визначенням
класу `AudioFileView`:

```python
def _serve_audio_file_response(request, file_path, content_type, filename):
    """Shared Range/206 + full-file response logic for audio playback views."""
    file_size = os.stat(file_path).st_size

    if request.GET.get("download"):
        return FileResponse(
            open(file_path, "rb"),
            content_type=content_type,
            as_attachment=True,
        )

    range_header = request.META.get("HTTP_RANGE", "").strip()
    range_match = (
        re.match(r"bytes=(\d+)-(\d*)", range_header) if range_header else None
    )

    if range_match:
        first = int(range_match.group(1))
        last = int(range_match.group(2)) if range_match.group(2) else file_size - 1
        last = min(last, file_size - 1)
        if first >= file_size or first > last:
            return HttpResponse(status=416)
        length = last - first + 1
        with open(file_path, "rb") as f:
            f.seek(first)
            data = f.read(length)
        response = HttpResponse(data, status=206, content_type=content_type)
        response["Content-Range"] = f"bytes {first}-{last}/{file_size}"
        response["Content-Length"] = str(length)
    else:
        response = FileResponse(open(file_path, "rb"), content_type=content_type)
        response["Content-Length"] = str(file_size)
        response["Content-Disposition"] = f'inline; filename="{filename}"'

    response["Accept-Ranges"] = "bytes"
    response["Cache-Control"] = "private, max-age=3600"
    return response
```

Заміни тіло `AudioFileView.get` (рядок ~370-422), залишаючи файл-специфічний
пошук шляху й `content_type` як є:

```python
class AudioFileView(ReportViewPermissionMixin, View):
    def get(self, request, record_id):
        record = get_object_or_404(MonitorFilenames, id=record_id)
        file_path = record.get_audio_file_path()

        try:
            os.stat(file_path)
        except FileNotFoundError:
            raise Http404("Audio file does not exist")

        content_type, _ = mimetypes.guess_type(file_path)
        if content_type is None:
            content_type = "audio/wav"

        filename = os.path.basename(file_path)
        return _serve_audio_file_response(request, file_path, content_type, filename)
```

Заміни тіло `AudioFileByUniqueidView.get` (рядок ~426-479), залишаючи пошук
`file_path` за `uniqueid`/розширенням як є:

```python
class AudioFileByUniqueidView(ReportViewPermissionMixin, View):
    def get(self, request, uniqueid):
        if not re.match(r"^[\d.]+$", uniqueid):
            raise Http404("Invalid uniqueid")

        file_path = None
        for ext in (".mp3", ".wav"):
            candidate = os.path.join(settings.ASTERISK_MONITOR_DIR, uniqueid + ext)
            if os.path.exists(candidate):
                file_path = candidate
                break

        if not file_path:
            raise Http404("Audio file does not exist")

        try:
            os.stat(file_path)
        except FileNotFoundError:
            raise Http404("Audio file does not exist")

        content_type, _ = mimetypes.guess_type(file_path)
        if content_type is None:
            content_type = "audio/mpeg" if file_path.endswith(".mp3") else "audio/wav"

        filename = os.path.basename(file_path)
        return _serve_audio_file_response(request, file_path, content_type, filename)
```

⚠️ Примітка (не фіксити зараз, лише занотовано в коді ISSUES.md): ranged-гілка
читає весь шматок у пам'ять одним `f.read(length)` — прийнятно для типових
довжин аудіодзвінка, але залиш це як відомий compromise, не переписуй на
`FileResponse`+`StreamingHttpResponse` у цьому раунді (більший, окремий рефакторинг).

---

## Перевірка (запускати після кожного пункту і в кінці)

Пам'ятай: після H9-фіксу (попередній раунд) режим `Development`/`Production`/
`Staging` без `DJANGO_SECRET_KEY` падає з `ImproperlyConfigured`. Для тестів
використовуй `without_asterisk_on_localhost` (як у `docker-compose.test.yml`):

```bash
export DEVMODE=without_asterisk_on_localhost
export DJANGO_SECRET_KEY=test-secret-key-for-testing-only

# 1. Міграції застосовуються (M10 генерує AlterField)
.python-venv/bin/python manage.py makemigrations --check --dry-run
.python-venv/bin/python manage.py migrate

# 2. Повний тестсьют
.python-venv/bin/python manage.py test --noinput --verbosity=2
```

Якщо для якогось пункту (M1, M2, M9, M16) немає існуючих тестів, що фіксують
поведінку — додай мінімальний тест у відповідний `tests.py` (apps/reports/tests.py,
core/tests.py тощо):
- M1: CSV-експорт має однакову кількість колонок у заголовку й у рядку даних.
- M2: результат `AnalyticsMissedCallsView` для набору `QueueLog`/`CDR` фікстур
  збігається з очікуваними called_back/operators (можна взяти існуючий тест, якщо
  він там уже є, і просто перевірити, що він і далі проходить — головне, щоб
  числа не змінились після рефакторингу).
- M9: `_make_single_queue_config()` для `Queue` з `maxlen=10, weight=5,
  setqueuevar=True` містить `maxlen=10`, `weight=5`, `setqueuevar=yes` у виводі.
- M16: обидва view (`AudioFileView`, `AudioFileByUniqueidView`) повертають
  однакові Range-заголовки для однакового файлу (regression test, що рефакторинг
  нічого не зламав).

Готово, коли `makemigrations --check` — "No changes detected", `migrate` проходить
чисто, і повний `manage.py test` — `OK`.
