# Image Logger — Tracker + Sherlock (setup desde cero)

Resumen
- Proyecto para generar enlaces "tracked" (append o redirect), capturar clics (IP/UA/referer), lanzar Sherlock de forma asíncrona si se dispone de un identificador (username/email/alias/phone) y notificar resultados (por webhook de Discord).
- El flujo incluye una página intersticial (delay configurable, por defecto 5s) antes de redirigir al destino original. Esto asegura que la petición pase por tu infraestructura y puedas registrar datos del visitante.
- Uso legal: únicamente ejecutar sobre objetivos/entornos para los que tengas autorización explícita. Protege accesos y registros.

Características principales
- Modo híbrido: append (añadir parámetros) para dominios whitelist; redirect (shortlink → interstitial → redirect) para el resto (ej. invites).
- Captura inmediata de IP/UA/Referer cuando un usuario abre un shortlink.
- Notificaciones estilo "embed" a Discord vía webhook con: IP, ISP/ASN, país/ciudad, coordenadas aproximadas, timezone, indicación Mobile/VPN/Proxy (cuando esté disponible), OS/Browser y User-Agent.
- Ejecución de Sherlock en background (Celery + Redis) para búsquedas OSINT sobre identificadores.
- Resultados y artefactos guardados en disco (JSON) para auditoría y revisión.

Estructura recomendada de carpetas
- tracker/                 # código del tracker (Flask + Celery tasks)
  - app.py
  - tasks.py
  - celery_app.py
  - requirements.txt
  - Dockerfile
- tools/                   # scripts auxiliar (ej. install_sherlock.sh)
- bot/                     # bot de Discord (slash command + cliente)
  - register_commands.js
  - discord_bot.js
- .pages/
  - IPlogger/
    - ip.php               # snippet PHP que envía hit al tracker y redirige
  - sherlock/               # salida de Sherlock (.json, .txt)
- docker-compose.yml       # orquestación (Redis, tracker, worker)
- .env.example             # variables de entorno ejemplo
- README.md                # este archivo

Requisitos mínimos
- Para desarrollo:
  - Python 3.10+
  - pip, Git
  - Node.js (si vas a ejecutar el bot con Discord.js) o Bot Designer en móvil (opcional)
- Para ejecución con Docker (recomendado):
  - Docker + docker-compose
- Opcional (mejora de precisión geoip/vpn):
  - Claves API para IPQualityScore, ipinfo, proxycheck, MaxMind, etc. (usualmente de pago)

Pasos rápidos (manual, sin Docker)
1. Crear la estructura de carpetas según el apartado anterior.
2. Editar `.env` a partir de `.env.example` y rellenar valores (TRACK_SECRET, HOOK_TOKEN, PUBLIC_BASE, DISCORD_WEBHOOK, etc.). Nunca comites `.env`.
3. Clonar Sherlock (solo si vas a usar la integración):
   - `chmod +x tools/install_sherlock.sh`
   - `./tools/install_sherlock.sh`
4. Crear e instalar entorno Python:
   - `python3 -m venv .venv`
   - `source .venv/bin/activate`
   - `pip install -r tracker/requirements.txt`
5. Ejecutar Redis (puedes instalar localmente o usar un servicio):
   - `redis-server` (o usar container)
6. Ejecutar worker Celery (en terminal separada):
   - `celery -A tracker.celery_app.celery worker --loglevel=info`
7. Ejecutar tracker:
   - `python tracker/app.py`
8. Registrar slash command (si usas Discord bot) y ejecutar bot:
   - `node bot/register_commands.js` (registrar)
   - `node bot/discord_bot.js` (ejecutar bot localmente)

Levantar con Docker Compose (recomendado)
1. Copia `.env.example` → `.env` y edítalo.
2. Asegúrate de haber clonado Sherlock en `.tools/sherlock` (o monta el repo donde corresponda).
3. Construye y levanta:
   - `sudo docker compose up --build -d`
4. Ver logs:
   - `sudo docker compose logs -f tracker`
   - `sudo docker compose logs -f tracker_worker`

Uso básico (flujo)
1. Crear tracked link (desde bot o curl):
   - POST `/convert` con JSON: { "url": "<original>", "prefer": "auto|append|redirect", "identifier": "<opcional>", "name": "<opcional>" }
