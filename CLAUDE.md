# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# 📄 SrealityScraper – Global Rules & Architecture

> **Note on scope vs. the original task:**  
> The initial assignment ("scrape first 500 items and show them") is now only a **subset**.  
> **Final goal:** scrape **all** listings across **all categories × offer types**, persist **full per-field change history**, and serve a **paginated UI** with analytics.

---

## Scope

These rules apply to the **entire repository**: Scrapy scraper, PostgreSQL schema & migrations, FastAPI web/API, Docker/Compose, CI, and tests.  
Module-local specifics may extend these rules but **must not** contradict them.

---

## Project structure

```
.
├─ compose.yml
├─ .env.example
├─ docs/                        # diagrams, notes (architecture, schema, flows)
├─ scraper/                     # Scrapy project (created via `scrapy startproject`)
│  ├─ scrapy.cfg
│  └─ sreality/
│     ├─ __init__.py
│     ├─ settings.py
│     ├─ pipelines.py
│     ├─ middlewares.py
│     └─ spiders/
│        └─ sreality.py         # param-driven spider (offer/category pagination)
├─ web/                         # FastAPI app
│  ├─ app/
│  │  ├─ __init__.py
│  │  ├─ main.py
│  │  ├─ db.py
│  │  ├─ models.py
│  │  ├─ queries.py
│  │  ├─ templates/
│  │  │  ├─ index.html
│  │  │  └─ listing_detail.html
│  │  └─ static/
│  ├─ Dockerfile.web
├─ db/
│  ├─ alembic.ini
│  ├─ alembic/                  # migrations
│  └─ seeds/
├─ docker/
│  ├─ Dockerfile.scraper
│  └─ wait-for-it.sh
├─ tests/
│  ├─ unit/
│  ├─ integration/
│  ├─ performance/
│  └─ security/
├─ IMPLEMENTATION_STATUS.md     # progress log (keep updated)
└─ CLAUDE.md                    # this file
```

**Outputs**  
- Primary persistence = **PostgreSQL**.  
- Optional exports under `exports/` (CSV/JSON).  
- No ad-hoc outputs elsewhere.

---

## Language & style

- **Python 3.12+** (always in venv).  
- **Black** (line length 120) and **Ruff** (lint).  
- **Type hints everywhere**; docstrings (Sphinx style).  
- Imports explicit (no `*`).  
- Web layer prefers `async`.
- **Code comments** must be in **English**.
- **Comments only for functions and classes** (for documentation generators). No inline comments after every line.

---

## Logging

- Single shared logger (structlog or colorlog).  
- Dev: human-readable; Prod: JSON.  
- Logs in **English** with context (offer, category, page, listing id, run id).

---

## Errors

- Normal flow: exceptions.  
- Fatal only at entrypoints (`sys.exit(1)`).  
- Retries/backoff configured (see Scrapy).
- Never silent failures.

---

## Tests

- Test **every function**, error paths included.  
- Timeouts: Unit ≤ 30 s; Integration ≤ 5 min; end-to-end with reduced data set.  
- Test logs under `tests/logs/`.  
- CI blocks merges on failing tests.
- Integration tests must cover: insert/update with per-field diffing, pagination API, price-history endpoints.

---

## Git workflow

- Claude-only branches: `claude/<type>/<action>` (e.g., `claude/feature/scraper`).  
  - On these branches Claude may commit/push freely.  
- Claude must **never auto-merge**.  
- One PR = one feature.
- Commits: short, precise.
- Multi-line commits: prefer `git commit -F <file>` (see patterns in your other project).

### Multi-line Commit Messages

For detailed commit messages, use one of these approaches:

