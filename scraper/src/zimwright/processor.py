import json
import logging
from pathlib import Path
from uuid import uuid4

from schedule import every
from zimscraperlib.zim.filesystem import (
    validate_file_creatable,
    validate_folder_writable,
)

from zimwright.context import Context
from zimwright.download import save_large_file

context = Context.get()
logger = context.logger

LOG_EVERY_SECONDS = 60


class Processor:
    """Generates ZIMs based on the user's configuration."""

    def __init__(self) -> None:
        """Initializes Processor."""

        self.stats_items_done = 0
        # we add 1 more items to process so that progress is not 100% at the beginning
        # when we do not yet know how many items we have to process and so that we can
        # increase counter at the beginning of every for loop, not minding about what
        # could happen in the loop in terms of exit conditions
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

        # create first progress report and and a timer to update every 10 seconds
        self._report_progress()
        every(10).seconds.do(  # pyright: ignore[reportUnknownMemberType]
            self._report_progress
        )

        logger.debug(f"User-Agent: {context.wm_user_agent}")

        zim_file_name = f"{uuid4()}.zim"
        zim_path = context.output_folder / zim_file_name

        validate_file_creatable(context.output_folder, zim_file_name)

        logger.info(f"Downloading the ZIM to {zim_path} ...")
        save_large_file(
            context.download_from,
            fpath=zim_path,
            user_agent=context.wm_user_agent,
        )

        # same reason than self.stats_items_done = 1 at the beginning, we need to add
        # a final item to complete the progress
        self.stats_items_done += 1
        self._report_progress()

        return zim_path

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
