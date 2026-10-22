#!/bin/python
"""EventService 测试事件上报（反向）: schema-aware checks with owned temporary subscriptions.

Run from the repository root with -i <bmc_ip> -u <username> -p <password>.
See docs/redfish_event_testing.md for receiver setup and verification scope.
"""

import os
import sys
import traceback

sys.path.append(os.path.join(os.path.dirname(__file__), "../.."))

from redfish_sdk import RedfishException

from func.redfish_event_test_base import (
    RedfishEventTestBase,
    error_message_keys,
)


class Event010SubmitEventNegative(RedfishEventTestBase):
    CASE_KEY = "Event010SubmitEventNegative"
    TEST_NAME = "EventService 测试事件上报（反向）"
    TEST_NUM = "Redfish_Event_010"
    LOG_BASE_NAME = "event_010_submit_event_negative"

    def _run_checks(self):
        action, info = self.submit_action()
        message_id, message_args = self.test_message()
        valid = {"MessageId": message_id}
        if message_args:
            valid["MessageArgs"] = message_args
        cases = [
            ("未知动作参数", dict(valid, InvalidParameter_XHS_TEST=True), "ActionParameterUnknown"),
            ("缺少必需 MessageId", {}, "ActionParameterMissing"),
            ("MessageId 类型错误", {"MessageId": 123}, "ActionParameterValueTypeError"),
        ]
        for name, body, expected in cases:
            try:
                response = self.client.post(action["target"], body)
            except RedfishException as exc:
                keys = error_message_keys(exc)
                self.require(name, exc.status_code == 400 and expected in keys, f"HTTP {exc.status_code}, keys={sorted(keys)}, body={exc.body}")
            else:
                self.record(name, False, f"BMC accepted invalid parameters: {response!r}")


if __name__ == "__main__":
    exit_code = 0
    obj = None
    try:
        obj = Event010SubmitEventNegative()
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
                   os.path.join(os.getcwd(), f"result/bmc/{Event010SubmitEventNegative.LOG_BASE_NAME}/exit_code"))
        os.makedirs(os.path.dirname(ec_path), exist_ok=True)
        with open(ec_path, "w") as f:
            f.write(str(exit_code))
    sys.exit(exit_code)
