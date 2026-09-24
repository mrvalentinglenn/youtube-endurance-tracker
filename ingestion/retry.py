"""Shared retry helper, used by every ingestion script that touches the Supabase REST
client, the direct Postgres connection, or the YouTube Data API. One retry loop
(with_retry); two transience checks, one per client stack, since what counts as "the
network dropped, nothing about the request itself was wrong" is a different set of
exception types for httpx (Supabase) than for requests (YouTube).

Supabase/Postgres (is_transient_supabase, the default) retries only:
  - a connection-level httpx error (ReadError, RemoteProtocolError, ConnectError, or a
    timeout) -- the network dropped mid-request, nothing about the request itself was
    wrong;
  - a Postgres statement_timeout (SQLSTATE 57014), surfaced through postgrest's APIError
    -- the same query would very likely succeed on a second, less contended attempt.

YouTube Data API (is_transient_youtube) retries only:
  - a connection-level requests error (ConnectionError, Timeout, ChunkedEncodingError);
  - an HTTP 500, 502, 503 or 504 response.
  403 (quota exceeded) and every other 4xx are never retried: a 403 means the day's
  quota is gone, not that this one call misfired, and any other 4xx means the request
  itself is wrong -- retrying either just spends the retry budget for nothing.

Everything else (a 4xx, a permission error, a constraint violation, a NOT NULL failure)
is raised immediately, with no retry: retrying a request that is wrong by construction
only delays the failure and can never fix it.

Not used for the Shorts HEAD check (youtube.com/shorts/...) -- it stays retry-free by
design, in classify_shorts.py and verify_shorts_check.py, so its failure and 429 counts
stay meaningful for the abort guards that read them. See DECISIONS.md.
"""

import time

import httpx
import requests
from postgrest import APIError

RETRYABLE_HTTPX_EXCEPTIONS = (
    httpx.ReadError,
    httpx.RemoteProtocolError,
    httpx.ConnectError,
    httpx.TimeoutException,  # base class for Connect/Read/Write/PoolTimeout
)

POSTGRES_STATEMENT_TIMEOUT_CODE = "57014"

RETRYABLE_REQUESTS_EXCEPTIONS = (
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
    requests.exceptions.ChunkedEncodingError,
)
RETRYABLE_HTTP_STATUS_CODES = {500, 502, 503, 504}

MAX_ATTEMPTS = 3
RETRY_DELAYS_SECONDS = (2, 4)  # waited before attempt 2, then before attempt 3


def is_transient_supabase(error):
    """True only for a connection-level httpx failure or a Postgres statement_timeout
    surfaced through postgrest's APIError. Anything else -- a 4xx, a permission error,
    a constraint violation -- is not transient and must fail immediately."""
    if isinstance(error, RETRYABLE_HTTPX_EXCEPTIONS):
        return True
    if isinstance(error, APIError) and error.code == POSTGRES_STATEMENT_TIMEOUT_CODE:
        return True
    return False


def is_transient_youtube(error):
    """True only for a connection-level requests failure or an HTTP 500/502/503/504
    response (from response.raise_for_status()). A 403 (quota exceeded) or any other
    4xx is not transient and must fail immediately -- see the module docstring."""
    if isinstance(error, RETRYABLE_REQUESTS_EXCEPTIONS):
        return True
    if isinstance(error, requests.exceptions.HTTPError):
        response = error.response
        return response is not None and response.status_code in RETRYABLE_HTTP_STATUS_CODES
    return False


def with_retry(operation, func, *args, is_transient=is_transient_supabase, **kwargs):
    """Calls func(*args, **kwargs), retrying up to MAX_ATTEMPTS times when the error is
    transient (see is_transient_supabase / is_transient_youtube). `operation` is a
    short label for the log line only -- e.g. "channels.update" -- never a key or a URL
    (a YouTube URL carries the API key in its query string). Raises immediately on a
    non-transient error, with no retry. Re-raises the last error if every attempt is
    transient and still fails.
    """
    last_error = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            return func(*args, **kwargs)
        except Exception as error:
            if not is_transient(error):
                raise
            last_error = error
            if attempt < MAX_ATTEMPTS:
                delay = RETRY_DELAYS_SECONDS[attempt - 1]
                print(
                    f"  Retrying {operation} after {type(error).__name__} "
                    f"(attempt {attempt}/{MAX_ATTEMPTS}, waiting {delay}s)...",
                    flush=True,
                )
                time.sleep(delay)
    raise last_error
