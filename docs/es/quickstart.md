*Also available in: [English](../en/quickstart.md) | [Українська](../ua/quickstart.md) | [Español](quickstart.md)*

# PearlPBX2 — Guía rápida

Dos formas de poner en marcha PearlPBX2, según lo que necesites. Consulta [README.md](../../README.md) para ver la lista completa de funciones, la arquitectura y la referencia de configuración.

## Requisitos

- **Opción 1 (Ansible)**: solo un host Debian o Ubuntu limpio, nada más. `install.sh`
  instala Ansible por sí mismo, y `install.yml` aprovisiona todo lo demás —
  Python, PostgreSQL, Redis y Asterisk 22 (compilado desde el código fuente) — en
  el host destino. No hace falta instalar nada a mano de antemano.
- **Opción 2 (Docker Compose)**: solo Docker y Docker Compose. Toda la pila
  (Python 3.10+/Django 5.2, PostgreSQL 14+, Redis 7+, Asterisk 22+ con
  `res_pjsip`/`res_agi`/`cdr_pgsql`) se ejecuta íntegramente en contenedores.

## Lo que obtienes desde el primer momento

Una instalación nueva siembra una PBX de demostración funcional, no una base de
datos vacía. Después de la primera ejecución de migraciones/despliegue, ya tienes:

| Extensiones | Qué es |
|---|---|
| `201`–`210` | 10 usuarios SIP (`ppbxuser201`…`ppbxuser210`), contraseñas aleatorias |
| `130` | Prueba de eco |
| `131` / `132` | Iniciar/cerrar sesión de un agente en la cola (`PauseQueueMember`) |
| `140` | Probar el IVR desde un teléfono interno |
| `141` | Cola Sales |
| `142` | Cola Support |

Además:

- Dos colas, **Sales** y **Support**, con los 10 usuarios como miembros
- Un IVR en inglés (`ivr-main`): "press 1 for Sales, press 2 for Support", con 2
  reintentos ante timeout/dígito inválido antes de derivar a Sales por defecto
