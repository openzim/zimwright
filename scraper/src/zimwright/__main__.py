import sys

from zimwright.context import Context
from zimwright.entrypoint import prepare_context

logger = Context.logger


def main():
    try:
        prepare_context(sys.argv[1:])

        # import this only once the Context has been initialized, so that it gets an
        # initialized context
        from zimwright.processor import Processor  # noqa: PLC0415

        Processor().run()

    except SystemExit as exc:
        if exc.code != 0:
            logger.error("Scraper failed, exiting")
        raise
    except Exception as exc:
        logger.exception(exc)
        logger.error(f"Scraper failed with the following error: {exc}")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
