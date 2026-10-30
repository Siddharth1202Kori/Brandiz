"""Writes the hand-built DataForSEO fixtures (shapes follow the v3 docs).

Re-record against the live API with `uv run python scripts/record_dataforseo.py` and diff.
"""

import json
from pathlib import Path

OUT = Path(__file__).parent / "dataforseo"


def envelope(
    result, *, cost=0.0101, code=20000, msg="Ok.", task_id="10301234-1234-0066-0000-abcdef012345"
):
    return {
        "version": "0.1.20260901",
        "status_code": 20000,
        "status_message": "Ok.",
        "time": "0.4812 sec.",
        "cost": cost,
        "tasks_count": 1,
        "tasks_error": 0 if code in (20000, 20100) else 1,
        "tasks": [
            {
                "id": task_id,
                "status_code": code,
                "status_message": msg,
                "time": "0.4011 sec.",
                "cost": cost,
                "result_count": len(result or []),
                "path": ["v3", "..."],
                "data": {},
                "result": result,
            }
        ],
    }


def monthly(base, start=(2025, 10)):
    y, m = start
    rows = []
    for i in range(12):  # newest first, like DataForSEO
        rows.append({"year": y, "month": m, "search_volume": base + i * 10})
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return rows


def labs_item(kw, vol, kd, cpc, comp, main="commercial", foreign=None, serp_types=None):
    return {
        "se_type": "google",
        "keyword": kw,
        "location_code": 2840,
        "language_code": "en",
        "search_partners": False,
        "keyword_info": {
            "se_type": "google",
            "last_updated_time": "2026-10-01 12:00:00 +00:00",
            "competition": comp,
            "competition_level": "HIGH" if comp and comp > 0.66 else "MEDIUM",
            "cpc": cpc,
            "search_volume": vol,
            "low_top_of_page_bid": 1.2,
            "high_top_of_page_bid": 6.4,
            "categories": [10004, 10019],
            "monthly_searches": monthly(vol or 0) if vol is not None else None,
            "search_volume_trend": {"monthly": 2, "quarterly": 5, "yearly": -3},
        },
        "keyword_properties": {
            "se_type": "google",
            "core_keyword": None,
            "synonym_clustering_algorithm": "text_processing",
            "keyword_difficulty": kd,
            "detected_language": "en",
            "is_another_language": False,
        },
        "serp_info": {
            "se_type": "google",
            "check_url": "https://www.google.com/search?q=x",
            "serp_item_types": serp_types or ["organic", "people_also_ask", "related_searches"],
            "se_results_count": 1630000000,
            "last_updated_time": "2026-10-10 00:00:00 +00:00",
            "previous_updated_time": "2026-09-10 00:00:00 +00:00",
        },
        "avg_backlinks_info": None,
        "search_intent_info": {
            "se_type": "google",
            "main_intent": main,
            "foreign_intent": foreign or ["informational"],
            "last_updated_time": "2026-09-20 00:00:00 +00:00",
        },
    }


def labs_result(items, total=None):
    return [
        {
            "se_type": "google",
            "seed_keywords": ["seo tools"],
            "location_code": 2840,
            "language_code": "en",
            "total_count": total if total is not None else len(items),
            "items_count": len(items),
            "offset": 0,
            "items": items,
        }
    ]


IDEAS = [
    labs_item("seo tools", 49500, 82, 9.12, 0.31),
    labs_item("Free SEO Tools", 18100, 71, 4.25, 0.45, main="transactional"),
    labs_item("seo tools  for  agencies", 880, 55, 18.4, 0.72),
    labs_item("best seo tools", 6600, 77, 11.9, 0.38),
    labs_item("seo checker", None, None, None, None, main="navigational", foreign=[]),
]

