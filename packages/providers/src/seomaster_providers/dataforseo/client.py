"""DataForSEO v3 HTTP client: basic auth, bounded retries with jitter, typed errors, cost.

Every v3 response looks like
    {"status_code": 20000, "cost": 0.01,
     "tasks": [{"status_code": 20000, "cost": 0.01, "result": [...]}]}
The top-level code covers the request (auth, balance), each task has its own code.
We always send exactly one task per request, so `post` returns that task.
"""

import asyncio
import logging
import random
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import httpx

log = logging.getLogger(__name__)

OK = 20000
TASK_CREATED = 20100
IN_QUEUE = {40601, 40602}  # "Task Handed." / "Task In Queue." — queued task not ready yet
RETRYABLE_HTTP = {429, 500, 502, 503, 504}


class DataForSEOError(Exception):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(f"DataForSEO {code}: {message}")
        self.code = code
        self.message = message


class DataForSEOAuthError(DataForSEOError):
    """Bad login/password or account not activated (401xx)."""


class DataForSEOPaymentError(DataForSEOError):
    """Balance is empty (402xx). Top up at app.dataforseo.com."""


class DataForSEORateLimitError(DataForSEOError):
    """Too many requests (HTTP 429 / 40202) after retries."""


class DataForSEORequestError(DataForSEOError):
    """Invalid parameters (other 4xxxx). A bug on our side, never retried."""


class DataForSEOServerError(DataForSEOError):
    """Provider-side or network failure (5xxxx) after retries."""


def error_for(code: int, message: str) -> DataForSEOError:
    if 40100 <= code < 40200:
        return DataForSEOAuthError(code, message)
    if code == 40202:
        return DataForSEORateLimitError(code, message)
    if 40200 <= code < 40300:
        return DataForSEOPaymentError(code, message)
    if code >= 50000:
        return DataForSEOServerError(code, message)
    return DataForSEORequestError(code, message)


@dataclass(frozen=True)
class TaskResponse:
    task_id: str
    status_code: int
    status_message: str
    cost: Decimal
    result: list[dict[str, Any]]

    @property
    def ready(self) -> bool:
        return self.status_code not in IN_QUEUE

    @property
    def first(self) -> dict[str, Any]:
        """Most endpoints put everything in result[0]; empty dict when there is no data."""
        return self.result[0] if self.result else {}


class DataForSEOClient:
    def __init__(
        self,
        login: str,
        password: str,
        *,
        base_url: str = "https://api.dataforseo.com",
        timeout_s: float = 40.0,  # live SERP calls can take ~10 s
        max_attempts: int = 3,
        backoff_s: float = 0.5,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._http = httpx.AsyncClient(
            base_url=f"{base_url.rstrip('/')}/v3/",
            auth=(login, password),
            timeout=httpx.Timeout(timeout_s, connect=5.0),
            transport=transport,
        )
        self.max_attempts = max_attempts
        self.backoff_s = backoff_s

    async def aclose(self) -> None:
        await self._http.aclose()

    async def post(self, path: str, task: dict[str, Any]) -> TaskResponse:
        return await self._request("POST", path, [task])

    async def get(self, path: str) -> TaskResponse:
        return await self._request("GET", path, None)

    async def _request(self, method: str, path: str, body: list[Any] | None) -> TaskResponse:
        last: DataForSEOError = DataForSEOServerError(0, "no attempt made")
        for attempt in range(1, self.max_attempts + 1):
            try:
                resp = await self._http.request(method, path, json=body)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last = DataForSEOServerError(0, f"network error: {exc!r}")
            else:
                if resp.status_code in RETRYABLE_HTTP:
                    last = (
                        DataForSEORateLimitError(429, "rate limited")
                        if resp.status_code == 429
                        else DataForSEOServerError(resp.status_code, resp.reason_phrase)
                    )
                else:
                    try:
                        return self._parse(resp)
                    except (DataForSEOServerError, DataForSEORateLimitError) as exc:
                        last = exc
            if attempt < self.max_attempts:
                delay = self.backoff_s * 2 ** (attempt - 1) * (1 + random.random())  # noqa: S311
                log.warning(
                    "dataforseo %s %s failed (%s); retry in %.1fs", method, path, last, delay
                )
                await asyncio.sleep(delay)
        raise last

    @staticmethod
    def _parse(resp: httpx.Response) -> TaskResponse:
        try:
            data = resp.json()
        except ValueError as exc:
            raise DataForSEOServerError(resp.status_code, "non-JSON response") from exc
        top = int(data.get("status_code") or 0)
        if resp.status_code == 401:
            raise DataForSEOAuthError(top or 40100, str(data.get("status_message", "")))
        if top != OK:
            raise error_for(top, str(data.get("status_message", "")))
        tasks = data.get("tasks") or []
        if not tasks:
            raise DataForSEOServerError(top, "response without tasks")
        task = tasks[0]
        code = int(task.get("status_code") or 0)
        if code not in (OK, TASK_CREATED) and code not in IN_QUEUE:
            raise error_for(code, str(task.get("status_message", "")))
        return TaskResponse(
            task_id=str(task.get("id", "")),
            status_code=code,
            status_message=str(task.get("status_message", "")),
            cost=Decimal(str(task.get("cost") or 0)),
            result=list(task.get("result") or []),
        )
