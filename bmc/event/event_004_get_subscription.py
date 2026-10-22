#!/bin/python
"""EventService 订阅资源查询: schema-aware checks with owned temporary subscriptions.

Run from the repository root with -i <bmc_ip> -u <username> -p <password>.
See docs/redfish_event_testing.md for receiver setup and verification scope.
"""

import os
import sys
import traceback

sys.path.append(os.path.join(os.path.dirname(__file__), "../.."))

from func.redfish_event_test_base import RedfishEventTestBase, schema_version


class Event004GetSubscription(RedfishEventTestBase):
    CASE_KEY = "Event004GetSubscription"
    TEST_NAME = "EventService 订阅资源查询"
    TEST_NUM = "Redfish_Event_004"
    LOG_BASE_NAME = "event_004_get_subscription"

    def _run_checks(self):
        created = self.create_subscription()
        sub = self.client.get_subscription(created.odata_id)
        version = schema_version(sub.odata_type)
        # Required properties from EventDestination; deprecated EventTypes is
        # required only by older schema versions, not modern implementations.
        attrs = ["odata_id", "odata_type", "id", "name", "context"]
        if version >= (1, 3, 0):
            attrs.append("subscription_type")
        for attr in attrs:
            value = getattr(sub, attr, None)
            self.require(f"Subscription.{attr}", value is not None, value)
        self.require("Destination 与创建参数一致", sub.destination == self.test_sub_dest, sub.destination)
        self.require("Protocol", sub.protocol == "Redfish", sub.protocol)
        if version < (1, 5, 0) or sub.event_types is not None:
            self.require("EventTypes 类型和内容", isinstance(sub.event_types, list) and bool(sub.event_types), sub.event_types)
        self.require("EventFormatType", sub.event_format_type in (None, "Event"), sub.event_format_type)


if __name__ == "__main__":
    exit_code = 0
    obj = None
    try:
        obj = Event004GetSubscription()
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
                   os.path.join(os.getcwd(), f"result/bmc/{Event004GetSubscription.LOG_BASE_NAME}/exit_code"))
        os.makedirs(os.path.dirname(ec_path), exist_ok=True)
        with open(ec_path, "w") as f:
            f.write(str(exit_code))
    sys.exit(exit_code)