1. **File-based (recommended)**: Create temporary file and use `git commit -F filename`
2. **Multiple -m flags**: `git commit -m "Title" -m "Line 1" -m "Line 2"`  
3. **...' syntax**: `git commit -m Title\n\nDescription\nMore details'`
4. **Printf with variable**: `MSG="$(printf "line1\nline2")" && git commit -m "$MSG"`

File-based approach avoids shell escaping issues and supports full formatting.

---

## Secrets

- Credentials via env (templates in repo as `.env.example`).  
- Do **not** commit `.env`.  
- Separate test-only values.

---

## Implementation status

Maintain **IMPLEMENTATION_STATUS.md**: implemented, pending, known limitations. Update with every meaningful change.

---

## References

- **Scrapy** (AutoThrottle, HTTP cache RFC policy, JOBDIR).  
- **FastAPI**, **Uvicorn**.  
- **PostgreSQL**: JSONB, generated columns, triggers, **Alembic**.  
- **Prometheus** client (metrics).  
- **Chart.js** (charts).  
- **CNB** exchange rates (CZK conversion).

---

# 🏗️ System Architecture & Pipeline

```
[ Scrapy spider ]  →  [ pipelines ] →  [ PostgreSQL ]
│                                ├─ listings (core, 3NF)
│                                ├─ listing_attributes (JSONB + GENERATED cols)
│                                ├─ listing_images
│                                ├─ price_history
│                                ├─ listing_change_log (per-field; JSONB + TEXT)
│                                ├─ sellers / locations
│                                └─ fx_rates (CNB rates)
└→ (manual runs as needed)
[ FastAPI web ] → HTML (paginated list + detail) & JSON API (list/detail/history/changes)
```

---

## 🔎 Scraping policy (Sreality.cz)

- **robots.txt:** **not obeyed** (owner's decision). Still be **polite** (AutoThrottle, conditional requests, retries/backoff, kill switch).  
- **User-Agent (fixed):** `SrealityScraper/1.0 (+contact@example.com)` — replace with real contact later.  
- **Offer slugs:** `prodej`, `pronajem`, `drazby`, `podily`.  
- **Category slugs:** `byty`, `domy`, `pozemky`, `komercni`, `ostatni`.  
- **Coverage:** all `/hledani/<offer>/<category>` pairs; **exclude** developer "projekty".  
- **Conditional requests:** Enable RFC 2616 HTTP cache (ETag/Last-Modified).  
- **Kill switch:** `SCRAPING_ENABLED=false` stops at spider start.

---

# 🗃️ Data model (PostgreSQL)

> **Hybrid 3NF:** core normalized tables + **JSONB** for variable attributes (with validation & generated columns).  
> Keep **per-field change log** with both **typed JSONB** and **verbatim TEXT** values.

### Enums

```sql
CREATE TYPE offer_type    AS ENUM ('prodej','pronajem','drazby','podily');
CREATE TYPE category_type AS ENUM ('byty','domy','pozemky','komercni','ostatni');
```

### Core tables (excerpt)

```sql
CREATE TABLE sources (
  id   SERIAL PRIMARY KEY,
  code TEXT UNIQUE NOT NULL  -- 'sreality'
);

CREATE TABLE listings (
  id               BIGSERIAL PRIMARY KEY,
  source_id        INT NOT NULL REFERENCES sources(id) ON DELETE RESTRICT,
  offer_type       offer_type    NOT NULL,
  category         category_type NOT NULL,
  external_id      TEXT NOT NULL,
  url              TEXT NOT NULL,
  title            TEXT NOT NULL,
  -- price (typed/normalized)
  price_value      NUMERIC(16,2),
  price_currency   TEXT,                        -- ISO 4217 (CZK, EUR, ...)
  price_value_czk  NUMERIC(16,2),               -- CNB converted (see FX section)
  location_text    TEXT,
  main_image_url   TEXT,
  seller_id        BIGINT REFERENCES sellers(id),
  location_id      BIGINT REFERENCES locations(id),
  first_seen_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  last_seen_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  is_active        BOOLEAN NOT NULL DEFAULT TRUE,
  UNIQUE (source_id, external_id)
);

