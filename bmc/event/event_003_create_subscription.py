#!/bin/python
"""EventService 订阅创建: schema-aware checks with owned temporary subscriptions.

Run from the repository root with -i <bmc_ip> -u <username> -p <password>.
See docs/redfish_event_testing.md for receiver setup and verification scope.
"""

import os
import sys
import traceback

sys.path.append(os.path.join(os.path.dirname(__file__), "../.."))

from func.redfish_event_test_base import RedfishEventTestBase


class Event003CreateSubscription(RedfishEventTestBase):
    CASE_KEY = "Event003CreateSubscription"
    TEST_NAME = "EventService 订阅创建"
    TEST_NUM = "Redfish_Event_003"
    LOG_BASE_NAME = "event_003_create_subscription"

    def _run_checks(self):
        before = self.member_uris()
        sub = self.create_subscription()
        after = self.member_uris()
        self.require("创建后订阅集合增加目标资源", after == before | {sub.odata_id} and sub.odata_id not in before, sorted(after))
        self.record("创建测试订阅", True, sub.odata_id)


if __name__ == "__main__":
    exit_code = 0
    obj = None
    try:
        obj = Event003CreateSubscription()
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
                   os.path.join(os.getcwd(), f"result/bmc/{Event003CreateSubscription.LOG_BASE_NAME}/exit_code"))
        os.makedirs(os.path.dirname(ec_path), exist_ok=True)
        with open(ec_path, "w") as f:
            f.write(str(exit_code))
    sys.exit(exit_code)
