"""Download a binary file from its URL, streaming the response with resume.

The previous implementation shelled out to `wget -c` with extra retry flags,
but wget's retry counter is a budget for the *whole* download, not for
consecutive failures: a connection that drops every few hundred MB can
exhaust the retry budget long before the file is complete, even though every
attempt is correctly resuming (see https://github.com/openzim/zimwright/issues/3).

Here, the retry counter only accumulates on attempts that make *no* progress
at all. Any attempt that receives at least one byte resets it, since it
proves the connection and the HTTP range resume are both working, so a
flaky-but-advancing download is never abandoned early.

The download is also written to a `.part` sibling file and only moved to
`fpath` once complete: the Zimfarm worker watches the output folder and
uploads the first file it finds ending in `.zim`, so writing straight to
`fpath` lets it grab a still-downloading, incomplete ZIM.
"""

import logging
import pathlib
import random
import time

import requests

logger = logging.getLogger(__name__)

HTTP_OK = 200
RETRYABLE_HTTP_STATUSES = {429, 500, 502, 503, 504}
CHUNK_SIZE = 1024 * 1024
CONNECT_TIMEOUT_SECONDS = 30
READ_TIMEOUT_SECONDS = 60
BACKOFF_BASE_SECONDS = 2
BACKOFF_MAX_SECONDS = 60


class DownloadError(Exception):
    """Raised when a download fails and cannot be retried any further."""


def save_large_file(
    url: str,
    fpath: pathlib.Path,
    retries: int = 5,
    user_agent: str | None = None,
) -> None:
    """Download a binary file from its URL, streaming it with resume support.

    Retries on connection errors, timeouts, incomplete reads, and HTTP
    429/500/502/503/504, resuming from the last byte written each time via a
    `Range` request. `retries` is the number of consecutive attempts that may
    fail *without making any progress* before giving up; an attempt that
    writes at least one byte resets this counter.
    """

    headers = {"User-Agent": user_agent} if user_agent else {}
    consecutive_failures = 0
    tmp_fpath = fpath.with_name(fpath.name + ".part")

    with requests.Session() as session:
        while True:
            resume_from = tmp_fpath.stat().st_size if tmp_fpath.exists() else 0
            request_headers = dict(headers)
            if resume_from:
                request_headers["Range"] = f"bytes={resume_from}-"

            bytes_written = 0
            error: Exception | None = None
            try:
                with session.get(
                    url,
                    headers=request_headers,
                    stream=True,
                    timeout=(CONNECT_TIMEOUT_SECONDS, READ_TIMEOUT_SECONDS),
                ) as response:
                    if resume_from and response.status_code == HTTP_OK:
                        logger.warning(
                            f"{url} does not support resuming downloads, "
                            "restarting from scratch"
                        )
                        tmp_fpath.unlink(missing_ok=True)
                        resume_from = 0

                    response.raise_for_status()

                    mode = "ab" if resume_from else "wb"
                    with tmp_fpath.open(mode) as fh:
                        for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                            if not chunk:
                                continue
                            fh.write(chunk)
                            bytes_written += len(chunk)
                tmp_fpath.replace(fpath)
                return  # response body was fully consumed without error
            except (
                requests.ConnectionError,
                requests.Timeout,
                requests.exceptions.ChunkedEncodingError,
            ) as exc:
                error = exc
            except requests.HTTPError as exc:
                status = exc.response.status_code if exc.response is not None else None
                if status not in RETRYABLE_HTTP_STATUSES:
                    raise DownloadError(
                        f"Download of {url} failed with non-retryable error"
                    ) from exc
                error = exc

            if bytes_written:
                consecutive_failures = 0
            else:
                consecutive_failures += 1

            if consecutive_failures > retries:
                raise DownloadError(
                    f"Download of {url} failed after {retries} consecutive "
                    "attempts without progress"
                ) from error

            wait = min(
                BACKOFF_MAX_SECONDS,
                BACKOFF_BASE_SECONDS * 2 ** (consecutive_failures - 1),
            )
            wait += random.uniform(0, wait * 0.1)  # noqa: S311 (jitter, not security)
            logger.warning(
                f"Download of {url} interrupted ({error}), retrying in "
                f"{wait:.1f}s from byte {resume_from}"
            )
            time.sleep(wait)