CREATE INDEX idx_listings_offer_cat ON listings(offer_type, category);
CREATE INDEX idx_listings_active    ON listings(is_active);
CREATE INDEX idx_listings_last_seen ON listings(last_seen_at DESC);
CREATE INDEX idx_listings_price     ON listings(price_value);
CREATE INDEX idx_listings_price_czk ON listings(price_value_czk);
```

**Variable attributes (JSONB) + GENERATED**

```sql
CREATE TABLE listing_attributes (
  listing_id BIGINT PRIMARY KEY REFERENCES listings(id) ON DELETE CASCADE,
  attrs      JSONB NOT NULL DEFAULT '{}'::JSONB
);

ALTER TABLE listing_attributes
  ADD COLUMN area_m2      NUMERIC GENERATED ALWAYS AS ((attrs->>'area_m2')::NUMERIC) STORED,
  ADD COLUMN disposition  TEXT    GENERATED ALWAYS AS (attrs->>'disposition') STORED,
  ADD COLUMN energy_class TEXT    GENERATED ALWAYS AS (attrs->>'energy_class') STORED;

CREATE INDEX idx_attrs_gin          ON listing_attributes USING GIN (attrs);
CREATE INDEX idx_attrs_area_m2      ON listing_attributes(area_m2);
CREATE INDEX idx_attrs_disposition  ON listing_attributes(disposition);
CREATE INDEX idx_attrs_energy_class ON listing_attributes(energy_class);
```

**Attribute catalog & validation (governance)**

```sql
CREATE TABLE attribute_catalog (
  key          TEXT PRIMARY KEY,          -- e.g., 'area_m2', 'disposition'
  category     category_type[] NOT NULL,  -- allowed categories
  scalar_type  TEXT NOT NULL,             -- 'numeric'|'text'|'boolean'|'date'
  min_value    NUMERIC,
  max_value    NUMERIC,
  allowed_vals TEXT[]
);
/* Implement check_attrs(listing_id) and enforce via CHECK (check_attrs(id)). */
```

**Price history**

```sql
CREATE TABLE price_history (
  id              BIGSERIAL PRIMARY KEY,
  listing_id      BIGINT NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
  observed_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  price_value     NUMERIC(16,2),
  price_value_czk NUMERIC(16,2),
  price_currency  TEXT
);

CREATE INDEX idx_price_hist_listing_time ON price_history(listing_id, observed_at DESC);
```

**Images**

```sql
CREATE TABLE listing_images (
  id          BIGSERIAL PRIMARY KEY,
  listing_id  BIGINT NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
  image_url   TEXT NOT NULL,
  position    INT  NOT NULL DEFAULT 0
);
CREATE INDEX idx_images_listing_pos ON listing_images(listing_id, position);
```

**Sellers / Locations**

```sql
CREATE TABLE sellers (
  id           BIGSERIAL PRIMARY KEY,
  name         TEXT,
  seller_type  TEXT,      -- 'osoba'|'kancelar'|...
  agency_name  TEXT,
  phone_masked TEXT,
  url          TEXT
);

CREATE TABLE locations (
  id       BIGSERIAL PRIMARY KEY,
  region   TEXT,
  district TEXT,
  city     TEXT,
  zip      TEXT,
  lat      DOUBLE PRECISION,
  lon      DOUBLE PRECISION,
  geohash  TEXT
);
CREATE INDEX idx_locations_geo  ON locations(geohash);
CREATE INDEX idx_locations_city ON locations(city);
```

**Scrape runs & fetch log**

```sql
CREATE TABLE scrape_runs (
  id            BIGSERIAL PRIMARY KEY,
  started_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  finished_at   TIMESTAMPTZ,
  offer_type    offer_type,
  category      category_type,
  pages_fetched INT,
  items_saved   INT,
  errors        INT,
  notes         TEXT
);

