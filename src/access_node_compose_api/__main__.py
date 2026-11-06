"""Entry point: python -m access_node_compose_api"""

import logging
import sys

import uvicorn
from pydantic import ValidationError

from .config import Settings
from .main import create_app

PROBE_SUFFIXES = ("/v1/health", "/v1/ready")


class _SkipProbes(logging.Filter):
    """Keep the access log readable: Kubernetes probes run every few seconds."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple) and len(args) >= 3 and isinstance(args[2], str):
            return not args[2].endswith(PROBE_SUFFIXES)
        return True


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    try:
        settings = Settings()  # type: ignore[call-arg]
    except ValidationError as exc:
        print(f"Invalid configuration:\n{exc}", file=sys.stderr)
        sys.exit(2)

    config = uvicorn.Config(
        create_app(settings),
        host="0.0.0.0",  # Runs in a container.
        port=settings.port,
        log_config=None,  # Use the logging configured above.
        server_header=False,
    )
    logging.getLogger("uvicorn.access").addFilter(_SkipProbes())
    uvicorn.Server(config).run()


if __name__ == "__main__":
    main()
