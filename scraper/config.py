import os
from datetime import datetime

# FCA Search Configuration
FCA_BASE_URL = "https://www.fca.org.uk/publications/search-results"
FCA_PUBLICATION_BASE = "https://www.fca.org.uk"

# Fixed query params. Verified against the live site:
#   - p_search_term="+"   matches everything (base search)
#   - sort_by=dmetaZ      orders by publication date, descending
#   - start is 1-INDEXED: start=1 -> page 1 (10 rows). Pagination uses
#     start = 1, 11, 21, ... and returns 0 rows once past the last result.
FCA_SEARCH_PARAMS = {
    "sort_by": "dmetaZ",
    "p_search_term": "+",
}
RESULTS_PER_PAGE = 10

# Document Types and Category Mappings.
# Category values are the FCA's documented slugs (space-separated form, the
# requests library URL-encodes "+" for spaces). Each maps to a distinct
# scrape, which makes the document type unambiguous at labelling time.
DOC_TYPES = {
    "PS": "policy and guidance-policy statements",      # Policy Statements
    "CP": "policy and guidance-consultation papers",    # Consultation Papers
    "FG": "policy and guidance-finalised guidance",     # Finalised Guidance
    "HN": "policy and guidance-handbook",               # Handbook (notices)
}

# Reference helpers. Curve: the FCA embeds refs like "PS25/20" at the start of
# the search-result title. Handbook notices use refs (e.g. "HN25/1").
REF_PREFIXES = {doc_type: doc_type for doc_type in DOC_TYPES}

# Date Range Filter (inclusive lower bound; results are date-descending)
DATE_START = datetime(2023, 1, 1)
DATE_END = datetime.now()  # hard ceiling at run time

# Rate Limiting
REQUEST_DELAY = 1  # Seconds between requests

# Paths. config.py lives at <project>/scraper/config.py, so the project root
# is its grandparent directory (two ``dirname`` calls).
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
INDEX_DIR = os.path.join(BASE_DIR, "data", "index")
PDFS_DIR = os.path.join(BASE_DIR, "data", "pdfs")
HTML_DIR = os.path.join(BASE_DIR, "data", "html")
METADATA_DIR = os.path.join(BASE_DIR, "data", "metadata")
TEXT_DIR = os.path.join(BASE_DIR, "data", "text")
LOGS_DIR = os.path.join(BASE_DIR, "data", "logs")

# Create directories if they don't exist
for dir_path in [INDEX_DIR, PDFS_DIR, HTML_DIR, METADATA_DIR, TEXT_DIR, LOGS_DIR]:
    os.makedirs(dir_path, exist_ok=True)