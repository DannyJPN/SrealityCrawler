"""
Custom Scrapy middlewares for SrealityCrawler
"""

import time
import logging
from scrapy import signals
from scrapy.exceptions import NotConfigured, IgnoreRequest
from scrapy.http import HtmlResponse
from scrapy.downloadermiddlewares.retry import RetryMiddleware as BaseRetryMiddleware


logger = logging.getLogger(__name__)


class SrealitySpiderMiddleware:
    """Spider middleware for processing responses"""

    @classmethod
    def from_crawler(cls, crawler):
        s = cls()
        crawler.signals.connect(s.spider_opened, signal=signals.spider_opened)
        return s

    def process_spider_input(self, response, spider):
        return None

    def process_spider_output(self, response, result, spider):
        for i in result:
            yield i

    def process_spider_exception(self, response, exception, spider):
        pass

    def process_start_requests(self, start_requests, spider):
        for r in start_requests:
            yield r

    def spider_opened(self, spider):
        logger.info(f'Spider opened: {spider.name}')


class ConditionalRequestMiddleware:
    """
    Middleware to handle conditional requests using ETag and Last-Modified headers
    """

    def __init__(self, enabled):
        self.enabled = enabled
        self.etag_cache = {}  # Cache ETag values per URL
        self.last_modified_cache = {}  # Cache Last-Modified values per URL

    @classmethod
    def from_crawler(cls, crawler):
        enabled = crawler.settings.getbool('CONDITIONAL_REQUESTS_ENABLED', True)
        return cls(enabled)

    def process_request(self, request, spider):
        """Add conditional request headers if we have cached values"""
        if not self.enabled:
            return None

        url = request.url

        # Add If-None-Match header if we have an ETag
        if url in self.etag_cache:
            request.headers['If-None-Match'] = self.etag_cache[url]

        # Add If-Modified-Since header if we have a Last-Modified value
        if url in self.last_modified_cache:
            request.headers['If-Modified-Since'] = self.last_modified_cache[url]

        return None

    def process_response(self, request, response, spider):
        """Handle 304 Not Modified responses and cache ETag/Last-Modified headers"""
        if not self.enabled:
            return response

        url = request.url

        # Cache ETag if present
        if 'ETag' in response.headers:
            self.etag_cache[url] = response.headers['ETag'].decode('utf-8')

        # Cache Last-Modified if present
        if 'Last-Modified' in response.headers:
            self.last_modified_cache[url] = response.headers['Last-Modified'].decode('utf-8')

        # Handle 304 Not Modified
        if response.status == 304:
            logger.debug(f'304 Not Modified for {url}')
            # Create a special response to indicate content hasn't changed
            response.meta['not_modified'] = True
            return response

        return response


class RetryMiddleware(BaseRetryMiddleware):
    """
    Enhanced retry middleware with dynamic backoff and error tracking
    """

    def __init__(self, settings):
        super().__init__(settings)
        self.error_counts = {}  # Track errors per domain
        self.base_delay = settings.getfloat('DOWNLOAD_DELAY', 0.1)
        self.current_delay = self.base_delay
        self.last_error_time = None

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler.settings)

    def process_response(self, request, response, spider):
        """Process response and adjust delay based on errors"""

        # Track successful requests
        if response.status < 400:
            # Gradually reduce delay on successful requests
            self._decrease_delay()
            return response

        # Track failed requests
        if response.status in self.retry_http_codes:
            self._increase_delay(response.status)
            reason = f'HTTP {response.status}'
            return self._retry(request, reason, spider) or response

        return response

    def process_exception(self, request, exception, spider):
        """Process exceptions and adjust delay"""
        self._increase_delay('exception')

        # Retry on timeout, DNS errors, connection errors, etc.
        if isinstance(exception, (
            TimeoutError,
            ConnectionError,
            OSError,
        )):
            reason = f'{exception.__class__.__name__}: {str(exception)}'
            return self._retry(request, reason, spider)

        return None

    def _increase_delay(self, error_type):
        """Increase delay geometrically on errors"""
        domain = getattr(error_type, '__name__', str(error_type))

        # Track error count
        self.error_counts[domain] = self.error_counts.get(domain, 0) + 1

        # Increase delay geometrically
        self.current_delay = min(self.current_delay * 1.5, 10.0)
        self.last_error_time = time.time()

        logger.warning(
            f'Error {error_type}: increasing delay to {self.current_delay:.2f}s '
            f'(error count: {self.error_counts[domain]})'
        )

    def _decrease_delay(self):
        """Gradually decrease delay on successful requests"""
        if self.current_delay > self.base_delay:
            # Decrease delay more slowly than we increase it
            self.current_delay = max(self.current_delay * 0.95, self.base_delay)

    def _retry(self, request, reason, spider):
        """Retry request with exponential backoff"""
        retries = request.meta.get('retry_times', 0) + 1

        retry_times = self.max_retry_times
        if retry_times is not None and retries <= retry_times:
            logger.debug(
                f"Retrying {request.url} (failed {retries} times): {reason}"
            )

            # GEOMETRICKÝ BACKOFF podle specifikace (řádek 48)
            # Exponenciálně zvyšuj delay podle počtu chyb
            backoff = min(2 ** retries + (time.time() % 1), 60)

            # ASYNC-SAFE implementace pomocí download_delay
            # Toto NEblokuje Twisted reactor
            retryreq = request.copy()
            retryreq.meta['retry_times'] = retries
            retryreq.meta['download_delay'] = backoff  # Scrapy respektuje tento meta tag
            retryreq.dont_filter = True
            retryreq.priority = request.priority + self.priority_adjust

            logger.debug(f"Retry {retries}/{retry_times} for {request.url} with {backoff:.1f}s delay")

            return retryreq
        else:
            logger.error(
                f"Gave up retrying {request.url} (failed {retries} times): {reason}"
            )
            return None
