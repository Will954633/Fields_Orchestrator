#!/usr/bin/env python3
"""
Property Search using Self-Hosted SearXNG Instance
Unlimited searches, no rate limits, completely free after VPS cost

Uses aiohttp for non-blocking async HTTP so concurrent searches actually
run in parallel rather than serialising on the event loop.
"""

import asyncio
import aiohttp
from typing import List, Dict


class SelfHostedSearXNG:
    """Search using your own SearXNG instance (fully async)"""

    _HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
    }

    def __init__(self, instance_url: str):
        self.instance = instance_url.rstrip('/')
        self._session: aiohttp.ClientSession | None = None
        print(f"Using self-hosted SearXNG: {self.instance}")

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(limit=200, ttl_dns_cache=300)
            self._session = aiohttp.ClientSession(
                headers=self._HEADERS,
                connector=connector,
            )
        return self._session

    async def search(self, query: str, num_results: int = 10) -> List[Dict[str, str]]:
        """
        Search using your SearXNG instance (non-blocking async).

        Args:
            query:       Search query string
            num_results: Maximum results to return

        Returns:
            List of dicts with 'url', 'title', 'content' keys
        """
        print(f"\n🔍 Searching: {query}")
        session = await self._get_session()
        try:
            params = {'q': query, 'format': 'json', 'pageno': 1}
            timeout = aiohttp.ClientTimeout(total=15)
            async with session.get(
                f"{self.instance}/search",
                params=params,
                timeout=timeout,
            ) as response:
                print(f"  Response: {response.status}")
                if response.status != 200:
                    print(f"  Unexpected status: {response.status}")
                    return []
                data = await response.json(content_type=None)
                results = [
                    {
                        'url': r.get('url', ''),
                        'title': r.get('title', ''),
                        'content': r.get('content', ''),
                    }
                    for r in data.get('results', [])[:num_results]
                ]
                print(f"  ✅ Found {len(results)} results")
                return results

        except asyncio.TimeoutError:
            print(f"  SearXNG timeout")
            return []
        except Exception as e:
            print(f"  SearXNG error: {e}")
            return []

    async def close(self):
        """Close the underlying HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
