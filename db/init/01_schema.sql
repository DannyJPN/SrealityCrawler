-- SrealityCrawler Database Schema
-- Hierarchical table structure for different property types
-- With full change history tracking via diff model

-- Set timezone
SET timezone = 'Europe/Prague';

-- Enable necessary extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================================
-- ENUMERATIONS
-- ============================================================================

-- Main property categories
CREATE TYPE property_category AS ENUM (
    'byty',          -- Apartments
    'domy',          -- Houses
    'pozemky',       -- Land
    'komercni',      -- Commercial
    'ostatni'        -- Other
);

-- Transaction types
CREATE TYPE transaction_type AS ENUM (
    'prodej',        -- Sale
    'pronajem',      -- Rent
    'drazba'         -- Auction
);

-- Apartment subtypes
CREATE TYPE apartment_subtype AS ENUM (
    'byt',
    'pokoj',
    'atypicky'
);

-- House subtypes
CREATE TYPE house_subtype AS ENUM (
    'rodinny_dum',
    'vila',
    'chata',
    'chalupa',
    'patrovy_dum',
    'zemedelska_usedlost'
);

-- Land subtypes
CREATE TYPE land_subtype AS ENUM (
    'pozemek_bydleni',
    'pozemek_komercni',
    'pozemek_pole',
    'pozemek_les',
    'pozemek_rybnik',
    'pozemek_sad',
    'pozemek_zahrada',
    'pozemek_ostatni'
);

-- Commercial subtypes
CREATE TYPE commercial_subtype AS ENUM (
    'kancelare',
    'sklad',
    'vyrobni_prostor',
    'obchodni_prostor',
    'ubytovaci_prostor',
    'restaurace',
    'zemedelsky_objekt',
    'cinzovni_dum',
    'ostatni_komercni'
);

-- Other subtypes
CREATE TYPE other_subtype AS ENUM (
    'garaz',
    'garaze',
    'vinny_sklep',
    'mobilheim',
    'ostatni'
);

-- ============================================================================
-- BASE LISTINGS TABLE (common fields for all property types)
-- ============================================================================

