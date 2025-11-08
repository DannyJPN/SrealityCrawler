"""
APScheduler integration for scheduled crawls with HTTP server
for manual triggers and progress monitoring
"""

import os
import sys
import logging
import subprocess
import threading
from datetime import datetime
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from flask import Flask, jsonify, request
import pytz


# Setup colored logging
class ColoredFormatter(logging.Formatter):
    """Custom formatter with colored log levels"""

    COLORS = {
        'DEBUG': '\033[36m',      # Cyan
        'INFO': '\033[32m',       # Green
        'WARNING': '\033[33m',    # Yellow
        'ERROR': '\033[31m',      # Red
        'CRITICAL': '\033[35m',   # Magenta
    }
    RESET = '\033[0m'

    def format(self, record):
        levelname = record.levelname
        if levelname in self.COLORS:
            record.levelname = f'{self.COLORS[levelname]}{levelname}{self.RESET}'
        return super().format(record)


def setup_logging():
    """Setup colored logging to console and file"""
    # Create logs directory
    logs_dir = Path('/app/data/logs')
    logs_dir.mkdir(parents=True, exist_ok=True)

    # Create log filename with timestamp
    log_filename = logs_dir / f'crawler_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'

    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # Console handler with colored output
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_formatter = ColoredFormatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    # File handler (no colors)
    file_handler = logging.FileHandler(log_filename)
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)

    logging.info(f'Logging initialized. Log file: {log_filename}')

    return log_filename


# Initialize logging
current_log_file = setup_logging()
logger = logging.getLogger(__name__)


# Flask app for HTTP endpoints
app = Flask(__name__)

# Global state
crawler_running = False
crawler_lock = threading.Lock()
crawler_process = None


def run_crawler():
    """Run the Scrapy crawler"""
    global crawler_running, crawler_process

    with crawler_lock:
        if crawler_running:
            logger.warning('Crawler is already running, skipping scheduled run')
            return

        crawler_running = True

    try:
        logger.info('Starting crawler...')

        # Change to scrapy project directory
        os.chdir('/app')

        # Run scrapy spider
        crawler_process = subprocess.Popen(
            ['scrapy', 'crawl', 'sreality'],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            cwd='/app'
        )

        # Log output in real-time
        for line in iter(crawler_process.stdout.readline, ''):
            if line:
                logger.info(f'[Scrapy] {line.rstrip()}')

        crawler_process.wait()

        if crawler_process.returncode == 0:
            logger.info('Crawler finished successfully')
        else:
            logger.error(f'Crawler failed with return code {crawler_process.returncode}')

    except Exception as e:
        logger.error(f'Error running crawler: {str(e)}', exc_info=True)

    finally:
        with crawler_lock:
            crawler_running = False
            crawler_process = None

        # Mark inactive listings after crawl
        try:
            mark_inactive_listings()
        except Exception as e:
            logger.error(f'Error marking inactive listings: {str(e)}')


def mark_inactive_listings():
    """Mark listings as inactive if they weren't seen in the latest crawl"""
    import psycopg2
    from datetime import datetime, timedelta

    try:
        conn = psycopg2.connect(
            host=os.getenv('POSTGRES_HOST', 'db'),
            port=os.getenv('POSTGRES_PORT', '5432'),
            database=os.getenv('POSTGRES_DB', 'reality_history'),
            user=os.getenv('POSTGRES_USER', 'sreality'),
            password=os.getenv('POSTGRES_PASSWORD', 'sreality')
        )

        cursor = conn.cursor()

        # Mark listings as inactive if they haven't been seen in the last hour
        # (assuming the crawl takes less than 1 hour)
        one_hour_ago = datetime.now() - timedelta(hours=1)

        cursor.execute("""
            UPDATE listings
            SET is_active = FALSE
            WHERE last_seen_at < %s AND is_active = TRUE
        """, (one_hour_ago,))

        rows_affected = cursor.rowcount
        conn.commit()

        logger.info(f'Marked {rows_affected} listings as inactive')

        cursor.close()
        conn.close()

    except Exception as e:
        logger.error(f'Failed to mark inactive listings: {str(e)}')


@app.route('/healthz', methods=['GET'])
def healthz():
    """Health check endpoint"""
    return jsonify({'status': 'healthy'}), 200


@app.route('/run-now', methods=['POST'])
def run_now():
    """Manual trigger endpoint"""
    global crawler_running

    with crawler_lock:
        if crawler_running:
            return jsonify({
                'error': 'Crawler is already running'
            }), 409

    # Run crawler in background thread
    thread = threading.Thread(target=run_crawler)
    thread.daemon = True
    thread.start()

    logger.info('Manual crawler run triggered')

    return jsonify({
        'status': 'started',
        'message': 'Crawler started successfully'
    }), 200


@app.route('/progress', methods=['GET'])
def progress():
    """Progress monitoring endpoint"""
    try:
        # Read progress from file written by spider
        progress_file = Path('/tmp/crawler_progress.txt')

        if not progress_file.exists():
            # If file doesn't exist, check if crawler is running
            if crawler_running:
                percent = 0
            else:
                percent = 100  # Not running, assume complete
        else:
            with open(progress_file, 'r') as f:
                content = f.read().strip()
                percent = int(content) if content else 0

        return jsonify({
            'percent': percent,
            'running': crawler_running
        }), 200

    except Exception as e:
        logger.error(f'Error getting progress: {str(e)}')
        return jsonify({
            'percent': 0,
            'running': crawler_running,
            'error': str(e)
        }), 500


def start_scheduler():
    """Start the APScheduler for daily crawls"""
    # Get timezone
    tz = pytz.timezone(os.getenv('TZ', 'Europe/Prague'))

    # Get schedule time from environment
    schedule_hour = int(os.getenv('CRAWL_SCHEDULE_HOUR', '20'))
    schedule_minute = int(os.getenv('CRAWL_SCHEDULE_MINUTE', '0'))

    # Create scheduler
    scheduler = BackgroundScheduler(timezone=tz)

    # Add daily job at specified time
    scheduler.add_job(
        run_crawler,
        trigger=CronTrigger(hour=schedule_hour, minute=schedule_minute, timezone=tz),
        id='daily_crawl',
        name='Daily Sreality Crawl',
        misfire_grace_time=3600,  # Allow up to 1 hour delay
        coalesce=True,  # Combine multiple missed runs into one
        max_instances=1  # Only one instance at a time
    )

    # Start scheduler
    scheduler.start()

    logger.info(
        f'Scheduler started. Daily crawl scheduled at {schedule_hour:02d}:{schedule_minute:02d} {tz}'
    )

    return scheduler


def main():
    """Main entry point"""
    logger.info('Starting SrealityCrawler scheduler')
    logger.info(f'Python version: {sys.version}')
    logger.info(f'Working directory: {os.getcwd()}')

    # Initialize progress file
    try:
        with open('/tmp/crawler_progress.txt', 'w') as f:
            f.write('0')
    except Exception as e:
        logger.error(f'Failed to initialize progress file: {e}')

    # Start scheduler
    scheduler = start_scheduler()

    # Run Flask app (blocking)
    # This serves the HTTP endpoints for manual trigger and progress
    port = int(os.getenv('CRAWLER_PORT', '7070'))

    logger.info(f'Starting HTTP server on port {port}')

    try:
        app.run(
            host='0.0.0.0',
            port=port,
            debug=False,
            use_reloader=False  # Important: disable reloader to prevent scheduler from running twice
        )
    except KeyboardInterrupt:
        logger.info('Received shutdown signal')
        scheduler.shutdown()
        logger.info('Scheduler stopped')


if __name__ == '__main__':
    main()
