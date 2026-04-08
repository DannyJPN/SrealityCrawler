"""
Scrapy pipelines for SrealityCrawler
"""

import os
import json
import hashlib
import logging
import lmdb
from pathlib import Path
from datetime import datetime
from typing import Optional
import unicodedata

import psycopg2
from psycopg2.extras import Json
import requests
from scrapy.exceptions import DropItem


logger = logging.getLogger(__name__)


class HTMLStoragePipeline:
    """
    Pipeline to store HTML files on disk and perform binary comparison
    to detect changes before parsing
    """

    def __init__(self, html_path, lmdb_path, lmdb_map_size):
        self.html_path = html_path
        self.lmdb_path = lmdb_path
        self.lmdb_map_size = lmdb_map_size
        self.lmdb_env = None

    @classmethod
    def from_crawler(cls, crawler):
        return cls(
            html_path=crawler.settings.get('HTML_STORAGE_PATH'),
            lmdb_path=crawler.settings.get('LMDB_PATH'),
            lmdb_map_size=crawler.settings.get('LMDB_MAP_SIZE'),
        )

    def open_spider(self, spider):
        """Initialize LMDB database for URL mapping"""
        os.makedirs(os.path.dirname(self.lmdb_path), exist_ok=True)
        self.lmdb_env = lmdb.open(
            self.lmdb_path,
            map_size=self.lmdb_map_size,
            max_dbs=1
        )
        logger.info(f'HTML storage pipeline opened with path: {self.html_path}')

    def close_spider(self, spider):
        """Close LMDB database"""
        if self.lmdb_env:
            self.lmdb_env.close()

    def process_item(self, item, spider):
        """Store HTML and check for changes"""

        url = item.get('source_url')
        html_content = item.get('html_content')
        listing_id = item.get('listing_id')
        category = item.get('category')
        transaction_type = item.get('transaction_type')

        if not url or not html_content or not listing_id:
            return item

        # Determine file path based on category and transaction type
        subdir = f"{category}_{transaction_type}"
        dir_path = os.path.join(self.html_path, subdir)
        os.makedirs(dir_path, exist_ok=True)

        filename = f"{listing_id}.html"
        file_path = os.path.join(dir_path, filename)

        # Store file path in item
        item['html_file_path'] = file_path

        # Check if file exists and compare
        if os.path.exists(file_path):
            with open(file_path, 'rb') as f:
                existing_html = f.read()

            # Binary comparison
            if existing_html == html_content.encode('utf-8'):
                logger.debug(f'HTML unchanged for {listing_id}, skipping parsing')
                # Mark as unchanged
                item['html_unchanged'] = True
                return item

        # Save HTML file
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(html_content)

        # Store URL -> filename mapping in LMDB
        with self.lmdb_env.begin(write=True) as txn:
            txn.put(url.encode('utf-8'), file_path.encode('utf-8'))

        item['html_unchanged'] = False
        logger.debug(f'HTML stored at {file_path}')

        return item


class ImageDownloadPipeline:
    """
    Pipeline to download all images and store them in the database
    """

    def __init__(self):
        self.session = requests.Session()

    def process_item(self, item, spider):
        """Download all images"""

        # Skip if HTML unchanged
        if item.get('html_unchanged'):
            return item

        image_urls = item.get('image_urls', [])
        if not image_urls:
            return item

        images_data = []

        for idx, image_url in enumerate(image_urls):
            try:
                response = self.session.get(image_url, timeout=30)
                response.raise_for_status()

                images_data.append({
                    'url': image_url,
                    'data': response.content,
                    'order': idx,
                    'is_primary': idx == 0
                })

                logger.debug(f'Downloaded image {idx + 1}/{len(image_urls)} for {item.get("listing_id")}')

            except Exception as e:
                logger.warning(f'Failed to download image {image_url}: {str(e)}')
                # Continue with other images (varianta A from spec)
                continue

        item['images_data'] = images_data
        logger.info(f'Downloaded {len(images_data)}/{len(image_urls)} images for {item.get("listing_id")}')

        return item

    def close_spider(self, spider):
        """Close HTTP session"""
        self.session.close()


