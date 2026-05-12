#!/usr/bin/env python3
"""
Robust Property Extractor — Unified scraper for all real estate agency websites.

Anti-detection profile tested against:
  raywhite.com, raywhiterobina.com.au, raywhitetmg.com.au, raywhitemalanandco.com.au,
  harcourts.net, propertyhub.harcourts.com.au, coastal.com.au, remaxgc.com.au,
  robinafn.com.au, crasto.com.au, prd.com.au, orrentopolansky.com.au,
  mcdermottresidential.com.au, robinarealty.com.au, gcsr.com.au

Known limitation: mcgrath.com.au uses Vercel JS challenge (TLS fingerprint check)
  — returns 429 from headless browsers. McGrath URLs are flagged as 'bot_blocked'.
"""

import asyncio
import json
import random
from datetime import datetime
from playwright.async_api import async_playwright
from urllib.parse import urljoin, urlparse
import os

# Domains known to require Vercel/Cloudflare JS challenges that headless shell cannot solve
VERCEL_BLOCKED_DOMAINS = {'mcgrath.com.au'}

# Realistic recent desktop UAs — rotated per request to avoid IP+UA fingerprint blocks.
# Mix of macOS + Windows, Chrome + Firefox. All are real production strings as of 2026.
USER_AGENTS = [
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
]

# Per-request jitter (seconds) — small random delay before navigation so we don't
# hit agency sites in a perfectly periodic pattern.
JITTER_MIN_SECONDS = 0.5
JITTER_MAX_SECONDS = 3.0

# Block signatures in page body that indicate bot detection fired
BLOCK_SIGNATURES = [
    'vercel security checkpoint',
    'checking your browser',
    'cf-browser-verification',
    'access denied',
    'rate limit exceeded',
]


