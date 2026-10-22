"""Regression checks for the existing event cases and their operation scope."""

import importlib
import logging
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from redfish_sdk import RedfishException
from redfish_sdk.models.event import EventService, Subscription

from func.redfish_event_compat import resolve_test_message


class FakeBmc:
    collection = "/redfish/v1/EventService/Subscriptions"

    def __init__(self):
        self.resources = {self.collection + "/existing": {
            "@odata.id": self.collection + "/existing", "Id": "existing",
            "@odata.type": "#EventDestination.v1_13_0.EventDestination",
            "Context": "existing", "Destination": "https://existing/events", "Protocol": "Redfish",
        }}
        self.created = []
        self.deleted = []
        self.close = Mock()
        self.submit_test_event = Mock(return_value=None)
        self.service = EventService.model_validate({
            "@odata.id": "/redfish/v1/EventService", "@odata.type": "#EventService.v1_5_0.EventService",
            "ServiceEnabled": True, "DeliveryRetryAttempts": 3, "DeliveryRetryIntervalSeconds": 60,
            "Subscriptions": {"@odata.id": self.collection},
            "Actions": {"#EventService.SubmitTestEvent": {
                "target": "/submit", "@Redfish.ActionInfo": "/action-info",
            }},
        })

    def get_event_service(self):
        return self.service

    def get_subscriptions(self):
        return [Subscription.model_validate(resource) for resource in self.resources.values()]

    def get_subscription(self, uri):
        if not uri.startswith("/"):
            uri = self.collection + "/" + uri
        if uri not in self.resources:
            raise RedfishException(404, "missing")
        return Subscription.model_validate(self.resources[uri])

    def subscribe(self, destination, event_types=None, context=None, **kwargs):
        self.created.append((event_types, kwargs))
        uri = self.collection + "/test"
        self.resources[uri] = {
            "@odata.id": uri, "Id": "test", "Context": context, "Destination": destination,
            "@odata.type": "#EventDestination.v1_13_0.EventDestination", "Protocol": "Redfish",
        }
        return self.get_subscription(uri)

    def delete_subscription(self, uri):
        if not uri.startswith("/"):
            uri = self.collection + "/" + uri
        self.deleted.append(uri)
        del self.resources[uri]

    delete = delete_subscription

    def get_raw(self, uri):
        assert uri == "/action-info", "An existing case must not poll tasks or add receiver checks"
        return {"Parameters": [{"Name": "MessageId", "Required": True}]}


def make_case(monkeypatch, basename, cls_name, bmc):
    module = importlib.import_module("bmc.event." + basename)
    cls = getattr(module, cls_name)
    case = cls.__new__(cls)
    case.BMC_IP, case.USERNAME, case.PASSWORD = "mock-bmc", "mock-user", "mock-password"
    case.command_check_result = "FAIL"
    case.test_sub_dest, case.test_sub_context = "https://receiver/events", "original_test_context"
    case._created_sub_uri = None
    case.event_types = ["StatusChange", "ResourceUpdated", "ResourceAdded", "ResourceRemoved", "Alert"]
    case.test_message_id, case.test_message_args = "Base.1.12.Success", []
    case.log = logging.getLogger("event-regression")
    case._write_result = Mock()
    monkeypatch.setattr(module, "RedfishClient", lambda *args: bmc)
    return case


def test_service_accepts_absent_optional_legacy_field(monkeypatch):
    case = make_case(monkeypatch, "event_001_get_service", "Event001GetService", FakeBmc())
    case.run_test()
    assert case.command_check_result == "PASS"


@pytest.mark.parametrize("number,operation,cls", [
    ("003", "create", "Event003CreateSubscription"), ("006", "delete", "Event006DeleteSubscription"),
])
@pytest.mark.parametrize("legacy", [False, True])
def test_original_create_delete_flow_uses_supported_parameters(monkeypatch, number, operation, cls, legacy):
    bmc = FakeBmc()
    if legacy:
        bmc.service.event_types_for_subscription = ["Alert"]
    before = dict(bmc.resources)
    case = make_case(monkeypatch, f"event_{number}_{operation}_subscription", cls, bmc)
    case.run_test()
    assert case.command_check_result == "PASS"
    assert bmc.resources == before
    assert len(bmc.created) == 1
    assert bmc.created[0][0] == (["Alert"] if legacy else None)
    assert "http_headers" in bmc.created[0][1]


def test_query_only_reads_an_existing_subscription(monkeypatch):
    bmc = FakeBmc()
    case = make_case(monkeypatch, "event_004_get_subscription", "Event004GetSubscription", bmc)
    case.run_test()
    assert case.command_check_result == "PASS"
    assert not bmc.created and not bmc.deleted


def test_empty_query_keeps_original_precondition(monkeypatch):
    bmc = FakeBmc()
    bmc.resources.clear()
    case = make_case(monkeypatch, "event_004_get_subscription", "Event004GetSubscription", bmc)
    case.run_test()
    assert case.command_check_result == "FAIL"
    assert not bmc.created and not bmc.deleted


def test_positive_only_checks_request_acceptance(monkeypatch):
    bmc = FakeBmc()
    case = make_case(monkeypatch, "event_009_submit_test_event", "Event009SubmitTestEvent", bmc)
    case.run_test()
    assert case.command_check_result == "PASS"
    bmc.submit_test_event.assert_called_once_with(message_id="Base.1.12.Success")
    assert not bmc.created and not bmc.deleted


def test_legacy_positive_keeps_original_event_type_cases(monkeypatch):
    bmc = FakeBmc()
    bmc.service.actions = {"#EventService.SubmitTestEvent": {
        "target": "/submit", "EventType@Redfish.AllowableValues": ["Alert", "StatusChange"],
    }}
    case = make_case(monkeypatch, "event_009_submit_test_event", "Event009SubmitTestEvent", bmc)
    case.run_test()
    assert case.command_check_result == "PASS"
    assert [call.args for call in bmc.submit_test_event.call_args_list] == [("StatusChange",), ("Alert",)]
    assert not bmc.created and not bmc.deleted


def test_message_id_uses_target_registry_version():
    bmc = Mock()
    bmc.get_registries.return_value = [SimpleNamespace(location=[SimpleNamespace(language="en", uri="/base")])]
    bmc.get_raw.return_value = {
        "RegistryPrefix": "Base", "RegistryVersion": "1.42.0", "Messages": {"Success": {"NumberOfArgs": 0}},
    }
    assert resolve_test_message(bmc) == ("Base.1.42.Success", [])
