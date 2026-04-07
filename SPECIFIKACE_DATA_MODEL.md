# Sreality Crawler — Data Model and History Specification

## Purpose

This document refines the implementation specification for storage, identity, history, and manual browsing.
It supersedes the earlier assumption that the persistence layer should mirror the category tree using table inheritance.

The guiding requirement is:

- preserve the full history of each individual listing,
- including value changes,
- including the addition of a previously missing property,
- including the removal of a previously present property,
- while keeping the data human-browseable without custom tooling.

## Core design decision

Use a hybrid model:

- in application code: one common parent domain object for all listings,
- in persistence: relational core tables plus typed dynamic attributes and explicit history events,
- for manual browsing: generated flat exports on top of the normalized store.

Do **not** model every subtype as a dedicated child table with subtype-only columns.

Reasoning:

- the analysis of official subtypes shows that only a small subset of fields is truly universal,
- subtype-specific fields vary widely and are not stable enough for large rigid schemas,
- the system must track property additions and removals, not only updates,
- the CSV fallback must imitate relational storage cleanly and remain inspectable by a human.

## Supported storage backends

The system must run in both modes:

1. PostgreSQL present:
   - primary storage backend is PostgreSQL.
2. PostgreSQL absent:
   - storage backend falls back to local `Data/` CSV files.

The logical schema must be identical across both modes.
CSV files are not an ad hoc dump; they are the file-form equivalent of the relational model.

## Identity rules

### Source identifier

`source_listing_id` is the original Sreality listing identifier.

It is not sufficient on its own for the historical identity of a stored listing entity.

### Entity identity

A stored listing entity is identified by the tuple:

- `source_listing_id`
- `offer_type`
- `main_category`
- `subtype`
- `location_key`

If any of these changes, the old entity ends and a new entity begins.

That is an explicit business rule, even if the upstream Sreality ID remains the same.

### Important consequence

Changes to these fields are **not** ordinary attribute-change events:

- `offer_type`
- `main_category`
- `subtype`
- `location_key`

Instead:

- old entity is marked ended/inactive,
- new entity is created,
- relationship may optionally be recorded as a continuity link.

## Category coverage and deactivation rules

The crawler must never deactivate an entity just because it was not seen in an unrelated crawl.

### Allowed deactivation

An entity may be marked inactive only when:

- the current run actually processed the relevant category scope for that entity,
- and the entity was not found in that processed scope.

### Forbidden deactivation

Do not deactivate when:

- a different main category was crawled,
- a different subtype was crawled,
- a different location scope was crawled,
- or the relevant scope was only partially processed.

No `unknown` state is used.
If the relevant scope was not processed, the entity is left unchanged.

## Location model

Location is part of identity, so it must be deterministic.

### Raw location data

Store all available parsed location fields separately, for example:

- country id/name
- region id/name
- district id/name
- city
- city part
- quarter
- street
- house number
- zip
- latitude
- longitude

### Normalized location key

Compute `location_key` from a normalized canonical representation of location data.

Recommended approach:

- normalize whitespace,
- normalize Unicode to NFKC,
- lowercase for key generation,
- preserve original values in display columns,
- hash the canonical JSON representation.

This allows:

- deterministic identity,
- stable comparisons,
- readable original values for UI and exports.

## Domain model

The application may use classes similar to:

- `ListingEntity`
- `ListingVersion`
- `AttributeDefinition`
- `AttributeValue`
- `AttributeEvent`
- `MediaItem`
- `CrawlRun`
- `CrawlRunScope`

Category-specific classes may exist in code, but persistence must not depend on subtype tables.

## Relational logical schema

### 1. `listing_entities`

Represents the long-lived identity of a listing as defined by the business identity tuple.

Required columns:

- `entity_id` PK
- `source_listing_id`
- `offer_type`
- `main_category`
- `subtype`
- `location_key`
- `location_display`
- `first_seen_at`
- `last_seen_at`
- `ended_at`
- `is_active`
- `current_version_id`
- `created_run_id`
- `ended_run_id`

Uniqueness:

- unique on `source_listing_id + offer_type + main_category + subtype + location_key`

### 2. `listing_versions`

Represents point-in-time states or checkpoints of a listing entity.

Required columns:

- `version_id` PK
- `entity_id` FK
- `crawl_run_id` FK
- `observed_at`
- `version_kind`
- `content_hash`
- `html_snapshot_id` FK nullable
- `is_checkpoint`
- `checkpoint_number`

`version_kind` values:

- `initial`
- `diff`
- `checkpoint`