CREATE TABLE fetch_log (
  id          BIGSERIAL PRIMARY KEY,
  run_id      BIGINT REFERENCES scrape_runs(id) ON DELETE SET NULL,
  url         TEXT NOT NULL,
  status      INT,
  fetched_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  duration_ms INT,
  error       TEXT
);
```

---

## 🧾 Per-field change log (dual JSONB + TEXT) & triggers

**Change log table**

```sql
CREATE TABLE IF NOT EXISTS listing_change_log (
  id               BIGSERIAL PRIMARY KEY,
  listing_id       BIGINT NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
  field_group      TEXT NOT NULL CHECK (field_group IN ('core','attr')),
  field_name       TEXT NOT NULL,
  -- typed copies
  old_value_json   JSONB,
  new_value_json   JSONB,
  -- verbatim text copies (e.g., "5 790 000 Kč")
  old_value_text   TEXT,
  new_value_text   TEXT,
  changed_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_change_listing_time ON listing_change_log(listing_id, changed_at DESC);
CREATE INDEX IF NOT EXISTS idx_change_field_name   ON listing_change_log(field_name);
```

**Simple view (exact requested shape)**

```sql
CREATE OR REPLACE VIEW listing_change_history_simple AS
SELECT
  lcl.listing_id     AS id,
  lcl.field_name     AS "property",
  lcl.new_value_text AS "new_state",
  lcl.old_value_text AS "old_state",
  lcl.changed_at     AS "changed_at"
FROM listing_change_log lcl;
```

**Core fields trigger (example)**

```sql
CREATE OR REPLACE FUNCTION log_listing_core_changes() RETURNS TRIGGER AS $$
BEGIN
  IF NEW.title IS DISTINCT FROM OLD.title THEN
    INSERT INTO listing_change_log(listing_id, field_group, field_name,
      old_value_json, new_value_json, old_value_text, new_value_text)
    VALUES (OLD.id,'core','title',to_jsonb(OLD.title),to_jsonb(NEW.title),OLD.title,NEW.title);
  END IF;

  IF NEW.price_value IS DISTINCT FROM OLD.price_value THEN
    INSERT INTO listing_change_log(listing_id, field_group, field_name,
      old_value_json, new_value_json, old_value_text, new_value_text)
    VALUES (OLD.id,'core','price_value',
      to_jsonb(OLD.price_value),to_jsonb(NEW.price_value),
      OLD.price_value::text,NEW.price_value::text);
  END IF;

  IF NEW.price_currency IS DISTINCT FROM OLD.price_currency THEN
    INSERT INTO listing_change_log(listing_id, field_group, field_name,
      old_value_json, new_value_json, old_value_text, new_value_text)
    VALUES (OLD.id,'core','price_currency',
      to_jsonb(OLD.price_currency),to_jsonb(NEW.price_currency),
      OLD.price_currency,NEW.price_currency);
  END IF;

  IF NEW.location_text IS DISTINCT FROM OLD.location_text THEN
    INSERT INTO listing_change_log(listing_id, field_group, field_name,
      old_value_json, new_value_json, old_value_text, new_value_text)
    VALUES (OLD.id,'core','location_text',
      to_jsonb(OLD.location_text),to_jsonb(NEW.location_text),
      OLD.location_text,NEW.location_text);
  END IF;

  IF NEW.main_image_url IS DISTINCT FROM OLD.main_image_url THEN
    INSERT INTO listing_change_log(listing_id, field_group, field_name,
      old_value_json, new_value_json, old_value_text, new_value_text)
    VALUES (OLD.id,'core','main_image_url',
      to_jsonb(OLD.main_image_url),to_jsonb(NEW.main_image_url),
      OLD.main_image_url,NEW.main_image_url);
  END IF;

  IF NEW.offer_type IS DISTINCT FROM OLD.offer_type THEN
    INSERT INTO listing_change_log(listing_id, field_group, field_name,
      old_value_json, new_value_json, old_value_text, new_value_text)
    VALUES (OLD.id,'core','offer_type',
      to_jsonb(OLD.offer_type),to_jsonb(NEW.offer_type),
      OLD.offer_type::text,NEW.offer_type::text);
  END IF;

  IF NEW.category IS DISTINCT FROM OLD.category THEN
    INSERT INTO listing_change_log(listing_id, field_group, field_name,
      old_value_json, new_value_json, old_value_text, new_value_text)
    VALUES (OLD.id,'core','category',
      to_jsonb(OLD.category),to_jsonb(NEW.category),
      OLD.category::text,NEW.category::text);
  END IF;

  IF NEW.is_active IS DISTINCT FROM OLD.is_active THEN
    INSERT INTO listing_change_log(listing_id, field_group, field_name,
      old_value_json, new_value_json, old_value_text, new_value_text)
    VALUES (OLD.id,'core','is_active',
      to_jsonb(OLD.is_active),to_jsonb(NEW.is_active),
      OLD.is_active::text,NEW.is_active::text);
  END IF;

  NEW.last_seen_at := NOW();
  RETURN NEW;
END; $$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_log_core_changes ON listings;
CREATE TRIGGER trg_log_core_changes
BEFORE UPDATE ON listings
FOR EACH ROW
EXECUTE FUNCTION log_listing_core_changes();
```

**Attributes JSONB diff trigger**

```sql
CREATE OR REPLACE FUNCTION log_listing_attr_changes() RETURNS TRIGGER AS $$
BEGIN
  INSERT INTO listing_change_log(listing_id, field_group, field_name,
    old_value_json, new_value_json, old_value_text, new_value_text, changed_at)
  SELECT NEW.listing_id,
         'attr',
         COALESCE(n.key, o.key),
         o.value,
         n.value,
         o.value::text,
         n.value::text,
         NOW()
  FROM jsonb_each(OLD.attrs) o
  FULL OUTER JOIN jsonb_each(NEW.attrs) n ON n.key = o.key
  WHERE o.value IS DISTINCT FROM n.value;  -- includes added/removed keys
  RETURN NEW;
END; $$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_log_attr_changes ON listing_attributes;
CREATE TRIGGER trg_log_attr_changes
BEFORE UPDATE ON listing_attributes
FOR EACH ROW
EXECUTE FUNCTION log_listing_attr_changes();
```

---

## 💱 Currency & CNB conversion (to CZK)

* **Store both**:
  * normalized numeric: `price_value` + `price_currency` (ISO 4217; **European currencies accepted**; if missing → `NULL`);
  * forensic text: `attrs.price_text` (verbatim, e.g., `"5 790 000 Kč"`).
* **Convert** to `price_value_czk` using **Czech National Bank** fixing:
  * `fx_rates(valid_date, code, amount, rate, source='CNB')`; refresh as needed.
  * Formula: `CZK = price_value * (rate / amount)`.
  * Do **not** retro-recompute historical values; analytics "as of date" should join the corresponding `fx_rates`.
* **Rounding**: persist `price_value_czk` as **NUMERIC(16,2)**; UI shows **whole CZK** with grouping (`5 790 000 Kč`).
* If currency is missing: keep `price_value_czk = NULL`; statistics may exclude or label as "no currency".

---

# 🌐 Web/API

**Framework:** FastAPI + Jinja2 (+ Chart.js via CDN).
**Pagination:** selectable **10 / 20 / 50 / 100**, default **50** (from `.env`).

### Endpoints

* `GET /` — paginated list (params: `page`, `pagesize {10,20,50,100}`, `sort`, `order`).
* `GET /items` — JSON list (same semantics).
* `GET /listing/{id}` — HTML detail (gallery, **price chart**, **recent changes** table).
* `GET /api/listings/{id}` — JSON detail (core + attrs + images).
* `GET /api/listings/{id}/price-history?bucket=daily|weekly` — JSON time-series (CZK + original if available).
* `GET /api/listings/{id}/changes?limit=100` — JSON last changes.
* `GET /healthz` — DB connectivity health.
* `GET /metrics` — Prometheus text (optional).

**UI notes**

* Detail header: title, `price_value_czk` (rounded on display), original `price_text`, location, offer/category tags.
* Chart.js line chart (primary series CZK; optional second series original currency).
* Changes table: property, new/old text, timestamp; filter by `field_name` and time range.

---

## 🔎 Filtering language (v1 – to follow after MVP rendering)

* Visual builder **+** advanced query string (`AND/OR`, parentheses).
* Operators:
  * Number: `= != > >= < <= BETWEEN IN` (+ approx `≈` with epsilon).
  * Text: `= != CONTAINS ILIKE STARTS_WITH ENDS_WITH REGEX`.
  * Enum/Bool: `= != IN NOT IN`, `IS TRUE/FALSE`.
  * Date/Time: `BEFORE AFTER BETWEEN`, relative windows (`last 7d`).
  * JSONB: `HAS_KEY`, path ops (e.g., `PATH('attrs.area_m2') BETWEEN 50 AND 80`).
  * Geo: `WITHIN_RADIUS(lat,lon,r_km)`, `WITHIN_BBOX(...)`.
* Price focus: filters on `price_value`, `price_value_czk`, `price_per_m2`, deltas & velocity.
* Shareable URLs & named segments.

---

# 🐍 Scrapy configuration (defaults)

> **CLI-first**: use Scrapy CLI to scaffold & run. Settings live in `settings.py` + `.env`.

```python
# scraper/sreality/settings.py (excerpt)
import os

BOT_NAME = "sreality"
SPIDER_MODULES = ["sreality.spiders"]
NEWSPIDER_MODULE = "sreality.spiders"

# Decision: do not obey robots.txt (owner requirement)
ROBOTSTXT_OBEY = False

# Politeness & adaptivity
DOWNLOAD_DELAY = float(os.getenv("DOWNLOAD_DELAY", 3.0))
RANDOMIZE_DOWNLOAD_DELAY = True
CONCURRENT_REQUESTS = int(os.getenv("CONCURRENT_REQUESTS", 8))
CONCURRENT_REQUESTS_PER_DOMAIN = int(os.getenv("CONCURRENT_REQUESTS_PER_DOMAIN", 2))

AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = float(os.getenv("AUTOTHROTTLE_START_DELAY", 3.0))
AUTOTHROTTLE_TARGET_CONCURRENCY = float(os.getenv("AUTOTHROTTLE_TARGET_CONCURRENCY", 0.5))
AUTOTHROTTLE_MAX_DELAY = float(os.getenv("AUTOTHROTTLE_MAX_DELAY", 60.0))

RETRY_TIMES = int(os.getenv("RETRY_TIMES", 3))  # 429 is in default RETRY_HTTP_CODES

# RFC-compliant conditional caching (ETag / Last-Modified)
HTTPCACHE_ENABLED = True
HTTPCACHE_POLICY = 'scrapy.extensions.httpcache.RFC2616Policy'
HTTPCACHE_STORAGE = 'scrapy.extensions.httpcache.FilesystemCacheStorage'
HTTPCACHE_DIR = os.getenv('HTTPCACHE_DIR', 'httpcache')

# Resume state (dupefilter, queues)
JOBDIR = os.getenv('JOBDIR', 'state/sreality')

USER_AGENT = os.getenv("USER_AGENT", "SrealityScraper/1.0 (+contact@example.com)")

ITEM_PIPELINES = {
    "sreality.pipelines.PostgresPipeline": 300,
}
```

---

## ⚙️ Configuration (.env example)

```dotenv
POSTGRES_HOST=db
POSTGRES_PORT=5432
POSTGRES_DB=sreality
POSTGRES_USER=sreality
POSTGRES_PASSWORD=secret

SCRAPING_ENABLED=true
DOWNLOAD_DELAY=1.8
CONCURRENT_REQUESTS=4
USER_AGENT=SrealityScraper/1.0 (+contact@example.com)

WEB_PORT=8080
PAGE_SIZE_DEFAULT=50

# FX rates (CNB)
FX_PROVIDER=cnb
FX_FAIL_STRATEGY=use_last   # or: null_out
```

---

# 🐳 Docker & Compose (excerpt)

```yaml
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_DB: ${POSTGRES_DB}
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $POSTGRES_USER -d $POSTGRES_DB"]
      interval: 5s
      timeout: 5s
      retries: 10
    volumes:
      - db_data:/var/lib/postgresql/data

  scraper:
    build:
      context: ./scraper
      dockerfile: ../docker/Dockerfile.scraper
    env_file: .env
    depends_on:
      db:
        condition: service_healthy
    command: ["scrapy", "crawl", "sreality"]
    restart: "no"

  web:
    build:
      context: ./web
      dockerfile: Dockerfile.web
    env_file: .env
    ports:
      - "${WEB_PORT}:8080"
    depends_on:
      db:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/healthz"]
      interval: 10s
      timeout: 5s
      retries: 10

volumes:
  db_data:
```

---

# 📈 Detail page (UI + API)

* `GET /listing/{id}` — HTML detail with gallery, **price chart** (CZK + original) and **recent changes** table.
* `GET /api/listings/{id}` — JSON detail (core + attrs + images).
* `GET /api/listings/{id}/price-history?bucket=daily|weekly` — JSON series.
* `GET /api/listings/{id}/changes?limit=100` — JSON last changes.

---

# 🧪 Observability & quality

* **Metrics** (Prometheus): fetch latency, error counts, HTTP status buckets, items saved per run, 429 counts, bandwidth if available.
* **Logs**: structured, include run id, offer/category, page, listing id.
* **Tracing**: optional (OpenTelemetry).

---

# 🔐 Security & legal

* **robots.txt not obeyed** (owner choice). Mitigate impact: AutoThrottle, conditional requests, exponential backoff with jitter, kill switch.
* DB not exposed outside Compose network.
* Secrets via env; `.env` untracked.
* Optional UI disclaimer: source attribution, scrape timestamp, contact.

---

# ✅ Acceptance criteria (MVP)

* `docker compose up --build` runs cleanly.
* `/healthz` returns **200**.
* `/` shows **paginated list** with selectable page size **10/20/50/100** (default from `.env`).
* Clicking a row opens `/listing/{id}` with gallery, **price chart**, and **recent changes**.
* `GET /items` JSON respects whitelist and returns `page`, `pagesize`, `items`.
* DB enforces `UNIQUE (source_id, external_id)` and records **per-field change log** on updates.
* Scraper runs manually as needed; AutoThrottle + RFC HTTP cache enabled.

---

# 🛠️ Makefile (suggested)

```
make up         # build + up
make down       # stop + rm
make logs       # tail all services
make psql       # psql shell into DB
make scrape     # manual spider run (local)
make migrate    # alembic upgrade head
```

---

# 🧭 CLI-first discipline for Claude

Claude **must** prefer official CLIs/scaffolds and the approved **Bash(...)** patterns (already implemented by the owner):

* **Scrapy**: `scrapy startproject`, `scrapy genspider`, `scrapy crawl ...`
* **DB**: **Alembic** for migrations (`revision --autogenerate`, `upgrade head`)
* **Web**: **uvicorn** (`uvicorn app.main:app --host 0.0.0.0 --port 8080`) / **flask** (if used)
* **Docker**: `docker compose up/down/build/logs` with healthchecks
* **Tests**: `pytest` ; lint via `ruff` ; format via `black` ; types via `mypy`

Manual file edits are allowed **only** when no equivalent CLI/scaffold exists; include a short rationale in the PR, add tests, and update **IMPLEMENTATION_STATUS.md**.