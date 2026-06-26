from fastapi import status


class DemoAppError(Exception):
    def __init__(self, detail: str, status_code: int = status.HTTP_400_BAD_REQUEST) -> None:
        self.detail = detail
        self.status_code = status_code
        super().__init__(detail)


class ConfigurationError(DemoAppError):
    def __init__(self, detail: str) -> None:
        super().__init__(detail, status.HTTP_503_SERVICE_UNAVAILABLE)


class ExternalServiceError(DemoAppError):
    def __init__(self, detail: str) -> None:
        super().__init__(detail, status.HTTP_502_BAD_GATEWAY)
