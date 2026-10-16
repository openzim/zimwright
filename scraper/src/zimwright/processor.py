import json
import logging
from pathlib import Path
from uuid import uuid4

from zimscraperlib.zim.filesystem import (
    validate_file_creatable,
    validate_folder_writable,
)

from zimwright.context import Context
from zimwright.download import save_large_file

context = Context.get()
logger = context.logger


class Processor:
    """Generates ZIMs based on the user's configuration."""

    def __init__(self) -> None:
        """Initializes Processor."""

        self.stats_items_done = 0
        # placeholder total so progress is not 100% before the download starts
        # reporting its real size; _report_download_progress replaces it once known
        self.stats_items_total = 1

    def run(self) -> Path:
        """Download ZIM

        Returns the path to the generated ZIM.
        """
        logger.setLevel(level=logging.DEBUG if context.debug else logging.INFO)

        # initialize all paths, ensuring they are ok for operation
        context.output_folder.mkdir(exist_ok=True)
        validate_folder_writable(context.output_folder)

        logger.info("Download ZIM")

        # create first progress report; later ones are driven by the download
        # itself, since it is the only long-running operation
        self._report_progress()

        logger.debug(f"User-Agent: {context.wm_user_agent}")

        zim_file_name = f"{uuid4()}.zim"
        zim_path = context.output_folder / zim_file_name

        validate_file_creatable(context.output_folder, zim_file_name)

        logger.info(f"Downloading the ZIM to {zim_path} ...")
        save_large_file(
            context.download_from,
            fpath=zim_path,
            user_agent=context.wm_user_agent,
            on_progress=self._report_download_progress,
        )

        # mark as fully done, whether progress was tracked in bytes (download
        # reported its size) or not (stats_items_total is still the initial 1)
        self.stats_items_done = self.stats_items_total
        self._report_progress()

        return zim_path

    def _report_download_progress(
        self, downloaded: int, total_size: int | None
    ) -> None:
        """relay the download's own progress to the stats file"""

        if not total_size:
            return
        self.stats_items_done = downloaded
        self.stats_items_total = total_size
        self._report_progress()

    def _report_progress(self):
        """report progress to stats file"""

        logger.info(f"  Progress {self.stats_items_done} / {self.stats_items_total}")
        if not context.stats_filename:
            return
        progress = {
            "done": self.stats_items_done,
            "total": self.stats_items_total,
        }
        context.stats_filename.write_text(json.dumps(progress, indent=2))
