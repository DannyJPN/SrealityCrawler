# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**SrealityCrawler** is a comprehensive real estate archiving system for sreality.cz that:
- Scrapes all real estate listings across all categories and offer types
- Stores complete per-field change history in PostgreSQL
- Provides a Flask-based web UI for browsing and filtering listings
- Runs entirely via Docker Compose with zero manual configuration

### Architecture

The system consists of 3 Docker containers:

1. **db** (PostgreSQL 16-alpine)
   - Stores all listing data with full history
   - Per-field change tracking via triggers
   - Hierarchical table structure for different property types

2. **crawler** (Scrapy + APScheduler)
   - Automated daily scraping at 20:00 Europe/Prague
   - Manual trigger via internal HTTP endpoint
   - Respects robots.txt and implements polite crawling
   - Stores HTML on disk with binary comparison for changes

3. **flask** (Flask + Jinja2)
   - Read-only web UI on localhost:8000
   - Filtering, sorting, pagination
   - Listing detail with complete change history
   - Live progress monitoring during crawl runs

### Key Features

- **Complete archiving**: All listings from sreality.cz (prodej/pronájem/dražba)
- **Change tracking**: Per-field history with diff model and checkpoints
- **Polite scraping**: AutoThrottle, conditional requests (ETag/If-Modified-Since)
- **Docker-first**: Single command `docker compose up` to start everything
- **Zero configuration**: All settings via .env file
- **Timezone-aware**: Europe/Prague throughout the system

## Implementation Specification

**IMPORTANT**: The complete, detailed implementation specification is in **SPECIFIKACE.md**.

That file contains:
- Complete Docker Compose setup
- Detailed crawler implementation (Scrapy + APScheduler)
- Full database schema with hierarchical tables
- Flask UI requirements and endpoints
- HTML storage and image handling
- Change tracking and diff model
- Acceptance criteria

**Always consult SPECIFIKACE.md before implementing features.**

## Project Structure

```
.
├── docker-compose.yml          # Main Docker Compose configuration
├── .env                        # Environment variables (not committed)
├── .env.example                # Environment template
├── SPECIFIKACE.md              # Complete implementation specification
├── crawler/                    # Scrapy crawler container
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── scrapy_project/         # Scrapy project root
│   └── scheduler/              # APScheduler integration
├── flask_app/                  # Flask web UI container
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       ├── templates/          # Jinja2 templates
│       ├── static/             # CSS/JS assets
│       └── routes.py           # Flask routes
├── db/                         # Database migrations and seeds
│   └── init/                   # Initial schema
└── data/                       # Persistent data (volumes)
    ├── html/                   # Stored HTML files
    ├── logs/                   # Crawler logs
    └── postgres/               # PostgreSQL data
```

## Development Workflow

### Running the Project

```bash
# Start all containers
docker compose up

# Access Flask UI
http://localhost:8000

# Trigger manual crawl (from within network)
curl -X POST http://crawler:7070/run-now
```

### Git Operations and Dropbox

**CRITICAL**: This repository may be in a Dropbox folder. Dropbox locks files in `.git/` directory causing "Permission denied" errors.

**ALWAYS follow this procedure before git commit/push:**

1. **Stop Dropbox**:
```powershell
powershell.exe -NoProfile -Command "Stop-Process -Name 'Dropbox' -Force -ErrorAction SilentlyContinue; Start-Sleep -Seconds 2"
```

2. **Perform git operations** (add, commit, push)

3. **Restart Dropbox** (optional):
```powershell
powershell.exe -NoProfile -Command "Start-Process -FilePath 'C:\Program Files (x86)\Dropbox\Client\Dropbox.exe'"
```

All Dropbox management commands are stored in `.claude/settings.json` under `dropboxManagement` section.

### Code Style

- **Python 3.12+** in all containers
- **Type hints** wherever applicable
- **Docstrings** for functions and classes
- **English** for all code and comments
- Follow PEP 8 style guidelines

### Logging

- Crawler: Timestamped log files in persistent volume
- Flask: Console output via Docker
- **Colored log levels** (not white)
- All timestamps in Europe/Prague timezone

### Testing

- Unit tests for business logic
- Integration tests for database operations
- Manual acceptance testing against SPECIFIKACE.md criteria

## Key Technical Decisions

### Why Flask instead of FastAPI?

The specification explicitly requires Flask + Jinja2 for simplicity and template rendering.

### Why store HTML on disk?

- Allows binary comparison to detect changes before parsing
- Reduces database size
- Enables forensic analysis
- Named volumes ensure persistence

### Why hierarchical database tables?

- Different property types (byty/domy/pozemky/komerční/ostatní) have type-specific fields
- Table inheritance keeps schema organized
- Allows type-specific queries and indexes

### Why per-field change tracking with diffs?

- Minimizes storage (only deltas saved)
- Enables precise history reconstruction
- Checkpoints every 100 changes ensure reasonable query performance

## Common Tasks

### Add a new scraping source

1. Update crawler spider to handle new URL patterns
2. Add category mappings in database
3. Update SPECIFIKACE.md if architecture changes
4. Test with manual crawl first

### Modify database schema

1. Create migration in db/init/
2. Update application code
3. Document in SPECIFIKACE.md
4. Rebuild db container

### Add UI feature

1. Update Flask routes
2. Create/modify Jinja2 templates
3. Test in browser
4. Ensure read-only compliance

## References

- **Full specification**: SPECIFIKACE.md
- **Scrapy documentation**: https://docs.scrapy.org
- **Flask documentation**: https://flask.palletsprojects.com
- **PostgreSQL documentation**: https://www.postgresql.org/docs/
- **APScheduler**: https://apscheduler.readthedocs.io

## Notes

- This is a **read-only archiving system** - the web UI never modifies data
- Crawler runs on **scheduled times only** (manual trigger available)
- All containers use **Europe/Prague timezone**
- **No authentication required** (localhost-only access)
- Project emphasizes **politeness and reliability** over speed
