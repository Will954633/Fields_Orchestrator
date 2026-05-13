#!/usr/bin/env python3
"""
Hybrid Property Data Extraction - Proof of Concept
Combines rule-based extraction with AI fallback for missing fields
"""

import re
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dateutil import parser as date_parser


class RuleBasedExtractor:
    """Extract property data using regex patterns and heuristics"""

    # Spelled-out numbers → digits
    WORD_TO_NUM = {
        'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
        'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10,
        'single': 1, 'double': 2, 'triple': 3,
    }

    @staticmethod
    def _word_num(match_obj) -> Optional[int]:
        """Convert a spelled-out number word to int."""
        word = match_obj.group(1).lower()
        return RuleBasedExtractor.WORD_TO_NUM.get(word)

    @staticmethod
    def extract_bedrooms(text: str) -> Optional[int]:
        """Extract bedroom count from text"""
        patterns = [
            r'(\d+)\s*bed(?:room)?s?(?:\s|,|$)',
            r'(\d+)\s*br(?:\s|,|$)',
            r'(\d+)B',  # Format like "4B"
            r'(\d+)\s*Beds',  # Format like "3 Beds" or "3Beds"
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return int(match.group(1))

        # Spelled-out: "three bedrooms", "four bedroom"
        m = re.search(r'\b(one|two|three|four|five|six|seven|eight|nine|ten)\s+bed(?:room)?s?\b', text, re.I)
        if m:
            return RuleBasedExtractor.WORD_TO_NUM.get(m.group(1).lower())
        return None

    @staticmethod
    def extract_bathrooms(text: str) -> Optional[int]:
        """Extract bathroom count from text"""
        patterns = [
            r'(\d+)\s*bath(?:room)?s?(?:\s|,|$)',
            r'(\d+)\s*ba(?:\s|,|$)',
            r'(\d+)\s*Baths',  # Format like "2 Baths" or "2Baths"
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return int(match.group(1))

        # Spelled-out: "two bathrooms", "three bathroom"
        m = re.search(r'\b(one|two|three|four|five|six|seven|eight|nine|ten)\s+bath(?:room)?s?\b', text, re.I)
        if m:
            return RuleBasedExtractor.WORD_TO_NUM.get(m.group(1).lower())
        return None

    @staticmethod
    def extract_carspaces(text: str) -> Optional[int]:
        """Extract car space count from text"""
        patterns = [
            r'(\d+)\s*car(?:\s+space|park)?s?(?:\s|,|$)',
            r'(\d+)\s*garage(?:\s|,|$)',
            r'(\d+)\s*Cars',  # Format like "2 Cars" or "2Cars"
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return int(match.group(1))

        # Spelled-out: "double garage", "double lock-up garage", "triple carport"
        m = re.search(r'\b(single|double|triple)\s+(?:lock[- ]?up\s+)?(?:garage|carport|car\s*(?:space|park))', text, re.I)
        if m:
            return RuleBasedExtractor.WORD_TO_NUM.get(m.group(1).lower())
        return None

    @staticmethod
    def extract_structured_bed_bath_car(text: str) -> dict:
        """
        Extract bed/bath/car from structured icon layouts like Harcourts.
        Pattern: numbers on their own lines, e.g. "\\n3\\n2\\n2\\n"
        Returns dict with keys 'bedrooms', 'bathrooms', 'carspaces' (any may be None).
        """
        # Match 2-4 bare numbers on consecutive lines (beds, baths, cars, optionally land)
        # Preceded by optional land size (e.g. "194 \n") or other text
        m = re.search(
            r'(?:^|\n)\s*(\d{1,2})\s*\n\s*(\d{1,2})\s*\n\s*(\d{1,2})\s*(?:\n|$)',
            text,
        )
        if m:
            beds, baths, cars = int(m.group(1)), int(m.group(2)), int(m.group(3))
            # Sanity: beds typically 1-10, baths 1-6, cars 0-6
            if 1 <= beds <= 10 and 0 <= baths <= 6 and 0 <= cars <= 6:
                return {'bedrooms': beds, 'bathrooms': baths, 'carspaces': cars}
        return {}

    @staticmethod
    def extract_price(text: str) -> Optional[str]:
        """
        Extract sale price from text.
        Ignores rental prices (per week / pw / per month / p/week).
        Ignores prices below $10,000 (likely weekly rents or irrelevant figures).
        """
        # Find all dollar amounts with their surrounding context
        for match in re.finditer(r'\$([\d,]+)', text):
            price_str = match.group(0)  # e.g. "$1,215,000"
            price_num = int(match.group(1).replace(',', ''))

            # Skip small numbers — likely weekly rent ($500-$5000) or irrelevant
            if price_num < 10000:
                continue

            # Check same line after the price for rental indicators
            line_end = text.find('\n', match.end())
            context_after = text[match.end():line_end if line_end >= 0 else match.end() + 40].lower()
            if re.search(r'per\s*week|p/\s*week|/\s*week|\bpw\b|per\s*month|/\s*month|p/\s*month', context_after):
                continue

            # Check same line before the price for "rental appraisal" context
            line_start = text.rfind('\n', max(0, match.start() - 80), match.start())
            context_before = text[line_start + 1 if line_start >= 0 else max(0, match.start() - 40):match.start()].lower()
            if re.search(r'rental\s+appraisal', context_before):
                continue

            return price_str

        return None

    @staticmethod
    def is_rental_listing(text: str, title: str = '') -> bool:
        """
        Detect if this is a rental/lease listing rather than a sale.

        Strategy:
        1. Trust the page title first — it's the most reliable signal.
           "House Sold" → not rental. "Unit Leased" / "For Rent" → rental.
        2. If title indicates sold, return False immediately regardless of body text.
        3. Only use body text signals if the title gives no clear status.
           Use strong signals only (price per week) not weak ones (word "rental").
        """
        title_lower = title.lower()

        # Title explicitly says sold → definitely not a rental
        if 'sold' in title_lower:
            return False

        # Title explicitly says for sale → not a rental
        if 'for sale' in title_lower:
            return False

        # Title has sale price indicators → not a rental
        if re.search(r'\boffers?\s+(?:above|over|from|around)\b|\bprice\s+guide\b|\bauction\b', title_lower):
            return False

        # Title explicitly says leased / for rent / for lease → rental
        if re.search(r'\bleased\b|for\s+rent\b|for\s+lease\b', title_lower):
            return True

        # Body text strong signals — check early visible text for "Rented" status badge
        # (e.g. Robina Realty pages show "Rented\nThis property is currently not available.")
        text_start = text[:300].lower()
        if re.search(r'\brented\b', text_start):
            return True

        # Title is ambiguous — check body text but only for strong signals
        # "per week" / "$X per week" / "pw" near a price are reliable rental indicators
        # Exclude "rental appraisal" context — for-sale listings often include rental estimates
        text_lower = text.lower()

        # Strip "rental appraisal" sections before checking for rental signals
        text_no_appraisal = re.sub(
            r'rental\s+appraisal[:\s]*\$[\d,]+(?:\s*[-–]\s*\$[\d,]+)?\s*(?:per\s+week|/\s*week|\bpw\b|per\s+month|/\s*month)',
            '', text_lower,
        )

        strong_rental_patterns = [
            r'\$[\d,]+\s*(?:per\s+week|/\s*week|\bpw\b)',  # "$580 per week" / "$580pw"
            r'\bfor\s+rent\b',
            r'\bfor\s+lease\b',
        ]
        for pattern in strong_rental_patterns:
            if re.search(pattern, text_no_appraisal):
                return True

        return False

    @staticmethod
    def extract_address(text: str, title: str = '') -> Optional[str]:
        """Extract full address from title or text"""
        # Queensland address pattern
        address_pattern = r'(\d+(?:/\d+)?\s+[A-Za-z\s]+(?:Street|St|Road|Rd|Drive|Dr|Court|Ct|Avenue|Ave|Place|Pl|Crescent|Cres|Circuit|Cct|Way|Boulevard|Blvd|Terrace|Tce|Lane|Ln|Highway|Hwy),\s*[A-Za-z\s]+,\s*QLD\s*\d{4})'

        # Try title first (most reliable)
        if title:
            match = re.search(address_pattern, title, re.IGNORECASE)
            if match:
                return match.group(1)

        # Try body text
        match = re.search(address_pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)

        return None

    @staticmethod
    def parse_address_components(address: str) -> Dict[str, str]:
        """Parse address into components"""
        if not address:
            return {}

        # Pattern: "123 Street Name, Suburb, QLD 4227"
        pattern = r'^(.+?),\s*(.+?),\s*QLD\s*(\d{4})$'
        match = re.search(pattern, address, re.IGNORECASE)

        if match:
            return {
                'street_address': match.group(1).strip(),
                'suburb': match.group(2).strip(),
                'postcode': match.group(3)
            }

        return {}

    @staticmethod
    def extract_land_size(text: str) -> Optional[int]:
        """Extract land size in square meters"""
        patterns = [
            r'(\d+)\s*(?:sqm|m2|m²|square\s+met(?:re|er)s?)',
            r'(\d+)\s*m²',
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return int(match.group(1))
        return None

    @staticmethod
    def extract_property_type(text: str, title: str = '') -> Optional[str]:
        """Extract property type"""
        combined_text = (title + ' ' + text).lower()

        type_keywords = {
            'house': ['house', 'home', 'residence'],
            'townhouse': ['townhouse', 'town house'],
            'apartment': ['apartment', 'apt'],
            'unit': ['unit'],
            'villa': ['villa'],
            'duplex': ['duplex'],
        }

        for prop_type, keywords in type_keywords.items():
            for keyword in keywords:
                if keyword in combined_text:
                    return prop_type.capitalize()

        return None

    @staticmethod
    def extract_features(text: str) -> List[str]:
        """Extract property features"""
        features = []

        feature_keywords = {
            'Pool': ['pool', 'swimming pool', 'inground pool'],
            'Air conditioning': ['air conditioning', 'air con', 'a/c', 'ducted air'],
            'Dishwasher': ['dishwasher'],
            'Balcony': ['balcony', 'balconies'],
            'Deck': ['deck', 'outdoor deck'],
            'Garden': ['garden', 'landscaped'],
            'Garage': ['garage'],
            'Study': ['study', 'home office'],
            'Ensuite': ['ensuite', 'en-suite'],
            'Built-in wardrobes': ['built-in', 'built in wardrobes', 'wardrobe'],
            'Security system': ['security system', 'alarm'],
            'Outdoor entertaining': ['outdoor entertaining', 'alfresco'],
            'Solar': ['solar panels', 'solar power'],
            'Water tank': ['water tank', 'rainwater tank'],
            'Floor heating': ['underfloor heating', 'in-slab heating'],
            'Fireplace': ['fireplace', 'wood fire', 'gas fire'],
            'Walk-in pantry': ['walk-in pantry', 'butlers pantry', "butler's pantry"],
            'Ducted heating': ['ducted heating'],
            'Ceiling fans': ['ceiling fan'],
            'Stone benchtops': ['stone benchtop', 'stone bench top', 'caesarstone'],
            'Polished concrete': ['polished concrete'],
            'Hardwood floors': ['hardwood floor', 'timber floor', 'oak floor'],
            'Tile floors': ['tiled throughout', 'tile flooring'],
            'NBN': ['nbn ready', 'nbn connected', 'nbn fibre'],
            'Pet friendly': ['pet friendly', 'pets allowed'],
            'Gated community': ['gated community', 'gated estate'],
            'Waterfront': ['waterfront', 'canal front', 'lake front'],
            'North-facing': ['north-facing', 'north facing'],
            'Subdividable': ['subdivisible', 'sub-dividable', 'subdivide'],
        }

        text_lower = text.lower()
        for feature, keywords in feature_keywords.items():
            for keyword in keywords:
                if keyword in text_lower:
                    features.append(feature)
                    break  # Only add once per feature

        return features

    @staticmethod
    def extract_price_text(text: str, title: str = '') -> Optional[str]:
        """
        Extract the price/sale guidance as TEXT (not just numeric).
        Production stores values like "Contact Agent", "Auction Sat 18 May",
        "Offers Over $1,200,000", "Under Contract". This complements
        extract_price (which gives the numeric).
        """
        combined = f"{title}\n{text}"
        patterns = [
            # "Under Contract" / "UNDER CONTRACT"
            r"\b(Under\s+Contract)\b",
            # "Auction Sat 18 May 11am" — require an actual date or TBA marker
            r"\b(Auction\s+(?:Sat|Sun|Mon|Tue|Wed|Thu|Fri)(?:\w*)?\s+\d{1,2}\s+[A-Z][a-z]+(?:\s+\d{4})?(?:\s+at\s+\d[^\n]{0,15}|\s+\d[^\n]{0,15})?)\b",
            r"\b(Auction\s+(?:Date\s+)?(?:Set|TBA|TBC|TBD))\b",
            r"\b(Auction\s+(?:on\s+)?\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})\b",
            # "Offers over $1,200,000" / "Offers above $X" / "Offers from $X"
            r"\b((?:Offers?|Asking|Guide|Price\s+Range)\s+(?:Over|Above|From|Around|Of)\s+\$[\d,.]+(?:\s*[Mm](?:illion)?)?(?:\s*-\s*\$[\d,.]+(?:\s*[Mm](?:illion)?)?)?)\b",
            # "For Sale by Negotiation" / "Tender" / "EOI"
            r"\b(For\s+Sale\s+by\s+(?:Negotiation|Tender|EOI|Expression(?:s)?\s+of\s+Interest))\b",
            r"\b(Expression(?:s)?\s+of\s+Interest(?:\s+[Cc]losing[^\n]{0,40})?)\b",
            # "Contact Agent" / "Contact agent for price"
            r"\b(Contact\s+(?:Agent|Office)(?:\s+for\s+(?:Price|Details))?)\b",
            # "Price on Application" / "POA"
            r"\b(Price\s+on\s+Application|POA)\b",
            # Plain "$1,250,000" with optional " neg" suffix
            r"\b(\$[\d,]+(?:\s*-\s*\$[\d,]+)?(?:\s*(?:Negotiable|Neg|ono|o\.n\.o\.))?)\b",
        ]
        for pattern in patterns:
            m = re.search(pattern, combined, re.IGNORECASE)
            if m:
                return m.group(1).strip()
        return None

    # Common Australian title-cased name → loose pattern. Two-to-four word names
    # where each word starts capital and is 2-30 chars. Excludes ALL-CAPS strings.
    _NAME_RE = re.compile(r"\b([A-Z][a-z'’]{1,29}(?:\s+(?:&|and|-)\s+)?(?:\s+[A-Z][a-z'’]{1,29}){1,3})\b")

    # Trigger phrases / lines that often follow an agent name on agency pages.
    _AGENCY_HINTS = (
        'harcourts', 'ray white', 'raywhite', 'mcgrath', 'remax', 're/max',
        'coastal', 'ljhooker', 'lj hooker', 'property hub', 'prd',
        'century 21', 'barry plant', 'mcdermott', 'gcsr', 'robinarealty',
        'orrentopolansky', 'crasto', 'robinafn', 'belle property',
        'first national', 'stone real estate', '@realty', 'realty',
        'image property', 'coronis', 'whitefox',
    )

    @staticmethod
    def extract_agents(text: str) -> List[str]:
        """
        Extract probable agent name(s).
        Heuristic: title-cased 2-3 word name on a line, immediately followed
        within 1-2 lines by an agency-name line. Filters out duplicates and
        obvious non-name tokens.
        """
        names: List[str] = []
        lines = [l.strip() for l in text.split("\n")]
        for i, line in enumerate(lines):
            if not line or len(line) < 4 or len(line) > 50:
                continue
            # Skip lines with non-name characters or ellipsis (heading-style)
            if any(c in line for c in "()$#@/\\|…"):
                continue
            # Skip lines ending in colon (typical for labels)
            if line.endswith(":"):
                continue
            # Must look like a name (2-4 title-case tokens) — every token must
            # be alphabetic, start uppercase, and have at least one lowercase
            # char (so we reject all-digits like "07 5578 8800" and ALL-CAPS
            # banners like "UNDER CONTRACT").
            words = line.split()
            if not (2 <= len(words) <= 4):
                continue
            if not all(
                w[:1].isalpha()
                and w[:1].isupper()
                and len(w) >= 2
                and any(c.islower() for c in w)
                for w in words
            ):
                continue
            # Skip if any word is in a stoplist (months, common headers, etc.)
            STOPWORDS = {'Property', 'Features', 'Building', 'Outgoings', 'Map',
                         'Location', 'Inspection', 'Open', 'Home', 'Repayment',
                         'Listings', 'Listing', 'About', 'Contact', 'Email',
                         'Phone', 'Office', 'Find', 'View', 'Show', 'More',
                         'Apartment', 'House', 'Townhouse', 'Unit', 'Villa',
                         'Sale', 'Sold', 'Rent', 'Lease', 'Robina', 'Queensland',
                         'Australia', 'Need', 'Get', 'Calculate', 'Speak',
                         'January', 'February', 'March', 'April', 'May', 'June',
                         'July', 'August', 'September', 'October', 'November',
                         'December', 'Year', 'Month', 'Week', 'Day', 'Today',
                         'Yesterday', 'Tomorrow', 'Privacy', 'Cookie',
                         'Disclaimer', 'Copyright', 'All', 'You', 'Might',
                         'Also', 'Like', 'Past', 'Recent', 'Latest', 'Featured',
                         'Similar', 'Related', 'Discover', 'Subscribe', 'Click',
                         'Read', 'Watch', 'See', 'Welcome', 'New', 'Sold',
                         'Auction', 'Inspection', 'Now', 'Stunning', 'Beautiful',
                         'Spacious', 'Modern', 'Luxury', 'Master', 'First',
                         'Second', 'Ground', 'Floor', 'Real', 'Estate', 'Agency',
                         'Group', 'Company', 'Limited', 'Pty', 'Ltd', 'The'}
            if any(w in STOPWORDS for w in words):
                continue
            # Skip if the candidate line itself contains an agency hint —
            # it's the agency name, not an agent (e.g. "Ray White Robina").
            if any(h in line.lower() for h in RuleBasedExtractor._AGENCY_HINTS):
                continue
            # Look ahead 1-3 lines for an agency hint
            ahead = " ".join(lines[i+1:i+4]).lower()
            if not any(h in ahead for h in RuleBasedExtractor._AGENCY_HINTS):
                continue
            if line not in names:
                names.append(line)
        return names[:3]  # cap at 3 agents per property

    @staticmethod
    def extract_inspection_times(text: str) -> List[str]:
        """
        Extract inspection times. Common formats on agency sites:
        - "Saturday, 11 Apr 11:00am - 11:45am"
        - "Sat 10 May 2026, 10:00 AM - 10:30 AM"
        - "Inspection: Saturday 10 May 11am-11:30am"
        - "Open Home: Sat 10 May, 11.00am - 11.30am"
        """
        results: List[str] = []
        # Collapse newlines to spaces first — many agency sites stack each
        # token on its own line ("Saturday\n4\nApril\n10:30am - 11:00am"),
        # which would otherwise leave newlines embedded in the match.
        single_line = re.sub(r"\s+", " ", text)
        patterns = [
            # Weekday word + day + month [+ year], time-range
            r"((?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)(?:day|nesday|sday|urday)?[,\s]+\d{1,2}\s+[A-Z][a-z]+(?:\s+\d{4})?[,\s]+\d{1,2}[:.]\d{2}\s*(?:am|pm|AM|PM)\s*[-–to]+\s*\d{1,2}[:.]\d{2}\s*(?:am|pm|AM|PM))",
            # Just date + time-range without weekday word
            r"(\d{1,2}\s+[A-Z][a-z]+\s+\d{4}[,\s]+\d{1,2}[:.]\d{2}\s*(?:am|pm)\s*[-–to]+\s*\d{1,2}[:.]\d{2}\s*(?:am|pm))",
        ]
        for pattern in patterns:
            for m in re.finditer(pattern, single_line):
                t = re.sub(r"\s+", " ", m.group(1).strip())
                if t not in results:
                    results.append(t)
        return results[:8]  # cap

    @staticmethod
    def extract_first_listed_date(text: str) -> Optional[str]:
        """
        Extract first-listed-on-agency date. Patterns:
        - "Added 04 February, 2026"
        - "Listed on 04/02/2026"
        - "Date Added: 5 March 2026"
        - "Posted 12 April 2026"
        """
        patterns = [
            r"(?:Added|Date\s+Added|Listed\s+on|Posted|Listed\s+Date)[:\s]+(\d{1,2}\s+[A-Z][a-z]+,?\s+\d{4})",
            r"(?:Added|Date\s+Added|Listed\s+on|Posted|Listed\s+Date)[:\s]+(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})",
        ]
        for p in patterns:
            m = re.search(p, text, re.IGNORECASE)
            if m:
                try:
                    return date_parser.parse(m.group(1), dayfirst=True).isoformat()
                except Exception:
                    continue
        return None

    @staticmethod
    def extract_total_floor_area(text: str) -> Optional[float]:
        """
        Extract internal/floor area in m² (distinct from land_size_sqm).
        Patterns the agencies use:
        - "approx. 110m² layout"
        - "Approx. 112m² of internal living"
        - "Internal Area: 195 sqm"
        - "Living: 192 m²"
        - "Under roof: 245 m²"
        """
        patterns = [
            r"(?:internal\s+living|internal\s+area|floor\s+area|living\s+area|under\s+roof|building)[^\n]{0,40}?(\d{2,4}(?:\.\d+)?)\s*(?:sqm|m²|m2)",
            r"(\d{2,4}(?:\.\d+)?)\s*(?:sqm|m²|m2)\s+(?:of\s+)?(?:internal|under\s+roof|of\s+living|layout)",
            r"approx\.?\s+(\d{2,4}(?:\.\d+)?)\s*m²?\s+(?:layout|of\s+internal)",
            # "Building: 362m²"
            r"\b(?:Building|Floor|House)\s*:\s*(\d{2,4}(?:\.\d+)?)\s*(?:sqm|m²|m2)",
        ]
        for p in patterns:
            m = re.search(p, text, re.IGNORECASE)
            if m:
                try:
                    val = float(m.group(1))
                    if 30 <= val <= 2000:  # sanity bounds
                        return val
                except ValueError:
                    continue
        return None

    @staticmethod
    def extract_floor_plans(images: List[Dict[str, Any]]) -> List[str]:
        """Pluck floor-plan URLs out of the raw images list."""
        plans: List[str] = []
        for img in images:
            url = img.get("url", "").lower()
            alt = img.get("alt", "").lower()
            if (
                "floor plan" in alt
                or "floorplan" in alt
                or "floor-plan" in url
                or "floorplan" in url
                or "/fp/" in url
                or "_fp_" in url
            ):
                if img["url"] not in plans:
                    plans.append(img["url"])
        return plans

    @staticmethod
    def extract_description(text: str, meta: str = '') -> str:
        """
        Extract the agent's prose description.
        Strategy: prefer meta_description when substantial; otherwise carve
        out body text between the listing title and known footer markers.
        """
        if meta and len(meta.strip()) > 150:
            return meta.strip()
        if not text:
            return ""

        # Find the first paragraph after a "Property for Sale" / "For Sale" / address line
        body = text
        start_markers = [
            r"Property\s+for\s+(?:Sale|Lease|Rent)\s*\n+",
            r"For\s+Sale\s*\n+",
            r"Description\s*\n+",
        ]
        for sm in start_markers:
            m = re.search(sm, body, re.IGNORECASE)
            if m:
                body = body[m.end():]
                break

        # Trim at known footer markers
        end_markers = [
            r"\n+Property\s+Features\b",
            r"\n+Building\s+Facilities\b",
            r"\n+Outgoings\b",
            r"\n+Inspection(?:\s+Times)?\b",
            r"\n+Open\s+(?:Home|for\s+Inspection)\b",
            r"\n+Show\s+More\b",
            r"\n+Map\s+Location\b",
            r"\n+Need\s+to\s+sell\b",
            r"\n+More\s+Properties\b",
            r"\n+Calculate\s+your\b",
            r"\n+Repayment\s+Calculator\b",
        ]
        for em in end_markers:
            m = re.search(em, body, re.IGNORECASE)
            if m:
                body = body[:m.start()]
                break

        body = body.strip()
        # Cap at 3000 chars — production descriptions average ~1500
        return body[:3000] if len(body) > 50 else (text[:1500].strip() if text else "")

    @staticmethod
    def extract_sold_date(text: str) -> Optional[datetime]:
        """
        Extract sold date from text.
        Handles formats used by Ray White, Harcourts, Coastal, PRD, etc:
        - "Sold for $1,215,000 on 15 May 2024"
        - "Sold on 15/05/2024"
        - "Sold Date: 06 March, 2025"
        - "Sold: 06 March 2025"
        - "Date Sold: 06/03/2025"
        """
        patterns = [
            # "Sold for $X on 15 May 2024" — Ray White / Coastal: DD Mon YYYY
            r'[Ss]old\s+for\s+\$[\d,]+\s+on\s+(\d{1,2}\s+\w+\s+\d{4})',
            # "Sold for $X on Mar 03 2025" — REMAX format: Mon DD YYYY (abbreviated month first)
            r'[Ss]old\s+for\s+\$[\d,]+\s+on\s+([A-Za-z]{3}\s+\d{1,2}\s+\d{4})',
            # "Sold on 15 May 2024" / "Sold on Mar 03 2025"
            r'[Ss]old\s+on\s+(\d{1,2}\s+\w+\s+\d{4})',
            r'[Ss]old\s+on\s+([A-Za-z]{3}\s+\d{1,2}\s+\d{4})',
            r'[Ss]old\s+on\s+(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4})',
            # "Sold Date: 06 March, 2025"
            r'sold\s*date\s*[:\-]?\s*(\d{1,2}\s+[a-zA-Z]+,?\s*\d{4})',
            # "Sold: 06 March 2025"
            r'sold\s*[:\-]\s*(\d{1,2}\s+[a-zA-Z]+,?\s*\d{4})',
            # "Sold: 06/03/2025"
            r'sold\s*[:\-]\s*(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4})',
            # "Date Sold: 06 March 2025"
            r'date\s+sold\s*[:\-]?\s*(\d{1,2}\s+[a-zA-Z]+,?\s*\d{4})',
            r'date\s+sold\s*[:\-]?\s*(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4})',
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                date_str = match.group(1)
                try:
                    parsed_date = date_parser.parse(date_str, dayfirst=True)
                    return parsed_date
                except:
                    continue

        return None

    @staticmethod
    def extract_listed_date(text: str) -> Optional[datetime]:
        """
        Extract listing date from text
        Looks for patterns like:
        - Listed: 06 March, 2025
        - Date Listed: 15/02/2025
        - Listed 20 January 2025
        """
        patterns = [
            r'(?:date\s+)?listed\s*[:\-]?\s*([0-9]{1,2}\s+[a-zA-Z]+,?\s*[0-9]{4})',  # Listed: 06 March, 2025
            r'(?:date\s+)?listed\s*[:\-]?\s*([0-9]{1,2}[\/\-][0-9]{1,2}[\/\-][0-9]{2,4})',  # Listed: 06/03/2025
            r'listing\s+date\s*[:\-]?\s*([0-9]{1,2}\s+[a-zA-Z]+,?\s*[0-9]{4})',  # Listing Date: 06 March 2025
            r'listing\s+date\s*[:\-]?\s*([0-9]{1,2}[\/\-][0-9]{1,2}[\/\-][0-9]{2,4})',  # Listing Date: 06/03/2025
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                date_str = match.group(1)
                try:
                    parsed_date = date_parser.parse(date_str, dayfirst=True)
                    return parsed_date
                except:
                    continue

        return None

    @staticmethod
    def is_recent_date(date_obj: Optional[datetime], months: int = 2) -> bool:
        """
        Check if a date is within the last N months

        Args:
            date_obj: datetime object to check
            months: number of months to look back (default 2)

        Returns:
            True if date is within last N months, False otherwise
        """
        if not date_obj:
            return False

        cutoff_date = datetime.now() - timedelta(days=months * 30)
        return date_obj >= cutoff_date


class ImageFilter:
    """Filter property images from all scraped images"""

    @staticmethod
    def filter_property_images(images: List[Dict[str, Any]], max_images: int = 30) -> List[str]:
        """
        Filter out UI elements, logos, icons and return property images

        Args:
            images: List of image dicts with 'url' and 'alt' keys
            max_images: Maximum number of images to return

        Returns:
            List of filtered image URLs
        """
        filtered = []
        priority = []

        skip_keywords = [
            'logo', 'icon', 'button', 'nav', 'menu', 'social',
            'facebook', 'twitter', 'instagram', 'linkedin',
            'avatar', 'profile', 'badge', 'banner'
        ]

        size_indicators = ['w100', 'h100', 'w50', 'h50', '100x100', '50x50']

        priority_keywords = [
            'bedroom', 'kitchen', 'bathroom', 'living', 'exterior',
            'view', 'lounge', 'dining', 'pool', 'garden', 'property'
        ]

        for img in images:
            url = img.get('url', '').lower()
            alt = img.get('alt', '').lower()

            # Skip obvious UI elements
            if any(skip in url for skip in skip_keywords):
                continue

            # Skip small images (likely icons)
            if any(size in url for size in size_indicators):
                continue

            # Skip SVG logos
            if url.endswith('.svg'):
                continue

            # Prioritize images with property-related alt text
            if any(word in alt for word in priority_keywords):
                priority.append(img['url'])
            else:
                filtered.append(img['url'])

        # Return priority images first, then others
        result = priority + filtered
        return result[:max_images]


class HybridExtractor:
    """
    Hybrid extraction combining rule-based extraction with AI fallback
    """

    def __init__(self, use_ai_fallback: bool = False, openai_api_key: str = None):
        """
        Initialize hybrid extractor

        Args:
            use_ai_fallback: Whether to use AI for missing fields (requires OpenAI API)
            openai_api_key: OpenAI API key (optional, only needed if use_ai_fallback=True)
        """
        self.rule_extractor = RuleBasedExtractor()
        self.image_filter = ImageFilter()
        self.use_ai_fallback = use_ai_fallback
        self.openai_api_key = openai_api_key

        if use_ai_fallback and not openai_api_key:
            print("⚠️ Warning: AI fallback enabled but no API key provided")

    def extract_property_data(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract structured property data from raw scraped data

        Args:
            raw_data: Raw data from GenericPropertyExtractor

        Returns:
            Structured property data dictionary
        """
        text_data = raw_data.get('data', {}).get('text', {})
        # The GenericPropertyExtractor uses 'visible_text' not 'body_text'
        body_text = text_data.get('visible_text', '') or text_data.get('body_text', '')
        title = text_data.get('page_title', '') or text_data.get('title', '')
        meta_description = text_data.get('meta_description', '')
        target_url = (raw_data.get('target_url') or '').lower()

        # Fix 16b: propertyhub.harcourts.com.au/listing/ has address in title, body empty
        # Status is implied by the active listing page (no -sold suffix = for_sale)
        if 'propertyhub.harcourts.com.au/listing/' in target_url:
            if '/sold-' in target_url or '-sold' in target_url:
                listing_status = 'sold'
            elif '/leased-' in target_url or '-leased' in target_url:
                listing_status = 'leased'
            else:
                listing_status = 'for_sale'  # active listing page

        # Fix 21: Detect 404 / "page not found" pages and return page_unavailable
        # These occur when a listing has been removed but the URL path still says
        # "residential-for-sale", causing the URL-path fallback to return for_sale.
        _body_lower = body_text.lower()
        _title_lower = title.lower()
        _page_not_found = (
            '404' in _title_lower or
            'page not found' in _title_lower or
            'page not found' in _body_lower or
            ('could not be found' in _body_lower and len(body_text) < 1500) or
            ('sorry' in _body_lower and 'not found' in _body_lower and len(body_text) < 1500)
        )
        if _page_not_found:
            return {
                'listing_status': 'page_unavailable',
                'address': None,
                'suburb': None,
                'sale_price': None,
                'sold_date': None,
                'bedrooms': None,
                'bathrooms': None,
                'carspaces': None,
                'land_size_sqm': None,
                'property_type': None,
                'features': [],
                'extraction_method': 'page_not_found',
                'extraction_confidence': 0,
                'missing_fields': [],
            }

        # Fix 16: PRD /property-search/ pages are address-indexed profiles with no status info
        # Body is only nav/contact text — force 'unknown' to avoid perpetual None
        if ('prd.com.au' in target_url and
                ('/property-search/' in target_url or '/corporate-search/' in target_url)):
            # Return early with unknown status — we at least have the address
            result = {
                'listing_status': 'unknown',
                'address': title or '',
                'suburb': '',
                'sale_price': None,
                'sold_date': None,
                'bedrooms': None,
                'bathrooms': None,
                'car_spaces': None,
                'land_size': None,
                'property_type': None,
                'agency': 'prd',
                'agent': None,
            }
            return result

        # Combine text sources for better extraction
        combined_text = f"{title} {meta_description} {body_text}"

        # Fix 4: Detect rental listings first — affects price extraction logic
        is_rental = self.rule_extractor.is_rental_listing(body_text, title)
        listing_category_override = 'rental' if is_rental else None

        # Rule-based extraction
        extracted = {
            'bedrooms': self.rule_extractor.extract_bedrooms(combined_text),
            'bathrooms': self.rule_extractor.extract_bathrooms(combined_text),
            'carspaces': self.rule_extractor.extract_carspaces(combined_text),
            # Fix 4: Pass full text — extract_price now skips rental amounts internally
            'sale_price': None if is_rental else self.rule_extractor.extract_price(combined_text),
            'price': None if is_rental else self.rule_extractor.extract_price_text(combined_text, title),
            'address': self.rule_extractor.extract_address(combined_text, title),
            'land_size_sqm': self.rule_extractor.extract_land_size(combined_text),
            'total_floor_area': self.rule_extractor.extract_total_floor_area(combined_text),
            'property_type': self.rule_extractor.extract_property_type(combined_text, title),
            'features': self.rule_extractor.extract_features(combined_text),
            'agent_names': self.rule_extractor.extract_agents(body_text),
            'inspection_times': self.rule_extractor.extract_inspection_times(combined_text),
            'first_listed_date': self.rule_extractor.extract_first_listed_date(combined_text),
        }
        # Derive agent_name singular from the first agent name we found
        extracted['agent_name'] = extracted['agent_names'][0] if extracted['agent_names'] else None

        # Fallback: structured icon layout (e.g. Harcourts "3\n2\n2")
        if not extracted['bathrooms'] or not extracted['carspaces']:
            structured = self.rule_extractor.extract_structured_bed_bath_car(body_text)
            if structured:
                for key in ('bedrooms', 'bathrooms', 'carspaces'):
                    if not extracted[key] and structured.get(key):
                        extracted[key] = structured[key]

        # Extract dates
        sold_date = self.rule_extractor.extract_sold_date(combined_text)
        listed_date = self.rule_extractor.extract_listed_date(combined_text)

        # Determine listing status and category
        listing_status = None
        listing_category = listing_category_override
        is_recent = False

        if sold_date:
            extracted['sold_date'] = sold_date.isoformat()
            listing_status = 'sold'
            is_recent = self.rule_extractor.is_recent_date(sold_date, months=2)
            if is_recent:
                listing_category = 'recently_sold'

        if listed_date:
            extracted['listed_date'] = listed_date.isoformat()
            if not listing_status:
                listing_status = 'for_sale'
                is_recent = self.rule_extractor.is_recent_date(listed_date, months=2)
                if is_recent:
                    listing_category = 'recently_listed'

        # Fix 3 + Fix 13: URL-path status detection (high confidence), then title fallback
        if not listing_status:
            if any(x in target_url for x in (
                '/sold-residential/', '/sold-commercial/', '/sold-rural/',
                '/properties/sold',
            )):
                listing_status = 'sold'
            elif any(x in target_url for x in (
                '/residential-for-sale/', '/commercial-for-sale/', '/rural-for-sale/',
                '/properties/residential-for-sale',
            )):
                listing_status = 'for_sale'
            elif any(x in target_url for x in (
                '/leased-residential/', '/leased-commercial/',
                '/residential-for-rent/', '/commercial-for-rent/',
                '/properties/leased', '/properties/residential-for-rent',
            )):
                listing_status = 'leased'

        if not listing_status and title:
            title_lower = title.lower()
            # Extended patterns (Fix 13): handles "3 Smith St - Sold House - Agency"
            # and "3 Smith St Sold - Remax" and Harcourts "house sold - harcourts.net"
            if (re.search(r'- sold (house|unit|apartment|townhouse|land|duplex|acreage)', title_lower)
                    or re.search(r'(house|unit|apartment|townhouse|land|duplex) sold', title_lower)
                    or (re.search(r'\bsold\b', title_lower) and 'for sale' not in title_lower)):
                listing_status = 'sold'
            elif (re.search(r'- leased (house|unit|apartment|townhouse|retail)', title_lower)
                    or re.search(r'(house|unit|apartment|townhouse) (for rent|for lease)', title_lower)
                    or 'leased' in title_lower
                    or 'for rent' in title_lower
                    or 'for lease' in title_lower):
                listing_status = 'leased'
            elif (re.search(r'(house|unit|apartment|townhouse|land|duplex) for sale', title_lower)
                    or 'for sale' in title_lower):
                listing_status = 'for_sale'

        # Override status for confirmed rentals
        if is_rental and listing_status not in ('sold',):
            listing_status = 'leased'

        extracted['listing_status'] = listing_status
        extracted['listing_category'] = listing_category
        extracted['is_recent'] = is_recent

        # sold_date_source records how we know the sale date.
        # If we extracted an actual date from the page text, source = "page_text".
        # If the page was sold but had no extractable date, we fall back to the
        # scrape timestamp as a proxy — source = "discovery_date_proxy".
        # Downstream consumers should prefer sold_date over sold_date_proxy,
        # and treat sold_date_proxy as approximate (within days/weeks of actual sale).
        if listing_status == 'sold':
            if extracted.get('sold_date'):
                extracted['sold_date_source'] = 'page_text'
            else:
                extracted['sold_date_proxy'] = datetime.now().isoformat()
                extracted['sold_date_source'] = 'discovery_date_proxy'

        # Parse address components
        if extracted['address']:
            address_components = self.rule_extractor.parse_address_components(extracted['address'])
            extracted.update(address_components)

        # Description — agent prose extracted between known markers (better than
        # the old "meta_description or first 500 chars" approach).
        extracted['description'] = self.rule_extractor.extract_description(
            body_text, meta_description
        )

        # Count missing fields
        missing_fields = [k for k, v in extracted.items()
                         if k not in ['features', 'description'] and v is None]

        # Calculate confidence score
        total_fields = len([k for k in extracted.keys() if k not in ['features', 'description']])
        extracted_fields = total_fields - len(missing_fields)
        confidence = extracted_fields / total_fields if total_fields > 0 else 0

        extracted['extraction_confidence'] = round(confidence, 2)
        extracted['missing_fields'] = missing_fields
        extracted['extraction_method'] = 'RULE_BASED'

        # AI fallback for missing fields (if enabled)
        if self.use_ai_fallback and missing_fields and self.openai_api_key:
            print(f"⚠️ {len(missing_fields)} fields missing, using AI fallback: {missing_fields}")
            # This would call OpenAI API - not implemented in POC
            extracted['extraction_method'] = 'HYBRID_RULE_AI'

        return extracted

    def filter_images(self, raw_data: Dict[str, Any]) -> List[str]:
        """
        Filter property images from raw scraped data.
        Excludes floor plans (returned separately by extract_floor_plans).
        """
        images = raw_data.get('data', {}).get('images', [])
        # Drop floor-plan images from the gallery first
        floor_plan_urls = set(RuleBasedExtractor.extract_floor_plans(images))
        gallery = [img for img in images if img.get('url', '') not in floor_plan_urls]
        return self.image_filter.filter_property_images(gallery)

    def filter_floor_plans(self, raw_data: Dict[str, Any]) -> List[str]:
        """Extract floor-plan URLs as a separate gallery (matches production schema)."""
        images = raw_data.get('data', {}).get('images', [])
        return RuleBasedExtractor.extract_floor_plans(images)

    def create_mongodb_document(self, extracted_data: Dict[str, Any],
                               raw_data: Dict[str, Any],
                               filtered_images: List[str],
                               floor_plans: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Transform extracted data into MongoDB document format.
        """
        suburb_scraped = extracted_data.get('suburb', '').lower().replace(' ', '_')
        if floor_plans is None:
            floor_plans = self.filter_floor_plans(raw_data)

        document = {
            'listing_status': extracted_data.get('listing_status'),
            'address': extracted_data.get('address'),
            'extraction_method': extracted_data.get('extraction_method'),
            'extraction_date': datetime.now().isoformat(),
            'extraction_confidence': extracted_data.get('extraction_confidence'),
            'street_address': extracted_data.get('street_address'),
            'suburb': extracted_data.get('suburb'),
            'postcode': extracted_data.get('postcode'),
            'bedrooms': extracted_data.get('bedrooms'),
            'bathrooms': extracted_data.get('bathrooms'),
            'carspaces': extracted_data.get('carspaces'),
            'property_type': extracted_data.get('property_type'),
            'sale_price': extracted_data.get('sale_price'),
            'price': extracted_data.get('price'),
            'sold_date': extracted_data.get('sold_date'),
            'sold_date_proxy': extracted_data.get('sold_date_proxy'),
            'sold_date_source': extracted_data.get('sold_date_source'),
            'land_size_sqm': extracted_data.get('land_size_sqm'),
            'total_floor_area': extracted_data.get('total_floor_area'),
            'description': extracted_data.get('description'),
            'features': extracted_data.get('features', []),
            'property_images': filtered_images,
            'floor_plans': floor_plans,
            'listing_url': raw_data.get('target_url'),
            'suburb_scraped': suburb_scraped,
            'og_title': raw_data.get('data', {}).get('text', {}).get('title'),
            'agents_description': extracted_data.get('description'),
            'agent_name': extracted_data.get('agent_name'),
            'agent_names': extracted_data.get('agent_names', []),
            'inspection_times': extracted_data.get('inspection_times', []),
            'first_listed_date': extracted_data.get('first_listed_date'),
            'missing_fields': extracted_data.get('missing_fields', []),
        }

        return document

    def process_property(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Complete processing pipeline: Extract → Filter → Transform

        Args:
            raw_data: Raw data from GenericPropertyExtractor

        Returns:
            MongoDB-ready document
        """
        print("\n" + "="*60)
        print("HYBRID EXTRACTION - PROOF OF CONCEPT")
        print("="*60)

        # Step 1: Extract structured data
        print("\n📊 Extracting structured data...")
        extracted_data = self.extract_property_data(raw_data)

        # Step 2: Filter images
        print(f"\n🖼️  Filtering images...")
        filtered_images = self.filter_images(raw_data)

        # Step 3: Create MongoDB document
        print(f"\n📝 Creating MongoDB document...")
        document = self.create_mongodb_document(extracted_data, raw_data, filtered_images)

        # Print summary
        print("\n" + "="*60)
        print("EXTRACTION SUMMARY")
        print("="*60)
        print(f"Address:        {document.get('address', 'NOT FOUND')}")
        print(f"Bedrooms:       {document.get('bedrooms', 'NOT FOUND')}")
        print(f"Bathrooms:      {document.get('bathrooms', 'NOT FOUND')}")
        print(f"Car spaces:     {document.get('carspaces', 'NOT FOUND')}")
        print(f"Property type:  {document.get('property_type', 'NOT FOUND')}")
        print(f"Price:          {document.get('sale_price', 'NOT FOUND')}")
        print(f"Land size:      {document.get('land_size_sqm', 'NOT FOUND')} sqm")
        print(f"Features:       {len(document.get('features', []))} found")
        print(f"Images:         {len(filtered_images)} filtered (from {len(raw_data.get('data', {}).get('images', []))})")
        print(f"Confidence:     {document.get('extraction_confidence', 0)*100:.0f}%")
        print(f"Missing fields: {', '.join(document.get('missing_fields', [])) if document.get('missing_fields') else 'None'}")
        print("="*60)

        return document


def main():
    """Example usage with mock data"""

    # Mock raw data (simulating output from test_generic_extraction.py)
    mock_raw_data = {
        "test_date": "2026-02-17 10:00:00",
        "target_url": "https://example-agency.com.au/property/123",
        "extraction_method": "GENERIC",
        "statistics": {
            "total_images": 45,
            "total_text_length": 2500,
            "extraction_success": True
        },
        "data": {
            "images": [
                {"url": "https://example.com/property-main.jpg", "alt": "Main bedroom with ensuite"},
                {"url": "https://example.com/property-kitchen.jpg", "alt": "Modern kitchen"},
                {"url": "https://example.com/property-exterior.jpg", "alt": "Exterior view"},
                {"url": "https://example.com/logo.png", "alt": "Agency logo"},
                {"url": "https://example.com/icon-w100.png", "alt": "Icon"},
                # ... more images
            ],
            "text": {
                "title": "38 Nardoo Street, Robina, QLD 4226 - House For Sale",
                "meta_description": "Spacious 4 bedroom, 2 bathroom house with pool and air conditioning",
                "body_text": """
                    38 Nardoo Street, Robina, QLD 4226

                    Price: $1,585,000

                    This stunning 4 bedroom, 2 bathroom home offers the perfect family lifestyle.
                    Set on 451 sqm of land, this beautiful house features:

                    - 4 bedrooms with built-in wardrobes
                    - 2 modern bathrooms with ensuite to master
                    - 2 car garage
                    - Inground pool
                    - Air conditioning throughout
                    - Modern kitchen with dishwasher
                    - Outdoor entertaining area
                    - Landscaped gardens

                    Located in the heart of Robina, close to schools, shopping, and transport.

                    Contact: Leanne Jenke from Harcourts Property Hub
                    Phone: 0400 000 000
                """,
                "headings": ["Features", "Location", "Contact"],
                "paragraphs": [],
                "links": []
            },
            "metadata": {}
        }
    }

    # Initialize hybrid extractor (without AI fallback for POC)
    extractor = HybridExtractor(use_ai_fallback=False)

    # Process property
    document = extractor.process_property(mock_raw_data)

    # Save result to file
    output_file = '/Users/projects/Documents/Property_Data_Scraping/12_Individual_Property_Web_Search/poc_output.json'
    with open(output_file, 'w') as f:
        json.dump(document, f, indent=2)

    print(f"\n✅ Document saved to: {output_file}")
    print("\nReady for MongoDB insertion!")


if __name__ == "__main__":
    main()
