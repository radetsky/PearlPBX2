# GOING TO OPENSOURCE — PearlPBX2

> План підготовки проєкту до публічного open-source релізу (ліцензія AGPL-3.0)
>
> **Статус оновлено:** 2026-04-12

---

## Аудит поточного стану

### ✅ Зроблено
| Пункт | Доказ |
|---|---|
| `proto/` видалено | директорії немає |
| `services/express/` видалено | директорії немає |
| `services/mocked-http-test/` видалено | директорії немає |
| Express design docs видалено | `docs/plans/` порожня |
| PARKING_ULINE FastAGI handler | `services/fastagi/fastagi.py:376` — `elif network_script == "parking-uline"` |
| `uline_redis.py` | `services/fastagi/uline_redis.py` (ключі `parking:uline:{N}`, `parking:uid:{uniqueid}`) |
| Dashboard listener ключі | `services/dashboard/dashboard_listener.py:462` пише `parking:uline:*`; `express:*` не зустрічається |
| Dashboard views ключі | `apps/dashboard/views.py:178,275` читає `parking:uline:*`, використовує `PARKING_ULINE_MIN/MAX` |
| `docs/en/CHANGELOG.md` | присутній у репозиторії |
| README: License section | `README.md:138-140` (лінк на LICENSE) |

### ⚠️ Частково
| Пункт | Що лишилось |
|---|---|
| README | немає AGPL shield badge |
| `.gitignore` | немає `.env` / `*.env`, немає `staticfiles/`; `staticfiles/` зараз у working tree |
| `PARKING_ULINE_MIN/MAX` у settings | використовується лише через `getattr(..., default)` у `apps/dashboard/views.py`; у `pbx/settings.py` змінних немає — варто явно оголосити |
| UI label | `pbx/settings.py:254` ще містить `"title": _("ULINE Monitor")` — треба `Parking ULINE Monitor` |

### ❌ Не зроблено (блокери AGPL релізу)
| Пункт | Нотатки |
|---|---|
| `LICENSE` | AGPL-3.0 повний текст у корені |
| `NOTICE` | авторство + короткий AGPL preamble |
| SPDX headers | `core/models.py`, `core/conf.py`, `manage.py`, `pbx/settings.py` |
| `env.sample` — `PARKING_ULINE_MIN/MAX` | файл взагалі не містить ULINE/PARKING змінних |
| `docker-compose.yml` — розширений стек | немає `fastagi`, `dashboard-listener`, `callback` сервісів |
| Service Dockerfiles | `services/fastagi/Dockerfile`, `services/dashboard/Dockerfile`, `services/callback/Dockerfile` відсутні |
| `CONTRIBUTING.md` | відсутній (у README є короткий блок, цього замало) |

---

## 1. Ліцензування (блокери)

### 1.1 Файл LICENSE
- Створити `LICENSE` у корені — повний текст AGPL-3.0
- Джерело: https://www.gnu.org/licenses/agpl-3.0.txt

### 1.2 Файл NOTICE
```
PearlPBX2 — Django-based Asterisk PBX management interface
Copyright (C) 2024-2026 Alex Radetsky

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published
by the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

License: AGPL-3.0 — see LICENSE file
```

### 1.3 README.md
- Badge нагорі: `[![License: AGPL v3](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)`
- Узгодити секцію `## License` з `LICENSE`/`NOTICE`

### 1.4 SPDX headers
```python
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2024-2026 Alex Radetsky
```
Мінімально: `core/models.py`, `core/conf.py`, `manage.py`, `pbx/settings.py`.

### 1.5 Перевірка історії на секрети
```bash
git log --all -p -- "*.env" | grep -i "password\|secret"
git grep -in "password\|secret\|api_key" -- "*.py" "*.yml" "*.sample"
```

---

## 2. Репо-гігієна

### 2.1 .gitignore
Поточний файл містить лише `.python-venv`, `.vscode`, `db.sqlite3`, `__pycache__`, `.coverage`, `.DS_Store`. Додати:
```
.env
*.env
staticfiles/
*.pyc
.idea/
local_settings.py
```

### 2.2 staticfiles/
- Перевірити чи директорія tracked; за потреби `git rm --cached -r staticfiles/` (destructive — узгодити з користувачем).

