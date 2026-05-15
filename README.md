What the scraper does
Task 1 – Entertainment news (scrape_entertainment):

Navigates to /entertainment, waits for networkidle, then scrolls to trigger lazy-loaded images
Tries 8 progressively broader card selectors until one yields results
For each card: extracts title (h1/h2/h3/a), image (prefers data-src for lazy-load), category (badge/label span, defaults to मनोरञ्जन), and author (strips prefixes like लेखक:)

Task 2 – Cartoon of the Day (scrape_cartoon):

Tries /cartoon, /cartoon-of-the-day, /photos/cartoon in sequence
Falls back to scanning the homepage for sections whose headings contain व्यङ्ग्य, ग्यात्र, or cartoon
Extracts title (nearest heading or alt text), image URL, and cartoonist name

Key robustness features:

safe_text / safe_attr helpers swallow exceptions and return None
absolute_url normalises // and /-relative image paths
ensure_ascii=False preserves Devanagari script in the JSON output
Change headless=True → headless=False to watch the browser while debugging