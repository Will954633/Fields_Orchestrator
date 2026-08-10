#!/usr/bin/env python3
"""Parse decoded Google SERP HTML into structured JSON. Python-only parsing."""
import json, os, re
from urllib.parse import urlparse
from bs4 import BeautifulSoup

HERE = os.path.dirname(os.path.abspath(__file__))
DEC = os.path.join(HERE, 'decoded')

TRACKED = ['realestate.com.au', 'domain.com.au', 'property.com.au',
           'onthehouse.com.au', 'allhomes.com.au', 'homely.com.au',
           'fieldsestate.com.au', 'propertyvalue.com.au', 'propertyupdate',
           'ratemyagent.com.au', 'openagent.com.au', 'homesales.com.au',
           'soho.com.au', 'view.com.au', 'realestateview.com.au']

PRICE_RE = re.compile(r'\$\s?\d[\d,]*(?:\.\d+)?\s?[mMkK]?\b')


def soup_of(path):
    s = BeautifulSoup(open(path, encoding='utf-8').read(), 'lxml')
    for t in s(['script', 'style', 'noscript']):
        t.decompose()
    return s


def parse(path):
    s = soup_of(path)
    full_text = s.get_text(' ', strip=True)
    res = {}

    # ---- organic results, in document order ----
    organic = []
    for h3 in s.find_all('h3'):
        a = h3.find_parent('a')
        if not a or not a.get('href'):
            continue
        href = a['href']
        title = h3.get_text(' ', strip=True)
        # snippet: nearest ancestor block text minus title
        blk = a
        for _ in range(6):
            if blk.parent:
                blk = blk.parent
        # domain: Google renders the real host in a <cite>; the h3 anchor href
        # is an obfuscated /goto? redirect on some SERP variants.
        dom = ''
        cite = blk.find('cite')
        if cite:
            ct = cite.get_text(' ', strip=True)
            m = re.search(r'https?://([^\s/›]+)', ct)
            if m:
                dom = m.group(1).lower()
        if not dom and href.startswith('http'):
            dom = urlparse(href).netloc.lower()
        if not dom:
            # social/video results label the source as "Instagram · handle"
            lbl = blk.find(string=re.compile(u'·'))
            if lbl:
                dom = '[social] ' + lbl.strip().split(u'·')[0].strip()
        dom = re.sub(r'^www\.', '', dom)
        if not dom:
            continue
        snip = blk.get_text(' ', strip=True)
        snip = snip.replace(title, ' ', 1)
        snip = re.sub(r'\s+', ' ', snip)[:600]
        organic.append({'pos': len(organic) + 1, 'domain': dom,
                        'title': title, 'url': href, 'snippet': snip,
                        'prices_in_snippet': PRICE_RE.findall(snip)})
    res['organic'] = organic

    # ---- People Also Ask ----
    paa = []
    for node in s.find_all(string=re.compile(r'People also ask')):
        blk = node.find_parent('div')
        for _ in range(6):
            if blk and blk.parent:
                blk = blk.parent
        if not blk:
            continue
        for q in blk.find_all(['div', 'span'], attrs={'data-q': True}):
            paa.append(q['data-q'])
        for q in blk.find_all(attrs={'jsname': 'Cpkphb'}):
            t = q.get_text(' ', strip=True)
            if t:
                paa.append(t)
        # fallback: text lines ending in '?'
        for t in blk.stripped_strings:
            t = t.strip()
            if t.endswith('?') and 8 < len(t) < 160:
                paa.append(t)
    res['paa'] = sorted(set(paa))
    res['paa_present'] = 'People also ask' in full_text

    # ---- related / people also search for ----
    rel = []
    for label in ['People also search for', 'Related searches',
                  'Searches related to']:
        for node in s.find_all(string=re.compile(re.escape(label))):
            blk = node.find_parent('div')
            for _ in range(6):
                if blk and blk.parent:
                    blk = blk.parent
            if not blk:
                continue
            for a in blk.find_all('a'):
                t = a.get_text(' ', strip=True)
                href = a.get('href', '')
                if t and ('/search?' in href or 'q=' in href):
                    rel.append(re.sub(r'\s+', ' ', t))
    res['related'] = sorted(set(x for x in rel if 3 < len(x) < 120))

    # ---- SERP features ----
    res['features'] = {
        'map_pack': 'Map results' in full_text or 'Street View' in full_text,
        'street_view': 'Street View' in full_text,
        'sponsored': 'Sponsored' in full_text,
        'knowledge_panel': bool(s.find(attrs={'data-attrid': True})),
        'images_pack': 'Images for' in full_text,
        'videos_pack': 'Videos' in full_text and 'Watch' in full_text,
        'ai_overview': 'AI Overview' in full_text,
    }
    res['prices_anywhere'] = PRICE_RE.findall(full_text)
    res['tracked_positions'] = {}
    for d in TRACKED:
        hits = [o['pos'] for o in organic if d in o['domain']]
        if hits:
            res['tracked_positions'][d] = hits
    return res


if __name__ == '__main__':
    queries = {q['slug']: q for q in
               json.load(open(os.path.join(HERE, 'queries.json')))}
    out = {}
    for f in sorted(os.listdir(DEC)):
        slug = f[:-5]
        out[slug] = {'meta': queries.get(slug, {'slug': slug}),
                     **parse(os.path.join(DEC, f))}
    json.dump(out, open(os.path.join(HERE, 'parsed.json'), 'w'), indent=1)
    for slug, d in out.items():
        print(slug, '| organic=%d' % len(d['organic']),
              '| paa=%s(%d)' % (d['paa_present'], len(d['paa'])),
              '| rel=%d' % len(d['related']),
              '|', {k: v for k, v in d['features'].items() if v})
