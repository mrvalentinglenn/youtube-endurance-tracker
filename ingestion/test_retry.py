"""Fakes the errors retry.with_retry is supposed to handle, without touching the
network or the database. Not a pytest suite -- this project has no test framework
installed (see requirements.txt), so this follows the same plain-script convention as
every other ingestion script: prints PASS/FAIL per case and exits non-zero if any fail.

Usage:
    python test_retry.py
"""

import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

from unittest.mock import Mock

import httpx
import requests

import retry
from postgrest.exceptions import APIError


def http_error(status_code):
    """A requests.exceptions.HTTPError carrying a fake .response with just the
    .status_code is_transient_youtube actually reads -- a full Response isn't needed."""
    return requests.exceptions.HTTPError(response=Mock(status_code=status_code))

# Real time.sleep would make this test take (2 + 4) seconds per failing case for no
# reason -- retry.py's own module-level `time` is patched so the retry loop still
# runs, just without the wait.
retry.time.sleep = lambda seconds: None


def make_flaky(exceptions_to_raise, return_value="ok"):
    """Returns a function that raises the next exception from `exceptions_to_raise`
    (a list, consumed in order) on each call, then returns `return_value` once the
    list is empty. Also tracks call_count on the function itself."""
    remaining = list(exceptions_to_raise)

    def flaky():
        flaky.call_count += 1
        if remaining:
            raise remaining.pop(0)
        return return_value

    flaky.call_count = 0
    return flaky


def case_two_transient_then_success():
    """httpx.ReadError twice, then success -- must succeed after two retries (3 calls total)."""
    fn = make_flaky([httpx.ReadError("connection reset"), httpx.ReadError("connection reset")])
    result = retry.with_retry("test op", fn)
    assert result == "ok", f"expected 'ok', got {result!r}"
    assert fn.call_count == 3, f"expected 3 calls (1 + 2 retries), got {fn.call_count}"


def case_three_transient_fails():
    """httpx.ReadError three times -- every attempt is used up and the error is re-raised."""
    fn = make_flaky([httpx.ReadError("a"), httpx.ReadError("b"), httpx.ReadError("c")])
    try:
        retry.with_retry("test op", fn)
    except httpx.ReadError:
        pass
    else:
        raise AssertionError("expected httpx.ReadError to propagate after 3 failed attempts")
    assert fn.call_count == 3, f"expected exactly 3 calls (MAX_ATTEMPTS), got {fn.call_count}"


def case_non_transient_fails_immediately():
    """A non-transient error (e.g. a permission/constraint error, or a plain bug) must
    fail on the first attempt, with no retry at all."""
    fn = make_flaky([ValueError("not a transient error")])
    try:
        retry.with_retry("test op", fn)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError to propagate immediately")
    assert fn.call_count == 1, f"expected exactly 1 call (no retry), got {fn.call_count}"


def case_statement_timeout_is_transient():
    """Postgres 57014 (statement_timeout), surfaced as postgrest.APIError, must retry
    the same as a network error."""
    error = APIError({"code": "57014", "message": "canceling statement due to statement timeout"})
    fn = make_flaky([error])
    result = retry.with_retry("test op", fn)
    assert result == "ok"
    assert fn.call_count == 2, f"expected 2 calls (1 + 1 retry), got {fn.call_count}"


def case_other_api_error_not_transient():
    """A postgrest APIError with a different code (e.g. a constraint violation, 23502
    not-null-violation) must not be retried."""
    error = APIError({"code": "23502", "message": "null value in column violates not-null constraint"})
    fn = make_flaky([error])
    try:
        retry.with_retry("test op", fn)
    except APIError:
        pass
    else:
        raise AssertionError("expected APIError (23502) to propagate immediately")
    assert fn.call_count == 1, f"expected exactly 1 call (no retry), got {fn.call_count}"


def case_youtube_connection_error_then_success():
    """requests.exceptions.ConnectionError twice, then success -- must succeed after
    two retries (3 calls total), using the YouTube transience check."""
    fn = make_flaky([requests.exceptions.ConnectionError("reset"), requests.exceptions.ConnectionError("reset")])
    result = retry.with_retry("test op", fn, is_transient=retry.is_transient_youtube)
    assert result == "ok", f"expected 'ok', got {result!r}"
    assert fn.call_count == 3, f"expected 3 calls (1 + 2 retries), got {fn.call_count}"


def case_youtube_503_then_success():
    """An HTTP 503 (as raise_for_status() would raise it), then success -- must retry."""
    fn = make_flaky([http_error(503)])
    result = retry.with_retry("test op", fn, is_transient=retry.is_transient_youtube)
    assert result == "ok", f"expected 'ok', got {result!r}"
    assert fn.call_count == 2, f"expected 2 calls (1 + 1 retry), got {fn.call_count}"


def case_youtube_403_fails_immediately():
    """A 403 (quota exceeded) must fail on the first attempt, with no retry: it means
    the day's quota is gone, not that this one call misfired."""
    fn = make_flaky([http_error(403)])
    try:
        retry.with_retry("test op", fn, is_transient=retry.is_transient_youtube)
    except requests.exceptions.HTTPError:
        pass
    else:
        raise AssertionError("expected HTTPError (403) to propagate immediately")
    assert fn.call_count == 1, f"expected exactly 1 call (no retry), got {fn.call_count}"


def case_youtube_three_failures_fails_the_run():
    """Three consecutive 502s -- every attempt is used up and the error is re-raised,
    which is what makes the caller (refresh.py) fail non-zero."""
    fn = make_flaky([http_error(502), http_error(502), http_error(502)])
    try:
        retry.with_retry("test op", fn, is_transient=retry.is_transient_youtube)
    except requests.exceptions.HTTPError:
        pass
    else:
        raise AssertionError("expected HTTPError (502) to propagate after 3 failed attempts")
    assert fn.call_count == 3, f"expected exactly 3 calls (MAX_ATTEMPTS), got {fn.call_count}"


CASES = [
    case_two_transient_then_success,
    case_three_transient_fails,
    case_non_transient_fails_immediately,
    case_statement_timeout_is_transient,
    case_other_api_error_not_transient,
    case_youtube_connection_error_then_success,
    case_youtube_503_then_success,
    case_youtube_403_fails_immediately,
    case_youtube_three_failures_fails_the_run,
]


def main():
    failures = 0
    for case in CASES:
        try:
            case()
        except Exception as error:
            failures += 1
            print(f"FAIL: {case.__name__}: {error}")
        else:
            print(f"PASS: {case.__name__}")

    print(f"\n{len(CASES) - failures}/{len(CASES)} passed.")
    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