files = {
    "keyword_overview.json": envelope(labs_result([IDEAS[0]])),
    "keyword_overview_empty.json": envelope(
        labs_result([]) and [{**labs_result([])[0], "items": None}]
    ),
    "keyword_ideas.json": envelope(labs_result(IDEAS, total=12345), cost=0.0105),
    "keyword_suggestions.json": envelope(labs_result(IDEAS[1:4]), cost=0.0103),
    "related_keywords.json": envelope(
        labs_result(
            [
                {"se_type": "google", "keyword_data": it, "depth": d, "related_keywords": ["x"]}
                for d, it in enumerate(IDEAS[:3])
            ]
        ),
        cost=0.0103,
    ),
    "bulk_keyword_difficulty.json": envelope(
        [
            {
                "se_type": "google",
                "location_code": 2840,
                "language_code": "en",
                "total_count": 3,
                "items_count": 3,
                "items": [
                    {"se_type": "google", "keyword": "seo tools", "keyword_difficulty": 82},
                    {"se_type": "google", "keyword": "Rank Tracker", "keyword_difficulty": 64},
                    {"se_type": "google", "keyword": "obscure phrase", "keyword_difficulty": None},
                ],
            }
        ],
        cost=0.0103,
    ),
    "search_intent.json": envelope(
        [
            {
                "language_code": "en",
                "items_count": 2,
                "items": [
                    {
                        "keyword": "seo tools",
                        "keyword_intent": {"label": "commercial", "probability": 0.81},
                        "secondary_keyword_intents": [
                            {"label": "informational", "probability": 0.42}
                        ],
                    },
                    {
                        "keyword": "buy seo software",
                        "keyword_intent": {"label": "transactional", "probability": 0.93},
                        "secondary_keyword_intents": None,
                    },
                ],
            }
        ],
        cost=0.0012,
    ),
    "serp_organic.json": envelope(
        [
            {
                "keyword": "seo tools",
                "type": "organic",
                "se_domain": "google.com",
                "location_code": 2840,
                "language_code": "en",
                "check_url": "https://www.google.com/search?q=seo+tools",
                "datetime": "2026-10-30 08:00:00 +00:00",
                "spell": None,
                "item_types": [
                    "organic",
                    "people_also_ask",
                    "video",
                    "organic",
                    "related_searches",
                ],
                "se_results_count": 1630000000,
                "items_count": 14,
                "items": (
                    [
                        {
                            "type": "people_also_ask",
                            "rank_group": 1,
                            "rank_absolute": 3,
                            "items": [],
                        }
                    ]
                    + [
                        {
                            "type": "organic",
                            "rank_group": n,
                            "rank_absolute": n + (1 if n > 2 else 0),
                            "position": "left",
                            "domain": f"www.site{n}.com",
                            "title": f"Result {n}",
                            "url": f"https://www.site{n}.com/seo-tools",
                            "description": "...",
                        }
                        for n in (3, 1, 2, 4, 5, 6, 7, 8, 9, 10, 11, 12)
                    ]
                    + [{"type": "video", "rank_group": 1, "rank_absolute": 8, "items": []}]
                ),
            }
        ],
        cost=0.002,
    ),
    "volume_task_post.json": envelope(
        None,
        cost=0.05,
        code=20100,
        msg="Task Created.",
        task_id="11011200-1535-0110-0000-1a2b3c4d5e6f",
    ),
    "volume_task_get_queued.json": envelope(None, cost=0, code=40602, msg="Task In Queue."),
    "volume_task_get.json": envelope(
        [
            {
                "keyword": "Seo Tools",
                "spell": None,
                "location_code": 2356,
                "language_code": "en",
                "search_partners": False,
                "competition": "HIGH",
                "competition_index": 87,
                "search_volume": 14800,
                "low_top_of_page_bid": 0.4,
                "high_top_of_page_bid": 2.1,
                "cpc": 1.07,
                "monthly_searches": monthly(14800),
            },
            {
                "keyword": "rare phrase",
                "competition": None,
                "competition_index": None,
                "search_volume": None,
                "cpc": None,
                "monthly_searches": None,
            },
        ],
        cost=0,
    ),
    "error_auth.json": {
        "version": "0.1.20260901",
        "status_code": 40100,
        "status_message": "You are not authorized to access this resource.",
        "time": "0 sec.",
        "cost": 0,
        "tasks_count": 0,
        "tasks_error": 0,
        "tasks": None,
    },
    "error_balance.json": {
        "version": "0.1.20260901",
        "status_code": 40200,
        "status_message": "Payment Required. Please top up your balance.",
        "time": "0 sec.",
        "cost": 0,
        "tasks_count": 0,
        "tasks_error": 0,
        "tasks": None,
    },
    "error_invalid_field.json": envelope(
        None, cost=0, code=40501, msg="Invalid Field: 'location_code'."
    ),
    "error_internal.json": envelope(None, cost=0, code=50000, msg="Internal Error."),
}

if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    for name, body in files.items():
        (OUT / name).write_text(json.dumps(body, indent=2) + "\n")
    print(f"wrote {len(files)} fixtures to {OUT}")
