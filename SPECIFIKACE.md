# Sreality Crawler — Master Prompt (v1.0)

## Cíl

Vybudovat lokální systém pro **kompletní archivaci inzerátů ze sreality.cz** s plnou historií změn, jednoduchým webovým UI pro prohlížení (filtrování/řazení) a nasazením pouze přes **Docker Compose**.

---

## 1) Architektura & běh

* **Kontejnery (3):**

  * `db`: PostgreSQL (image `postgres:16-alpine`), **TZ=Europe/Prague**, perzistentní data (named volume).
  * `crawler`: Scrapy + plánovač (APScheduler) + malý interní HTTP (pro `/run-now`, `/progress`).
  * `flask`: Flask + Jinja2 UI (read-only k DB), publikuje se jen na `127.0.0.1`.
* **Spuštění:** celé se spouští `docker compose up`.
* **Síť:** všechny služby na **jedné interní síti**; ven se publikuje **pouze Flask** (na localhost).
* **Restart politika:** `always` pro všechny služby.
* **Paměť:** crawler `mem_limit: 2g` (implementátor může upravit po měření).
* **Časová zóna:** **všechny** kontejnery `TZ=Europe/Prague`.
* **.env v rootu:**

  * `POSTGRES_DB=reality_history`
  * `POSTGRES_USER=sreality`
  * `POSTGRES_PASSWORD=sreality`
  * `TZ=Europe/Prague`
* **Porty:** žádný konflikt s veřejnými službami; `db` se **nepublikuje ven**, `crawler` se **nepublikuje ven**, `flask` jen na `127.0.0.1:8000`.

---

## 2) Crawler — plán, šetrnost, spouštění

* **Plán:** automaticky **každý den 20:00 (Europe/Prague)** přes APScheduler (cron trigger).
* **Manuální spuštění:** interní endpoint `POST http://crawler:7070/run-now` (bez tokenu, dostupný jen v Compose síti).

  * Kontrola **„už neběží?"** musí proběhnout **dřív než cokoliv jiného** (ještě před I/O či DB). Pokud běží → okamžitě skončit (HTTP 409/„already running").
* **Respekt robots.txt** (včetně případného `Crawl-delay` → má **přednost** před vlastním delayem).
* **Zdroje URL:**

  1. **Hlavní stránka** → odvodit všechny kombinace **sekce × typ obchodu** (domy/byty/pozemky/komerční/ostatní × prodej/pronájem/dražba). **„Projekty" vyloučit** (pravidlo odvoď z DOM).
  2. **Sitemap** (`sitemap.xml` a indexy).
  3. **Union** (výpisy mají prioritu, sitemapa doplní; duplicity vyřaď).