### 3. `attribute_definitions`

Catalog of known attributes.

Required columns:

- `attribute_id` PK
- `attribute_code` unique
- `label`
- `value_type`
- `unit`
- `category_scope`
- `main_category_scope`
- `is_identity_part`
- `is_filterable`
- `is_display_priority`
- `display_order`
- `notes`

`value_type` examples:

- `string`
- `text`
- `integer`
- `decimal`
- `boolean`
- `date`
- `datetime`
- `json`

### 4. `listing_attribute_current`

Current value of each attribute for each active or historical entity.

Required columns:

- `entity_id` FK
- `attribute_id` FK
- typed value columns
- `value_hash`
- `updated_at`
- `last_seen_in_version_id`

Primary key:

- `entity_id + attribute_id`

Typed value columns:

- `value_string`
- `value_text`
- `value_integer`
- `value_decimal`
- `value_boolean`
- `value_date`
- `value_datetime`
- `value_json`

Only one typed value column is populated according to `attribute_definitions.value_type`.

### 5. `listing_attribute_events`

Full attribute-level history.

Required columns:

- `event_id` PK
- `entity_id` FK
- `version_id` FK
- `crawl_run_id` FK
- `attribute_id` FK
- `event_type`
- old typed value columns
- new typed value columns
- `old_value_hash`
- `new_value_hash`
- `event_time`

`event_type` values:

- `added`
- `changed`
- `removed`

### 6. `html_snapshots`

Metadata for stored raw HTML.

Required columns:

- `html_snapshot_id` PK
- `entity_id` FK
- `crawl_run_id` FK
- `file_path`
- `content_hash`
- `stored_at`
- `is_latest`

HTML content itself remains on disk, not in the database.

### 7. `listing_media`

Current media set for an entity.

Required columns:

- `media_id` PK
- `entity_id` FK
- `external_media_id`
- `media_type`
- `source_url`
- `original_url`
- `sort_order`
- `mime_type`
- `checksum`
- `storage_backend`
- `storage_path` nullable
- `storage_ref` nullable
- `is_active`
- `first_seen_at`
- `last_seen_at`

### 8. `listing_media_events`

History of media additions/removals/changes.

Required columns:

- `media_event_id` PK
- `entity_id` FK
- `version_id` FK
- `crawl_run_id` FK
- `media_id` FK nullable
- `event_type`
- `source_url`
- `sort_order`
- `event_time`

`event_type` values:

- `added`
- `removed`
- `reordered`
- `download_failed`

### 9. `crawl_runs`

Metadata for each crawler execution.

Required columns:

- `crawl_run_id` PK
- `started_at`
- `finished_at`
- `status`
- `trigger_type`
- `storage_backend`
- `notes`

`trigger_type` values:

- `scheduled`
- `manual`
- `local_cli`

`status` values:

- `running`
- `completed`
- `failed`
- `aborted`

### 10. `crawl_run_scopes`

Defines which logical scopes were actually processed during a run.

Required columns:

- `crawl_run_scope_id` PK
- `crawl_run_id` FK
- `offer_type`
- `main_category`
- `subtype` nullable
- `location_scope_type`
- `location_scope_key`
- `coverage_status`
- `expected_page_count` nullable
- `fetched_page_count`
- `notes`

`coverage_status` values:

- `complete`
- `partial`
- `failed`

This table is required for correct deactivation behavior.

### 11. `listing_presence`

Records that an entity was actually seen in a given run.

Required columns:

- `crawl_run_id` FK
- `entity_id` FK
- `crawl_run_scope_id` FK nullable
- `seen_at`

Primary key:

- `crawl_run_id + entity_id`

### 12. `entity_links` optional

Optional linkage between a terminated entity and a successor entity when the upstream listing ID remains the same but identity-defining fields changed.

Required columns:

- `link_id` PK
- `old_entity_id`
- `new_entity_id`
- `link_type`
- `created_at`

`link_type` examples:

- `location_changed`
- `subtype_changed`
- `category_changed`
- `offer_type_changed`

## Attribute handling strategy

### Rule

All non-identity listing properties are stored as attributes.

Examples:

- price
- price per m2
- description
- ownership
- building type
- building condition
- utilities
- floor
- usable area
- plot area
- parking
- elevator
- garden
- equipment
- energy rating
- price note

### Why typed attributes are preferred

- supports wide variation across subtypes,
- supports property addition/removal naturally,
- avoids schema explosion,
- keeps both PostgreSQL and CSV fallback aligned,
- allows manual exports to be generated from a single source of truth.

## Versioning and diff rules

