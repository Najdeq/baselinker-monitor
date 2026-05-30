#!/usr/bin/env python3
"""
BaseLinker Monitor – pełna wersja z zakładkami konkurentów
==========================================================
Panel: http://localhost:5000
"""

import csv, io, json, os, sys, time, signal, logging, logging.handlers, threading
from datetime import datetime
from pathlib import Path

import requests
from flask import Flask, jsonify, request, send_from_directory

try:
    from dotenv import load_dotenv; load_dotenv()
except ImportError:
    pass

# ══════════════════════════════════════════════════════════════════
#  KONFIGURACJA
# ══════════════════════════════════════════════════════════════════
DISCORD_WEBHOOK_URL  = os.getenv("DISCORD_WEBHOOK_URL", "TWÓJ_WEBHOOK_URL_DISCORD")
EXPORT_URL           = os.getenv("EXPORT_URL", "")
OWELL_EXPORT_URL     = os.getenv("OWELL_EXPORT_URL", "")
CHECK_INTERVAL_MIN   = int(os.getenv("CHECK_INTERVAL_MINUTES", "30"))
PRICE_DIFF_THRESHOLD = float(os.getenv("PRICE_DIFF_THRESHOLD", "0.01"))
WEB_PORT             = int(os.getenv("WEB_PORT", "5000"))

BASE_DIR    = Path(__file__).parent
LOG_FILE    = BASE_DIR / "monitor.log"
CACHE_FILE  = BASE_DIR / "price_cache.json"
CONFIG_FILE = BASE_DIR / "monitor_config.json"
ALERTS_FILE = BASE_DIR / "alerts_history.json"

# Mapowanie konkurentów — jak ich nazwy pojawiają się w eksporcie BaseLinker
COMPETITORS = {
    "Owell":      ["owell", "o-well", "owell-eu"],
    "Wuberg":     ["wuberg"],
    "Avenido":    ["avenido-eu", "avenido"],
    "SevenKraft": ["sevenkraft", "seven kraft", "7kraft", "sevenkraft-eu"],
    "Rottwell":   ["rottwell", "rotwell", "rottwell-eu"],
}

# ══════════════════════════════════════════════════════════════════
#  LOGI
# ══════════════════════════════════════════════════════════════════
def setup_logging():
    fmt  = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    ch = logging.StreamHandler(sys.stdout); ch.setFormatter(fmt); root.addHandler(ch)
    fh = logging.handlers.RotatingFileHandler(
        LOG_FILE, maxBytes=5*1024*1024, backupCount=3, encoding="utf-8")
    fh.setFormatter(fmt); root.addHandler(fh)

setup_logging()
log = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════
#  KONFIGURACJA JSON
# ══════════════════════════════════════════════════════════════════
DEFAULT_CONFIG = {
    "check_interval_minutes": CHECK_INTERVAL_MIN,
    "price_diff_threshold":   PRICE_DIFF_THRESHOLD,
    "discord_enabled":        True,
    "include_delivery":       False,
    "updated_at":             None,
}

def load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, encoding="utf-8") as f:
                cfg = json.load(f)
            for k, v in DEFAULT_CONFIG.items():
                cfg.setdefault(k, v)
            return cfg
        except Exception:
            pass
    save_config(DEFAULT_CONFIG.copy())
    return DEFAULT_CONFIG.copy()

def save_config(cfg: dict):
    cfg["updated_at"] = datetime.now().isoformat()
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)

# ══════════════════════════════════════════════════════════════════
#  HISTORIA ALERTÓW
# ══════════════════════════════════════════════════════════════════
def load_alerts() -> list:
    if ALERTS_FILE.exists():
        try:
            with open(ALERTS_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception: pass
    return []

def append_alert(alert: dict):
    alerts = load_alerts()
    alert["timestamp"] = datetime.now().isoformat()
    alerts.insert(0, alert)
    with open(ALERTS_FILE, "w", encoding="utf-8") as f:
        json.dump(alerts[:500], f, indent=2, ensure_ascii=False)

# ══════════════════════════════════════════════════════════════════
#  CACHE
# ══════════════════════════════════════════════════════════════════
def load_cache() -> dict:
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, encoding="utf-8") as f: return json.load(f)
        except Exception: pass
    return {}

