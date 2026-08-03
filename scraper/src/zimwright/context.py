import dataclasses
import logging
import os
from pathlib import Path
from typing import Any

from zimscraperlib.constants import NAME as SCRAPERLIB_NAME
from zimscraperlib.constants import VERSION as SCRAPERLIB_VERSION
from zimscraperlib.logging import DEFAULT_FORMAT_WITH_THREADS, getLogger

from zimwright.constants import (
    NAME,
    VERSION,
)

MAPS_TMP = os.getenv("MAPS_TMP")


@dataclasses.dataclass(kw_only=True)
class Context:
    """Class holding every contextual / configuration bits which can be moved

    Used to easily pass information around in the scraper. One singleton instance is
    always available.
    """

    # singleton instance
    _instance: Context | None = None

    # debug flag
    debug: bool = False

    # URL to download the ZIM from
    download_from: str

    # info passed in User-Agent header of web requests
    contact_info: str = os.getenv("ZIMWRIGHT_CONTACT_INFO", "https://www.kiwix.org")

    # folder where the ZIM will be built
    output_folder: Path = Path(os.getenv("ZIMWRIGHT_OUTPUT", "output"))

    # Path to store the progress JSON file to
    stats_filename: Path | None = None

    # logger to use everywhere (do not mind about mutability, we want to reuse same
    # logger everywhere)
    logger: logging.Logger = getLogger(  # noqa: RUF009
        NAME, level=logging.DEBUG, log_format=DEFAULT_FORMAT_WITH_THREADS
    )

    @classmethod
    def setup(cls, **kwargs: Any):
        new_instance = cls(**kwargs)
        if cls._instance:
            # replace values 'in-place' so that we do not change the Context object
            # which might be already imported in some modules
            for field in dataclasses.fields(new_instance):
                cls._instance.__setattr__(
                    field.name, new_instance.__getattribute__(field.name)
                )
        else:
            cls._instance = new_instance

    @classmethod
    def get(cls) -> Context:
        if not cls._instance:
            raise OSError("Uninitialized context")  # pragma: no cover
        return cls._instance

    @property
    def wm_user_agent(self) -> str:
        """User-Agent header compliant with Wikimedia requirements"""
        return (
            f"{NAME}/{VERSION} ({self.contact_info}) "
            f"{SCRAPERLIB_NAME}/{SCRAPERLIB_VERSION}"
        )
