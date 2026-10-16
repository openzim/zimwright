import logging
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import requests

from zimwright.download import DownloadError, save_large_file


class FakeResponse:
    """Minimal stand-in for requests.Response, usable as a context manager."""

    def __init__(
        self,
        status_code: int,
        chunks: list[bytes] | None = None,
        raise_while_streaming: Exception | None = None,
        content_length: int | None = None,
    ) -> None:
        self.status_code = status_code
        self._chunks = chunks or []
        self._raise_while_streaming = raise_while_streaming
        self.headers = (
            {"Content-Length": str(content_length)}
            if content_length is not None
            else {}
        )

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            response = requests.Response()
            response.status_code = self.status_code
            raise requests.HTTPError(response=response)

    def iter_content(self, chunk_size: int) -> Iterator[bytes]:  # noqa: ARG002
        yield from self._chunks
        if self._raise_while_streaming:
            raise self._raise_while_streaming


def test_save_large_file_single_attempt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A clean download writes all chunks in one attempt, no Range header."""

    get_mock = MagicMock(return_value=FakeResponse(200, [b"hello ", b"world"]))
    monkeypatch.setattr(requests.Session, "get", get_mock)

    fpath = tmp_path / "out.zim"
    save_large_file("https://example.com/file.zim", fpath, user_agent="some-agent")

    assert fpath.read_bytes() == b"hello world"
    assert not fpath.with_name("out.zim.part").exists()
    _args, kwargs = get_mock.call_args
    assert kwargs["headers"] == {"User-Agent": "some-agent"}
    assert "Range" not in kwargs["headers"]


def test_save_large_file_without_user_agent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    get_mock = MagicMock(return_value=FakeResponse(200, [b"data"]))
    monkeypatch.setattr(requests.Session, "get", get_mock)

    fpath = tmp_path / "out.zim"
    save_large_file("https://example.com/file.zim", fpath)

    _args, kwargs = get_mock.call_args
    assert "User-Agent" not in kwargs["headers"]


def test_save_large_file_resumes_after_connection_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A dropped connection resumes with a Range header for the missing bytes."""

    responses = [
        FakeResponse(
            200,
            [b"hello "],
            raise_while_streaming=requests.ConnectionError("dropped"),
        ),
        FakeResponse(206, [b"world"]),
    ]
    get_mock = MagicMock(side_effect=responses)
    monkeypatch.setattr(requests.Session, "get", get_mock)
    monkeypatch.setattr("zimwright.download.time.sleep", MagicMock())

    fpath = tmp_path / "out.zim"
    save_large_file("https://example.com/file.zim", fpath)

    assert fpath.read_bytes() == b"hello world"
    assert get_mock.call_count == 2
    second_call_headers = get_mock.call_args_list[1].kwargs["headers"]
    assert second_call_headers["Range"] == "bytes=6-"


def test_save_large_file_does_not_expose_incomplete_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The final path only appears once the download is complete: a worker
    watching the output folder for a `*.zim` file must never see a partial
    one under that name."""

    responses = [
        FakeResponse(
            200,
            [b"hello "],
            raise_while_streaming=requests.ConnectionError("dropped"),
        ),
        FakeResponse(206, [b"world"]),
    ]
    get_mock = MagicMock(side_effect=responses)
    monkeypatch.setattr(requests.Session, "get", get_mock)

    def fake_sleep(_seconds: float) -> None:
        assert not fpath.exists()
        assert fpath.with_name("out.zim.part").read_bytes() == b"hello "

    monkeypatch.setattr("zimwright.download.time.sleep", fake_sleep)

    fpath = tmp_path / "out.zim"
    save_large_file("https://example.com/file.zim", fpath)

    assert fpath.read_bytes() == b"hello world"
    assert not fpath.with_name("out.zim.part").exists()


def test_save_large_file_logs_progress_periodically(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Progress is logged at most once per PROGRESS_LOG_INTERVAL_SECONDS, not
    once per chunk, and includes the percentage when the size is known."""

    chunks = [b"a" * 1024, b"b" * 1024, b"c" * 1024]
    get_mock = MagicMock(
        return_value=FakeResponse(200, chunks, content_length=sum(map(len, chunks)))
    )
    monkeypatch.setattr(requests.Session, "get", get_mock)
    # one call before the loop, then one per chunk: only the 2nd chunk
    # crosses the 30s interval since the previous log.
    monkeypatch.setattr(
        "zimwright.download.time.monotonic", MagicMock(side_effect=[0, 10, 40, 41])
    )

    fpath = tmp_path / "out.zim"
    with caplog.at_level(logging.INFO, logger="zimwright.download"):
        save_large_file("https://example.com/file.zim", fpath)

    progress_logs = [r.message for r in caplog.records if "Downloaded" in r.message]
    assert len(progress_logs) == 1
    assert "67%" in progress_logs[0]


