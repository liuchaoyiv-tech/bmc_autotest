#!/bin/python
"""EventService 测试事件上报（正向）: schema-aware checks with owned temporary subscriptions.

Run from the repository root with -i <bmc_ip> -u <username> -p <password>.
See docs/redfish_event_testing.md for receiver setup and verification scope.
"""

import os
import sys
import traceback

sys.path.append(os.path.join(os.path.dirname(__file__), "../.."))

from func.redfish_event_test_base import RedfishEventTestBase


class Event009SubmitTestEvent(RedfishEventTestBase):
    CASE_KEY = "Event009SubmitTestEvent"
    TEST_NAME = "EventService 测试事件上报（正向）"
    TEST_NUM = "Redfish_Event_009"
    LOG_BASE_NAME = "event_009_submit_test_event"

    def _run_checks(self):
        action, info = self.submit_action()
        message_id, message_args = self.test_message()
        parameters = {p["Name"]: p for p in info["Parameters"]} if info else None
        supplied = {"MessageId": message_id, "MessageArgs": message_args}
        if parameters is not None:
            self.require("ActionInfo 支持 MessageId", "MessageId" in parameters, sorted(parameters))
            missing = [name for name, param in parameters.items() if param.get("Required") and name not in supplied]
            self.require("ActionInfo 必填参数", not missing, missing)
        # Keep our own subscription alive until the asynchronous task finishes.
        # A reachable receiver is required; unrelated subscriptions are untouched.
        sub = self.create_subscription()
        kwargs = {"message_id": message_id}
        if parameters is None or "MessageArgs" in parameters:
            kwargs["message_args"] = message_args
        self.log.info("SubmitTestEvent MessageId=%s，测试订阅=%s", message_id, sub.odata_id)
        response = self.client.submit_test_event(**kwargs)
        self.wait_for_event_task(response)
        self.record("SubmitTestEvent 请求及任务成功", True, message_id)


if __name__ == "__main__":
    exit_code = 0
    obj = None
    try:
        obj = Event009SubmitTestEvent()
        obj.run_test()
        exit_code = 0 if obj.command_check_result == "PASS" else 2
    except KeyboardInterrupt:
        exit_code = 130
    except Exception as e:
        if obj: obj.log.error(f"脚本异常：{e}\n{traceback.format_exc()}")
        else: print(f"初始化异常：{e}"); traceback.print_exc()
        exit_code = 1
    finally:
        ec_path = (obj.exit_code_path if obj else
                   os.path.join(os.getcwd(), f"result/bmc/{Event009SubmitTestEvent.LOG_BASE_NAME}/exit_code"))
        os.makedirs(os.path.dirname(ec_path), exist_ok=True)
        with open(ec_path, "w") as f:
            f.write(str(exit_code))
    sys.exit(exit_code)
