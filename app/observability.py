import reflex as rx

import logging
import posixpath
import secrets


def _install_state_log_redaction() -> None:
    previous_factory = logging.getLogRecordFactory()
    if getattr(previous_factory, "_app_state_log_redaction", False):
        return

    def state_redacting_factory(*args, **kwargs) -> logging.LogRecord:
        record = previous_factory(*args, **kwargs)
        pathname = posixpath.normpath(record.pathname.replace("\\", "/"))
        if "/app/states/" in pathname:
            record.msg = "application_state_event"
            record.args = ()
            record.exc_info = None
            record.exc_text = None
            record.stack_info = None
        return record

    state_redacting_factory._app_state_log_redaction = True
    logging.setLogRecordFactory(state_redacting_factory)


_install_state_log_redaction()
_logger = logging.getLogger("app.observability")


def report_unexpected(operation: str, error: Exception) -> str:
    """Report only allowlisted, non-payload diagnostic fields; return an opaque reference."""
    reference = secrets.token_hex(8)
    _logger.error(
        "application_failure operation=%s exception_class=%s incident=%s",
        operation,
        type(error).__name__,
        reference,
        exc_info=False,
        stack_info=False,
    )
    return reference