### 2.3 Завершити PARKING_ULINE конфіг
- `pbx/settings.py` — явно оголосити:
  ```python
  PARKING_ULINE_MIN = env.int("PARKING_ULINE_MIN", default=1)
  PARKING_ULINE_MAX = env.int("PARKING_ULINE_MAX", default=199)
  ```
- `pbx/settings.py:254` — перейменувати UI title `ULINE Monitor` → `Parking ULINE Monitor`.
- `env.sample` — додати:
  ```
  PARKING_ULINE_MIN=1
  PARKING_ULINE_MAX=199
  ```

---

## 3. Docker Compose — повний локальний стек

### 3.1 Dockerfile для кожного сервісу
- `services/fastagi/Dockerfile` — entrypoint `python fastagi.py`, expose 4573
- `services/dashboard/Dockerfile` — entrypoint `python dashboard_listener.py`
- `services/callback/Dockerfile` — entrypoint `python callback.py`

### 3.2 Розширити docker-compose.yml
Поточний стек: `django`, `asterisk`, `postgres`, `redis`. Додати:
```yaml
fastagi:
  build: services/fastagi
  environment: [DB, Redis config]
  depends_on: [postgres, redis]
  restart: unless-stopped

dashboard-listener:
  build: services/dashboard
  environment: [AMI, Redis config]
  depends_on: [redis, asterisk]
  restart: unless-stopped

callback-service:
  build: services/callback
  environment: [DB, AMI config]
  depends_on: [postgres, asterisk]
  profiles: ["callback"]
```

### 3.3 Django контейнер
- Entrypoint запускає `migrate` + `collectstatic` ідемпотентно на старті.
- `docker-compose.override.yml` (dev): volumes hot-reload, DEBUG=1.

### 3.4 README Quick Start
```bash
cp env.sample .env
docker-compose up -d
docker-compose exec django python manage.py createsuperuser
# http://localhost:8000/admin/
```

---

## 4. Community документація

### 4.1 CONTRIBUTING.md
- Fork → feature branch → PR процес
- PEP 8, `python manage.py test`
- Issue tracker, code review очікування

### 4.2 docs/
- Переглянути `tasks/backlog.md`, `docs/en/realtime_in_future.md` — що винести у `docs/roadmap/`, що приховати до релізу.

---

## Файли для модифікації

| Файл | Дія |
|---|---|
| `LICENSE` | **створити** (AGPL-3.0) |
| `NOTICE` | **створити** (авторство) |
| `CONTRIBUTING.md` | **створити** |
| `README.md` | badge + Quick Start |
| `.gitignore` | додати `.env`, `*.env`, `staticfiles/`, `*.pyc`, `.idea/` |
| `core/models.py`, `core/conf.py`, `manage.py`, `pbx/settings.py` | SPDX header |
| `pbx/settings.py` | оголосити `PARKING_ULINE_MIN/MAX` + rename UI title |
| `env.sample` | додати `PARKING_ULINE_MIN/MAX` |
| `services/fastagi/Dockerfile` | **створити** |
| `services/dashboard/Dockerfile` | **створити** |
| `services/callback/Dockerfile` | **створити** |
| `docker-compose.yml` | додати `fastagi`, `dashboard-listener`, `callback` (profile) |
| `docker-compose.override.yml` | **створити** (dev hot-reload) |

---

## Пріоритети

1. **Блокери AGPL:** `LICENSE`, `NOTICE`, SPDX headers, README badge, sensitive-data scan.
2. **Гігієна:** `.gitignore`, `PARKING_ULINE_MIN/MAX` у settings + env.sample, UI title.
3. **Docker:** Dockerfile-и сервісів + розширення compose.
4. **Спільнота:** `CONTRIBUTING.md`, cleanup `docs/`.

---

## Верифікація

```bash
# 1. Django sanity
python manage.py check
python manage.py test

# 2. License presence
test -f LICENSE && test -f NOTICE && echo OK

# 3. Sensitive data scan
git grep -in "password\|secret\|api_key" -- "*.py" "*.yml" "*.sample"

# 4. Docker full stack
docker-compose up -d
docker-compose ps
docker-compose --profile callback up -d callback-service

# 5. PARKING_ULINE e2e
# - тестовий виклик через fastagi parking-uline endpoint
# - redis-cli keys 'parking:uline:*'
# - http://localhost:8000/dashboard/ulines/

# 6. Dependency licenses
pip install pip-licenses && pip-licenses --from=mixed --order=license
```
