"""
Scrapy settings for SrealityCrawler project

For simplicity, this file contains only settings considered important or
commonly used. You can find more settings consulting the documentation:

    https://docs.scrapy.org/en/latest/topics/settings.html
"""

import os

BOT_NAME = 'SrealityCrawler'

SPIDER_MODULES = ['scrapy_project.spiders']
NEWSPIDER_MODULE = 'scrapy_project.spiders'

# Crawl responsibly by identifying yourself (and your website) on the user-agent
USER_AGENT = 'SrealityCrawler/1.0 (+https://github.com/)'

# Obey robots.txt rules
ROBOTSTXT_OBEY = True

# Configure maximum concurrent requests performed by Scrapy
CONCURRENT_REQUESTS = 4  # Low parallelism for politeness

# Configure a delay for requests for the same website (default: 0)
# See https://docs.scrapy.org/en/latest/topics/settings.html#download-delay
DOWNLOAD_DELAY = 0.1  # Default delay, can be adjusted dynamically

# The download delay setting will honor only one of:
CONCURRENT_REQUESTS_PER_DOMAIN = 4
CONCURRENT_REQUESTS_PER_IP = 0

# Disable cookies (enabled by default)
COOKIES_ENABLED = False

# Disable Telnet Console (enabled by default)
TELNETCONSOLE_ENABLED = False

# Override the default request headers:
DEFAULT_REQUEST_HEADERS = {
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'cs,en-US;q=0.9,en;q=0.8',
}

# Enable or disable spider middlewares
# See https://docs.scrapy.org/en/latest/topics/spider-middleware.html
SPIDER_MIDDLEWARES = {
    'scrapy_project.middlewares.SrealitySpiderMiddleware': 543,
}

# Enable or disable downloader middlewares
# See https://docs.scrapy.org/en/latest/topics/downloader-middleware.html
DOWNLOADER_MIDDLEWARES = {
    'scrapy_project.middlewares.ConditionalRequestMiddleware': 585,
    'scrapy_project.middlewares.RetryMiddleware': 550,
}

# Enable or disable extensions
# See https://docs.scrapy.org/en/latest/topics/extensions.html
EXTENSIONS = {
    'scrapy.extensions.telnet.TelnetConsole': None,
}

# Configure item pipelines
# See https://docs.scrapy.org/en/latest/topics/item-pipeline.html
ITEM_PIPELINES = {
    'scrapy_project.pipelines.HTMLStoragePipeline': 100,
    'scrapy_project.pipelines.ImageDownloadPipeline': 200,
    'scrapy_project.pipelines.DatabasePipeline': 300,
}

# Enable and configure the AutoThrottle extension (disabled by default)
# See https://docs.scrapy.org/en/latest/topics/autothrottle.html
AUTOTHROTTLE_ENABLED = True
# The initial download delay
AUTOTHROTTLE_START_DELAY = 0.1
# The maximum download delay to be set in case of high latencies
AUTOTHROTTLE_MAX_DELAY = 10
# The average number of requests Scrapy should be sending in parallel to
# each remote server
AUTOTHROTTLE_TARGET_CONCURRENCY = 2.0
# Enable showing throttle stats for every response received:
AUTOTHROTTLE_DEBUG = False

# Enable and configure HTTP caching (disabled by default)
# See https://docs.scrapy.org/en/latest/topics/downloader-middleware.html#httpcache-middleware-settings
HTTPCACHE_ENABLED = False

# Retry configuration
RETRY_TIMES = 100  # Maximum retry attempts
RETRY_HTTP_CODES = [408, 429, 500, 502, 503, 504, 522, 524]
RETRY_PRIORITY_ADJUST = -1

# Download timeout
DOWNLOAD_TIMEOUT = 30  # 30 seconds

# Disable redirect middleware
REDIRECT_ENABLED = True
REDIRECT_MAX_TIMES = 5

# Memory management
MEMUSAGE_ENABLED = True
MEMUSAGE_LIMIT_MB = 1900  # Leave some headroom from 2GB limit
MEMUSAGE_WARNING_MB = 1700

# Logging
LOG_LEVEL = 'INFO'
LOG_FORMAT = '%(levelname)s: %(message)s'
LOG_DATEFORMAT = '%Y-%m-%d %H:%M:%S'

# Database configuration from environment
POSTGRES_HOST = os.getenv('POSTGRES_HOST', 'db')
POSTGRES_PORT = os.getenv('POSTGRES_PORT', '5432')
POSTGRES_DB = os.getenv('POSTGRES_DB', 'reality_history')
POSTGRES_USER = os.getenv('POSTGRES_USER', 'sreality')
POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD', 'sreality')

# Storage paths
HTML_STORAGE_PATH = '/app/data/html'
LOGS_PATH = '/app/data/logs'

# LMDB configuration for URL mapping
LMDB_PATH = '/app/data/html/url_mapping.lmdb'
LMDB_MAP_SIZE = 10 * 1024 * 1024 * 1024  # 10 GB

# Conditional request support
CONDITIONAL_REQUESTS_ENABLED = True

# Request fingerprinter
REQUEST_FINGERPRINTER_IMPLEMENTATION = '2.7'

# Twisted reactor
TWISTED_REACTOR = 'twisted.internet.asyncioreactor.AsyncioSelectorReactor'

# Feed export encoding
FEED_EXPORT_ENCODING = 'utf-8'
