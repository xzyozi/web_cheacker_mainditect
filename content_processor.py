import json
import logging
from urllib.parse import urlparse

import requests
import trafilatura
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Configuration for credibility scoring
TLD_WEIGHTS = {
    '.gov': 0.3,
    '.edu': 0.3,
    '.org': 0.1,
    'default': 0.0
}
METADATA_WEIGHTS = {
    'author': 0.15,
    'date': 0.15,
}
HTTPS_WEIGHT = 0.1
TOTAL_WEIGHT_SUM = sum(TLD_WEIGHTS.values()) - TLD_WEIGHTS['default'] + sum(METADATA_WEIGHTS.values()) + HTTPS_WEIGHT

class ContentProcessor:
    """
    Extracts content and metadata from a URL and calculates a credibility score.
    """

    def process_url(self, url: str) -> dict:
        """
        Processes a single URL to extract content and calculate credibility.
        """
        try:
            # Use a session for potential connection reuse
            session = requests.Session()
            session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'})
            
            # Fetch HTML content
            response = session.get(url, timeout=10, allow_redirects=True)
            response.raise_for_status()
            html_content = response.text
            final_url = response.url # Use the final URL after redirects

            # 1. High-precision content extraction with trafilatura
            extracted_json = trafilatura.extract(html_content, include_metadata=True, output_format='json')
            content = json.loads(extracted_json) if extracted_json else {}

            # 2. Fallback metadata extraction with BeautifulSoup
            if not content.get('author') or not content.get('date'):
                soup = BeautifulSoup(html_content, 'html.parser')
                if not content.get('author'):
                    author_tag = soup.find('meta', attrs={'name': 'author'})
                    if author_tag and author_tag.get('content'):
                        content['author'] = author_tag['content']
                if not content.get('date'):
                    date_tag = soup.find('meta', property='article:published_time')
                    if date_tag and date_tag.get('content'):
                        content['date'] = date_tag['content']
            
            # 3. Multi-factor credibility scoring
            content['credibility_score'] = self._calculate_credibility(final_url, content)
            return content

        except requests.RequestException as e:
            logger.error(f"Failed to fetch URL {url}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error processing URL {url}: {e}")
            return None

    def _calculate_credibility(self, url: str, metadata: dict) -> float:
        """Calculates a credibility score based on various signals."""
        score = 0.0
        parsed_url = urlparse(url)
        tld = "." + ".".join(parsed_url.netloc.split('.')[-2:]) # handles .co.uk etc.
        score += TLD_WEIGHTS.get(tld, TLD_WEIGHTS.get('.' + parsed_url.netloc.split('.')[-1], TLD_WEIGHTS['default']))
        if metadata.get('author'): score += METADATA_WEIGHTS['author']
        if metadata.get('date'): score += METADATA_WEIGHTS['date']
        if parsed_url.scheme == 'https': score += HTTPS_WEIGHT
        normalized_score = score / TOTAL_WEIGHT_SUM if TOTAL_WEIGHT_SUM > 0 else 0.0
        return min(normalized_score, 1.0)