- Un troncal SIP de ejemplo, `myprovider` (`csbc.myprovider.net`, usuario `test` / `secret`) —
  un marcador de posición para sustituir por tu proveedor real (ver
  [Sustituir el troncal de ejemplo](#sustituir-el-troncal-de-ejemplo))
- Dos tablas de enrutamiento: **Incoming** (toda llamada entrante → el IVR) y **Outgoing**
  (los 10 usuarios se enrutan a través de ella: extensiones internas, los números
  `130`–`142`, y cualquier otra cosa saliente vía `myprovider`)

Todo esto lo siembra `manage.py seed_quickstart`, que solo se ejecuta una vez, en una
instalación nueva — ver [Notas / próximos pasos](#notas--próximos-pasos) para saber cómo se garantiza esto.

## Opción 1: Ansible (instalación de producción)

Requiere un host Debian o Ubuntu (el playbook usa `apt` y systemd directamente — no se admiten otras distribuciones).

Aprovisiona Asterisk (compilado desde el código fuente), PostgreSQL, Redis, nginx, unidades systemd y el firewall en un host nuevo — sin pasos manuales:

```bash
git clone https://github.com/radetsky/PearlPBX2.git
cd PearlPBX2
sudo ./install.sh
```

`install.sh` instala Ansible por sí mismo si hace falta y ejecuta `ansible/install.yml` (añade `-v` para salida detallada de Ansible), registrando todo en `/var/log/pearlpbx2-install.log`. Cuando termine, crea el usuario administrador con:

```bash
./manage.sh createsuperuser
```

luego abre `https://<tu-host>/admin/`.

Para aplicar actualizaciones más adelante, ejecuta `sudo ./update.sh` desde el mismo directorio — este ejecuta `ansible/update.yml`, que mantiene un historial de reversión (`rollback.sh`) por si una actualización necesita deshacerse. `update.sh` nunca vuelve a sembrar los datos de quick-start descritos arriba, así que es seguro ejecutarlo en un sistema en producción.

Consulta `ansible/group_vars/all.yml` para las variables que usa (directorio de instalación, nombre de la BD, versión de Asterisk, etc.) y `ansible/roles/` para lo que hace cada rol.

## Opción 2: Docker Compose (recomendado — evaluación, desarrollo)

```bash
git clone https://github.com/radetsky/PearlPBX2.git
cd PearlPBX2

cp env.sample .env
# Edita .env — configura las credenciales de la BD, luego genera y rellena:
#   DJANGO_SECRET_KEY:       openssl rand -hex 50
#   ASTERISK_MANAGER_SECRET: openssl rand -base64 48

docker compose up -d
docker compose exec django python manage.py createsuperuser
```

Abre `http://localhost:8000/admin/`, inicia sesión y ve directamente a
[Apply Changes](#apply-changes) — los datos de quick-start ya están en la
base de datos, solo falta enviarlos a Asterisk una vez.

Notas:
- `django` ejecuta las migraciones y la siembra de quick-start automáticamente en cada arranque (`docker-entrypoint.sh`) — no hace falta un `migrate` manual. La siembra solo actúa una vez; los reinicios posteriores no hacen nada.
- `asterisk-init` siembra un `manager.conf` mínimo con AMI habilitado antes del primer arranque de Asterisk, para que `fastagi`/`dashboard-listener` se conecten de inmediato; "Apply Changes" lo sobrescribe después con la configuración real generada, usando las mismas credenciales.
- El demonio de callback es opcional (origina llamadas salientes reales): `docker compose --profile callback up -d callback-service`.
- Un `docker-compose.override.yml` se detecta automáticamente y le da al contenedor `django` recarga en caliente del código fuente para desarrollo local; ejecuta `docker compose -f docker-compose.yml up -d` para omitirlo.

## Obtén tus credenciales SIP

Las contraseñas de 201–210 se generan aleatoriamente y solo se guardan en la
base de datos. En el admin, ve a **SIP Users**, abre **201** (o cualquier otro) y revela el
campo **Password** — estas instrucciones usan **201** y **202**.

## Registra dos softphones

En cualquier cliente SIP (Zoiper, Linphone, un teléfono de sobremesa, …), registra dos cuentas usando
las credenciales anteriores:

- **Server**: la IP/host de tu PBX
- **Transport**: UDP, puerto `5060`
- **Username / Password**: `ppbxuser201` / la contraseña del admin (e igual para 202)

## Apply Changes

Nada de lo anterior llega a Asterisk hasta que lo apliques. En la interfaz de admin, ve a
**Admin → Apply Changes** (`/admin/apply`). Esto regenera `extensions.ael`,
`pjsip.conf`, `queues.conf`, `queuerules.conf`, `manager.conf`, `musiconhold.conf`
y `confbridge.conf` a partir de la base de datos, hace una copia de seguridad de las
versiones anteriores y recarga Asterisk. Hazlo una vez ahora, y de nuevo después de
cualquier cambio realizado desde el admin.

## Escenarios de prueba de llamadas

Haz esto en orden — cada paso se apoya en el anterior.

| # | Escenario | Marcar | Resultado esperado / verificación |
|---|---|---|---|
| 1 | Prueba de eco | `130` | Escucharás tu propia voz en bucle. `asterisk -rx "core show channels"` muestra la llamada. |
| 2 | Llamada interna | 201 marca `202` | 202 suena. `asterisk -rx "pjsip show endpoints"` muestra ambos como `Avail`. |
| 3 | Transferencia | Durante la llamada, transferencia ciega con `#` o asistida con `*`, destino `202` o `141` | Ver [Transferencia](#transferencia) más abajo |
| 4 | Salida al mundo exterior | Marca cualquier número externo | Falla hasta que [sustituyas el troncal de ejemplo](#sustituir-el-troncal-de-ejemplo). Luego `asterisk -rx "pjsip show registrations"` debería mostrar `myprovider` como `Registered`. |
| 5 | IVR desde un teléfono interno | `140`, luego pulsa `1` o `2` | Caes en Sales o Support. `asterisk -rx "queue show Sales"` muestra la llamada. |
| 6 | Llamada entrante de producción | Llama a tu DID desde el exterior | Enrutada vía **Incoming** → `ivr-main`. `asterisk -rx "pjsip set logger on"` para ver la traza SIP en vivo. |

(Docker Compose: antepón `docker compose exec asterisk` a cada `asterisk -rx "..."`.)

### Transferencia

Los códigos de función de transferencia vienen de `contrib/configs/features.conf`:
`#` = transferencia ciega, `*` = transferencia asistida (sección `[featuremap]`). Ambas
requieren las opciones `t`/`T` en el `Dial()` por el que entró la llamada — ya presentes
en cada extensión sembrada (p. ej. `Dial(PJSIP/${EXTEN}@myprovider,120,tT)`).

Puedes llamar desde la extensión 201 a la 202, y durante la llamada, pulsar `#130#` para transferir tu llamada a la prueba de eco. Tu llamada debería finalizar, y la otra parte debería escuchar el saludo `demo-echotest`.

Una vez iniciada una transferencia, Asterisk resuelve los dígitos marcados a través de la
variable global **`TRANSFER_CONTEXT`**, en lugar del contexto propio del canal —
sembrada como:

```
globals {
    TRANSFER_CONTEXT=Outgoing;
}
```

Por eso los usuarios están en la tabla de enrutamiento `Outgoing`: es lo que permite
que el destino de una transferencia sea tanto una extensión interna (`_2XX`) como un número
externo (`_X.`) vía `myprovider`, desde un único contexto consistente.

## Sustituir el troncal de ejemplo

`myprovider` (`csbc.myprovider.net` / `test` / `secret`) es un marcador de posición — nunca
se registrará. En **Admin → SIP Uplinks and Peers → myprovider**, sustituye:

- `registration_uri` / `contact_uri` / `match_hosts` — el hostname del SBC de tu proveedor
- `username` / `secret` — las credenciales de tu cuenta

Luego [Apply Changes](#apply-changes) y verifica:

```bash
asterisk -rx "pjsip show registrations"
```

`myprovider` debería pasar de `Rejected`/`No response` a `Registered`.

## Notas / próximos pasos

- **Las llamadas internacionales están bloqueadas por defecto.** La tabla `Outgoing`
  enruta `_00X!` (prefijos internacionales) al contexto `international-calls`, que
  simplemente cuelga — un valor predeterminado seguro para que una instalación nueva con
  credenciales de ejemplo nunca se convierta en un vector de fraude telefónico. Elimina o
  redirige esa `DialplanExtension` cuando estés listo para permitirlas.
- **`Outgoing` frente a la tabla heredada `PEARLPBX`.** `PEARLPBX` sigue existiendo (es
  `settings.PEARLPBX_DEFAULT_ROUTING_TABLE`, usada como respaldo en otros lugares) pero ningún
  usuario SIP se enruta ya a través de ella después de que se ejecuta la siembra de quick-start — todos
  están en `Outgoing`.
- **Varios troncales / enrutamiento por menor costo.** El contexto sembrado
  `outbound-external` marca `myprovider` directamente. Para más de un troncal, cambia a
  `AGI(agi://127.0.0.1:4573/dial-trunk-group,...)` — ver
  `services/fastagi/README.md` para grupos de troncales con failover.
- **La música en espera (MOH)** de las colas usa `contrib/moh/on_hold_music.wav` — sustituye
  los archivos de la clase MOH `default` por los tuyos.
- **La grabación de llamadas** no está habilitada por defecto; ver `MixMonitor` en
  [admin-guide.md](admin-guide.md).
- **La propia siembra de quick-start** es `manage.py seed_quickstart` — comprueba si
  ya existe alguna `Queue`, `SIPPeer` o tabla de enrutamiento `Incoming`/`Outgoing`,
  y no hace nada si es así, por lo que es seguro invocarla manualmente. El `install.yml`
  de Ansible la llama una vez, condicionada por la misma comprobación de "primera
  instalación en este host" usada para generar los secretos; `update.yml` nunca la llama.