class DatabasePipeline:
    """
    Pipeline to store listings in PostgreSQL with change history tracking
    """

    def __init__(self, db_config):
        self.db_config = db_config
        self.conn = None
        self.cursor = None

    @classmethod
    def from_crawler(cls, crawler):
        return cls(
            db_config={
                'host': crawler.settings.get('POSTGRES_HOST'),
                'port': crawler.settings.get('POSTGRES_PORT'),
                'database': crawler.settings.get('POSTGRES_DB'),
                'user': crawler.settings.get('POSTGRES_USER'),
                'password': crawler.settings.get('POSTGRES_PASSWORD'),
            }
        )

    def open_spider(self, spider):
        """Connect to database"""
        try:
            self.conn = psycopg2.connect(**self.db_config)
            self.cursor = self.conn.cursor()
            logger.info('Connected to PostgreSQL database')
        except Exception as e:
            logger.error(f'Failed to connect to database: {str(e)}')
            raise

    def close_spider(self, spider):
        """Close database connection"""
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.close()
        logger.info('Closed database connection')

    def process_item(self, item, spider):
        """Store or update listing in database with change tracking"""

        try:
            # If HTML unchanged, just update last_seen_at
            if item.get('html_unchanged'):
                self._update_last_seen(item)
                return item

            # Normalize item data
            normalized_item = self._normalize_item(item)

            # Check if listing exists
            listing_db_id = self._get_listing_db_id(normalized_item['listing_id'])

            if listing_db_id:
                # Update existing listing and track changes
                self._update_listing(listing_db_id, normalized_item, item)
            else:
                # Insert new listing
                self._insert_listing(normalized_item, item)

            self.conn.commit()
            logger.debug(f'Stored listing {normalized_item["listing_id"]} in database')

        except Exception as e:
            self.conn.rollback()
            logger.error(f'Failed to store listing {item.get("listing_id")}: {str(e)}')
            raise DropItem(f'Database error: {str(e)}')

        return item

    def _normalize_item(self, item):
        """Normalize item data according to specification"""
        normalized = {}

        # Copy basic fields
        for field in ['listing_id', 'category', 'transaction_type', 'title',
                      'description', 'source_url', 'html_file_path']:
            normalized[field] = item.get(field)

        # Normalize title and description
        normalized['title'] = self._normalize_text(normalized.get('title', ''))
        normalized['description'] = self._normalize_text(normalized.get('description', ''))

        # Normalize price (integer in CZK)
        price = item.get('price')
        if price:
            # Remove spaces and convert to integer
            if isinstance(price, str):
                price = price.replace(' ', '').replace('\xa0', '')
                try:
                    normalized['price'] = int(price)
                except ValueError:
                    normalized['price'] = None
            else:
                normalized['price'] = int(price)
        else:
            normalized['price'] = None

        # Normalize areas (convert to m² as float)
        for area_field in ['usable_area', 'floor_area', 'land_area']:
            area = item.get(area_field)
            if area:
                try:
                    normalized[area_field] = float(area)
                except (ValueError, TypeError):
                    normalized[area_field] = None
            else:
                normalized[area_field] = None

        # Calculate price per m²
        if normalized.get('price') and normalized.get('usable_area'):
            normalized['price_per_sqm'] = round(
                normalized['price'] / normalized['usable_area'], 2
            )
        else:
            normalized['price_per_sqm'] = None

        # Copy location fields
        for field in ['region', 'district', 'municipality', 'city_part', 'street',
                      'latitude', 'longitude']:
            normalized[field] = item.get(field)

        # Copy property details
        for field in ['building_type', 'condition', 'ownership']:
            normalized[field] = item.get(field)

        # Price note
        normalized['price_note'] = item.get('price_note')

        return normalized

    def _normalize_text(self, text):
        """Normalize text: remove HTML, collapse whitespace, trim, NFKC normalization"""
        if not text:
            return ''

        # Unicode NFKC normalization
        text = unicodedata.normalize('NFKC', text)

        # Remove extra whitespace
        text = ' '.join(text.split())

        # Trim
        text = text.strip()

        return text

    def _get_listing_db_id(self, listing_id):
        """Get database ID for a listing by its Sreality listing_id"""
        self.cursor.execute(
            'SELECT id FROM listings WHERE listing_id = %s',
            (listing_id,)
        )
        result = self.cursor.fetchone()
        return result[0] if result else None

    def _update_last_seen(self, item):
        """Update last_seen_at for unchanged listings"""
        self.cursor.execute(
            'UPDATE listings SET last_seen_at = CURRENT_TIMESTAMP WHERE listing_id = %s',
            (item['listing_id'],)
        )
        self.conn.commit()

    def _insert_listing(self, normalized_item, original_item):
        """Insert new listing into database"""

        # Insert into listings table
        self.cursor.execute("""
            INSERT INTO listings (
                listing_id, category, transaction_type, title, description,
                price, price_note, region, district, municipality, city_part, street,
                latitude, longitude, usable_area, floor_area, land_area, price_per_sqm,
                building_type, condition, ownership, source_url, html_file_path,
                is_active, first_seen_at, last_seen_at, last_modified_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, TRUE, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            ) RETURNING id
        """, (
            normalized_item['listing_id'], normalized_item['category'],
            normalized_item['transaction_type'], normalized_item['title'],
            normalized_item['description'], normalized_item['price'],
            normalized_item.get('price_note'), normalized_item.get('region'),
            normalized_item.get('district'), normalized_item.get('municipality'),
            normalized_item.get('city_part'), normalized_item.get('street'),
            normalized_item.get('latitude'), normalized_item.get('longitude'),
            normalized_item.get('usable_area'), normalized_item.get('floor_area'),
            normalized_item.get('land_area'), normalized_item.get('price_per_sqm'),
            normalized_item.get('building_type'), normalized_item.get('condition'),
            normalized_item.get('ownership'), normalized_item['source_url'],
            normalized_item.get('html_file_path')
        ))

        listing_db_id = self.cursor.fetchone()[0]

        # Insert type-specific data
        self._insert_type_specific_data(listing_db_id, normalized_item, original_item)

        # Insert images
        self._insert_images(listing_db_id, original_item.get('images_data', []))

        # Create first history entry (full state, checkpoint)
        self._create_history_entry(listing_db_id, normalized_item, original_item, is_first=True)

        logger.info(f'Inserted new listing {normalized_item["listing_id"]} with ID {listing_db_id}')

    def _update_listing(self, listing_db_id, normalized_item, original_item):
        """Update existing listing and track changes"""

        # Get current state
        current_state = self._get_current_state(listing_db_id)

        # Compare and find changes
        changes = self._find_changes(current_state, normalized_item, original_item)

        if not changes:
            # No changes, just update last_seen_at
            self.cursor.execute(
                'UPDATE listings SET last_seen_at = CURRENT_TIMESTAMP WHERE id = %s',
                (listing_db_id,)
            )
            return

        # Update listings table
        self.cursor.execute("""
            UPDATE listings SET
                title = %s, description = %s, price = %s, price_note = %s,
                region = %s, district = %s, municipality = %s, city_part = %s, street = %s,
                latitude = %s, longitude = %s, usable_area = %s, floor_area = %s, land_area = %s,
                price_per_sqm = %s, building_type = %s, condition = %s, ownership = %s,
                source_url = %s, html_file_path = %s, last_seen_at = CURRENT_TIMESTAMP,
                last_modified_at = CURRENT_TIMESTAMP
            WHERE id = %s
        """, (
            normalized_item['title'], normalized_item['description'],
            normalized_item['price'], normalized_item.get('price_note'),
            normalized_item.get('region'), normalized_item.get('district'),
            normalized_item.get('municipality'), normalized_item.get('city_part'),
            normalized_item.get('street'), normalized_item.get('latitude'),
            normalized_item.get('longitude'), normalized_item.get('usable_area'),
            normalized_item.get('floor_area'), normalized_item.get('land_area'),
            normalized_item.get('price_per_sqm'), normalized_item.get('building_type'),
            normalized_item.get('condition'), normalized_item.get('ownership'),
            normalized_item['source_url'], normalized_item.get('html_file_path'),
            listing_db_id
        ))

        # Update type-specific data
        self._update_type_specific_data(listing_db_id, normalized_item, original_item)

        # Update images (delete old, insert new)
        self._update_images(listing_db_id, original_item.get('images_data', []))

        # Create history entry
        self._create_history_entry(listing_db_id, changes, original_item, is_first=False)

        logger.info(f'Updated listing {normalized_item["listing_id"]} with {len(changes)} changes')

    def _get_current_state(self, listing_db_id):
        """Get current state of a listing from database"""
        self.cursor.execute("""
            SELECT listing_id, category, transaction_type, title, description,
                   price, price_note, region, district, municipality, city_part, street,
                   latitude, longitude, usable_area, floor_area, land_area, price_per_sqm,
                   building_type, condition, ownership, source_url, html_file_path
            FROM listings WHERE id = %s
        """, (listing_db_id,))

        row = self.cursor.fetchone()
        if not row:
            return {}

        return {
            'listing_id': row[0],
            'category': row[1],
            'transaction_type': row[2],
            'title': row[3],
            'description': row[4],
            'price': row[5],
            'price_note': row[6],
            'region': row[7],
            'district': row[8],
            'municipality': row[9],
            'city_part': row[10],
            'street': row[11],
            'latitude': row[12],
            'longitude': row[13],
            'usable_area': row[14],
            'floor_area': row[15],
            'land_area': row[16],
            'price_per_sqm': row[17],
            'building_type': row[18],
            'condition': row[19],
            'ownership': row[20],
            'source_url': row[21],
            'html_file_path': row[22],
        }

    def _find_changes(self, current_state, new_state, original_item):
        """Find differences between current and new state"""
        changes = {}

        # Compare all fields
        for key in new_state:
            if key in current_state:
                if current_state[key] != new_state[key]:
                    changes[key] = new_state[key]

        return changes

    def _create_history_entry(self, listing_db_id, data, original_item, is_first=False):
        """Create history entry with checkpoint logic"""

        # Get current change number
        self.cursor.execute(
            'SELECT COALESCE(MAX(change_number), 0) FROM listing_history WHERE listing_id = %s',
            (listing_db_id,)
        )
        current_change_number = self.cursor.fetchone()[0]
        new_change_number = current_change_number + 1

        # Determine if this should be a checkpoint (every 100 changes or first entry)
        is_checkpoint = is_first or (new_change_number % 100 == 0)

        # Store as JSONB
        changed_fields = Json(data)

        # Insert history entry
        self.cursor.execute("""
            INSERT INTO listing_history (listing_id, change_number, is_checkpoint, changed_fields)
            VALUES (%s, %s, %s, %s)
        """, (listing_db_id, new_change_number, is_checkpoint, changed_fields))

        logger.debug(
            f'Created history entry #{new_change_number} for listing {listing_db_id} '
            f'(checkpoint: {is_checkpoint})'
        )

    def _insert_type_specific_data(self, listing_db_id, normalized_item, original_item):
        """Insert type-specific data based on category"""
        category = normalized_item['category']
        type_specific = original_item.get('type_specific', {})

        if category == 'byty':
            self._insert_apartment_data(listing_db_id, type_specific)
        elif category == 'domy':
            self._insert_house_data(listing_db_id, type_specific)
        elif category == 'pozemky':
            self._insert_land_data(listing_db_id, type_specific)
        elif category == 'komercni':
            self._insert_commercial_data(listing_db_id, type_specific)
        elif category == 'ostatni':
            self._insert_other_data(listing_db_id, type_specific)

    def _update_type_specific_data(self, listing_db_id, normalized_item, original_item):
        """Update type-specific data based on category"""
        category = normalized_item['category']
        type_specific = original_item.get('type_specific', {})

        if category == 'byty':
            self._update_apartment_data(listing_db_id, type_specific)
        elif category == 'domy':
            self._update_house_data(listing_db_id, type_specific)
        elif category == 'pozemky':
            self._update_land_data(listing_db_id, type_specific)
        elif category == 'komercni':
            self._update_commercial_data(listing_db_id, type_specific)
        elif category == 'ostatni':
            self._update_other_data(listing_db_id, type_specific)

    def _insert_apartment_data(self, listing_db_id, data):
        """Insert apartment-specific data"""
        self.cursor.execute("""
            INSERT INTO apartments (
                listing_id, subtype, disposition, floor, total_floors,
                balcony, terrace, loggia, cellar, parking, garage, elevator,
                heating, gas, water, electricity, sewage, barrier_free,
                energy_class, equipped, furnished
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            ) ON CONFLICT (listing_id) DO NOTHING
        """, (
            listing_db_id, data.get('subtype'), data.get('disposition'),
            data.get('floor'), data.get('total_floors'), data.get('balcony'),
            data.get('terrace'), data.get('loggia'), data.get('cellar'),
            data.get('parking'), data.get('garage'), data.get('elevator'),
            data.get('heating'), data.get('gas'), data.get('water'),
            data.get('electricity'), data.get('sewage'), data.get('barrier_free'),
            data.get('energy_class'), data.get('equipped'), data.get('furnished')
        ))

    def _update_apartment_data(self, listing_db_id, data):
        """Update apartment-specific data"""
        self.cursor.execute("""
            UPDATE apartments SET
                subtype = %s, disposition = %s, floor = %s, total_floors = %s,
                balcony = %s, terrace = %s, loggia = %s, cellar = %s, parking = %s,
                garage = %s, elevator = %s, heating = %s, gas = %s, water = %s,
                electricity = %s, sewage = %s, barrier_free = %s, energy_class = %s,
                equipped = %s, furnished = %s
            WHERE listing_id = %s
        """, (
            data.get('subtype'), data.get('disposition'), data.get('floor'),
            data.get('total_floors'), data.get('balcony'), data.get('terrace'),
            data.get('loggia'), data.get('cellar'), data.get('parking'),
            data.get('garage'), data.get('elevator'), data.get('heating'),
            data.get('gas'), data.get('water'), data.get('electricity'),
            data.get('sewage'), data.get('barrier_free'), data.get('energy_class'),
            data.get('equipped'), data.get('furnished'), listing_db_id
        ))

    def _insert_house_data(self, listing_db_id, data):
        """Insert house-specific data"""
        self.cursor.execute("""
            INSERT INTO houses (
                listing_id, subtype, total_floors, rooms, bedrooms, bathrooms,
                heating, gas, water, electricity, sewage, garage, parking,
                cellar, terrace, balcony, pool, garden, barrier_free,
                energy_class, construction_year, reconstruction_year
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            ) ON CONFLICT (listing_id) DO NOTHING
        """, (
            listing_db_id, data.get('subtype'), data.get('total_floors'),
            data.get('rooms'), data.get('bedrooms'), data.get('bathrooms'),
            data.get('heating'), data.get('gas'), data.get('water'),
            data.get('electricity'), data.get('sewage'), data.get('garage'),
            data.get('parking'), data.get('cellar'), data.get('terrace'),
            data.get('balcony'), data.get('pool'), data.get('garden'),
            data.get('barrier_free'), data.get('energy_class'),
            data.get('construction_year'), data.get('reconstruction_year')
        ))

    def _update_house_data(self, listing_db_id, data):
        """Update house-specific data"""
        self.cursor.execute("""
            UPDATE houses SET
                subtype = %s, total_floors = %s, rooms = %s, bedrooms = %s,
                bathrooms = %s, heating = %s, gas = %s, water = %s, electricity = %s,
                sewage = %s, garage = %s, parking = %s, cellar = %s, terrace = %s,
                balcony = %s, pool = %s, garden = %s, barrier_free = %s,
                energy_class = %s, construction_year = %s, reconstruction_year = %s
            WHERE listing_id = %s
        """, (
            data.get('subtype'), data.get('total_floors'), data.get('rooms'),
            data.get('bedrooms'), data.get('bathrooms'), data.get('heating'),
            data.get('gas'), data.get('water'), data.get('electricity'),
            data.get('sewage'), data.get('garage'), data.get('parking'),
            data.get('cellar'), data.get('terrace'), data.get('balcony'),
            data.get('pool'), data.get('garden'), data.get('barrier_free'),
            data.get('energy_class'), data.get('construction_year'),
            data.get('reconstruction_year'), listing_db_id
        ))

    def _insert_land_data(self, listing_db_id, data):
        """Insert land-specific data"""
        self.cursor.execute("""
            INSERT INTO land (
                listing_id, subtype, electricity, gas, water, sewage,
                road_access, development_potential, zoning
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s
            ) ON CONFLICT (listing_id) DO NOTHING
        """, (
            listing_db_id, data.get('subtype'), data.get('electricity'),
            data.get('gas'), data.get('water'), data.get('sewage'),
            data.get('road_access'), data.get('development_potential'),
            data.get('zoning')
        ))

    def _update_land_data(self, listing_db_id, data):
        """Update land-specific data"""
        self.cursor.execute("""
            UPDATE land SET
                subtype = %s, electricity = %s, gas = %s, water = %s, sewage = %s,
                road_access = %s, development_potential = %s, zoning = %s
            WHERE listing_id = %s
        """, (
            data.get('subtype'), data.get('electricity'), data.get('gas'),
            data.get('water'), data.get('sewage'), data.get('road_access'),
            data.get('development_potential'), data.get('zoning'), listing_db_id
        ))

    def _insert_commercial_data(self, listing_db_id, data):
        """Insert commercial-specific data"""
        self.cursor.execute("""
            INSERT INTO commercial (
                listing_id, subtype, office_space, production_space, storage_space,
                sales_space, heating, gas, water, electricity, sewage,
                parking_spaces, loading_ramp, elevator, barrier_free, energy_class
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            ) ON CONFLICT (listing_id) DO NOTHING
        """, (
            listing_db_id, data.get('subtype'), data.get('office_space'),
            data.get('production_space'), data.get('storage_space'),
            data.get('sales_space'), data.get('heating'), data.get('gas'),
            data.get('water'), data.get('electricity'), data.get('sewage'),
            data.get('parking_spaces'), data.get('loading_ramp'),
            data.get('elevator'), data.get('barrier_free'), data.get('energy_class')
        ))

    def _update_commercial_data(self, listing_db_id, data):
        """Update commercial-specific data"""
        self.cursor.execute("""
            UPDATE commercial SET
                subtype = %s, office_space = %s, production_space = %s,
                storage_space = %s, sales_space = %s, heating = %s, gas = %s,
                water = %s, electricity = %s, sewage = %s, parking_spaces = %s,
                loading_ramp = %s, elevator = %s, barrier_free = %s, energy_class = %s
            WHERE listing_id = %s
        """, (
            data.get('subtype'), data.get('office_space'), data.get('production_space'),
            data.get('storage_space'), data.get('sales_space'), data.get('heating'),
            data.get('gas'), data.get('water'), data.get('electricity'),
            data.get('sewage'), data.get('parking_spaces'), data.get('loading_ramp'),
            data.get('elevator'), data.get('barrier_free'), data.get('energy_class'),
            listing_db_id
        ))

    def _insert_other_data(self, listing_db_id, data):
        """Insert other property-specific data"""
        self.cursor.execute("""
            INSERT INTO other_properties (
                listing_id, subtype, has_electricity, has_water
            ) VALUES (
                %s, %s, %s, %s
            ) ON CONFLICT (listing_id) DO NOTHING
        """, (
            listing_db_id, data.get('subtype'),
            data.get('has_electricity'), data.get('has_water')
        ))

    def _update_other_data(self, listing_db_id, data):
        """Update other property-specific data"""
        self.cursor.execute("""
            UPDATE other_properties SET
                subtype = %s, has_electricity = %s, has_water = %s
            WHERE listing_id = %s
        """, (
            data.get('subtype'), data.get('has_electricity'),
            data.get('has_water'), listing_db_id
        ))

    def _insert_images(self, listing_db_id, images_data):
        """Insert images for a listing"""
        for image in images_data:
            self.cursor.execute("""
                INSERT INTO images (
                    listing_id, image_url, image_data, image_order, is_primary, downloaded_at
                ) VALUES (
                    %s, %s, %s, %s, %s, CURRENT_TIMESTAMP
                )
            """, (
                listing_db_id, image['url'], psycopg2.Binary(image['data']),
                image['order'], image['is_primary']
            ))

    def _update_images(self, listing_db_id, images_data):
        """Update images for a listing (delete old, insert new)"""
        # Delete old images
        self.cursor.execute('DELETE FROM images WHERE listing_id = %s', (listing_db_id,))

        # Insert new images
        self._insert_images(listing_db_id, images_data)