CREATE TABLE listings (
    id SERIAL PRIMARY KEY,
    listing_id VARCHAR(50) UNIQUE NOT NULL,  -- Sreality unique ID

    -- Basic information
    category property_category NOT NULL,
    transaction_type transaction_type NOT NULL,
    title TEXT NOT NULL,
    description TEXT,

    -- Pricing
    price BIGINT,  -- Price in CZK (integer)
    price_note TEXT,  -- Additional pricing notes

    -- Location
    region VARCHAR(100),
    district VARCHAR(100),
    municipality VARCHAR(200),
    city_part VARCHAR(200),
    street VARCHAR(200),
    latitude DECIMAL(10, 8),
    longitude DECIMAL(11, 8),

    -- Areas
    usable_area DECIMAL(10, 2),  -- in m²
    floor_area DECIMAL(10, 2),    -- in m²
    land_area DECIMAL(10, 2),     -- in m²

    -- Calculated fields
    price_per_sqm DECIMAL(12, 2),  -- CZK/m²

    -- Property details
    building_type VARCHAR(100),
    condition VARCHAR(100),
    ownership VARCHAR(100),

    -- Contact & source
    source_url TEXT NOT NULL,
    html_file_path TEXT,  -- Path to stored HTML file

    -- Metadata
    is_active BOOLEAN DEFAULT TRUE,
    first_seen_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_seen_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_modified_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    -- Indexes
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Indexes on listings table
CREATE INDEX idx_listings_listing_id ON listings(listing_id);
CREATE INDEX idx_listings_category ON listings(category);
CREATE INDEX idx_listings_transaction_type ON listings(transaction_type);
CREATE INDEX idx_listings_price ON listings(price);
CREATE INDEX idx_listings_municipality ON listings(municipality);
CREATE INDEX idx_listings_is_active ON listings(is_active);
CREATE INDEX idx_listings_last_seen_at ON listings(last_seen_at);
CREATE INDEX idx_listings_price_per_sqm ON listings(price_per_sqm);
CREATE INDEX idx_listings_usable_area ON listings(usable_area);

-- Full text search index on title and description
CREATE INDEX idx_listings_title_trgm ON listings USING gin(title gin_trgm_ops);
CREATE INDEX idx_listings_description_trgm ON listings USING gin(description gin_trgm_ops);

-- ============================================================================
-- APARTMENTS (Byty)
-- ============================================================================

CREATE TABLE apartments (
    id SERIAL PRIMARY KEY,
    listing_id INTEGER REFERENCES listings(id) ON DELETE CASCADE,

    subtype apartment_subtype,
    disposition VARCHAR(20),  -- 1+kk, 2+1, etc.
    floor INTEGER,
    total_floors INTEGER,
    balcony BOOLEAN,
    terrace BOOLEAN,
    loggia BOOLEAN,
    cellar BOOLEAN,
    parking BOOLEAN,
    garage BOOLEAN,
    elevator BOOLEAN,

    -- Utilities
    heating VARCHAR(100),
    gas BOOLEAN,
    water VARCHAR(100),
    electricity BOOLEAN,
    sewage VARCHAR(100),

    -- Barrier-free
    barrier_free BOOLEAN,

    -- Energy certificate
    energy_class VARCHAR(10),

    -- Equipment
    equipped BOOLEAN,
    furnished BOOLEAN,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(listing_id)
);

CREATE INDEX idx_apartments_subtype ON apartments(subtype);
CREATE INDEX idx_apartments_disposition ON apartments(disposition);
CREATE INDEX idx_apartments_floor ON apartments(floor);
CREATE INDEX idx_apartments_elevator ON apartments(elevator);

-- ============================================================================
-- HOUSES (Domy)
-- ============================================================================

CREATE TABLE houses (
    id SERIAL PRIMARY KEY,
    listing_id INTEGER REFERENCES listings(id) ON DELETE CASCADE,

    subtype house_subtype,
    total_floors INTEGER,
    rooms INTEGER,
    bedrooms INTEGER,
    bathrooms INTEGER,

    -- Utilities
    heating VARCHAR(100),
    gas BOOLEAN,
    water VARCHAR(100),
    electricity BOOLEAN,
    sewage VARCHAR(100),

    -- Features
    garage BOOLEAN,
    parking BOOLEAN,
    cellar BOOLEAN,
    terrace BOOLEAN,
    balcony BOOLEAN,
    pool BOOLEAN,
    garden BOOLEAN,

    -- Barrier-free
    barrier_free BOOLEAN,

    -- Energy certificate
    energy_class VARCHAR(10),

    -- Construction
    construction_year INTEGER,
    reconstruction_year INTEGER,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(listing_id)
);

CREATE INDEX idx_houses_subtype ON houses(subtype);
CREATE INDEX idx_houses_rooms ON houses(rooms);
CREATE INDEX idx_houses_construction_year ON houses(construction_year);

-- ============================================================================
-- LAND (Pozemky)
-- ============================================================================

CREATE TABLE land (
    id SERIAL PRIMARY KEY,
    listing_id INTEGER REFERENCES listings(id) ON DELETE CASCADE,

    subtype land_subtype,

    -- Utilities
    electricity BOOLEAN,
    gas BOOLEAN,
    water BOOLEAN,
    sewage BOOLEAN,
    road_access BOOLEAN,

    -- Development potential
    development_potential BOOLEAN,
    zoning VARCHAR(100),

    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(listing_id)
);

CREATE INDEX idx_land_subtype ON land(subtype);
CREATE INDEX idx_land_development_potential ON land(development_potential);

-- ============================================================================
-- COMMERCIAL (Komerční)
-- ============================================================================

CREATE TABLE commercial (
    id SERIAL PRIMARY KEY,
    listing_id INTEGER REFERENCES listings(id) ON DELETE CASCADE,

    subtype commercial_subtype,

    -- Space details
    office_space DECIMAL(10, 2),
    production_space DECIMAL(10, 2),
    storage_space DECIMAL(10, 2),
    sales_space DECIMAL(10, 2),

    -- Utilities
    heating VARCHAR(100),
    gas BOOLEAN,
    water BOOLEAN,
    electricity BOOLEAN,
    sewage BOOLEAN,

    -- Features
    parking_spaces INTEGER,
    loading_ramp BOOLEAN,
    elevator BOOLEAN,

    -- Barrier-free
    barrier_free BOOLEAN,

    -- Energy certificate
    energy_class VARCHAR(10),

    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(listing_id)
);

CREATE INDEX idx_commercial_subtype ON commercial(subtype);
CREATE INDEX idx_commercial_parking_spaces ON commercial(parking_spaces);

-- ============================================================================
-- OTHER (Ostatní)
-- ============================================================================

CREATE TABLE other_properties (
    id SERIAL PRIMARY KEY,
    listing_id INTEGER REFERENCES listings(id) ON DELETE CASCADE,

    subtype other_subtype,

    -- Basic details
    has_electricity BOOLEAN,
    has_water BOOLEAN,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(listing_id)
);

CREATE INDEX idx_other_subtype ON other_properties(subtype);

-- ============================================================================
-- IMAGES
-- ============================================================================

CREATE TABLE images (
    id SERIAL PRIMARY KEY,
    listing_id INTEGER REFERENCES listings(id) ON DELETE CASCADE,

    image_url TEXT NOT NULL,
    image_data BYTEA,  -- Store image binary data
    image_order INTEGER DEFAULT 0,
    is_primary BOOLEAN DEFAULT FALSE,

    downloaded_at TIMESTAMP WITH TIME ZONE,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(listing_id, image_url)
);

CREATE INDEX idx_images_listing_id ON images(listing_id);
CREATE INDEX idx_images_is_primary ON images(is_primary);

-- ============================================================================
-- CHANGE HISTORY (Diff Model with Checkpoints)
-- ============================================================================

CREATE TABLE listing_history (
    id SERIAL PRIMARY KEY,
    listing_id INTEGER REFERENCES listings(id) ON DELETE CASCADE,

    -- Change tracking
    change_number INTEGER NOT NULL,  -- Sequential change number for this listing
    is_checkpoint BOOLEAN DEFAULT FALSE,  -- Checkpoint every 100 changes

    -- Changed data (stored as JSONB for flexibility)
    -- For checkpoint: full state
    -- For regular change: only diffs
    changed_fields JSONB NOT NULL,

    -- Metadata
    changed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    -- Ensure unique change numbers per listing
    UNIQUE(listing_id, change_number)
);

CREATE INDEX idx_history_listing_id ON listing_history(listing_id);
CREATE INDEX idx_history_change_number ON listing_history(listing_id, change_number);
CREATE INDEX idx_history_is_checkpoint ON listing_history(listing_id, is_checkpoint);
CREATE INDEX idx_history_changed_at ON listing_history(changed_at);

-- ============================================================================
-- TRIGGER FUNCTIONS
-- ============================================================================

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Add triggers to all tables
CREATE TRIGGER update_listings_updated_at BEFORE UPDATE ON listings
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_apartments_updated_at BEFORE UPDATE ON apartments
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_houses_updated_at BEFORE UPDATE ON houses
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_land_updated_at BEFORE UPDATE ON land
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_commercial_updated_at BEFORE UPDATE ON commercial
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_other_properties_updated_at BEFORE UPDATE ON other_properties
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- HELPER VIEWS
-- ============================================================================

-- View to get current state of all listings with their type-specific data
CREATE VIEW current_listings AS
SELECT
    l.*,
    'apartment' as property_type,
    row_to_json(a.*) as type_specific_data
FROM listings l
LEFT JOIN apartments a ON l.id = a.listing_id
WHERE l.category = 'byty' AND l.is_active = true

UNION ALL

SELECT
    l.*,
    'house' as property_type,
    row_to_json(h.*) as type_specific_data
FROM listings l
LEFT JOIN houses h ON l.id = h.listing_id
WHERE l.category = 'domy' AND l.is_active = true

UNION ALL

SELECT
    l.*,
    'land' as property_type,
    row_to_json(ld.*) as type_specific_data
FROM listings l
LEFT JOIN land ld ON l.id = ld.listing_id
WHERE l.category = 'pozemky' AND l.is_active = true

UNION ALL

SELECT
    l.*,
    'commercial' as property_type,
    row_to_json(c.*) as type_specific_data
FROM listings l
LEFT JOIN commercial c ON l.id = c.listing_id
WHERE l.category = 'komercni' AND l.is_active = true

UNION ALL

SELECT
    l.*,
    'other' as property_type,
    row_to_json(o.*) as type_specific_data
FROM listings l
LEFT JOIN other_properties o ON l.id = o.listing_id
WHERE l.category = 'ostatni' AND l.is_active = true;

-- ============================================================================
-- UTILITY FUNCTIONS
-- ============================================================================

-- Function to get current state of a listing (reconstructed from history)
CREATE OR REPLACE FUNCTION get_listing_state_at(p_listing_id INTEGER, p_timestamp TIMESTAMP WITH TIME ZONE)
RETURNS JSONB AS $$
DECLARE
    v_state JSONB;
    v_checkpoint JSONB;
    v_change RECORD;
BEGIN
    -- Find the most recent checkpoint before the timestamp
    SELECT changed_fields INTO v_checkpoint
    FROM listing_history
    WHERE listing_id = p_listing_id
      AND is_checkpoint = true
      AND changed_at <= p_timestamp
    ORDER BY change_number DESC
    LIMIT 1;

    -- If no checkpoint found, start with empty state
    IF v_checkpoint IS NULL THEN
        v_state := '{}'::JSONB;
    ELSE
        v_state := v_checkpoint;
    END IF;

    -- Apply all changes after the checkpoint up to the timestamp
    FOR v_change IN
        SELECT changed_fields
        FROM listing_history
        WHERE listing_id = p_listing_id
          AND changed_at <= p_timestamp
          AND (v_checkpoint IS NULL OR change_number > (
              SELECT change_number FROM listing_history
              WHERE listing_id = p_listing_id
                AND is_checkpoint = true
                AND changed_at <= p_timestamp
              ORDER BY change_number DESC
              LIMIT 1
          ))
        ORDER BY change_number
    LOOP
        -- Merge changes into state
        v_state := v_state || v_change.changed_fields;
    END LOOP;

    RETURN v_state;
END;
$$ LANGUAGE plpgsql;

-- Create trgm extension for text search
CREATE EXTENSION IF NOT EXISTS pg_trgm;
