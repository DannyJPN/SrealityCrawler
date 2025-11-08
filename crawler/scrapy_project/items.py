"""
Scrapy items for SrealityCrawler
"""

import scrapy


class ListingItem(scrapy.Item):
    """Base listing item with common fields"""

    # Unique identifier
    listing_id = scrapy.Field()

    # Basic information
    category = scrapy.Field()  # byty, domy, pozemky, komercni, ostatni
    transaction_type = scrapy.Field()  # prodej, pronajem, drazba
    title = scrapy.Field()
    description = scrapy.Field()

    # Pricing
    price = scrapy.Field()  # Integer in CZK
    price_note = scrapy.Field()

    # Location
    region = scrapy.Field()
    district = scrapy.Field()
    municipality = scrapy.Field()
    city_part = scrapy.Field()
    street = scrapy.Field()
    latitude = scrapy.Field()
    longitude = scrapy.Field()

    # Areas (in m²)
    usable_area = scrapy.Field()
    floor_area = scrapy.Field()
    land_area = scrapy.Field()

    # Calculated fields
    price_per_sqm = scrapy.Field()

    # Property details
    building_type = scrapy.Field()
    condition = scrapy.Field()
    ownership = scrapy.Field()

    # Source
    source_url = scrapy.Field()
    html_file_path = scrapy.Field()

    # Raw HTML content
    html_content = scrapy.Field()

    # Images
    image_urls = scrapy.Field()
    images_data = scrapy.Field()

    # Type-specific data (stored as dict)
    type_specific = scrapy.Field()

    # Metadata
    scraped_at = scrapy.Field()


class ApartmentData(scrapy.Item):
    """Apartment-specific fields"""
    subtype = scrapy.Field()
    disposition = scrapy.Field()  # 1+kk, 2+1, etc.
    floor = scrapy.Field()
    total_floors = scrapy.Field()
    balcony = scrapy.Field()
    terrace = scrapy.Field()
    loggia = scrapy.Field()
    cellar = scrapy.Field()
    parking = scrapy.Field()
    garage = scrapy.Field()
    elevator = scrapy.Field()
    heating = scrapy.Field()
    gas = scrapy.Field()
    water = scrapy.Field()
    electricity = scrapy.Field()
    sewage = scrapy.Field()
    barrier_free = scrapy.Field()
    energy_class = scrapy.Field()
    equipped = scrapy.Field()
    furnished = scrapy.Field()


class HouseData(scrapy.Item):
    """House-specific fields"""
    subtype = scrapy.Field()
    total_floors = scrapy.Field()
    rooms = scrapy.Field()
    bedrooms = scrapy.Field()
    bathrooms = scrapy.Field()
    heating = scrapy.Field()
    gas = scrapy.Field()
    water = scrapy.Field()
    electricity = scrapy.Field()
    sewage = scrapy.Field()
    garage = scrapy.Field()
    parking = scrapy.Field()
    cellar = scrapy.Field()
    terrace = scrapy.Field()
    balcony = scrapy.Field()
    pool = scrapy.Field()
    garden = scrapy.Field()
    barrier_free = scrapy.Field()
    energy_class = scrapy.Field()
    construction_year = scrapy.Field()
    reconstruction_year = scrapy.Field()


class LandData(scrapy.Item):
    """Land-specific fields"""
    subtype = scrapy.Field()
    electricity = scrapy.Field()
    gas = scrapy.Field()
    water = scrapy.Field()
    sewage = scrapy.Field()
    road_access = scrapy.Field()
    development_potential = scrapy.Field()
    zoning = scrapy.Field()


class CommercialData(scrapy.Item):
    """Commercial property-specific fields"""
    subtype = scrapy.Field()
    office_space = scrapy.Field()
    production_space = scrapy.Field()
    storage_space = scrapy.Field()
    sales_space = scrapy.Field()
    heating = scrapy.Field()
    gas = scrapy.Field()
    water = scrapy.Field()
    electricity = scrapy.Field()
    sewage = scrapy.Field()
    parking_spaces = scrapy.Field()
    loading_ramp = scrapy.Field()
    elevator = scrapy.Field()
    barrier_free = scrapy.Field()
    energy_class = scrapy.Field()


class OtherPropertyData(scrapy.Item):
    """Other property-specific fields"""
    subtype = scrapy.Field()
    has_electricity = scrapy.Field()
    has_water = scrapy.Field()
