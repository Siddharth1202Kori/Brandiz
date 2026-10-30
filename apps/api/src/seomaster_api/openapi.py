"""Print the OpenAPI schema (consumed by `openapi-typescript` in apps/web).

Usage: uv run python -m seomaster_api.openapi > apps/web/src/api/openapi.json
"""

import json

from seomaster_api.app import create_app

if __name__ == "__main__":
    print(json.dumps(create_app().openapi(), indent=1))
