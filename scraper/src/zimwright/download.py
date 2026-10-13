"""Download a binary file from its URL, using wget.

This mirrors `zimscraperlib.download.save_large_file`, which does not reliably
retry interrupted downloads: wget treats non-2xx HTTP responses and host/DNS
errors as fatal by default and gives up instead of retrying, so a transient
502/503/504/429 from a flaky server or proxy aborts the whole download (see
https://github.com/openzim/zimwright/issues/3).

This is a stopgap copy of `save_large_file` with `--retry-on-http-error` and
`--retry-on-host-error` added, to confirm the fix works before it lands
upstream in zimscraperlib. Once released there, this module should be removed
and callers should go back to `zimscraperlib.download.save_large_file`.
"""

import pathlib
import subprocess

RETRYABLE_HTTP_ERRORS = "429,500,502,503,504"


def save_large_file(
    url: str, fpath: pathlib.Path, retries: int = 5, user_agent: str | None = None
) -> None:
    """download a binary file from its URL, using wget"""

    command = [
        "/usr/bin/env",
        "wget",
        "-t",
        f"{retries}",
        "--retry-connrefused",
        "--retry-on-host-error",
        f"--retry-on-http-error={RETRYABLE_HTTP_ERRORS}",
        "--random-wait",
        "--progress=dot:giga",
        "-O",
        str(fpath),
        "-c",
        url,
    ]
    if user_agent:
        command += ["-U", user_agent]
    subprocess.run(
        command,
        check=True,
    )
