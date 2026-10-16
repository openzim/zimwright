import json
from collections.abc import Callable
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from zimwright.context import Context

Context.setup(download_from="https://example.com/file.zim")

from zimwright.processor import Processor  # noqa: E402


@pytest.fixture
def processor(tmp_path: Path) -> Processor:
    context = Context.get()
    context.output_folder = tmp_path
    context.stats_filename = None
    return Processor()


def test_report_download_progress_updates_stats_when_size_known(
    processor: Processor,
) -> None:
    processor._report_download_progress(  # pyright: ignore[reportPrivateUsage]
        512, 2048
    )

    assert processor.stats_items_done == 512
    assert processor.stats_items_total == 2048


def test_report_download_progress_ignores_unknown_size(processor: Processor) -> None:
    processor._report_download_progress(  # pyright: ignore[reportPrivateUsage]
        512, None
    )

    assert processor.stats_items_done == 0
    assert processor.stats_items_total == 1


def test_report_download_progress_writes_stats_file(
    processor: Processor, tmp_path: Path
) -> None:
    stats_filename = tmp_path / "stats.json"
    Context.get().stats_filename = stats_filename

    processor._report_download_progress(  # pyright: ignore[reportPrivateUsage]
        512, 2048
    )

    assert json.loads(stats_filename.read_text()) == {"done": 512, "total": 2048}


def test_run_marks_fully_done_once_download_completes(
    processor: Processor, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_save_large_file(
        _url: str,
        fpath: Path,
        *,
        user_agent: str,  # noqa: ARG001
        on_progress: Callable[[int, int | None], None],
    ) -> None:
        on_progress(1024, 2048)
        fpath.write_bytes(b"zim-content")

    save_large_file_mock = MagicMock(side_effect=fake_save_large_file)
    monkeypatch.setattr("zimwright.processor.save_large_file", save_large_file_mock)

    zim_path = processor.run()

    assert zim_path.read_bytes() == b"zim-content"
    assert processor.stats_items_done == processor.stats_items_total == 2048