def save_cache(c: dict):
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(c, f, indent=2, ensure_ascii=False)

# ══════════════════════════════════════════════════════════════════
#  POBIERANIE CSV
# ══════════════════════════════════════════════════════════════════
def _to_float(s) -> float:
    try: return float(str(s).strip().replace(",", "."))
    except: return 0.0

def fetch_csv(url: str) -> list[dict]:
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    sample = resp.text[:500]
    sep    = ";" if sample.count(";") > sample.count(",") else ","
    return list(csv.DictReader(io.StringIO(resp.text), delimiter=sep))

def fetch_export() -> list[dict]:
    """Główny eksport — wszystkie aukcje z cenami konkurencji."""
    rows_raw = fetch_csv(EXPORT_URL)
    rows = []
    for r in rows_raw:
        comp_price = r.get("competition_price", "").strip()
        if not comp_price:
            continue
        rows.append({
            "auction_id":                 r.get("auction_id", "").strip(),
            "products_id":                r.get("products_id", "").strip(),
            "price":                      _to_float(r.get("price", "")),
            "competition_auction_id":     r.get("competition_auction_id", "").strip(),
            "competition_price":          _to_float(comp_price),
            "competition_price_delivery": _to_float(r.get("competition_price_delivery", "")),
            "competition_seller_name":    r.get("competition_seller_name", "").strip(),
        })
    return rows

def fetch_owell_ids() -> set:
    """Eksport aukcji Owell — tylko auction_id."""
    if not OWELL_EXPORT_URL:
        return set()
    try:
        rows = fetch_csv(OWELL_EXPORT_URL)
        ids  = {r.get("auction_id", "").strip() for r in rows if r.get("auction_id", "").strip()}
        log.info(f"  Pobrano {len(ids)} aukcji Owell")
        return ids
    except Exception as e:
        log.warning(f"  Błąd eksportu Owell: {e}")
        return set()

def seller_to_competitor(seller_name: str) -> str | None:
    """Mapuje nazwę sprzedawcy z eksportu na nazwę zakładki."""
    s = seller_name.strip().lower()
    for comp_name, aliases in COMPETITORS.items():
        if s in [a.lower() for a in aliases]:
            return comp_name
    return None

