"""Structured logging setup with structlog."""

import contextlib
import logging
import sys

import structlog


def setup_logging(log_level: str = "DEBUG") -> None:
    """Configure structlog for the application."""
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # foreign_pre_chain handles log records NOT originating from structlog
    # (e.g. LiveKit's subprocess log forwarding sends plain-string messages).
    # Without this, ProcessorFormatter crashes on record.msg.copy() because
    # it expects a dict but gets a string.
    foreign_pre_chain: list[structlog.types.Processor] = [
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
    ]

    class _IPCSafeFormatter(structlog.stdlib.ProcessorFormatter):
        """Handle structlog records whose msg was stringified by LiveKit IPC.

        LiveKit's subprocess log queue pickles LogRecords across processes.
        structlog's ``wrap_for_formatter`` stores ``_logger`` and ``_name``
        sentinel attrs + sets ``record.msg`` to a dict.  After IPC the
        sentinels survive but ``msg`` becomes its ``str()`` representation.
        ``ProcessorFormatter.format()`` checks ``_logger``/``_name`` (NOT
        ``_structlog``) to decide whether to call ``record.msg.copy()``
        — which then crashes on the string.

        Fix: strip the sentinels when msg is a string so the record is
        treated as a foreign (non-structlog) record.
        """

        def format(self, record: logging.LogRecord) -> str:
            if isinstance(record.msg, str) and hasattr(record, "_logger"):
                for attr in ("_logger", "_name"):
                    with contextlib.suppress(AttributeError):
                        delattr(record, attr)
            return super().format(record)

    formatter = _IPCSafeFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.dev.ConsoleRenderer(),
        ],
        foreign_pre_chain=foreign_pre_chain,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, log_level.upper(), logging.DEBUG))
