import json
import re
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout


# ── helpers ──────────────────────────────────────────────────────────────────

def safe_text(el, selector: str | None = None) -> str | None:
    """Return stripped text content, or None if element / selector missing."""
    try:
        target = el.query_selector(selector) if selector else el
        if target is None:
            return None
        text = target.text_content()
        return text.strip() if text else None
    except Exception:
        return None


def safe_attr(el, selector: str | None, attr: str) -> str | None:
    """Return an attribute value from a (possibly nested) element, or None."""
    try:
        target = el.query_selector(selector) if selector else el
        if target is None:
            return None
        return target.get_attribute(attr)
    except Exception:
        return None


def absolute_url(url: str | None, base: str = "https://ekantipur.com") -> str | None:
    """Ensure image / href URLs are fully qualified."""
    if not url:
        return None
    url = url.strip()
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("/"):
        return base + url
    return url  # already absolute


def wait_and_get(page, selector: str, timeout: int = 8_000):
    """Wait for a selector then return all matching elements (list)."""
    try:
        page.wait_for_selector(selector, timeout=timeout)
        return page.query_selector_all(selector)
    except PlaywrightTimeout:
        print(f"  [warn] Timed out waiting for: {selector}")
        return []


def dump_structure(page, label="PAGE"):
    """Debug helper — print tag/class combos visible on the page."""
    tags = page.evaluate("""() => {
        const els = document.querySelectorAll('div[class], section[class], ul[class], li[class]');
        const seen = new Set();
        const out = [];
        for (const el of els) {
            const key = el.tagName.toLowerCase() + '.' + [...el.classList].join('.');
            if (!seen.has(key)) { seen.add(key); out.push(key); }
            if (out.length >= 80) break;
        }
        return out;
    }""")
    print(f"\n  [{label} STRUCTURE SAMPLE]")
    for t in tags:
        print("   ", t)
    print()


# ── task 1: entertainment news ────────────────────────────────────────────────

def extract_card_data(card) -> dict | None:
    """Extract title/image/category/author from a single card element."""
    title = (
        safe_text(card, "h1")
        or safe_text(card, "h2")
        or safe_text(card, "h3")
        or safe_text(card, "h4")
        or safe_text(card, ".title")
        or safe_text(card, ".headline")
        or safe_text(card, "a")
    )
    if not title:
        return None   # skip cards with no title

    # Image — prefer lazy-load attrs, fall back to src; handle srcset strings
    img_el = card.query_selector("img")
    image_url = None
    if img_el:
        image_url = (
            img_el.get_attribute("data-src")
            or img_el.get_attribute("data-lazy-src")
            or img_el.get_attribute("srcset")
            or img_el.get_attribute("src")
        )
        if image_url and " " in image_url:
            image_url = image_url.split()[0]   # take first URL from srcset
    image_url = absolute_url(image_url)

    category = (
        safe_text(card, ".category")
        or safe_text(card, ".section-label")
        or safe_text(card, ".label")
        or safe_text(card, ".tag")
        or safe_text(card, ".badge")
        or safe_text(card, "[class*='cat']")
        or "मनोरञ्जन"
    )

    author = (
        safe_text(card, ".author")
        or safe_text(card, ".byline")
        or safe_text(card, "[class*='author']")
        or safe_text(card, "[class*='writer']")
        or safe_text(card, "[class*='reporter']")
    )
    if author:
        author = re.sub(
            r"^(लेखक\s*:\s*|प्रकाशित\s*:\s*|By\s+)", "", author, flags=re.IGNORECASE
        ).strip() or None

    return {"title": title, "image_url": image_url, "category": category, "author": author}