### Initial observation

When a new entity is first observed:

- create row in `listing_entities`,
- create `initial` row in `listing_versions`,
- populate `listing_attribute_current`,
- create `added` events for all present attributes.

### Subsequent observation

For an existing entity:

- parse and normalize all observed attributes,
- compare against `listing_attribute_current`.

For each attribute:

- absent before, present now -> `added`
- present before, absent now -> `removed`
- present before and now, value differs -> `changed`
- same value -> no attribute event

If there are any changes:

- create a new `listing_versions` row,
- write corresponding attribute events,
- update `listing_attribute_current`.

If there are no changes:

- only update `last_seen_at`,
- optionally update version-touch metadata if required.

### Checkpoints

After every 100 attribute events for one entity:

- create a checkpoint version,
- materialize a full snapshot of current attributes.

## Manual browsing requirements

The system must be inspectable by a human without needing the application UI.

That means the normalized internal storage must be accompanied by human-oriented exports.

### Required human-readable outputs

Generate these browse-friendly files for both PostgreSQL exports and CSV fallback mode:

- `Data/browse/entities.csv`
- `Data/browse/current_flat.csv`
- `Data/browse/history_log.csv`
- `Data/browse/attribute_catalog.csv`
- `Data/browse/run_scopes.csv`

### Purpose of each export

`entities.csv`

- one row per entity,
- identity, lifecycle, category, subtype, location summary, active flag.

`current_flat.csv`

- one row per entity,
- most important common fields as columns,
- remaining dynamic attributes in `extra_attributes_json`.

`history_log.csv`

- append-only human-readable event log,
- one row per change,
- examples:
  - `changed Celkova cena: 5900000 -> 5700000`
  - `added Terasa: 12`
  - `removed Vytah`

`attribute_catalog.csv`

- all known attributes,
- codes, labels, types, units, scopes, display order.

`run_scopes.csv`

- which scopes each run really processed,
- required to manually audit deactivation decisions.

### Raw HTML browsing

Stored HTML must also remain directly accessible on disk in a stable path layout.

Recommended layout:

- `Data/html/<offer_type>/<main_category>/<subtype>/<entity_id>/<timestamp>.html`

Optionally keep:

- `latest.html`
- versioned historical files

The minimum requirement remains at least the latest raw HTML, but historical HTML retention is recommended when storage allows it.

## CSV fallback layout

When PostgreSQL is absent, the following CSV files must exist in `Data/csv/`:

- `listing_entities.csv`
- `listing_versions.csv`
- `attribute_definitions.csv`
- `listing_attribute_current.csv`
- `listing_attribute_events.csv`
- `html_snapshots.csv`
- `listing_media.csv`
- `listing_media_events.csv`
- `crawl_runs.csv`
- `crawl_run_scopes.csv`
- `listing_presence.csv`
- `entity_links.csv` if used

These CSV files are the canonical persistence backend in fallback mode.
Human-browseable exports are generated in addition, not instead.

## OOP guidance

The domain model should still present a shared parent type because all listings share lifecycle and history behavior.

Recommended structure:

- `ListingEntity` as parent
- category-specific parser or view models as needed
- attribute normalization layer separated from persistence layer

Do not encode subtype differences primarily through subclass-specific storage schemas.

Subtype differences belong in:

- parser rules,
- attribute definitions,
- display configuration,
- optional helper view models.

## Parser normalization rules

Before comparison, values must be normalized.

### Text

- strip HTML
- collapse whitespace
- trim
- normalize Unicode NFKC

### Prices

- integer CZK

### Areas

- decimal square meters

### Booleans

- explicit `true/false`

### Missing values

- distinguish between empty string and absent property
- removed property means the attribute is not present in the current observation at all

## UI implications

The web UI should read from:

- `listing_entities`
- `listing_attribute_current`
- `listing_versions`
- `listing_attribute_events`

The listing page should be backed by:

- current flattened values for speed

The detail page should show:

- identity metadata
- current attributes
- timeline of attribute events
- access to current and optionally historical HTML

## Acceptance criteria additions

The implementation is not complete unless all of the following are true:

- the system runs with PostgreSQL and without PostgreSQL,
- CSV fallback mirrors the logical relational model,
- a listing property can be added, changed, and removed with explicit history events,
- identity changes in `offer_type`, `main_category`, `subtype`, or `location_key` create a new entity,
- deactivation only happens for scopes actually processed in the run,
- a human can inspect entity lifecycle and history directly from files without the web UI,
- generated browse-friendly exports exist and remain synchronized with the normalized store.
