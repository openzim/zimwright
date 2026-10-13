from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from zimwright.download import save_large_file


def test_save_large_file_wget_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """wget is invoked with retry flags covering connection, host and HTTP errors."""

    run_mock = MagicMock()
    monkeypatch.setattr("zimwright.download.subprocess.run", run_mock)

    fpath = tmp_path / "out.zim"
    save_large_file(
        "https://example.com/file.zim",
        fpath,
        retries=7,
        user_agent="some-agent",
    )

    args: Any
    (args,), kwargs = run_mock.call_args
    assert args[:3] == ["/usr/bin/env", "wget", "-t"]
    assert "7" in args
    assert "--retry-connrefused" in args
    assert "--retry-on-host-error" in args
    assert "--retry-on-http-error=429,500,502,503,504" in args
    assert "-c" in args
    assert "https://example.com/file.zim" in args
    assert "-U" in args
    assert "some-agent" in args
    assert kwargs["check"] is True


def test_save_large_file_without_user_agent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_mock = MagicMock()
    monkeypatch.setattr("zimwright.download.subprocess.run", run_mock)

    fpath = tmp_path / "out.zim"
    save_large_file("https://example.com/file.zim", fpath)

    (args,), _kwargs = run_mock.call_args
    assert "-U" not in args
