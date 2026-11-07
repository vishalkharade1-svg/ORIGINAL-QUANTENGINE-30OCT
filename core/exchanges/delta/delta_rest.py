"""
====================================================

Delta REST Client

Shared REST interface used by all Delta modules.

====================================================
"""

import time

import httpx


class DeltaREST:

    BASE_URL = "https://api.delta.exchange"

    def __init__(self, max_retries=3, backoff_base=1.0, base_url=None):

        # Environment separation: callers must pass an explicit base_url
        # to reach any non-default host (e.g. the India Testnet catalog).
        # The default preserves the legacy Global endpoint byte-for-byte
        # so existing callers are behavior-neutral.
        self.base_url = (base_url or self.BASE_URL).rstrip("/")
        self.client = httpx.Client(

            base_url=self.base_url,

            timeout=20,

        )
        self.max_retries = max_retries
        self.backoff_base = backoff_base

    def _request_with_retry(self, method, endpoint, **kwargs):
        """429-aware request with Retry-After + exponential backoff (9S)."""
        last_exc = None
        for attempt in range(self.max_retries + 1):
            response = getattr(self.client, method)(endpoint, **kwargs)
            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                try:
                    wait = float(retry_after) if retry_after is not None else self.backoff_base * (2 ** attempt)
                except (ValueError, TypeError):
                    wait = self.backoff_base * (2 ** attempt)
                # Cap wait at 30s
                wait = min(wait, 30.0)
                if attempt < self.max_retries:
                    time.sleep(wait)
                    last_exc = httpx.HTTPStatusError(f"429 Too Many Requests (retry {attempt+1}/{self.max_retries})", request=response.request, response=response)
                    continue
                response.raise_for_status()
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                last_exc = exc
                if attempt < self.max_retries and response.status_code >= 500:
                    wait = self.backoff_base * (2 ** attempt)
                    time.sleep(wait)
                    continue
                raise
            return response.json()
        if last_exc is not None:
            raise last_exc
        raise httpx.HTTPStatusError("Max retries exceeded", request=None, response=None)

    # -------------------------------------------------

    def get(

        self,

        endpoint,

        params=None,

        headers=None,

    ):

        return self._request_with_retry("get", endpoint, params=params, headers=headers)

    # -------------------------------------------------

    def post(

        self,

        endpoint,

        json=None,

        headers=None,

    ):

        return self._request_with_retry("post", endpoint, json=json, headers=headers)