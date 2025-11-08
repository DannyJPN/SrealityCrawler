"""
Flask application main entry point.

This is a placeholder file for future implementation.
See SPECIFIKACE.md for detailed requirements.
"""

from flask import Flask, jsonify

app = Flask(__name__)


@app.route('/healthz')
def healthz():
    """Health check endpoint."""
    # TODO: Check database connectivity
    return jsonify({"status": "ok"}), 200


@app.route('/')
def index():
    """Main listing page with pagination, filtering, and sorting."""
    # TODO: Implement listing page with Jinja2 template
    return "SrealityCrawler - Coming soon"


@app.route('/listing/<int:listing_id>')
def listing_detail(listing_id):
    """Listing detail page with full history."""
    # TODO: Implement detail page with change history
    return f"Listing {listing_id} detail - Coming soon"


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