# ══════════════════════════════════════════════════════════════════
#  DISCORD
# ══════════════════════════════════════════════════════════════════
def send_discord_alert(alerts: list[dict], cfg: dict):
    if not alerts or not cfg.get("discord_enabled"): return
    embeds = []
    for a in alerts:
        diff     = a["our_price"] - a["comp_total"]
        my_url   = f"https://allegro.pl/oferta/{a['auction_id']}"
        comp_url = f"https://allegro.pl/oferta/{a['comp_auction_id']}" if a.get("comp_auction_id") else None
        embeds.append({
            "title": f"🚨 Przebita cena! Aukcja {a['auction_id']}",
            "url":   my_url,
            "color": 0xFF3B30,
            "fields": [
                {"name": "💰 Twoja cena",  "value": f"**{a['our_price']:.2f} zł**\n[→ Twoja aukcja]({my_url})", "inline": True},
                {"name": "📉 Konkurencja", "value": f"**{a['comp_total']:.2f} zł**" + (f"\n[→ Aukcja]({comp_url})" if comp_url else ""), "inline": True},
                {"name": "📊 Różnica",     "value": f"**-{diff:.2f} zł**",           "inline": True},
                {"name": "🏪 Sprzedawca",  "value": a.get("seller") or "—",          "inline": True},
                {"name": "🆔 ID produktu", "value": a.get("products_id") or "—",     "inline": True},
            ],
            "footer": {"text": f"BaseLinker Monitor • {datetime.now().strftime('%d.%m.%Y %H:%M')}"},
        })
    for i in range(0, len(embeds), 10):
        chunk   = embeds[i:i+10]
        payload = {
            "username": "BaseLinker Monitor 🔍",
            "content":  f"⚠️ **{len(chunk)} aukcji z przebitą ceną!**" if i == 0 else "",
            "embeds":   chunk,
        }
        try:
            resp = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
            if resp.status_code not in (200, 204):
                log.error(f"Discord błąd {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            log.error(f"Discord: {e}")
        time.sleep(1)

def send_discord_summary(total: int, n_alerts: int, cfg: dict):
    if not cfg.get("discord_enabled"): return
    color   = 0xFF3B30 if n_alerts > 0 else 0x34C759
    icon    = "🚨" if n_alerts > 0 else "✅"
    payload = {
        "username": "BaseLinker Monitor 🔍",
        "embeds": [{"title": f"{icon} Podsumowanie skanu", "color": color, "fields": [
            {"name": "📦 Aukcji z konk.", "value": str(total),    "inline": True},
            {"name": "🚨 Przebite ceny",  "value": str(n_alerts), "inline": True},
            {"name": "⏰ Następny skan",   "value": f"za {cfg['check_interval_minutes']} min", "inline": True},
        ], "footer": {"text": datetime.now().strftime("%d.%m.%Y %H:%M")}}],
    }
    try: requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
    except Exception as e: log.error(f"Discord summary: {e}")

# ══════════════════════════════════════════════════════════════════
#  SKAN
# ══════════════════════════════════════════════════════════════════
_scan_status = {
    "running": False, "last_scan": None,
    "last_total": 0, "last_alerts": 0,
    "last_owell": 0, "next_scan": None,
}

def run_scan():
    cfg              = load_config()
    threshold        = cfg.get("price_diff_threshold", PRICE_DIFF_THRESHOLD)
    include_delivery = cfg.get("include_delivery", False)

    log.info("=" * 60)
    log.info("▶  Skan start")
    log.info("=" * 60)

    owell_ids = fetch_owell_ids()

    try:
        rows = fetch_export()
    except Exception as e:
        log.error(f"  Błąd eksportu: {e}")
        _scan_status.update({"running": False, "last_scan": datetime.now().isoformat()})
        return

    log.info(f"  Wierszy z danymi konkurencji: {len(rows)}")

    # Dla każdego SKU (products_id) wybierz aukcję z najniższą naszą ceną.
    # Alerty będą wysyłane tylko dla tych "zwycięskich" aukcji — duplikaty z
    # wyższą ceną są ignorowane, bo i tak mamy tańszą ofertę tego produktu.
    best_per_sku: dict[str, tuple[str, float]] = {}  # sku -> (auction_id, price)
    for row in rows:
        sku = row["products_id"]
        if not sku:
            continue
        aid, price = row["auction_id"], row["price"]
        if sku not in best_per_sku or price < best_per_sku[sku][1]:
            best_per_sku[sku] = (aid, price)
    winning_auctions = {aid for aid, _ in best_per_sku.values()}

    skipped_sku = sum(
        1 for row in rows
        if row["products_id"] and row["auction_id"] not in winning_auctions
    )
    if skipped_sku:
        log.info(f"  Pominięto duplikatów SKU (wyższa cena): {skipped_sku}")

    cache      = load_cache()
    all_alerts = []

    for row in rows:
        if not _running: break

        auction_id  = row["auction_id"]
        our_price   = row["price"]
        comp_price  = row["competition_price"]
        comp_del    = row["competition_price_delivery"] if include_delivery else 0.0
        comp_total  = comp_price + comp_del
        seller      = row["competition_seller_name"]

        if our_price <= 0 or comp_total <= 0:
            continue

        sku        = row["products_id"]
        is_winning = (not sku) or (auction_id in winning_auctions)
        key        = f"auction:{auction_id}"
        prev       = cache.get(key, {}).get("comp_total")
        is_owell   = (not owell_ids) or (auction_id in owell_ids)

        if our_price - comp_total >= threshold:
            if prev != comp_total and is_owell and is_winning:
                diff = our_price - comp_total
                log.warning(f"  🚨 {auction_id} | My:{our_price:.2f} Konk:{comp_total:.2f} ({seller}) -{diff:.2f}zł")
                alert = {
                    "auction_id":    auction_id,
                    "products_id":   row["products_id"],
                    "our_price":     our_price,
                    "comp_total":    comp_total,
                    "comp_auction_id": row["competition_auction_id"],
                    "seller":        seller,
                    "competitor":    seller_to_competitor(seller) or seller,
                }
                all_alerts.append(alert)
                append_alert(alert)
            elif not is_winning:
                log.debug(f"  ⏭ {auction_id} pominięty — tańsza oferta SKU '{sku}' istnieje")

        cache[key] = {
            "our_price":       our_price,
            "comp_total":      comp_total,
            "comp_price":      comp_price,
            "comp_delivery":   comp_del,
            "seller":          seller,
            "competitor":      seller_to_competitor(seller),
            "products_id":     row["products_id"],
            "comp_auction_id": row["competition_auction_id"],
            "is_owell":        auction_id in owell_ids if owell_ids else True,
            "is_winning_sku":  is_winning,
            "checked_at":      datetime.now().isoformat(),
        }

    save_cache(cache)
    _scan_status.update({
        "running": False, "last_scan": datetime.now().isoformat(),
        "last_total": len(rows), "last_alerts": len(all_alerts),
        "last_owell": len(owell_ids),
    })
    log.info(f"📊 Sprawdzono: {len(rows)} | Alerty: {len(all_alerts)}")
    if all_alerts:
        send_discord_alert(all_alerts, cfg)
    send_discord_summary(len(rows), len(all_alerts), cfg)
    log.info("▶  Skan zakończony\n")

# ══════════════════════════════════════════════════════════════════
#  FLASK API
# ══════════════════════════════════════════════════════════════════
app = Flask(__name__, static_folder=str(BASE_DIR / "web_static"))

@app.route("/")
def index():
    return send_from_directory(BASE_DIR / "web_static", "index.html")

@app.route("/api/config", methods=["GET"])
def api_get_config():
    return jsonify(load_config())

@app.route("/api/config", methods=["POST"])
def api_save_config():
    data = request.json
    cfg  = load_config()
    for k in ["check_interval_minutes","price_diff_threshold","discord_enabled","include_delivery"]:
        if k in data: cfg[k] = data[k]
    save_config(cfg)
    return jsonify({"ok": True})

@app.route("/api/status")
def api_status():
    return jsonify(_scan_status)

@app.route("/api/alerts")
def api_alerts():
    limit = int(request.args.get("limit", 200))
    return jsonify({"alerts": load_alerts()[:limit]})

@app.route("/api/scan/trigger", methods=["POST"])
def api_trigger():
    if _scan_status["running"]:
        return jsonify({"ok": False, "msg": "Skan już trwa"}), 409
    _scan_status["running"] = True
    threading.Thread(target=run_scan, daemon=True).start()
    return jsonify({"ok": True})

@app.route("/api/log")
def api_log():
    try:
        lines = int(request.args.get("lines", 150))
        if LOG_FILE.exists():
            with open(LOG_FILE, encoding="utf-8") as f:
                return jsonify({"lines": f.readlines()[-lines:]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify({"lines": []})

@app.route("/api/prices")
def api_prices():
    """Wszystkie ostatnie ceny z cache."""
    cache = load_cache()
    rows  = []
    for k, v in cache.items():
        if not k.startswith("auction:"): continue
        rows.append({"auction_id": k.replace("auction:", ""), **v})
    rows.sort(key=lambda x: x.get("checked_at", ""), reverse=True)
    return jsonify({"rows": rows})

@app.route("/api/competitor/<name>")
def api_competitor(name: str):
    """
    Dane dla zakładki konkretnego konkurenta.
    Zwraca aukcje gdzie competition_seller_name pasuje do tego konkurenta.
    Dla zakładki 'Owell' — filtruje dodatkowo po owell_ids z cache.
    """
    cache = load_cache()
    rows  = []

    # Pobierz aliasy dla tego konkurenta
    aliases = [a.lower() for a in COMPETITORS.get(name, [name.lower()])]

    for k, v in cache.items():
        if not k.startswith("auction:"): continue
        auction_id = k.replace("auction:", "")

        seller = (v.get("seller") or "").strip().lower()

        if name == "Owell":
            # Zakładka Owell = Twoje aukcje gdzie konkurencja je przebija
            if not v.get("is_owell"): continue
            diff = v.get("our_price", 0) - v.get("comp_total", 0)
            if diff < 0.01: continue  # pokazuj tylko przebite
            rows.append({
                "auction_id":      auction_id,
                "comp_auction_id": v.get("comp_auction_id", ""),
                "comp_price":      v.get("comp_total", 0),
                "our_price":       v.get("our_price", 0),
                "diff":            round(diff, 2),
                "seller":          v.get("seller", ""),
            })
        else:
            # Zakładki konkurentów = aukcje gdzie dany konkurent jest najtańszy
            if seller not in aliases: continue
            diff = v.get("our_price", 0) - v.get("comp_total", 0)
            rows.append({
                "auction_id":      auction_id,
                "comp_auction_id": v.get("comp_auction_id", ""),
                "comp_price":      v.get("comp_total", 0),
                "our_price":       v.get("our_price", 0),
                "diff":            round(diff, 2),
                "seller":          v.get("seller", ""),
            })

    rows.sort(key=lambda x: x["diff"], reverse=True)
    cheaper  = sum(1 for r in rows if r["diff"] > 0)
    pricier  = sum(1 for r in rows if r["diff"] < 0)
    avg_diff = round(sum(r["diff"] for r in rows) / len(rows), 2) if rows else 0

    return jsonify({
        "rows": rows,
        "total": len(rows),
        "cheaper": cheaper,
        "pricier": pricier,
        "avg_diff": avg_diff,
    })

# ══════════════════════════════════════════════════════════════════
#  GŁÓWNA PĘTLA
# ══════════════════════════════════════════════════════════════════
_running = True

def _stop(sig, frame):
    global _running
    log.info("⛔ Zatrzymuję..."); _running = False

signal.signal(signal.SIGINT,  _stop)
signal.signal(signal.SIGTERM, _stop)

def monitor_loop():
    while _running:
        cfg      = load_config()
        interval = cfg.get("check_interval_minutes", CHECK_INTERVAL_MIN) * 60
        _scan_status["running"] = True
        next_dt  = datetime.fromtimestamp(time.time() + interval)
        try:
            run_scan()
        except Exception as e:
            log.exception(f"Błąd skanu: {e}")
            _scan_status["running"] = False
        _scan_status["next_scan"] = next_dt.isoformat()
        log.info(f"💤 Następny skan: {next_dt.strftime('%H:%M:%S')}")
        for _ in range(interval):
            if not _running: break
            time.sleep(1)

def main():
    if not EXPORT_URL:
        print("❌ Ustaw EXPORT_URL w pliku .env"); sys.exit(1)
    if DISCORD_WEBHOOK_URL == "TWÓJ_WEBHOOK_URL_DISCORD":
        print("❌ Ustaw DISCORD_WEBHOOK_URL w pliku .env"); sys.exit(1)

    (BASE_DIR / "web_static").mkdir(exist_ok=True)
    log.info("🚀 BaseLinker Monitor uruchomiony")
    log.info(f"   Panel: http://localhost:{WEB_PORT}")

    threading.Thread(target=monitor_loop, daemon=True).start()

    import logging as pylog
    pylog.getLogger("werkzeug").setLevel(pylog.WARNING)
    app.run(host="0.0.0.0", port=WEB_PORT, debug=False, use_reloader=False)

if __name__ == "__main__":
    main()
