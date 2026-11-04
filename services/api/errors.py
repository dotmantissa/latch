"""Safe public error taxonomy."""


class ApiError(Exception):
    def __init__(
        self,
        status: int,
        code: str,
        message_key: str = "error.generic",
        *,
        fields: dict[str, str] | None = None,
        current_version: int | None = None,
    ):
        self.status = status
        self.code = code
        self.message_key = message_key
        self.fields = fields or {}
        self.current_version = current_version
