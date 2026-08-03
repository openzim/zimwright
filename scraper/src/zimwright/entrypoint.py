import argparse
from pathlib import Path

from zimwright.constants import (
    NAME,
    VERSION,
)
from zimwright.context import Context


def prepare_context(raw_args: list[str]) -> None:
    """Initialize scraper context from command line arguments"""

    parser = argparse.ArgumentParser(
        prog=NAME,
    )

    parser.add_argument(
        "--version",
        help="Display scraper version and exit",
        action="version",
        version=VERSION,
    )

    parser.add_argument(
        "--output",
        help="Output folder for ZIMs. Default: /output",
        type=Path,
        dest="output_folder",
    )

    parser.add_argument("--debug", help="Enable verbose output", action="store_true")

    parser.add_argument(
        "--stats-filename",
        type=Path,
        help="Path to store the progress JSON file to.",
    )

    parser.add_argument(
        "--download-from",
        help="URL where ZIM is currently located and will be downloaded",
        dest="download_from",
    )

    parser.add_argument(
        "--contact-info",
        help="Contact information to pass in User-Agent headers",
        dest="contact_info",
    )

    args = parser.parse_args(raw_args)

    # Ignore unset values so they do not override the default specified in Context
    args_dict = {key: value for key, value in args._get_kwargs() if value}
    Context.setup(**args_dict)
