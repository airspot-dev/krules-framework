import pytest
import os
from reactivex import subject as rx_subject

from krules_core.route.dispatcher import BaseDispatcher
from krules_core.route.router import EventRouter
from krules_env import RULE_PROC_EVENT, publish_proc_events_filtered
from krules_core.providers import proc_events_rx_factory, subject_factory, event_router_factory, \
    subject_storage_factory, event_dispatcher_factory

from dependency_injector import providers
from krules_core.base_functions.filters import Filter
from krules_core.base_functions.processing import Process, SetPayloadProperty

from krules_core import RuleConst, ProcEventsLevel

from krules_core.core import RuleFactory
from tests.test_core.utils.sqlite_storage import SQLLiteSubjectStorage

counter = 0

@pytest.fixture(autouse=True)
def reset_providers():
    # Store original providers
    original_router = event_router_factory.provider
    original_storage = subject_storage_factory.provider
    original_dispatcher = event_dispatcher_factory.provider

    event_router_factory.override(
        providers.Singleton(EventRouter)
    )

    subject_storage_factory.override(
        providers.Factory(lambda x, **kwargs: SQLLiteSubjectStorage(x, ":memory:"))
    )

    event_dispatcher_factory.provider.override(
        providers.Factory(BaseDispatcher)
    )

    # Let the test run
    yield

    # Reset all providers after each test
    event_router_factory.override(original_router)
    subject_storage_factory.override(original_storage)
    event_dispatcher_factory.provider.override(original_dispatcher)
@pytest.fixture
def subject():
    import pdb; pdb.set_trace()

    global counter
    counter += 1

    return subject_factory('f-test-subject-{0}'.format(counter)).flush()


@pytest.fixture
def router():
    router = event_router_factory()
    router.unregister_all()
    proc_events_rx_factory.override(providers.Singleton(rx_subject.ReplaySubject))

    return event_router_factory()


filters = RuleConst.FILTERS
processing = RuleConst.PROCESSING
rulename = RuleConst.RULENAME
processed = RuleConst.PASSED




def test_filtered(router, subject):

    subscribed_rules = []
    os.environ["PUBLISH_PROCEVENTS_LEVEL"] = str(ProcEventsLevel.FULL)
    os.environ["PUBLISH_PROCEVENTS_MATCHING"] = "passed=true"

    proc_events_rx_factory().subscribe(
        on_next=lambda x: publish_proc_events_filtered(x, "passed=true", lambda match: match is not None,
                                                       debug=True))

    RuleFactory.create('check-even-value',
                       subscribe_to="event-test-procevents",
                       data={
                           filters: [
                               Filter(lambda payload: payload["value"] % 2 == 0),
                           ],
                           processing: [
                               SetPayloadProperty("isEven", True),
                           ]
                       })

    RuleFactory.create('check-odd-value',
                       subscribe_to="event-test-procevents",
                       data={
                           filters: [
                               Filter(lambda payload: payload["value"] % 2 != 0),
                           ],
                           processing: [
                               SetPayloadProperty("isEven", False),
                           ]
                       })

    RuleFactory.create('test-procevents-filter',
                       subscribe_to=RULE_PROC_EVENT,
                       data={
                           processing: [
                               Process(lambda payload: subscribed_rules.append(payload["name"])),
                           ],
                       })
    router.route("event-test-procevents", subject, {"value": 2})

    assert "check-even-value" in subscribed_rules
    assert "check-odd-value" not in subscribed_rules


def test_got_errors(router, subject):
    subscribed_rules = []
    os.environ["PUBLISH_PROCEVENTS_LEVEL"] = str(ProcEventsLevel.LIGHT)
    os.environ["PUBLISH_PROCEVENTS_MATCHING"] = "got_errors=true"

    proc_events_rx_factory().subscribe(
        on_next=lambda x: publish_proc_events_filtered(x, "got_errors=true", lambda match: match is not None,
                                                       debug=True))

    RuleFactory.create('set-half-with-error',
                       subscribe_to="event-test-procevents",
                       data={
                           processing: [
                               SetPayloadProperty("half", lambda payload: payload["wrong_key"] / 2, ),
                           ]
                       })

    RuleFactory.create('set-half',
                       subscribe_to="event-test-procevents",
                       data={
                           processing: [
                               SetPayloadProperty("half", lambda payload: payload["value"] / 2, ),
                           ]
                       })

    RuleFactory.create('test-procevents-errors',
                       subscribe_to=RULE_PROC_EVENT,
                       data={
                           processing: [
                               Process(lambda payload: subscribed_rules.append(payload["name"])),
                           ],
                       })

    router.route("event-test-procevents", subject, {"value": 2})

    assert "set-half-with-error" in subscribed_rules
    assert "set-half" not in subscribed_rules
