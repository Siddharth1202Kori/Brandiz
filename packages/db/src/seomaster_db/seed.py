"""Plan definitions. Placeholder limits — final numbers are a pricing decision (Phase 7).

`ideas_rows_per_report` is a cap (rows visible per Keyword Magic report), not a counter.

Metric periods: see `seomaster_api.services.limits.METRICS`.
"""

from typing import Any

PLANS: list[dict[str, Any]] = [
    {
        "id": "free",
        "name": "Free",
        "limits": {
            "reports_per_day": 10,
            "keyword_ideas_rows": 250,
            "ideas_rows_per_report": 50,
            "keyword_lists": 1,
            "exports_per_day": 0,
            "projects": 1,
            "rank_keywords": 10,
            "audit_pages": 100,
            "gsc_sites": 1,
        },
    },
    {
        "id": "pro",
        "name": "Pro",
        "limits": {
            "reports_per_day": 300,
            "keyword_ideas_rows": 10000,
            "ideas_rows_per_report": 500,
            "keyword_lists": 20,
            "exports_per_day": 50,
            "projects": 5,
            "rank_keywords": 500,
            "audit_pages": 20000,
            "gsc_sites": 5,
        },
    },
    {
        "id": "agency",
        "name": "Agency",
        "limits": {
            "reports_per_day": 1500,
            "keyword_ideas_rows": 50000,
            "ideas_rows_per_report": 500,
            "keyword_lists": 100,
            "exports_per_day": 500,
            "projects": 40,
            "rank_keywords": 2500,
            "audit_pages": 100000,
            "gsc_sites": 40,
        },
    },
]