2. Respuesta:
   - `mode: append` → `appended_url` (no cambia dominio)
   - `mode: redirect` → `short_url` (por ejemplo `https://PUBLIC_BASE/r/<slug>`)
3. Usuario abre `short_url`:
   - Tracker registra IP/UA/referer e inmediatamente encola tareas (notificación + Sherlock si aplica).
   - Tracker devuelve interstitial (delay configurable; por defecto 5s) y luego redirige al original.

Seguridad y secretos (resumen)
- Genera secretos fuertes (TRACK_SECRET, HOOK_TOKEN). Ejemplo:
  - `openssl rand -hex 32`
  - `python3 - <<'PY'\nimport secrets; print(secrets.token_urlsafe(48))\nPY`
- No comites `.env`. Añádelo a `.gitignore`.
- Usa HTTPS cuando expongas PUBLIC_BASE. Considera Caddy/Nginx con Let's Encrypt.
- Protege `/convert` con HOOK_TOKEN validado en cabecera `x-hook-token`.
- No ejecutes el mismo bot token en dos clientes distintos simultáneamente (evita sesiones inestables).

Detección VPN / Proxy
- Por ahora el sistema usa ip-api/ipinfo como fallback y marca `proxy`/`mobile` cuando esas APIs indican. Para mayor precisión puedes integrar IPQualityScore o proxycheck (servicios de pago). El sistema permite incluir esas integraciones más adelante.

Auditoría y retención
- Todos los hits y resultados de Sherlock se guardan en archivos JSON (p. ej. `.pages/sherlock/` y `tracker_data/store.json`). Asegura permisos de acceso y considera cifrado/rotación en producción.

Próximos pasos (qué haremos en la sesión)
- Crearás manualmente los archivos en este orden (yo te doy cada archivo listo para pegar):
  1. `.env.example` (ya listo)
  2. `tools/install_sherlock.sh` (ya listo)
  3. `.pages/IPlogger/ip.php`
  4. `tracker/requirements.txt`
  5. `tracker/celery_app.py`
  6. `tracker/tasks.py`
  7. `tracker/app.py` (con interstitial forzado y verificación HOOK_TOKEN)
  8. `tracker/Dockerfile`
  9. `docker-compose.yml`
  10. `bot/register_commands.js`
  11. `bot/discord_bot.js`
  Extenciones a instalar:

    Python (ms-python.python) — soporte Python (intellisense, debug, ejecutar archivos, selección de intérprete).
    Pyright (ms-pyright) — comprobación estática y tipado rápido (alternativa ligera a Pylance).
    YAML (redhat.vscode-yaml) — validación y autocompletado para docker-compose.yml y otros YAML.
    Docker (ms-azuretools.vscode-docker) — gestión de imágenes/containers y ayuda con Docker Compose.
    DotENV (mikestead.dotenv) — coloreado y ayuda con archivos .env.

Altamente recomendadas

    GitLens — mejoras en Git: blame por línea, history, insights. (eamodio.gitlens)
    Prettier — formateador para JS/JSON/Markdown (esbenp.prettier-vscode)
    ESLint — linting para JavaScript/Node (dbaeumer.vscode-eslint)
    Markdown All in One — ayudas para editar README.md (yzhang.markdown-all-in-one)
    REST Client — probar endpoints HTTP desde el editor sin curl (humao.rest-client)
    ShellCheck — lint para scripts bash (timonwong.shellcheck)

Útiles para este proyecto (dependiendo de lo que uses)

    PHP Intelephense — soporte PHP para ip.php (bmewburn.vscode-intelephense-client)
    Jinja (wholroyd.jinja) — si editas plantillas HTML/Jinja (p. ej. interstitials)
    EditorConfig — aplica reglas de formato del equipo (.editorconfig) (EditorConfig.EditorConfig)
    Node.js / NPM Intellisense — para el bot JS (christian-kohler.npm-intellisense)
    Remote - SSH — editar/depurar en un VPS remoto desde el editor (ms-vscode-remote.remote-ssh) — opcional

Notas sobre VSCodium / OpenVSX

    Si usas VSCodium puede que algunas extensiones Microsoft no estén en OpenVSX. En general:
        Pyright está disponible y suficiente si ms-python no aparece.
        Busca por el nombre de la extensión (p. ej. “Python”, “Pyright”, “Docker”) en el panel de extensiones.
    Si alguna extensión no aparece, instala la alternativa indicada (p. ej. Pyright en lugar de Pylance).