def scrape_entertainment(page) -> list[dict]:
    """Navigate to the Entertainment section and return top-5 articles."""

    print("→ Navigating to Entertainment section …")
    page.goto("https://ekantipur.com/entertainment", wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle", timeout=25_000)

    # Scroll incrementally so lazy-loaded cards below the fold can render
    for scroll_y in [600, 1200, 1800]:
        page.evaluate(f"window.scrollTo(0, {scroll_y})")
        page.wait_for_timeout(800)

    # ── Multi-pass card collection ────────────────────────────────────────────
    # ekantipur's entertainment page layout (confirmed via DevTools):
    #   .main-news-templates-wrapper
    #     └── .template-one-wrapper   (repeated for each content block)
    #           └── .row
    #                 └── .col-lg-4  (grid column)
    #                       └── .news-wrapper  ← THIS is each news card
    # Multiple .template-one-wrapper blocks exist on the page, giving us
    # more than 5 cards total — we collect, deduplicate, and stop at 5.

    # Selectors derived from DevTools inspection of ekantipur.com/entertainment:
    # DOM path: .main-news-section > .container > .row > .col-lg-9
    #           > .main-news-templates-wrapper > .template-one-wrapper
    #           > .row > .col-lg-4 > .news-wrapper   ← each card lives here
    # We go most-specific first; broader fallbacks handle layout changes.
    CARD_SELECTORS = [
        ".template-one-wrapper .news-wrapper",   # exact path seen in DevTools
        ".news-wrapper",                          # same class, any ancestor
        ".template-one-wrapper .col-lg-4",        # parent column as card unit
        ".col-lg-4 .news-wrapper",
        "div:has(img):has(h2)",                   # broadest fallback
        "div:has(img):has(h3)",
    ]

    seen_titles: set[str] = set()
    articles: list[dict] = []

    for sel in CARD_SELECTORS:
        if len(articles) >= 5:
            break
        elements = page.query_selector_all(sel)
        if not elements:
            continue
        print(f"  [info] Trying selector '{sel}' → {len(elements)} elements")
        for el in elements:
            if len(articles) >= 5:
                break
            data = extract_card_data(el)
            if data and data["title"] not in seen_titles:
                seen_titles.add(data["title"])
                articles.append(data)

    # Last resort: dump structure so you can identify the right selector
    if not articles:
        print("  [warn] No articles found. Dumping page structure for debugging …")
        dump_structure(page, "ENTERTAINMENT")

    print(f"  [ok] Extracted {len(articles)} entertainment articles")
    return articles


# ── task 2: cartoon of the day ────────────────────────────────────────────────

def scrape_cartoon(page) -> dict:
    """Find the Cartoon of the Day (व्यङ्ग्यचित्र) and return its data."""

    print("→ Looking for Cartoon of the Day …")

    # Known URL paths for the cartoon section on ekantipur
    CARTOON_PATHS = [
        "https://ekantipur.com/cartoon",
        "https://ekantipur.com/cartoon-of-the-day",
        "https://ekantipur.com/photos/cartoon",
    ]

    cartoon = {"title": None, "image_url": None, "author": None}

    for path in CARTOON_PATHS:
        page.goto(path, wait_until="domcontentloaded")
        try:
            page.wait_for_load_state("networkidle", timeout=15_000)
        except PlaywrightTimeout:
            pass

        # ekantipur cartoon pages typically have one large image in a figure/div
        CARTOON_IMG_SELECTORS = [
            ".cartoon-section img",
            "[class*='cartoon'] img",
            "article.cartoon img",
            ".cartoon img",
            ".cartoon-of-day img",
            "figure img",
            # broad: first large image on the page (cartoon pages are minimal)
            "main img",
            "img",
        ]
        img_el = None
        for sel in CARTOON_IMG_SELECTORS:
            img_el = page.query_selector(sel)
            if img_el:
                break

        if img_el:
            # Walk up to the nearest meaningful container
            container = img_el.evaluate_handle(
                "el => el.closest('article') || el.closest('figure')"
                "    || el.closest('[class*=\"cartoon\"]') || el.closest('div')"
            ).as_element()

            title = None
            if container:
                title = (
                    safe_text(container, "h1")
                    or safe_text(container, "h2")
                    or safe_text(container, "h3")
                    or safe_text(container, ".title")
                    or safe_text(container, "figcaption")
                    or safe_text(container, ".caption")
                )
            # Ultimate fallback: alt attribute
            if not title:
                title = img_el.get_attribute("alt")

            image_url = absolute_url(
                img_el.get_attribute("data-src") or img_el.get_attribute("src")
            )

            author = None
            if container:
                author = (
                    safe_text(container, ".author")
                    or safe_text(container, ".byline")
                    or safe_text(container, "[class*='author']")
                    or safe_text(container, "[class*='cartoonist']")
                    or safe_text(container, "[class*='artist']")
                )
            if author:
                author = re.sub(
                    r"^(लेखक\s*:\s*|By\s+)", "", author, flags=re.IGNORECASE
                ).strip() or None

            cartoon = {"title": title, "image_url": image_url, "author": author}
            print(f"  [ok] Cartoon found at: {path}")
            break

    # ── Fallback: scan the homepage for a cartoon widget ─────────────────────
    if not cartoon["image_url"]:
        print("  [warn] Dedicated cartoon page yielded no image, trying homepage …")
        page.goto("https://ekantipur.com", wait_until="domcontentloaded")
        try:
            page.wait_for_load_state("networkidle", timeout=15_000)
        except PlaywrightTimeout:
            pass

        # Scroll halfway to trigger lazy loading
        page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
        page.wait_for_timeout(2_000)

        # Search every section/widget for Nepali cartoon-related headings
        sections = page.query_selector_all(
            "section, div[class*='widget'], div[class*='section'], div[class*='block']"
        )
        for sec in sections:
            heading_text = (
                safe_text(sec, "h2") or safe_text(sec, "h3") or safe_text(sec, "h4") or ""
            )
            if re.search(r"व्यङ्ग्य|व्यंग्य|cartoon", heading_text, re.IGNORECASE):
                img_el = sec.query_selector("img")
                if img_el:
                    cartoon["title"] = heading_text or img_el.get_attribute("alt")
                    cartoon["image_url"] = absolute_url(
                        img_el.get_attribute("data-src") or img_el.get_attribute("src")
                    )
                    cartoon["author"] = (
                        safe_text(sec, ".author")
                        or safe_text(sec, ".byline")
                        or safe_text(sec, "[class*='author']")
                    )
                    print("  [ok] Cartoon found on homepage via keyword match")
                    break

    if not cartoon["image_url"]:
        print("  [warn] Cartoon of the Day not found on any path")

    return cartoon


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    with sync_playwright() as pw:
        print("Launching browser …")
        browser = pw.chromium.launch(
            headless=True,          # set False to watch the browser while debugging
            args=["--lang=ne,en"],
        )
        context = browser.new_context(
            locale="ne-NP",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
        )
        page = context.new_page()

        # ── Task 1 ────────────────────────────────────────────────────────────
        entertainment_news = scrape_entertainment(page)

        # ── Task 2 ────────────────────────────────────────────────────────────
        cartoon_of_the_day = scrape_cartoon(page)

        browser.close()

    # ── Build & save output ───────────────────────────────────────────────────
    output = {
        "entertainment_news": entertainment_news,
        "cartoon_of_the_day": cartoon_of_the_day,
    }

    output_path = "output.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n✓ Data saved to {output_path}")
    print(f"  Entertainment articles : {len(entertainment_news)}")
    print(f"  Cartoon title          : {cartoon_of_the_day.get('title')}")


if __name__ == "__main__":
    main()