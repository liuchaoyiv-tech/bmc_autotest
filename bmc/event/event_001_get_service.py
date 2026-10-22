#!/bin/python
"""EventService 资源查询: schema-aware checks with owned temporary subscriptions.

Run from the repository root with -i <bmc_ip> -u <username> -p <password>.
See docs/redfish_event_testing.md for receiver setup and verification scope.
"""

import os
import sys
import traceback

sys.path.append(os.path.join(os.path.dirname(__file__), "../.."))

from func.redfish_event_test_base import RedfishEventTestBase, schema_version


class Event001GetService(RedfishEventTestBase):
    CASE_KEY = "Event001GetService"
    TEST_NAME = "EventService 资源查询"
    TEST_NUM = "Redfish_Event_001"
    LOG_BASE_NAME = "event_001_get_service"

    def _run_checks(self):
        service = self.client.get_event_service()
        schema_version(service.odata_type)
        for attr in ("odata_id", "odata_type", "id", "name", "subscriptions"):
            self.require(f"EventService.{attr}", getattr(service, attr, None) is not None, getattr(service, attr, None))
        self.require("ServiceEnabled", service.service_enabled is True, service.service_enabled)
        action, info = self.submit_action()
        self.record("SubmitTestEvent 可发现", True, action)
        # This optional property was deprecated in EventService v1.3.
        if service.event_types_for_subscription is not None:
            self.require("兼容字段 EventTypesForSubscription 类型", isinstance(service.event_types_for_subscription, list), service.event_types_for_subscription)


if __name__ == "__main__":
    exit_code = 0
    obj = None
    try:
        obj = Event001GetService()
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
                   os.path.join(os.getcwd(), f"result/bmc/{Event001GetService.LOG_BASE_NAME}/exit_code"))
        os.makedirs(os.path.dirname(ec_path), exist_ok=True)
        with open(ec_path, "w") as f:
            f.write(str(exit_code))
    sys.exit(exit_code)
