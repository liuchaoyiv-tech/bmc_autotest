#!/bin/python
"""EventService 订阅删除: schema-aware checks with owned temporary subscriptions.

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
)


class Event006DeleteSubscription(RedfishEventTestBase):
    CASE_KEY = "Event006DeleteSubscription"
    TEST_NAME = "EventService 订阅删除"
    TEST_NUM = "Redfish_Event_006"
    LOG_BASE_NAME = "event_006_delete_subscription"

    def _run_checks(self):
        before = self.member_uris()
        sub = self.create_subscription()
        self.client.delete_subscription(sub.odata_id)
        after = self.member_uris()
        self.require("删除后订阅集合恢复", after == before, sorted(after))
        self.require("已删除订阅 GET 返回 404", self.subscription_is_missing(sub.odata_id), sub.odata_id)

    def subscription_is_missing(self, uri):
        try:
            self.client.get_subscription(uri)
        except RedfishException as exc:
            if exc.status_code == 404:
                return True
            raise
        return False


if __name__ == "__main__":
    exit_code = 0
    obj = None
    try:
        obj = Event006DeleteSubscription()
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
                   os.path.join(os.getcwd(), f"result/bmc/{Event006DeleteSubscription.LOG_BASE_NAME}/exit_code"))
        os.makedirs(os.path.dirname(ec_path), exist_ok=True)
        with open(ec_path, "w") as f:
            f.write(str(exit_code))
    sys.exit(exit_code)
