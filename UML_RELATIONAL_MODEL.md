# UML Relational Model Proposal

## Scope

This document describes the relational design for the Sreality archival system in a way that is consistent with the detailed data model specification in `SPECIFIKACE_DATA_MODEL.md`.

The goal is to support:

- full entity lifecycle tracking,
- attribute-level history,
- HTML and media persistence,
- correct category-scoped deactivation,
- CSV fallback with the same logical structure,
- manual browsing of the stored data.

## Modeling principles

### 1. One shared root entity

All listings share a common parent concept:

- `ListingEntity`

This is the persisted identity root for all listing records.

### 2. Identity is stricter than upstream ID

A persisted listing entity is identified by:

- `source_listing_id`
- `offer_type`
- `main_category`
- `subtype`
- `location_key`

If any of those changes, the old entity ends and a new entity begins.

### 3. History is event-based

Regular listing changes are represented as attribute events:

- `added`
- `changed`
- `removed`

### 4. Rigid subtype tables are avoided

Subtype-specific data is stored through typed attribute rows rather than dedicated child tables per subtype.

This avoids:

- schema explosion,
- repeated migrations for new fields,
- poor CSV parity,
- awkward manual inspection.

## Entity overview

### Lifecycle and identity

- `listing_entities`
- `entity_links`
- `crawl_runs`
- `crawl_run_scopes`
- `listing_presence`

### Versioning and history

- `listing_versions`
- `attribute_definitions`
- `listing_attribute_current`
- `listing_attribute_events`

### Raw source artifacts

- `html_snapshots`
- `listing_media`
- `listing_media_events`

## Table responsibilities

### `listing_entities`

Stores the durable identity and lifecycle of a listing entity.

Main responsibilities:

- stable identity,
- active/inactive lifecycle,
- linkage to current version,
- created/ended run references.

### `listing_versions`

Stores point-in-time states of one listing entity.

Main responsibilities:

- initial version,
- ordinary diff-bearing version,
- periodic checkpoint version.

### `attribute_definitions`

Stores the catalog of normalized attributes.

Main responsibilities:

- canonical attribute code,
- display label,
- value type,
- scope and UI hints.

### `listing_attribute_current`

Stores the latest known value for each attribute on an entity.

Main responsibilities:

- fast read path for UI,
- fast comparison target during crawl,
- source of flattened exports.

### `listing_attribute_events`

Stores attribute-level history.

Main responsibilities:

- change audit,
- reconstruction support,
- human-readable history export input.

### `crawl_runs`

Stores execution metadata for a crawler run.

Main responsibilities:

- run lifecycle,
- trigger type,
- backend mode,
- operational traceability.

### `crawl_run_scopes`

Stores which logical category scopes were really processed.

Main responsibilities:

- deactivation safety,
- run coverage audit,
- support for partial runs.

### `listing_presence`

Stores that an entity was actually seen during a run.

Main responsibilities:

- existence evidence,
- deactivation decisions,
- run-to-entity association.

### `html_snapshots`

Stores metadata about raw HTML files kept on disk.

Main responsibilities:

- path mapping,
- content hashing,
- latest snapshot pointer.

### `listing_media`

Stores the current media set for an entity.

Main responsibilities:

- current image/file state,
- storage reference,
- order and checksum tracking.

### `listing_media_events`

Stores media-level history.

Main responsibilities:

- added/removed/reordered media,
- failed download trace.

### `entity_links`

Optional bridge between logically related entities.

Main responsibilities:

- connect old and new entity when identity-defining fields changed,
- preserve navigability across entity restarts.

## Cardinalities

### Core

- one `crawl_run` has many `crawl_run_scopes`
- one `crawl_run` has many `listing_versions`
- one `crawl_run` has many `listing_presence` rows
- one `listing_entity` has many `listing_versions`
- one `listing_entity` has many `listing_attribute_current` rows
- one `listing_entity` has many `listing_attribute_events`
- one `listing_entity` has many `html_snapshots`
- one `listing_entity` has many `listing_media`

### Versioning

- one `listing_version` belongs to one `listing_entity`
- one `listing_version` has many `listing_attribute_events`
- one `listing_version` has many `listing_media_events`
- one `listing_version` may reference one `html_snapshot`

### Attribute model

- one `attribute_definition` is referenced by many `listing_attribute_current` rows
- one `attribute_definition` is referenced by many `listing_attribute_events`

### Scope and presence

- one `crawl_run_scope` may be referenced by many `listing_presence` rows
- one `listing_entity` may appear in many runs

## Keys and constraints

### Primary identity constraint

Unique constraint on:

- `source_listing_id`
- `offer_type`
- `main_category`
- `subtype`
- `location_key`

### Current attribute constraint

Primary key on:

- `entity_id`
- `attribute_id`

### Presence constraint

Primary key on:

- `crawl_run_id`
- `entity_id`

## Normalized persistence vs browse-oriented exports

The normalized schema is the canonical store.

For human inspection, generate browse-friendly derivatives:

- `Data/browse/entities.csv`
- `Data/browse/current_flat.csv`
- `Data/browse/history_log.csv`
- `Data/browse/attribute_catalog.csv`
- `Data/browse/run_scopes.csv`

These exports are projections, not primary storage.

## CSV fallback mapping

When PostgreSQL is not available, each logical table maps 1:1 to a CSV file:

- `listing_entities.csv`
- `listing_versions.csv`
- `attribute_definitions.csv`
- `listing_attribute_current.csv`
- `listing_attribute_events.csv`
- `crawl_runs.csv`
- `crawl_run_scopes.csv`
- `listing_presence.csv`
- `html_snapshots.csv`
- `listing_media.csv`
- `listing_media_events.csv`
- `entity_links.csv`

## Recommended use

Use this UML model as:

- the reference for PostgreSQL DDL,
- the reference for CSV file layout,
- the reference for crawler write logic,
- the reference for Flask read models,
- the basis for future migrations.
