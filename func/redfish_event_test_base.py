"""Shared ownership, schema and task checks for Redfish event cases."""

import json
import re
import time
import uuid

from redfish_sdk import RedfishClient, RedfishException

from func.bmc_event_test_base import BmcEventTestBase


def schema_version(odata_type):
    match = re.search(r"\.v(\d+)_(\d+)_(\d+)\.", odata_type or "")
    if not match:
        raise ValueError(f"Missing or invalid versioned @odata.type: {odata_type!r}")
    return tuple(int(part) for part in match.groups())


def error_message_keys(exc):
    """Read all ExtendedInfo keys, including errors wrapped in GeneralError."""
    try:
        error = json.loads(exc.body).get("error", {})
    except (TypeError, ValueError):
        return set()
    messages = error.get("@Message.ExtendedInfo", [])
    return {
        item.get("MessageId", item.get("code", "")).rsplit(".", 1)[-1]
        for item in [error] + messages
        if isinstance(item, dict) and (item.get("MessageId") or item.get("code"))
    }


class RedfishEventTestBase(BmcEventTestBase):
    """Own temporary subscriptions by unique Context, never collection diffs."""

    CONFIG_FILE = "event_test.json"
    CONF_DIR = "event"

    def _load_extra_config(self, conf):
        self.event_conf = conf
        self.test_sub_dest = conf.get("TestSubDestination", "https://192.0.2.99:9999/test")
        self.test_sub_context = conf.get("TestSubContext", "bmc_autotest_event")

    def record(self, item, ok, detail):
        self.findings.append({"item": item, "result": "PASS" if ok else "FAIL", "detail": str(detail)})
        (self.log.info if ok else self.log.error)("%s: %s", item, detail)

    def require(self, item, ok, detail):
        self.record(item, ok, detail)
        if not ok:
            raise AssertionError(detail)

    def member_uris(self):
        service = self.client.get_event_service()
        self.collection_uri = service.subscriptions.odata_id.rstrip("/")
        collection = self.client.get_raw(self.collection_uri)
        return {member["@odata.id"] for member in collection["Members"]}

    def create_subscription(self):
        if not self.test_sub_dest:
            raise ValueError("Configure TestSubDestination with a reachable event receiver URL")
        context = f"{self.test_sub_context}_{uuid.uuid4().hex}"
        self.owned_contexts[context] = self.test_sub_dest
        # EventTypes is a legacy opt-in. Modern subscriptions use EventFormatType
        # and optional RegistryPrefixes / ResourceTypes / MessageIds filters.
        sub = self.client.subscribe(
            self.test_sub_dest,
            event_types=self.event_conf.get("TestSubEventTypes"),
            context=context,
            event_format_type="Event",
            subscription_type="RedfishEvent",
            http_headers=self.event_conf.get("TestSubHttpHeaders"),
        )
        uri = sub.odata_id
        if not uri or not uri.startswith(self.collection_uri + "/"):
            # A successful POST may omit the representation; recover only a
            # resource whose unique Context and Destination belong to this run.
            matches = [
                candidate for candidate in self.member_uris()
                if self.is_owned(self.client.get_raw(candidate))
            ]
            if len(matches) != 1:
                raise AssertionError(f"Cannot identify the created subscription: {matches}")
            uri = matches[0]
        detail = self.client.get_subscription(uri)
        self.require("新建订阅归属验证", detail.context == context and detail.destination == self.test_sub_dest, uri)
        return detail

    def is_owned(self, resource):
        context = resource.get("Context")
        return context in self.owned_contexts and resource.get("Destination") == self.owned_contexts[context]

    def cleanup_subscriptions(self):
        if not self.owned_contexts:
            return
        for uri in self.member_uris():
            if not uri.startswith(self.collection_uri + "/"):
                raise AssertionError(f"Refusing to delete a non-member URI: {uri}")
            if self.is_owned(self.client.get_raw(uri)):
                self.client.delete_subscription(uri)
                self.require("清理测试订阅", uri not in self.member_uris(), uri)

    def test_message(self):
        configured = self.event_conf.get("TestMessageId")
        if configured:
            return configured, self.event_conf.get("TestMessageArgs", [])
        # Resolve the version from the target BMC instead of pinning Base.1.x.
        for registry in self.client.get_registries():
            for location in registry.location or []:
                if not location.uri or location.language not in (None, "en"):
                    continue
                data = self.client.get_raw(location.uri)
                if data.get("RegistryPrefix") != "Base":
                    continue
                success = data.get("Messages", {}).get("Success", {})
                if success.get("NumberOfArgs") != 0:
                    continue
                version = data["RegistryVersion"].split(".")
                return f"Base.{version[0]}.{version[1]}.Success", []
        raise ValueError("No Base.Success registry found; configure TestMessageId and TestMessageArgs")

    def submit_action(self):
        action = (self.client.get_event_service().actions or {}).get("#EventService.SubmitTestEvent", {})
        if not action.get("target"):
            raise ValueError("EventService does not expose SubmitTestEvent.target")
        info_uri = action.get("@Redfish.ActionInfo")
        info = self.client.get_raw(info_uri) if info_uri else None
        return action, info

    def wait_for_event_task(self, response):
        if response is None:
            raise ValueError("SDK discarded SubmitTestEvent response; install the SDK task-response fix")
        data = response.model_dump(by_alias=True, exclude_none=True)
        task_uri = data.get("@odata.id") if data.get("TaskState") is not None else None
        if not task_uri:
            self.require("SubmitTestEvent 同步响应", "TaskState" not in data, data)
            return
        deadline = time.monotonic() + float(self.event_conf.get("TaskTimeout", 60))
        while True:
            task = self.client.get_raw(task_uri)
            state = task.get("TaskState")
            if state == "Completed":
                self.require("SubmitTestEvent 任务完成", task.get("TaskStatus") in (None, "OK"), task)
                return
            if state in ("Exception", "Killed", "Cancelled", "Interrupted"):
                raise AssertionError(f"SubmitTestEvent task failed: {task}")
            if time.monotonic() >= deadline:
                raise TimeoutError(f"SubmitTestEvent task did not complete: {task}")
            time.sleep(min(1, max(0, deadline - time.monotonic())))

    def run_test(self):
        self.findings = []
        self.owned_contexts = {}
        self.client = RedfishClient(self.BMC_IP, self.USERNAME, self.PASSWORD)
        self.log.info("开始：%s（%s）", self.TEST_NAME, self.TEST_NUM)
        try:
            self.member_uris()
            self._run_checks()
        except Exception as exc:
            detail = f"{exc}; response={exc.body}" if isinstance(exc, RedfishException) else str(exc)
            self.record("事件测试执行", False, detail)
        finally:
            try:
                self.cleanup_subscriptions()
            except Exception as exc:
                self.record("清理测试订阅", False, exc)
            self.client.close()
        self.command_check_result = "PASS" if self.findings and all(
            finding["result"] == "PASS" for finding in self.findings
        ) else "FAIL"
        self.log.info("最终结果：%s", self.command_check_result)
        self._write_result(self.command_check_result, self.findings)
