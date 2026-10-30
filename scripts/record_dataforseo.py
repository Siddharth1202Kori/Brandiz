"""Records live DataForSEO responses next to the hand-built test fixtures, for diffing.

    uv run python scripts/record_dataforseo.py            # ~ $0.15 of DataForSEO credit

Writes packages/providers/tests/fixtures/dataforseo/recorded/*.json (git-ignored).
Compare with the hand-built fixtures; if the shape changed, update make_fixtures.py + normalizers.
"""

import asyncio
import json
import sys
from decimal import Decimal
from pathlib import Path

from seomaster_core.config import get_settings
from seomaster_core.markets import Market
from seomaster_providers.dataforseo.adapter import PATHS
from seomaster_providers.dataforseo.client import DataForSEOClient

OUT = Path(__file__).parents[1] / "packages/providers/tests/fixtures/dataforseo/recorded"
KW = "seo tools"
GEO = {"location_code": Market.US.location_code, "language_code": "en"}
CALLS = {
    "keyword_overview": (PATHS["overview"], {"keywords": [KW], **GEO, "include_serp_info": True}),
    "keyword_ideas": (PATHS["ideas"], {"keywords": [KW], **GEO, "limit": 5}),
    "related_keywords": (PATHS["related"], {"keyword": KW, **GEO, "depth": 1, "limit": 5}),
    "keyword_suggestions": (PATHS["suggestions"], {"keyword": KW, **GEO, "limit": 5}),
    "bulk_keyword_difficulty": (PATHS["difficulty"], {"keywords": [KW, "rank tracker"], **GEO}),
    "search_intent": (PATHS["intents"], {"keywords": [KW], "language_code": "en"}),
    "serp_organic": (PATHS["serp"], {"keyword": KW, **GEO, "depth": 10}),
}


async def main() -> int:
    s = get_settings()
    if not (s.dataforseo_login and s.dataforseo_password.get_secret_value()):
        print("Set DATAFORSEO_LOGIN and DATAFORSEO_PASSWORD in .env first.")
        return 1
    client = DataForSEOClient(
        s.dataforseo_login, s.dataforseo_password.get_secret_value(), base_url=s.dataforseo_base_url
    )
    # Raw httpx access so the file holds the full envelope, exactly as DataForSEO sent it.
    http = client._http
    OUT.mkdir(parents=True, exist_ok=True)
    total = Decimal(0)
    try:
        for name, (path, body) in CALLS.items():
            resp = await http.post(path, json=[body])
            data = resp.json()
            total += Decimal(str(data.get("cost") or 0))
            (OUT / f"{name}.json").write_text(json.dumps(data, indent=2) + "\n")
            print(f"{name:26} HTTP {resp.status_code}  status {data.get('status_code')}")
    finally:
        await client.aclose()
    print(f"spent ${total}; files in {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
