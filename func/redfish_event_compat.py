"""Request compatibility helpers for the existing Redfish event cases."""

import re


def modern_event_destination(odata_type):
    match = re.search(r"\.v(\d+)_(\d+)_(\d+)\.", odata_type or "")
    return bool(match and tuple(map(int, match.groups())) >= (1, 5, 0))


def subscription_event_types(client):
    supported = client.get_event_service().event_types_for_subscription or []
    return ["Alert"] if "Alert" in supported else None


def message_id_parameters(client, service):
    """Return None for a legacy action, or its supported modern parameters."""
    action = (service.actions or {}).get("#EventService.SubmitTestEvent", {})
    info_uri = action.get("@Redfish.ActionInfo")
    if info_uri:
        names = {param["Name"] for param in client.get_raw(info_uri)["Parameters"]}
        return None if "EventType" in names else names
    if action.get("EventType@Redfish.AllowableValues"):
        return None
    return {"MessageId", "MessageArgs"}


def resolve_test_message(client, configured_id=None, message_args=None):
    if configured_id:
        return configured_id, message_args or []
    for registry in client.get_registries():
        for location in registry.location or []:
            if not location.uri or location.language not in (None, "en"):
                continue
            data = client.get_raw(location.uri)
            if data.get("RegistryPrefix") != "Base":
                continue
            if data.get("Messages", {}).get("Success", {}).get("NumberOfArgs") != 0:
                continue
            major, minor = data["RegistryVersion"].split(".")[:2]
            return f"Base.{major}.{minor}.Success", []
    raise ValueError("Configure TestMessageId and TestMessageArgs for this BMC")
