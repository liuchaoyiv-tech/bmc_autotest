"""Regression tests for event ownership and false PASS prevention; no BMC."""

import importlib
import json
import logging
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from redfish_sdk import RedfishException
from redfish_sdk.models.common import RedfishResponse
from redfish_sdk.models.event import Subscription

from func import redfish_event_test_base as support


class FakeBmc:
    collection = "/redfish/v1/EventService/Subscriptions"

    def __init__(self):
        self.resources = {
            self.collection + "/existing": {
                "@odata.id": self.collection + "/existing",
                "Context": "someone_else", "Destination": "https://existing/events",
            }
        }
        self.created = []
        self.deleted = []
        self.close = Mock()

    def get_event_service(self):
        return SimpleNamespace(subscriptions=SimpleNamespace(odata_id=self.collection))

    def get_raw(self, uri):
        if uri == self.collection:
            return {"Members": [{"@odata.id": key} for key in self.resources]}
        if uri not in self.resources:
            raise RedfishException(404, "missing")
        return self.resources[uri]

    def subscribe(self, destination, **kwargs):
        self.created.append(kwargs)
        uri = self.collection + "/test"
        resource = {
            "@odata.id": uri, "@odata.type": "#EventDestination.v1_13_0.EventDestination",
            "Id": "test", "Name": "Test subscription", "Context": kwargs["context"],
            "Destination": destination, "Protocol": "Redfish",
            "EventFormatType": "Event", "SubscriptionType": "RedfishEvent",
        }
        self.resources[uri] = resource
        return Subscription.model_validate(resource)

    def get_subscription(self, uri):
        return Subscription.model_validate(self.get_raw(uri))

    def delete_subscription(self, uri):
        self.deleted.append(uri)
        del self.resources[uri]


def make_case(monkeypatch, module_name, class_name, bmc):
    module = importlib.import_module("bmc.event." + module_name)
    case = getattr(module, class_name).__new__(getattr(module, class_name))
    case.BMC_IP, case.USERNAME, case.PASSWORD = "mock-bmc", "mock-user", "mock-password"
    case.test_sub_dest = "https://receiver/events"
    case.test_sub_context = "test"
    case.event_conf = {}
    case.log = logging.getLogger("event-regression")
    case._write_result = Mock()
    monkeypatch.setattr(support, "RedfishClient", lambda *args: bmc)
    return case


@pytest.mark.parametrize("number,operation", [("003", "create"), ("004", "get"), ("006", "delete")])
@pytest.mark.parametrize("empty", [False, True])
def test_crud_is_independent_and_preserves_unrelated_subscriptions(monkeypatch, number, operation, empty):
    bmc = FakeBmc()
    if empty:
        bmc.resources.clear()
    before = dict(bmc.resources)
    case = make_case(monkeypatch, f"event_{number}_{operation}_subscription", {
        "003": "Event003CreateSubscription", "004": "Event004GetSubscription", "006": "Event006DeleteSubscription",
    }[number], bmc)
    case.run_test()
    assert case.command_check_result == "PASS"
    assert bmc.resources == before
    assert bmc.created[0]["event_types"] is None
    assert bmc.created[0]["http_headers"] is None
    assert bmc.created[0]["context"] != "test"


def test_cleanup_failure_is_not_a_pass(monkeypatch):
    bmc = FakeBmc()
    bmc.delete_subscription = Mock(side_effect=RedfishException(500, "delete failed"))
    case = make_case(monkeypatch, "event_003_create_subscription", "Event003CreateSubscription", bmc)
    case.run_test()
    assert case.command_check_result == "FAIL"


def test_custom_headers_are_explicit_and_not_silently_removed(monkeypatch):
    bmc = FakeBmc()
    case = make_case(monkeypatch, "event_003_create_subscription", "Event003CreateSubscription", bmc)
    headers = [{"X-Test": "value"}]
    case.event_conf["TestSubHttpHeaders"] = headers
    case.run_test()
    assert case.command_check_result == "PASS"
    assert bmc.created[0]["http_headers"] == headers


