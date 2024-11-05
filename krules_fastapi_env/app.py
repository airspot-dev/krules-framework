import logging
from contextvars import ContextVar
from typing import Optional

from dependency_injector import providers
from fastapi import FastAPI, Request
from rich.logging import RichHandler

from krules_core.providers import subject_factory

ctx_subjects = ContextVar('g_subjects', default=[])




class KrulesApp(FastAPI):

    @staticmethod
    async def krules_middleware(request: Request, call_next):
        # Code to be executed before the request is processed
        ctx_subjects.set([])  # Initialize the request-specific list

        response = await call_next(request)

        # Code to be executed after the request is processed
        for sub in ctx_subjects.get():
            sub.store()

        return response

    def __init__(
            self,
            wrap_subjects: bool = True,
            logger: Optional[logging.Logger] = None,
            logger_name: str = "krules-app",
            log_level: int = logging.INFO,
            *args, **kwargs,
    ) -> None:
        super().__init__(
            *args, **kwargs,
        )
        self.setup()
        self.middleware("http")(self.krules_middleware)

        # Set up the logger
        if logger is not None:
            self._logger = logger
        else:
            # Create default logger
            self._logger = logging.getLogger(logger_name)

            handler = RichHandler(
                rich_tracebacks=True,  # Enable rich tracebacks
                markup=True,  # Enable markup for log messages
                show_time=True,  # Show time in log messages
                show_path=True  # Show file path in log messages
            )
            self._logger.addHandler(handler)
            self._logger.setLevel(log_level)

        if wrap_subjects:
            self._logger.info("Overriding subject_factory for wrapping")
            subject_factory.override(
                providers.Factory(lambda *_args, **_kw: _subjects_wrap(subject_factory.cls, self, *_args, **_kw)))
        else:
            self._logger.info("Subject wrapping is disabled")

    @property
    def logger(self) -> logging.Logger:
        return self._logger

    @logger.setter
    def logger(self, logger: logging.Logger):
        self._logger = logger


def _subjects_wrap(subject_class, app, *args, **kwargs):
    event_info = kwargs.pop("event_info", {})
    subjects = ctx_subjects.get()  # Get the request-specific list

    if event_info is None and len(subjects) > 0:
        event_info = subjects[0].event_info()

    subject = subject_class(*args, event_info=event_info, **kwargs)
    subjects.append(subject)  # Append to the request-specific list
    app.logger.debug("wrapped: {}".format(subject))
    return subject


# override wrap subjects defafult behaviour
class KRulesApp(KrulesApp):
    def __init__(
            self,
            wrap_subjects: bool = False,  # Changed default here
            *args, **kwargs
    ) -> None:
        super().__init__(
            wrap_subjects=wrap_subjects,
            *args, **kwargs
        )