def test_save_large_file_calls_on_progress_at_the_same_pace_as_logging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """on_progress is invoked at the same ticks as the progress log, with
    the bytes downloaded so far and the total size."""

    chunks = [b"a" * 1024, b"b" * 1024, b"c" * 1024]
    get_mock = MagicMock(
        return_value=FakeResponse(200, chunks, content_length=sum(map(len, chunks)))
    )
    monkeypatch.setattr(requests.Session, "get", get_mock)
    monkeypatch.setattr(
        "zimwright.download.time.monotonic", MagicMock(side_effect=[0, 10, 40, 41])
    )

    on_progress = MagicMock()
    fpath = tmp_path / "out.zim"
    save_large_file("https://example.com/file.zim", fpath, on_progress=on_progress)

    on_progress.assert_called_once_with(2048, 3072)


def test_save_large_file_retries_on_retryable_http_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    responses = [FakeResponse(503), FakeResponse(200, [b"ok"])]
    get_mock = MagicMock(side_effect=responses)
    monkeypatch.setattr(requests.Session, "get", get_mock)
    monkeypatch.setattr("zimwright.download.time.sleep", MagicMock())

    fpath = tmp_path / "out.zim"
    save_large_file("https://example.com/file.zim", fpath)

    assert fpath.read_bytes() == b"ok"
    assert get_mock.call_count == 2


def test_save_large_file_restarts_when_server_ignores_range(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If the server replies 200 (not 206) to a Range request, start over."""

    fpath = tmp_path / "out.zim"
    fpath.with_name("out.zim.part").write_bytes(b"stale-partial-data")

    get_mock = MagicMock(return_value=FakeResponse(200, [b"fresh"]))
    monkeypatch.setattr(requests.Session, "get", get_mock)

    save_large_file("https://example.com/file.zim", fpath)

    assert fpath.read_bytes() == b"fresh"


def test_save_large_file_does_not_retry_non_retryable_http_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    get_mock = MagicMock(return_value=FakeResponse(404))
    monkeypatch.setattr(requests.Session, "get", get_mock)

    fpath = tmp_path / "out.zim"
    with pytest.raises(DownloadError):
        save_large_file("https://example.com/file.zim", fpath)

    assert get_mock.call_count == 1


def test_save_large_file_gives_up_after_consecutive_failures_without_progress(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    get_mock = MagicMock(
        side_effect=requests.ConnectionError("always fails before any byte")
    )
    monkeypatch.setattr(requests.Session, "get", get_mock)
    monkeypatch.setattr("zimwright.download.time.sleep", MagicMock())

    fpath = tmp_path / "out.zim"
    with pytest.raises(DownloadError):
        save_large_file("https://example.com/file.zim", fpath, retries=2)

    assert get_mock.call_count == 3  # initial attempt + 2 retries


def test_save_large_file_keeps_retrying_as_long_as_progress_is_made(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every attempt but the last writes a byte before failing; progress
    keeps resetting the failure counter, so more than `retries` attempts in
    a row are allowed as long as each one makes progress."""

    failing_responses = [
        FakeResponse(
            200 if i == 0 else 206,
            [b"x"],
            raise_while_streaming=requests.ConnectionError("dropped"),
        )
        for i in range(4)
    ]
    responses = [*failing_responses, FakeResponse(206, [b"x"])]
    get_mock = MagicMock(side_effect=responses)
    monkeypatch.setattr(requests.Session, "get", get_mock)
    monkeypatch.setattr("zimwright.download.time.sleep", MagicMock())

    fpath = tmp_path / "out.zim"
    # retries=1 would give up after 2 consecutive no-progress failures, but
    # every attempt here writes a byte first, so it keeps going instead.
    save_large_file("https://example.com/file.zim", fpath, retries=1)

    assert get_mock.call_count == 5
    assert fpath.read_bytes() == b"xxxxx"