def test_partial_create_failure_cleans_only_owned_resource(monkeypatch):
    bmc = FakeBmc()
    original = bmc.subscribe

    def parsed_response_failed(*args, **kwargs):
        original(*args, **kwargs)
        raise RedfishException(201, "parse failed")

    bmc.subscribe = parsed_response_failed
    case = make_case(monkeypatch, "event_003_create_subscription", "Event003CreateSubscription", bmc)
    case.run_test()
    assert case.command_check_result == "FAIL"
    assert list(bmc.resources) == [bmc.collection + "/existing"]
    assert bmc.deleted == [bmc.collection + "/test"]


def test_modern_service_does_not_require_deprecated_field(monkeypatch):
    bmc = FakeBmc()
    bmc.get_event_service = lambda: SimpleNamespace(
        odata_type="#EventService.v1_5_0.EventService", odata_id="/redfish/v1/EventService",
        id="EventService", name="Event Service", service_enabled=True,
        event_types_for_subscription=None,
        subscriptions=SimpleNamespace(odata_id=bmc.collection),
    )
    case = make_case(monkeypatch, "event_001_get_service", "Event001GetService", bmc)
    case.submit_action = lambda: ({"target": "/submit"}, None)
    case.run_test()
    assert case.command_check_result == "PASS"


@pytest.mark.parametrize("state,status,expected", [
    ("Completed", "OK", "PASS"), ("Exception", "Warning", "FAIL"),
    ("Completed", "Critical", "FAIL"), ("Interrupted", "Critical", "FAIL"),
])
def test_positive_event_checks_task_terminal_state(monkeypatch, state, status, expected):
    bmc = FakeBmc()
    raw = bmc.get_raw
    bmc.get_raw = lambda uri: {"TaskState": state, "TaskStatus": status} if uri == "/task" else raw(uri)
    bmc.submit_test_event = Mock(return_value=RedfishResponse.model_validate({"@odata.id": "/task", "TaskState": "New"}))
    case = make_case(monkeypatch, "event_009_submit_test_event", "Event009SubmitTestEvent", bmc)
    case.submit_action = lambda: ({"target": "/submit"}, {"Parameters": [{"Name": "MessageId", "Required": True}]})
    case.test_message = lambda: ("Base.1.12.Success", [])
    case.run_test()
    assert case.command_check_result == expected
    bmc.submit_test_event.assert_called_once_with(message_id="Base.1.12.Success")
    assert list(bmc.resources) == [bmc.collection + "/existing"]


@pytest.mark.parametrize("response", [None, RedfishResponse.model_validate({"@odata.id": "/task", "TaskState": "Running"})])
def test_missing_response_or_task_timeout_fails(monkeypatch, response):
    bmc = FakeBmc()
    raw = bmc.get_raw
    bmc.get_raw = lambda uri: {"TaskState": "Running"} if uri == "/task" else raw(uri)
    bmc.submit_test_event = Mock(return_value=response)
    case = make_case(monkeypatch, "event_009_submit_test_event", "Event009SubmitTestEvent", bmc)
    case.submit_action = lambda: ({"target": "/submit"}, None)
    case.test_message = lambda: ("Base.1.12.Success", [])
    case.event_conf["TaskTimeout"] = 0
    case.run_test()
    assert case.command_check_result == "FAIL"
    assert list(bmc.resources) == [bmc.collection + "/existing"]


@pytest.mark.parametrize("status,key", [(401, "ActionParameterUnknown"), (500, "ActionParameterUnknown"), (400, "GeneralError")])
def test_negative_does_not_accept_unrelated_errors(monkeypatch, status, key):
    bmc = FakeBmc()
    body = json.dumps({"error": {"code": "Base.1.12." + key}})
    bmc.post = Mock(side_effect=RedfishException(status, "failure", body))
    case = make_case(monkeypatch, "event_010_submit_event_negative", "Event010SubmitEventNegative", bmc)
    case.submit_action = lambda: ({"target": "/submit"}, None)
    case.test_message = lambda: ("Base.1.12.Success", [])
    case.run_test()
    assert case.command_check_result == "FAIL"


def test_extended_info_is_used_instead_of_general_error():
    body = json.dumps({"error": {"code": "Base.1.12.GeneralError", "@Message.ExtendedInfo": [
        {"MessageId": "Base.1.12.ActionParameterMissing"},
    ]}})
    assert "ActionParameterMissing" in support.error_message_keys(RedfishException(400, "failure", body))
