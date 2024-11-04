import logging
import os
import sys
from contextvars import ContextVar
from typing import Callable

import json_logging
from dependency_injector import providers
from fastapi import FastAPI, routing, Response, Request
from fastapi.types import DecoratedCallable
from starlette.exceptions import HTTPException
from starlette.responses import PlainTextResponse
from starlette.types import Scope, Receive, Send

from krules_core.providers import subject_factory
from .globals import GlobalsMiddleware

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
            *args, **kwargs,
    ) -> None:
        super().__init__(
            *args, **kwargs,
        )
        #self.router.route_class = KRulesAPIRoute
        # self.router = KRulesAPIRouter(
        #     *args, **kwargs,
        # )
        self.setup()
        self.middleware("http")(self.krules_middleware)
        #self.add_middleware(GlobalsMiddleware)
        json_logging.init_fastapi(enable_json=True)
        json_logging.init_request_instrument(self)
        self.logger = logging.getLogger(self.title)
        self.logger.setLevel(int(os.environ.get("LOGGING_LEVEL", logging.INFO)))
        self.logger.addHandler(logging.StreamHandler(sys.stdout))
        self.logger.propagate = False

        if wrap_subjects:
            self.logger.info("Overriding subject_factory for wrapping")
            subject_factory.override(
                providers.Factory(lambda *_args, **_kw: _subjects_wrap(subject_factory.cls, self, *_args, **_kw)))
        else:
            self.logger.info("Subject wrapping is disabled")


def _subjects_wrap(subject_class, app, *args, **kwargs):
    event_info = kwargs.pop("event_info", {})
    subjects = ctx_subjects.get()  # Get the request-specific list

    if event_info is None and len(subjects) > 0:
        event_info = subjects[0].event_info()

    subject = subject_class(*args, event_info=event_info, **kwargs)
    subjects.append(subject)  # Append to the request-specific list
    app.logger.debug("wrapped: {}".format(subject))
    return subject
