# BaseLinker Monitor Cen – Instrukcja konfiguracji

## Co robi ten skrypt?

Co X minut pobiera Twoje aukcje z BaseLinker, porównuje ceny z najtańszymi ofertami
konkurencji i wysyła alert na Discord gdy ktoś przebije Twoją cenę.

---

## 1. Wymagania

- Python 3.10+ (sprawdź: `python3 --version`)
- Konto BaseLinker z aktywnym modułem „Sprawdzanie cen konkurencji"
- Kanał na Discord z uprawnieniami do tworzenia webhooków

---

## 2. Instalacja

```bash
# Sklonuj / pobierz pliki do folderu
cd /opt/bl_monitor   # lub dowolna inna lokalizacja

# Zainstaluj zależności
pip3 install -r requirements.txt
```

---

## 3. Konfiguracja tokenów

### Token BaseLinker API
1. Zaloguj się do BaseLinker
2. Idź do: **Moje konto → API**
3. Wpisz nazwę aplikacji (np. „Monitor cen") i kliknij **Generuj token**
4. Skopiuj token

### Webhook Discord
1. Otwórz Discord → wejdź na wybrany kanał
2. **Ustawienia kanału → Integracje → Webhooki → Nowy webhook**
3. Nadaj nazwę i skopiuj **URL webhooka**

### Plik .env
```bash
cp .env.example .env
nano .env   # lub otwórz w edytorze
```

Uzupełnij:
```
BL_API_TOKEN=1-12345-ABCDEFGHIJ...
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/123.../abc...
```

---

## 4. Konfiguracja skryptu

Otwórz `price_monitor.py` i znajdź sekcję `MARKETPLACE_ACCOUNTS`:

```python
MARKETPLACE_ACCOUNTS = [
    {
        "account_id": "123456",   # ← Twoje ID konta w BaseLinker
        "name": "Allegro",        # ← Nazwa (do alertów)
        "platform": "allegro",
    },
]
```

**Jak znaleźć account_id?**
W panelu BaseLinker wejdź w:
**Integracje → [nazwa platformy]** – ID widoczne w URL lub w ustawieniach konta.

Możesz monitorować wiele platform jednocześnie – dodaj kolejne słowniki do listy.

### Próg alertu
```python
PRICE_DIFF_THRESHOLD = 0.01  # alert gdy konkurencja tańsza choćby o 1 grosz
# Zmień np. na 1.00 żeby ignorować różnice poniżej 1 zł
```

---

## 5. Test ręczny

```bash
# Załaduj zmienne środowiskowe i uruchom
export $(cat .env | xargs)
python3 price_monitor.py
```

Powinieneś zobaczyć logi w konsoli i wiadomość podsumowującą na Discordzie.

---

## 6. Cron – automatyczne uruchamianie

Edytuj crontab:
```bash
crontab -e
```

Przykłady harmonogramu:
```bash
# Co 30 minut:
*/30 * * * * cd /opt/bl_monitor && export $(cat .env | xargs) && python3 price_monitor.py >> /var/log/bl_monitor.log 2>&1

# Co godzinę:
0 * * * * cd /opt/bl_monitor && export $(cat .env | xargs) && python3 price_monitor.py >> /var/log/bl_monitor.log 2>&1

# Raz dziennie o 8:00 rano:
0 8 * * * cd /opt/bl_monitor && export $(cat .env | xargs) && python3 price_monitor.py >> /var/log/bl_monitor.log 2>&1
```

Sprawdź logi:
```bash
tail -f /var/log/bl_monitor.log
```

---

## 7. Jak działają powiadomienia Discord

Skrypt wysyła dwa typy wiadomości:

**Alert o przebitej cenie** (czerwony embed):
- Twoja cena vs cena konkurencji
- Różnica w złotówkach
- Nazwa produktu, SKU, ID, platforma

**Podsumowanie skanu** (zielony = OK, czerwony = znaleziono alerty):
- Ile produktów sprawdzono
- Ile alertów wygenerowano

### Mechanizm cache
Skrypt zapamiętuje ostatnią cenę konkurencji w pliku `price_cache.json`.
Dzięki temu nie będziesz dostawać alertu za każdym razem gdy skrypt się uruchomi –
tylko gdy cena konkurencji **zmieni się**.

---

## 8. Rozwiązywanie problemów

| Problem | Rozwiązanie |
|---------|-------------|
| `ERROR: invalid token` | Sprawdź BL_API_TOKEN w pliku .env |
| Brak alertów Discord | Sprawdź DISCORD_WEBHOOK_URL; przetestuj webhook w Discord |
| `competition_prices` puste | Upewnij się, że masz aktywny moduł „Sprawdzanie cen konkurencji" w BaseLinker dla danych aukcji |
| Zbyt wiele żądań API | Zwiększ `API_REQUEST_DELAY` np. do 1.5 sekundy |
| Skrypt nie działa z crona | Użyj pełnych ścieżek: `/usr/bin/python3`, `/opt/bl_monitor/price_monitor.py` |

---

## 9. Uwaga o dostępności danych konkurencji przez API

BaseLinker umożliwia sprawdzanie cen konkurencji przez panel (zakładka „Konkurencja"
przy aukcji). Dane te mogą nie być w pełni dostępne przez publiczne REST API –
zależy to od Twojego planu i ustawień.

**Jeśli `competition_prices` jest zawsze puste:**
Skontaktuj się z supportem BaseLinker i zapytaj, przez które endpointy API
dostępne są dane z modułu „Sprawdzanie cen konkurencji" dla Twojego planu.
Alternatywnie rozważ pobieranie danych przez eksport CSV z panelu.

---

## Struktura plików

```
bl_monitor/
├── price_monitor.py     ← główny skrypt
├── requirements.txt     ← zależności Python
├── .env.example         ← szablon konfiguracji
├── .env                 ← Twoja konfiguracja (NIE wgrywaj do Git!)
├── price_cache.json     ← cache (tworzony automatycznie)
└── README.md            ← ta instrukcja
```
