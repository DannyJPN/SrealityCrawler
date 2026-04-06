    """
Flask application for SrealityCrawler web UI
Read-only interface for browsing and filtering listings
"""

import os
import logging
from datetime import datetime
from typing import Optional, Dict, List

from flask import Flask, render_template, request, jsonify
import psycopg2
from psycopg2.extras import RealDictCursor
import requests


# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


app = Flask(__name__)


# Database configuration
DB_CONFIG = {
    'host': os.getenv('POSTGRES_HOST', 'db'),
    'port': os.getenv('POSTGRES_PORT', '5432'),
    'database': os.getenv('POSTGRES_DB', 'reality_history'),
    'user': os.getenv('POSTGRES_USER', 'sreality'),
    'password': os.getenv('POSTGRES_PASSWORD', 'sreality'),
}


def get_db_connection():
    """Get database connection"""
    return psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)


@app.route('/healthz')
def healthz():
    """Health check endpoint"""
    try:
        # Check database connectivity
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT 1')
        cursor.close()
        conn.close()
        return jsonify({"status": "healthy"}), 200
    except Exception as e:
        logger.error(f'Health check failed: {str(e)}')
        return jsonify({"status": "unhealthy", "error": str(e)}), 500


@app.route('/')
def index():
    """Main listing page with pagination, filtering, and sorting"""

    # Get pagination parameters
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 100, type=int)

    # Validate per_page options
    if per_page not in [20, 50, 100, 200, 500]:
        per_page = 100

    # Get filter parameters
    filters = {
        'category': request.args.get('category'),
        'transaction_type': request.args.get('transaction_type'),
        'municipality': request.args.get('municipality'),
        'price_min': request.args.get('price_min', type=int),
        'price_max': request.args.get('price_max', type=int),
        'usable_area_min': request.args.get('usable_area_min', type=float),
        'usable_area_max': request.args.get('usable_area_max', type=float),
        'is_active': request.args.get('is_active', 'true').lower() == 'true',
    }

    # Get sorting parameters (default: alphabetical by title)
    sort_by = request.args.get('sort_by', 'title')
    sort_order = request.args.get('sort_order', 'asc')

    # Validate sort order
    if sort_order not in ['asc', 'desc']:
        sort_order = 'asc'

    # Build SQL query
    query = """
        SELECT
            l.id,
            l.listing_id,
            l.title,
            l.category,
            l.transaction_type,
            l.price,
            l.municipality,
            l.usable_area,
            l.price_per_sqm,
            l.is_active,
            l.first_seen_at,
            l.last_seen_at
        FROM listings l
        WHERE 1=1
    """

    params = []

    # Apply filters
    if filters['category']:
        query += " AND l.category = %s"
        params.append(filters['category'])

    if filters['transaction_type']:
        query += " AND l.transaction_type = %s"
        params.append(filters['transaction_type'])

    if filters['municipality']:
        query += " AND l.municipality ILIKE %s"
        params.append(f"%{filters['municipality']}%")

    if filters['price_min'] is not None:
        query += " AND l.price >= %s"
        params.append(filters['price_min'])

    if filters['price_max'] is not None:
        query += " AND l.price <= %s"
        params.append(filters['price_max'])

    if filters['usable_area_min'] is not None:
        query += " AND l.usable_area >= %s"
        params.append(filters['usable_area_min'])

    if filters['usable_area_max'] is not None:
        query += " AND l.usable_area <= %s"
        params.append(filters['usable_area_max'])

    query += " AND l.is_active = %s"
    params.append(filters['is_active'])

    # Count total results
    count_query = f"SELECT COUNT(*) as total FROM ({query}) AS filtered"

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Get total count
        cursor.execute(count_query, params)
        total = cursor.fetchone()['total']

        # Add sorting
        # Validate sort_by against allowed columns
        allowed_sort_columns = [
            'title', 'price', 'category', 'transaction_type', 'municipality',
            'usable_area', 'price_per_sqm', 'first_seen_at', 'last_seen_at'
        ]

        if sort_by in allowed_sort_columns:
            # Handle NULL values in sorting (Excel-like behavior)
            query += f" ORDER BY l.{sort_by} {sort_order} NULLS LAST"
        else:
            # Default to title
            query += " ORDER BY l.title ASC"

        # Add pagination
        offset = (page - 1) * per_page
        query += " LIMIT %s OFFSET %s"
        params.extend([per_page, offset])

        # Execute main query
        cursor.execute(query, params)
        listings = cursor.fetchall()

        # Get distinct values for filters
        cursor.execute("SELECT DISTINCT category FROM listings WHERE category IS NOT NULL ORDER BY category")
        categories = [row['category'] for row in cursor.fetchall()]

        cursor.execute("SELECT DISTINCT transaction_type FROM listings WHERE transaction_type IS NOT NULL ORDER BY transaction_type")
        transaction_types = [row['transaction_type'] for row in cursor.fetchall()]

        cursor.execute("SELECT DISTINCT municipality FROM listings WHERE municipality IS NOT NULL ORDER BY municipality LIMIT 1000")
        municipalities = [row['municipality'] for row in cursor.fetchall()]

        cursor.close()
        conn.close()

        # Calculate pagination
        total_pages = (total + per_page - 1) // per_page

        return render_template(
            'index.html',
            listings=listings,
            page=page,
            per_page=per_page,
            total=total,
            total_pages=total_pages,
            filters=filters,
            sort_by=sort_by,
            sort_order=sort_order,
            categories=categories,
            transaction_types=transaction_types,
            municipalities=municipalities,
        )

    except Exception as e:
        logger.error(f'Error loading listings: {str(e)}', exc_info=True)
        return render_template('error.html', error=str(e)), 500


