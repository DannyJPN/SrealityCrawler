"""
Main spider for scraping sreality.cz listings
"""

import re
import logging
from urllib.parse import urljoin, urlparse, parse_qs
from datetime import datetime

import scrapy
from scrapy.http import Request
from bs4 import BeautifulSoup

from scrapy_project.items import ListingItem


logger = logging.getLogger(__name__)


class SrealitySpider(scrapy.Spider):
    name = 'sreality'
    allowed_domains = ['sreality.cz']
    start_urls = ['https://www.sreality.cz/']

    # Category and transaction type mappings
    CATEGORIES = {
        'byty': 'byty',
        'domy': 'domy',
        'pozemky': 'pozemky',
        'komercni': 'komercni',
        'ostatni': 'ostatni',
    }

    TRANSACTION_TYPES = {
        'prodej': 'prodej',
        'pronajem': 'pronajem',
        'drazba': 'drazba',
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.seen_urls = set()
        self.listing_urls = set()
        self.total_listings = 0
        self.processed_listings = 0

    def start_requests(self):
        """Start by fetching the main page and sitemap"""
        # Fetch main page to derive categories
        yield Request(
            'https://www.sreality.cz/',
            callback=self.parse_main_page,
            dont_filter=True
        )

        # Fetch sitemap
        yield Request(
            'https://www.sreality.cz/sitemap.xml',
            callback=self.parse_sitemap,
            dont_filter=True
        )

    def parse_main_page(self, response):
        """Parse main page to derive all category×transaction combinations"""
        logger.info('Parsing main page to derive categories')

        # Generate all combinations of categories and transaction types
        # Excluding "projekty" as per specification
        for category_slug, category_name in self.CATEGORIES.items():
            for transaction_slug, transaction_name in self.TRANSACTION_TYPES.items():
                # Build listing page URL
                # Format: /hledani/{transaction}/{category}
                listing_url = f'https://www.sreality.cz/hledani/{transaction_slug}/{category_slug}'

                logger.info(f'Queueing category page: {listing_url}')

                yield Request(
                    listing_url,
                    callback=self.parse_listing_page,
                    meta={
                        'category': category_name,
                        'transaction_type': transaction_name,
                        'page': 1
                    },
                    dont_filter=True
                )

    def parse_sitemap(self, response):
        """Parse sitemap.xml and extract listing URLs"""
        logger.info('Parsing sitemap')

        # Parse XML
        soup = BeautifulSoup(response.text, 'lxml-xml')

        # Check if this is a sitemap index or a sitemap
        sitemap_urls = soup.find_all('sitemap')
        if sitemap_urls:
            # This is a sitemap index, fetch individual sitemaps
            for sitemap in sitemap_urls:
                loc = sitemap.find('loc')
                if loc:
                    sitemap_url = loc.text.strip()
                    logger.info(f'Found sitemap: {sitemap_url}')
                    yield Request(
                        sitemap_url,
                        callback=self.parse_sitemap,
                        dont_filter=True
                    )
        else:
            # This is a regular sitemap with URLs
            urls = soup.find_all('url')
            for url in urls:
                loc = url.find('loc')
                if loc:
                    page_url = loc.text.strip()

                    # Filter for detail pages (format: /detail/{category}/{id})
                    if '/detail/' in page_url:
                        # Extract listing ID from URL
                        listing_id = self._extract_listing_id(page_url)
                        if listing_id and page_url not in self.seen_urls:
                            self.seen_urls.add(page_url)
                            self.listing_urls.add(page_url)

                            logger.debug(f'Found listing from sitemap: {listing_id}')

    def parse_listing_page(self, response):
        """Parse a category listing page and paginate"""
        category = response.meta['category']
        transaction_type = response.meta['transaction_type']
        page = response.meta['page']

        logger.info(f'Parsing listing page for {category}/{transaction_type} (page {page})')

        # Extract listing URLs from this page
        # Sreality uses a structure like: div.property with links
        # We need to find all detail page links

        # Try multiple selectors as Sreality structure may vary
        detail_links = response.css('a.title::attr(href)').getall()
        if not detail_links:
            detail_links = response.xpath('//a[contains(@href, "/detail/")]/@href').getall()

        for link in detail_links:
            full_url = urljoin(response.url, link)

            if full_url not in self.seen_urls:
                self.seen_urls.add(full_url)
                self.listing_urls.add(full_url)

                listing_id = self._extract_listing_id(full_url)
                logger.debug(f'Found listing from category page: {listing_id}')

        # Check for next page
        # Sreality uses pagination like: ?strana=2
        next_page_links = response.css('a.paging-next::attr(href)').getall()
        if not next_page_links:
            next_page_links = response.xpath('//a[contains(@class, "paging") and contains(., "další")]/@href').getall()

        if next_page_links:
            next_page_url = urljoin(response.url, next_page_links[0])
            logger.info(f'Found next page: {next_page_url}')

            yield Request(
                next_page_url,
                callback=self.parse_listing_page,
                meta={
                    'category': category,
                    'transaction_type': transaction_type,
                    'page': page + 1
                }
            )
        else:
            logger.info(f'No more pages for {category}/{transaction_type}')

            # Now that we have all URLs from this category, start fetching details
            self._start_detail_fetching()

    def _start_detail_fetching(self):
        """Start fetching detail pages for all collected listing URLs"""
        # This is called after pagination is complete
        # We'll fetch detail pages in the spider's idle callback

        if hasattr(self, '_detail_fetching_started'):
            return

        self._detail_fetching_started = True
        self.total_listings = len(self.listing_urls)

        logger.info(f'Starting detail fetching for {self.total_listings} listings')

        for listing_url in self.listing_urls:
            yield Request(
                listing_url,
                callback=self.parse_detail,
                errback=self.handle_detail_error,
                dont_filter=True
            )

    def parse_detail(self, response):
        """Parse a listing detail page"""

        # Check if this is a 304 Not Modified response
        if response.meta.get('not_modified'):
            # HTML unchanged, just update last_seen_at
            listing_id = self._extract_listing_id(response.url)
            logger.debug(f'Listing {listing_id} unchanged (304 Not Modified)')

            item = ListingItem()
            item['listing_id'] = listing_id
            item['source_url'] = response.url
            item['html_unchanged'] = True

            self.processed_listings += 1
            self._update_progress()

            return item

        listing_id = self._extract_listing_id(response.url)
        logger.info(f'Parsing detail page for listing {listing_id}')

        # Create item
        item = ListingItem()

        # Basic fields
        item['listing_id'] = listing_id
        item['source_url'] = response.url
        item['html_content'] = response.text
        item['scraped_at'] = datetime.now().isoformat()

        # Extract category and transaction type from URL
        # URL format: /detail/{transaction}/{category}/{subtype}/{id}
        url_parts = urlparse(response.url).path.split('/')
        if len(url_parts) >= 4:
            item['transaction_type'] = self._normalize_transaction_type(url_parts[2])
            item['category'] = self._normalize_category(url_parts[3])
        else:
            # Fallback
            item['transaction_type'] = 'prodej'
            item['category'] = 'ostatni'

        # Parse detail page content
        soup = BeautifulSoup(response.text, 'html.parser')

        # Extract title
        title_elem = soup.find('h1', class_='name')
        if not title_elem:
            title_elem = soup.select_one('.property-title h1')
        if not title_elem:
            title_elem = soup.select_one('h1')

        item['title'] = title_elem.get_text(strip=True) if title_elem else ''

        # Extract price
        price_elem = soup.find(class_='norm-price')
        if not price_elem:
            price_elem = soup.select_one('.price')

        if price_elem:
            price_text = price_elem.get_text(strip=True)
            # Extract number from price (remove currency, spaces, etc.)
            price_match = re.search(r'([\d\s\.]+)', price_text.replace('\xa0', ' '))
            if price_match:
                price_str = price_match.group(1).replace(' ', '').replace('.', '')
                try:
                    item['price'] = int(price_str)
                except ValueError:
                    item['price'] = None
            else:
                item['price'] = None
        else:
            item['price'] = None

        # Extract description
        desc_elem = soup.find(class_='description')
        if not desc_elem:
            desc_elem = soup.select_one('.text-content')

        item['description'] = desc_elem.get_text(strip=True) if desc_elem else ''

        # Extract parameters from table
        params = {}
        param_tables = soup.find_all('table', class_='params')
        if not param_tables:
            param_tables = soup.select('.param-table')

        for table in param_tables:
            rows = table.find_all('tr')
            for row in rows:
                cols = row.find_all('td')
                if len(cols) >= 2:
                    key = cols[0].get_text(strip=True).lower()
                    value = cols[1].get_text(strip=True)
                    params[key] = value

        # Extract location
        location = self._extract_location(soup, params)
        item.update(location)

        # Extract areas
        areas = self._extract_areas(params)
        item.update(areas)

        # Calculate price per m²
        if item.get('price') and item.get('usable_area'):
            item['price_per_sqm'] = round(item['price'] / item['usable_area'], 2)

        # Extract property details
        item['building_type'] = params.get('stavba', params.get('typ stavby'))
        item['condition'] = params.get('stav objektu', params.get('stav'))
        item['ownership'] = params.get('vlastnictví', params.get('ownership'))

        # Extract images
        image_urls = []
        img_elements = soup.select('img[src*="img.sreality"]')
        if not img_elements:
            img_elements = soup.select('.gallery img')

        for img in img_elements:
            src = img.get('src') or img.get('data-src')
            if src and 'img.sreality' in src:
                # Get full resolution image URL
                full_res_url = re.sub(r'/\d+x\d+/', '/0x0/', src)
                if full_res_url not in image_urls:
                    image_urls.append(full_res_url)

        item['image_urls'] = image_urls

        # Extract type-specific data
        item['type_specific'] = self._extract_type_specific_data(
            item['category'],
            params,
            soup
        )

        self.processed_listings += 1
        self._update_progress()

        yield item

    def handle_detail_error(self, failure):
        """Handle errors when fetching detail pages"""
        logger.error(f'Error fetching detail page: {failure.request.url} - {failure.value}')

        # Still count this as processed to update progress
        self.processed_listings += 1
        self._update_progress()

    def _extract_listing_id(self, url):
        """Extract listing ID from URL"""
        # URL format: /detail/{transaction}/{category}/{id} or similar
        match = re.search(r'/detail/[^/]+/[^/]+/[^/]+/(\d+)', url)
        if match:
            return match.group(1)

        # Try simpler pattern
        match = re.search(r'/(\d{7,})', url)
        if match:
            return match.group(1)

        # Fallback: use URL hash
        return hashlib.md5(url.encode()).hexdigest()[:12]

    def _normalize_category(self, category_slug):
        """Normalize category name from URL slug"""
        mapping = {
            'byty': 'byty',
            'domy': 'domy',
            'pozemky': 'pozemky',
            'komercni': 'komercni',
            'komerční': 'komercni',
            'ostatni': 'ostatni',
            'ostatní': 'ostatni',
        }
        return mapping.get(category_slug.lower(), 'ostatni')

    def _normalize_transaction_type(self, transaction_slug):
        """Normalize transaction type from URL slug"""
        mapping = {
            'prodej': 'prodej',
            'pronajem': 'pronajem',
            'pronájem': 'pronajem',
            'drazba': 'drazba',
            'draž ba': 'drazba',
        }
        return mapping.get(transaction_slug.lower(), 'prodej')

    def _extract_location(self, soup, params):
        """Extract location information"""
        location = {}

        # Try to extract from breadcrumbs or location section
        breadcrumbs = soup.select('.breadcrumbs a, .breadcrumb a')
        if breadcrumbs:
            # Usually: Home > Category > Region > District > Municipality
            if len(breadcrumbs) > 2:
                location['region'] = breadcrumbs[2].get_text(strip=True)
            if len(breadcrumbs) > 3:
                location['district'] = breadcrumbs[3].get_text(strip=True)
            if len(breadcrumbs) > 4:
                location['municipality'] = breadcrumbs[4].get_text(strip=True)

        # Try to extract from params
        location['municipality'] = params.get('lokalita', params.get('obec', location.get('municipality')))

        # Extract from location meta
        loc_elem = soup.find(class_='location')
        if loc_elem:
            loc_text = loc_elem.get_text(strip=True)
            parts = [p.strip() for p in loc_text.split(',')]
            if parts:
                location['municipality'] = parts[0]
            if len(parts) > 1:
                location['city_part'] = parts[1]

        # Extract coordinates if available
        # Look for map data or coordinates in script tags
        scripts = soup.find_all('script')
        for script in scripts:
            script_text = script.get_text()
            # Look for latitude/longitude patterns
            lat_match = re.search(r'latitude["\s:]+([0-9.]+)', script_text)
            lon_match = re.search(r'longitude["\s:]+([0-9.]+)', script_text)

            if lat_match:
                location['latitude'] = float(lat_match.group(1))
            if lon_match:
                location['longitude'] = float(lon_match.group(1))

        return location

    def _extract_areas(self, params):
        """Extract area measurements from parameters"""
        areas = {}

        # Common keys for areas (in Czech)
        area_mappings = {
            'užitná plocha': 'usable_area',
            'uzitná plocha': 'usable_area',
            'plocha': 'usable_area',
            'podlahová plocha': 'floor_area',
            'podlahova plocha': 'floor_area',
            'plocha parcely': 'land_area',
            'plocha pozemku': 'land_area',
            'výměra': 'land_area',
            'vymera': 'land_area',
        }

        for param_key, param_value in params.items():
            normalized_key = param_key.lower().strip()

            if normalized_key in area_mappings:
                area_type = area_mappings[normalized_key]

                # Extract number from value (format: "120 m²" or "120m2")
                area_match = re.search(r'([0-9\s,.]+)', param_value)
                if area_match:
                    area_str = area_match.group(1).replace(' ', '').replace(',', '.')
                    try:
                        areas[area_type] = float(area_str)
                    except ValueError:
                        pass

        return areas

    def _extract_type_specific_data(self, category, params, soup):
        """Extract type-specific data based on category"""
        data = {}

        if category == 'byty':
            data = self._extract_apartment_data(params, soup)
        elif category == 'domy':
            data = self._extract_house_data(params, soup)
        elif category == 'pozemky':
            data = self._extract_land_data(params, soup)
        elif category == 'komercni':
            data = self._extract_commercial_data(params, soup)
        elif category == 'ostatni':
            data = self._extract_other_data(params, soup)

        return data

    def _extract_apartment_data(self, params, soup):
        """Extract apartment-specific data"""
        data = {}

        # Disposition (1+kk, 2+1, etc.)
        data['disposition'] = params.get('dispozice', params.get('layout'))

        # Floor
        floor_str = params.get('podlaží', params.get('floor'))
        if floor_str:
            floor_match = re.search(r'(\d+)', floor_str)
            if floor_match:
                data['floor'] = int(floor_match.group(1))

        # Boolean features
        data['balcony'] = self._has_feature(params, ['balkon', 'balcony'])
        data['terrace'] = self._has_feature(params, ['terasa', 'terrace'])
        data['loggia'] = self._has_feature(params, ['lodžie', 'loggia'])
        data['cellar'] = self._has_feature(params, ['sklep', 'cellar'])
        data['parking'] = self._has_feature(params, ['parkování', 'parking'])
        data['garage'] = self._has_feature(params, ['garáž', 'garage'])
        data['elevator'] = self._has_feature(params, ['výtah', 'vytah', 'elevator'])

        # Utilities
        data['heating'] = params.get('topení', params.get('heating'))
        data['gas'] = self._has_feature(params, ['plyn', 'gas'])
        data['electricity'] = self._has_feature(params, ['elektřina', 'elektrina', 'electricity'])

        # Equipment
        data['equipped'] = self._has_feature(params, ['vybavení', 'vybaveno', 'equipped'])
        data['furnished'] = self._has_feature(params, ['zařízeno', 'zarizeno', 'furnished'])

        return data

    def _extract_house_data(self, params, soup):
        """Extract house-specific data"""
        data = {}

        # Rooms
        rooms_str = params.get('počet pokojů', params.get('pocet pokoju', params.get('rooms')))
        if rooms_str:
            rooms_match = re.search(r'(\d+)', rooms_str)
            if rooms_match:
                data['rooms'] = int(rooms_match.group(1))

        # Boolean features
        data['garage'] = self._has_feature(params, ['garáž', 'garage'])
        data['parking'] = self._has_feature(params, ['parkování', 'parking'])
        data['cellar'] = self._has_feature(params, ['sklep', 'cellar'])
        data['terrace'] = self._has_feature(params, ['terasa', 'terrace'])
        data['balcony'] = self._has_feature(params, ['balkon', 'balcony'])
        data['pool'] = self._has_feature(params, ['bazén', 'bazen', 'pool'])
        data['garden'] = self._has_feature(params, ['zahrada', 'garden'])

        # Utilities
        data['heating'] = params.get('topení', params.get('heating'))
        data['gas'] = self._has_feature(params, ['plyn', 'gas'])
        data['electricity'] = self._has_feature(params, ['elektřina', 'elektrina', 'electricity'])

        # Construction year
        year_str = params.get('rok výstavby', params.get('rok vystavby', params.get('construction year')))
        if year_str:
            year_match = re.search(r'(\d{4})', year_str)
            if year_match:
                data['construction_year'] = int(year_match.group(1))

        return data

    def _extract_land_data(self, params, soup):
        """Extract land-specific data"""
        data = {}

        # Boolean features
        data['electricity'] = self._has_feature(params, ['elektřina', 'elektrina', 'electricity'])
        data['gas'] = self._has_feature(params, ['plyn', 'gas'])
        data['water'] = self._has_feature(params, ['voda', 'water'])
        data['sewage'] = self._has_feature(params, ['kanalizace', 'sewage'])
        data['road_access'] = self._has_feature(params, ['přístup', 'pristup', 'road access'])

        return data

    def _extract_commercial_data(self, params, soup):
        """Extract commercial property-specific data"""
        data = {}

        # Parking spaces
        parking_str = params.get('parkovací místa', params.get('parkovaci mista', params.get('parking')))
        if parking_str:
            parking_match = re.search(r'(\d+)', parking_str)
            if parking_match:
                data['parking_spaces'] = int(parking_match.group(1))

        # Boolean features
        data['loading_ramp'] = self._has_feature(params, ['rampa', 'loading ramp'])
        data['elevator'] = self._has_feature(params, ['výtah', 'vytah', 'elevator'])

        # Utilities
        data['heating'] = params.get('topení', params.get('heating'))
        data['gas'] = self._has_feature(params, ['plyn', 'gas'])
        data['electricity'] = self._has_feature(params, ['elektřina', 'elektrina', 'electricity'])

        return data

    def _extract_other_data(self, params, soup):
        """Extract other property-specific data"""
        data = {}

        data['has_electricity'] = self._has_feature(params, ['elektřina', 'elektrina', 'electricity'])
        data['has_water'] = self._has_feature(params, ['voda', 'water'])

        return data

    def _has_feature(self, params, keywords):
        """Check if a feature is present in params"""
        for key, value in params.items():
            key_lower = key.lower()
            value_lower = value.lower() if isinstance(value, str) else ''

            for keyword in keywords:
                if keyword in key_lower or keyword in value_lower:
                    # Check for "ano" (yes) in value
                    if 'ano' in value_lower or 'yes' in value_lower:
                        return True
                    # If keyword is in key, assume it's present
                    if keyword in key_lower:
                        return True

        return False

    def _update_progress(self):
        """Update crawl progress (for /progress endpoint)"""
        if self.total_listings > 0:
            progress_percent = (self.processed_listings / self.total_listings) * 100
            logger.info(f'Progress: {progress_percent:.1f}% ({self.processed_listings}/{self.total_listings})')

            # Store progress in a file that the HTTP server can read
            try:
                with open('/tmp/crawler_progress.txt', 'w') as f:
                    f.write(str(int(progress_percent)))
            except Exception as e:
                logger.error(f'Failed to write progress: {e}')

    def closed(self, reason):
        """Called when spider is closed"""
        logger.info(f'Spider closed: {reason}')
        logger.info(f'Total listings processed: {self.processed_listings}/{self.total_listings}')

        # Reset progress
        try:
            with open('/tmp/crawler_progress.txt', 'w') as f:
                f.write('0')
        except Exception:
            pass


import hashlib