class RobustPropertyExtractor:
    """Unified extractor with anti-detection for all Gold Coast agency sites"""

    def __init__(self, target_url):
        self.target_url = target_url
        self._domain = urlparse(target_url).netloc.lower().lstrip('www.')

    async def extract_all_text_robust(self, page):
        """Extract text with robust error handling"""
        text_data = {}

        try:
            # Get visible text (this rarely fails)
            body_text = await page.locator('body').inner_text()
            text_data['visible_text'] = body_text
            print(f"✓ Extracted {len(body_text)} characters of visible text")
        except Exception as e:
            print(f"⚠️ Could not get body text: {e}")
            text_data['visible_text'] = ''

        try:
            # Get page title
            text_data['page_title'] = await page.title()
            print(f"✓ Page title: {text_data['page_title']}")
        except Exception as e:
            print(f"⚠️ Could not get title: {e}")
            text_data['page_title'] = ''

        # Get meta description with timeout
        try:
            meta_desc = await page.locator('meta[name="description"]').get_attribute('content', timeout=2000)
            text_data['meta_description'] = meta_desc or ''
        except:
            text_data['meta_description'] = ''

        # Extract headings
        try:
            headings = {}
            for i in range(1, 7):
                heading_elements = await page.locator(f'h{i}').all()
                heading_texts = []
                for h in heading_elements:
                    try:
                        text = await h.inner_text()
                        if text.strip():
                            heading_texts.append(text.strip())
                    except:
                        continue
                headings[f'h{i}'] = heading_texts
            text_data['headings'] = headings
            total_headings = sum(len(v) for v in headings.values())
            print(f"✓ Extracted {total_headings} headings")
        except Exception as e:
            print(f"⚠️ Could not extract headings: {e}")
            text_data['headings'] = {}

        # Extract paragraphs
        try:
            paragraphs = await page.locator('p').all()
            paragraph_texts = []
            for p in paragraphs:
                try:
                    text = await p.inner_text()
                    if text.strip():
                        paragraph_texts.append(text.strip())
                except:
                    continue
            text_data['paragraphs'] = paragraph_texts
            print(f"✓ Extracted {len(paragraph_texts)} paragraphs")
        except Exception as e:
            print(f"⚠️ Could not extract paragraphs: {e}")
            text_data['paragraphs'] = []

        # Extract list items
        try:
            list_items = await page.locator('li').all()
            list_texts = []
            for li in list_items:
                try:
                    text = await li.inner_text()
                    if text.strip():
                        list_texts.append(text.strip())
                except:
                    continue
            text_data['list_items'] = list_texts
            print(f"✓ Extracted {len(list_texts)} list items")
        except Exception as e:
            print(f"⚠️ Could not extract list items: {e}")
            text_data['list_items'] = []

        return text_data

    async def extract_all_images_robust(self, page):
        """Extract images with robust error handling"""
        all_images = []
        image_sources = set()

        try:
            # Extract from <img> tags
            img_elements = await page.locator('img').all()
            print(f"Found {len(img_elements)} <img> elements")

            for img in img_elements:
                try:
                    src = await img.get_attribute('src')
                    alt = await img.get_attribute('alt')

                    if src and src not in image_sources:
                        absolute_url = urljoin(self.target_url, src)
                        if not absolute_url.startswith('data:'):
                            image_sources.add(src)
                            all_images.append({
                                'url': absolute_url,
                                'alt': alt or '',
                                'source_type': 'img_tag'
                            })
                except Exception as e:
                    continue

            print(f"✓ Total unique images extracted: {len(all_images)}")
        except Exception as e:
            print(f"⚠️ Error extracting images: {e}")

        return all_images

    def _is_blocked(self, status_code, body_text):
        """Detect bot-blocking responses from any agency site."""
        if status_code == 429:
            return True
        body_lower = body_text.lower()
        return any(sig in body_lower for sig in BLOCK_SIGNATURES)

    async def run_extraction(self):
        """Run robust extraction with unified anti-detection."""
        print("="*60)
        print("ROBUST PROPERTY EXTRACTION")
        print("="*60)
        print(f"URL: {self.target_url}\n")

        results = {
            'extraction_date': datetime.now().isoformat(),
            'target_url': self.target_url,
            'data': {}
        }

        # Early exit for known-blocked domains
        if any(self._domain.endswith(d) for d in VERCEL_BLOCKED_DOMAINS):
            print(f"⚠️ {self._domain} uses Vercel JS challenge — skipping (bot_blocked)")
            results['data']['text'] = {
                'visible_text': '', 'page_title': '', 'meta_description': '',
                'headings': {}, 'paragraphs': [], 'list_items': [],
            }
            results['data']['images'] = []
            results['statistics'] = {
                'extraction_success': False,
                'error': 'bot_blocked',
                'blocked_domain': self._domain,
            }
            return results

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--no-sandbox',
                    '--disable-dev-shm-usage',
                ],
            )
            chosen_ua = random.choice(USER_AGENTS)
            context = await browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent=chosen_ua,
                extra_http_headers={
                    'Accept-Language': 'en-AU,en;q=0.9',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                },
            )
            await context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                window.chrome = { runtime: {} };
                Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3]});
            """)
            page = await context.new_page()

            try:
                # Jitter — small random delay before navigation so concurrent requests
                # don't all hit the same agency site at the same instant.
                jitter = random.uniform(JITTER_MIN_SECONDS, JITTER_MAX_SECONDS)
                await asyncio.sleep(jitter)
                print(f"Navigating to URL... (UA={chosen_ua.split(')')[0].split('(')[-1][:30]}, jitter={jitter:.1f}s)")
                status_code = 0
                try:
                    resp = await page.goto(self.target_url, wait_until='domcontentloaded', timeout=15000)
                    status_code = resp.status if resp else 0
                    print(f"✓ Page loaded (HTTP {status_code})\n")
                except Exception:
                    print("⚠️ domcontentloaded timed out — extracting partial DOM\n")

                # Quick block check before waiting for JS content
                if status_code in (403, 429):
                    try:
                        early_body = await page.locator('body').inner_text()
                    except Exception:
                        early_body = ''
                    if self._is_blocked(status_code, early_body):
                        print(f"⚠️ Bot-blocked (HTTP {status_code}) on {self._domain}")
                        results['data']['text'] = {
                            'visible_text': early_body, 'page_title': '',
                            'meta_description': '', 'headings': {},
                            'paragraphs': [], 'list_items': [],
                        }
                        results['data']['images'] = []
                        results['statistics'] = {
                            'extraction_success': False,
                            'error': 'bot_blocked',
                            'blocked_domain': self._domain,
                            'http_status': status_code,
                        }
                        return results

                # Wait for JS-rendered content
                JS_CONTENT_SELECTORS = 'h1, [class*="price"], [class*="Price"], [class*="address"], [class*="Address"], [class*="listing"], [class*="property-detail"]'
                try:
                    await page.wait_for_selector(JS_CONTENT_SELECTORS, timeout=8000)
                    print("✓ Content selectors found")
                except Exception:
                    print("⚠️ Content selectors not found within 8s, falling back to sleep")
                    await asyncio.sleep(4)

                # Extract text
                print("Extracting text...")
                results['data']['text'] = await self.extract_all_text_robust(page)

                # Post-extraction block check (some sites return 200 but serve challenge page)
                visible = results['data']['text'].get('visible_text', '')
                if len(visible) < 200 and self._is_blocked(status_code, visible):
                    print(f"⚠️ Bot-blocked (challenge page) on {self._domain}")
                    results['statistics'] = {
                        'extraction_success': False,
                        'error': 'bot_blocked',
                        'blocked_domain': self._domain,
                    }
                    return results

                # Extract images
                print("\nExtracting images...")
                results['data']['images'] = await self.extract_all_images_robust(page)

                # Statistics
                results['statistics'] = {
                    'total_images': len(results['data']['images']),
                    'total_text_length': len(results['data']['text'].get('visible_text', '')),
                    'extraction_success': True
                }

                print(f"\n✅ Extraction complete:")
                print(f"   Images: {results['statistics']['total_images']}")
                print(f"   Text: {results['statistics']['total_text_length']} characters")

            except Exception as e:
                print(f"\n❌ Extraction failed: {e}")
                results['statistics'] = {
                    'extraction_success': False,
                    'error': str(e)
                }
            finally:
                await browser.close()

        return results


async def main():
    """Test extraction"""
    url = "https://raywhitemalanandco.com.au/properties/sold-residential/qld/varsity-lakes-4227/townhouse/3344866"

    extractor = RobustPropertyExtractor(url)
    data = await extractor.run_extraction()

    # Save to file
    with open('robust_extraction_output.json', 'w') as f:
        json.dump(data, f, indent=2)

    print(f"\n✅ Saved to: robust_extraction_output.json")

    # Show text sample
    visible_text = data.get('data', {}).get('text', {}).get('visible_text', '')
    if visible_text:
        print(f"\nText sample (first 500 chars):")
        print(visible_text[:500])


if __name__ == "__main__":
    asyncio.run(main())