@app.route('/listing/<listing_id>')
def listing_detail(listing_id):
    """Listing detail page with full history"""

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Get listing details
        cursor.execute("""
            SELECT * FROM listings WHERE listing_id = %s
        """, (listing_id,))

        listing = cursor.fetchone()

        if not listing:
            cursor.close()
            conn.close()
            return render_template('error.html', error=f'Listing {listing_id} not found'), 404

        # Get type-specific data based on category
        type_specific = None
        category = listing['category']

        if category == 'byty':
            cursor.execute("SELECT * FROM apartments WHERE listing_id = %s", (listing['id'],))
            type_specific = cursor.fetchone()
        elif category == 'domy':
            cursor.execute("SELECT * FROM houses WHERE listing_id = %s", (listing['id'],))
            type_specific = cursor.fetchone()
        elif category == 'pozemky':
            cursor.execute("SELECT * FROM land WHERE listing_id = %s", (listing['id'],))
            type_specific = cursor.fetchone()
        elif category == 'komercni':
            cursor.execute("SELECT * FROM commercial WHERE listing_id = %s", (listing['id'],))
            type_specific = cursor.fetchone()
        elif category == 'ostatni':
            cursor.execute("SELECT * FROM other_properties WHERE listing_id = %s", (listing['id'],))
            type_specific = cursor.fetchone()

        # Get images
        cursor.execute("""
            SELECT image_url, image_order, is_primary
            FROM images
            WHERE listing_id = %s
            ORDER BY image_order
        """, (listing['id'],))
        images = cursor.fetchall()

        # Get change history
        cursor.execute("""
            SELECT
                change_number,
                is_checkpoint,
                changed_fields,
                changed_at
            FROM listing_history
            WHERE listing_id = %s
            ORDER BY change_number DESC
        """, (listing['id'],))
        history = cursor.fetchall()

        cursor.close()
        conn.close()

        return render_template(
            'detail.html',
            listing=listing,
            type_specific=type_specific,
            images=images,
            history=history,
        )

    except Exception as e:
        logger.error(f'Error loading listing detail: {str(e)}', exc_info=True)
        return render_template('error.html', error=str(e)), 500


@app.route('/progress')
def progress():
    """Get crawl progress from crawler service"""
    try:
        # Query crawler service for progress
        response = requests.get('http://crawler:7070/progress', timeout=5)
        response.raise_for_status()
        data = response.json()

        return jsonify(data), 200

    except Exception as e:
        logger.error(f'Error getting crawler progress: {str(e)}')
        return jsonify({
            'percent': 0,
            'running': False,
            'error': str(e)
        }), 500


@app.route('/trigger-crawl', methods=['POST'])
def trigger_crawl():
    """Trigger manual crawl (admin function)"""
    try:
        # Send POST request to crawler service
        response = requests.post('http://crawler:7070/run-now', timeout=5)
        response.raise_for_status()
        data = response.json()

        return jsonify(data), response.status_code

    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 409:
            return jsonify({'error': 'Crawler is already running'}), 409
        else:
            logger.error(f'Error triggering crawl: {str(e)}')
            return jsonify({'error': str(e)}), 500
    except Exception as e:
        logger.error(f'Error triggering crawl: {str(e)}')
        return jsonify({'error': str(e)}), 500


@app.route('/stats')
def stats():
    """Statistics page"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Get statistics
        stats_data = {}

        # Total listings
        cursor.execute("SELECT COUNT(*) as total FROM listings")
        stats_data['total_listings'] = cursor.fetchone()['total']

        # Active listings
        cursor.execute("SELECT COUNT(*) as total FROM listings WHERE is_active = TRUE")
        stats_data['active_listings'] = cursor.fetchone()['total']

        # By category
        cursor.execute("""
            SELECT category, COUNT(*) as count
            FROM listings
            WHERE is_active = TRUE
            GROUP BY category
            ORDER BY count DESC
        """)
        stats_data['by_category'] = cursor.fetchall()

        # By transaction type
        cursor.execute("""
            SELECT transaction_type, COUNT(*) as count
            FROM listings
            WHERE is_active = TRUE
            GROUP BY transaction_type
            ORDER BY count DESC
        """)
        stats_data['by_transaction'] = cursor.fetchall()

        # Average price by category
        cursor.execute("""
            SELECT category, AVG(price) as avg_price
            FROM listings
            WHERE is_active = TRUE AND price IS NOT NULL
            GROUP BY category
            ORDER BY avg_price DESC
        """)
        stats_data['avg_price_by_category'] = cursor.fetchall()

        cursor.close()
        conn.close()

        return render_template('stats.html', stats=stats_data)

    except Exception as e:
        logger.error(f'Error loading stats: {str(e)}', exc_info=True)
        return render_template('error.html', error=str(e)), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=False)
