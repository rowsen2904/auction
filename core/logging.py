import logging
from contextvars import ContextVar

request_id_ctx_var: ContextVar[str] = ContextVar("request_id", default="-")


def set_request_id(value: str) -> None:
    request_id_ctx_var.set(value)


def get_request_id() -> str:
    return request_id_ctx_var.get()


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        return True
