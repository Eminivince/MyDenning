"""Shared HTTP client with retry, rate limiting, and circuit breaker for all adapters."""

import asyncio
import time
from typing import Any

import httpx
import structlog

logger = structlog.get_logger(__name__)


class AdapterHTTPClient:
    """Resilient HTTP client shared across all legal source adapters.

    Features:
    - Automatic retry with exponential backoff
    - Per-adapter rate limiting
    - Circuit breaker (open after N consecutive failures)
    - Request/response logging
    """

    def __init__(
        self,
        base_url: str,
        adapter_name: str,
        rate_limit_per_minute: int = 30,
        max_retries: int = 3,
        timeout: float = 30.0,
        headers: dict[str, str] | None = None,
        circuit_breaker_threshold: int = 5,
    ):
        self.base_url = base_url.rstrip("/")
        self.adapter_name = adapter_name
        self.rate_limit_per_minute = rate_limit_per_minute
        self.max_retries = max_retries
        self.timeout = timeout
        self.default_headers = headers or {}

        # Rate limiting state
        self._request_times: list[float] = []

        # Circuit breaker state
        self._consecutive_failures = 0
        self._circuit_breaker_threshold = circuit_breaker_threshold
        self._circuit_open_until: float = 0

        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=self.default_headers,
                timeout=httpx.Timeout(self.timeout),
                follow_redirects=True,
            )
        return self._client

    async def get(self, path: str, params: dict[str, Any] | None = None) -> dict | str:
        return await self._request("GET", path, params=params)

    async def post(self, path: str, json: dict | None = None, data: dict | None = None) -> dict | str:
        return await self._request("POST", path, json=json, data=data)

    async def _request(self, method: str, path: str, **kwargs) -> dict | str:
        # Circuit breaker check
        if self._is_circuit_open():
            raise ConnectionError(
                f"Circuit breaker open for {self.adapter_name}. "
                f"Will retry after {int(self._circuit_open_until - time.time())}s"
            )

        # Rate limiting
        await self._wait_for_rate_limit()

        client = await self._get_client()
        last_error = None

        for attempt in range(self.max_retries):
            try:
                response = await client.request(method, path, **kwargs)

                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 60))
                    logger.warning(
                        "rate_limited",
                        adapter=self.adapter_name,
                        retry_after=retry_after,
                    )
                    await asyncio.sleep(min(retry_after, 120))
                    continue

                response.raise_for_status()
                self._consecutive_failures = 0

                content_type = response.headers.get("content-type", "")
                if "json" in content_type:
                    return response.json()
                elif "xml" in content_type:
                    return response.text
                else:
                    return response.text

            except httpx.HTTPStatusError as e:
                last_error = e
                if e.response.status_code in (500, 502, 503, 504):
                    wait = (2 ** attempt) * 1.5
                    logger.warning(
                        "server_error_retrying",
                        adapter=self.adapter_name,
                        status=e.response.status_code,
                        attempt=attempt + 1,
                        wait=wait,
                    )
                    await asyncio.sleep(wait)
                else:
                    self._record_failure()
                    raise

            except (httpx.ConnectError, httpx.TimeoutException, httpx.ReadTimeout) as e:
                last_error = e
                wait = (2 ** attempt) * 2
                logger.warning(
                    "connection_error_retrying",
                    adapter=self.adapter_name,
                    error=str(e),
                    attempt=attempt + 1,
                    wait=wait,
                )
                await asyncio.sleep(wait)

        self._record_failure()
        raise ConnectionError(
            f"Failed to reach {self.adapter_name} after {self.max_retries} attempts: {last_error}"
        )

    async def _wait_for_rate_limit(self):
        now = time.time()
        window = now - 60
        self._request_times = [t for t in self._request_times if t > window]

        if len(self._request_times) >= self.rate_limit_per_minute:
            sleep_time = 60 - (now - self._request_times[0])
            if sleep_time > 0:
                logger.debug("rate_limit_waiting", adapter=self.adapter_name, sleep=sleep_time)
                await asyncio.sleep(sleep_time)

        self._request_times.append(time.time())

    def _record_failure(self):
        self._consecutive_failures += 1
        if self._consecutive_failures >= self._circuit_breaker_threshold:
            self._circuit_open_until = time.time() + 300  # 5 min cool-down
            logger.error(
                "circuit_breaker_opened",
                adapter=self.adapter_name,
                failures=self._consecutive_failures,
            )

    def _is_circuit_open(self) -> bool:
        if time.time() > self._circuit_open_until:
            if self._consecutive_failures >= self._circuit_breaker_threshold:
                self._consecutive_failures = 0  # reset for half-open state
            return False
        return True

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def ping(self) -> bool:
        try:
            client = await self._get_client()
            response = await client.get("/")
            return response.status_code < 500
        except Exception:
            return False