* **Výpisy:** pro každou kombinaci projdi **paginaci až do konce**.
* **Šetrnost & retry:**

  * **DOWNLOAD_TIMEOUT=30s**.
  * **Nízký paralelismus** (implementátor určí po testu, masivní paralelismus bude až ve zpracování).
  * **Dynamický delay**: default ~**0.1 s**, geometricky navyšuj podle kumulativní chybovosti (stejná logika platí pro timeouty, 408/429/5xx, resety, DNS, CAPTCHA).
  * **RETRY_TIMES=100** (všechny „chyby stahování/DB" se řídí jednotnou retry logikou).
  * **CAPTCHA/ban** = běžná chyba stahování → do retry/backoff.
* **Podmíněné požadavky:** pokud Sreality podporuje `ETag`/`Last-Modified`, používej `If-None-Match`/`If-Modified-Since` a při **304** neparsuj (jen aktualizuj `last_seen_at`). Implementátor ověří.

---

## 3) Ukládání HTML a obrázků

* **HTML detail:**

  * Ukládej **jen poslední verzi** raw HTML **na disk** v části Scrapy (perzistentní **named volume**).
  * **Adresářová hierarchie** souborů **kopíruje DB hierarchii typů** (např. `/html/byty_prodej/123456.html`, `/html/domy_pronajem/...`).
  * Po stažení **porovnej** stažené HTML s uloženým **v paměti** (binární srovnání dvou souborů); pokud stejné → přeskoč parsování.
* **Mapování URL→soubor:** ukládej **pár** `{url, filename}` v **on-disk KV** (LMDB/SQLite), ať neroste RAM.
* **Obrázky:** **stáhnout všechny v původním rozlišení** a **uložit do DB** (BYTEA nebo Large Object — volba na implementátorovi).

  * Pokud se některá fotka ani po retry nestáhne → **ulož zbytek inzerátu** a **zaloguj** selhanou URL (varianta A).

---

## 4) Datový model & historie

* **Unikátní klíč:** `listing_id` ze Sreality (implementátor určí typ podle reálných hodnot).
* **Hierarchie tabulek (dědičnost podle typů):**

  * `listings` (společné všem) → *pět hlavních typů* (byty/domy/pozemky/komerční/ostatní) × (prodej/pronájem/dražba) → z toho **podtypy** (např. u domů: chata/chalupa/vila…).
  * Každá „potomkovská" tabulka má **vazbu** na nadřazenou a **jen svoje specifické sloupce**.
* **Indexy:** **nad každým sloupcem** (implementátor zvolí vhodný typ – BTREE/GIN/GIST podle dat).
* **Normalizace hodnot při parsování:**

  * **Cena:** integer v CZK (bez mezer).
  * **Plochy:** v **m²** (float).
  * **Cena/m²:** **vypočítat a uložit**.
  * **Texty:** odstranit HTML, zkolabovat whitespace, trim, case-insensitive porovnání, Unicode NFKC.
* **Lokalita:** implementátor zvolí reprezentaci podle dostupných dat z inzerátů (bez externí geokódace).
* **Historie změn (diff model):**

  * 1. verze = **plný stav**.
  * Další změny = **diffy po atributech** (šetří místo).
  * **Checkpoint** (plný snapshot) **po každých 100 změnách** daného inzerátu (časový limit žádný — když nejsou změny, nevadí dlouhá mezera).
  * Musí být možné **rekonstruovat libovolný stav** v čase i číst **aktuální stav**.
* **Neaktivní inzeráty:** pokud v aktuálním běhu URL/ID **nepřijdou**, označ `is_active=false` (nesmazávat).

---

## 5) Ukládání „posledního HTML" v DB

* V DB drž **odkaz**/metadata na soubor (cestu), **ne samotný obsah**.
* (Přímo v DB se HTML **neukládá**, jen na disku – viz výše.)

---

## 6) Flask (UI & API)

* **Lokalita:** jen **lokální přístup** (bez autentizace), publikace na `127.0.0.1:8000`.
* **Server:** stačí vestavěný `flask run` (ne Gunicorn).
* **UI (Jinja2):**

  * **Výpis**: filtrování a řazení **dle každé vlastnosti**, stránkování **100** (volby: 20/50/100/200/500), výchozí řazení **abecední**.
  * **Povinné sloupce ve výpisu:** **název, cena, typ, obec**.
  * **Detail inzerátu:** zobrazí **všechny parametry** + **historii změn**.
  * **Řazení chování:** jako v Excelu (deterministické, vícestupňové podle typů hodnot).
* **Read-only:** web **nic neupravuje**, změny dělá výhradně crawler.
* **Progress bar živého běhu:**

  * Flask periodicky (každých **10 s**) dotazuje `GET http://crawler:7070/progress`.
  * Endpoint vrací `{"percent": 0–100}`.
  * **Procenta zahrnují i parsování/uložení**, ne jen stažení.

---

## 7) Logování & healthchecky

* **Logging:** Python `logging` do **konzole** i **souboru**.

  * **Barevné úrovně** (ne bílé).
  * Název log souboru = **čas startu běhu**.
  * Logy perzistentní (named volume). Rotaci může implementátor zvolit dle potřeby.
* **Healthchecky (Compose):**

  * `db`: `pg_isready -U $POSTGRES_USER -d $POSTGRES_DB` **každých 10 s**, timeout 5 s, retries 6.
  * `crawler`: `GET http://localhost:7070/healthz` **každých 15 s**, timeout 5 s, retries 6.
  * `flask`: `GET http://localhost:8000/healthz` **každých 15 s**, timeout 5 s, retries 6.
  * `depends_on`: crawler i flask čekají na **healthy `db`**.

---

## 8) Chyby, ukončování, limity

* **Chyby stahování/DB:** jednotná retry/backoff/jitter logika, max **100 pokusů**; dynamické zpomalování.
* **Nekritické chyby detailu** (např. 404 výpisové stránky) → **přeskočit a pokračovat**.
* **Kritické chyby kódu** (např. chybějící knihovna) → **logovaný pád**.
* **Ukončení kontejneru:** crawler **okamžitě končí** (nečeká na „graceful").
* **Denní limit stažení:** **bez limitu** (šetrnost řeší režie výše).
* **Max velikost HTML:** implementátor stanoví z praxe (stránky jsou rozsáhlé).

---

## 9) Co implementátor určí sám (záměrně necháno otevřené)

* Konkrétní **paralelismus** a **parametry backoffu/jitteru**.
* Způsob odlišení **„projekty"** při parsování hlavní stránky.
* **Datové typy** (např. `listing_id`), přesné **indexy** a jejich typy.
* **Model uložení obrázků** (BYTEA vs LO), tabulky a referenční integrita.
* **Struktura šablon** (URL cesty, názvy view), **SQL dotazy** pro filtry/řazení.
* **Umístění logů** a volitelná rotace.
* **Exact** `requirements.txt` pro crawler/flask, build strategie (`--no-cache-dir` dle potřeby).
* **Adresáře HTML/logs volumes** (názvy volume; musí být **perzistentní**).
* případně **optimalizace** (on-disk KV pro URL→soubor, caching, ETag ap.).

---

## 10) Akceptační kritéria (rychlý checklist)

* [ ] `docker compose up` spustí `db`, `crawler`, `flask` bez ručního zásahu.
* [ ] `db` běží, je **nepublikovaná** ven; `flask` na `127.0.0.1:8000`; `crawler` bez publikace.
* [ ] V 20:00 proběhne plánovaný běh; `POST /run-now` z Flasku spustí manuálně (pokud neběží).
* [ ] Crawler získá **všechny kombinace sekce×obchod**, vyřadí **projekty**, projde **paginaci** a sjednotí se **sitemapou** (union).
* [ ] HTML detail každého inzerátu uložen jako **poslední verze** v perzistentním volume; **porovnání** před parsováním snižuje práci.
* [ ] **Všechny fotky** uloženy do DB v originálním rozlišení (při selhání některé fotky se inzerát uloží i tak).
* [ ] DB model s **hierarchií tabulek**, **index nad každým sloupcem**, diff historie + checkpointy (100 změn).
* [ ] UI: výpis s filtrováním/řazením každé vlastnosti; výchozí řazení abecední; stránkování 100 (volby 20/50/100/200/500); povinné sloupce **název, cena, typ, obec**; detail zobrazuje **historii změn**.
* [ ] `/progress` ukazuje **% včetně parsování/uložení**, aktualizace ve Flasku **každých 10 s**.
* [ ] Barevné logy → konzole + soubor (timestamp v názvu); healthchecky v Compose; restart politika `always`.

---
