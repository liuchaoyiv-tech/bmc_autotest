#!/bin/python
"""
BMC Web一键日志收集（Web_012）
2026/10/16: SDK 1.3.0 适配 - 硬编码 URI 改为 SDK/ServiceRoot 动态发现（issue/8）
2026/10/19: 使用 SDK 完成新日志采集、等待和下载，校验文件后判定结果
RDSV_BMC_131 - 验证一键日志收集与下载功能（不验证浏览器页面交互）

Usage: python3 bmc/web/web_012_one_click_log.py -i <bmc_ip> -u <user> -p <pass>
"""
import os, sys, time, traceback
sys.path.append(os.path.join(os.path.dirname(__file__), "../.."))
from func.common_function import CommonFunction
from func.bmc_web_test_base import BmcWebTestBase
from redfish_sdk import RedfishClient


class WebOneClickLog(BmcWebTestBase):
    CASE        = 'WebOneClickLog'
    CONFIG_FILE = 'web_012_one_click_log.json'

    def _load_extra_config(self, conf: dict) -> None:
        self.conf = conf

    def run(self):
        test = CommonFunction()
        steps = [];  all_pass = True
        try:
            # 由 SDK 识别厂商并处理采集参数、任务等待及下载；每次触发新采集。
            with RedfishClient(self.BMC_IP, self.USERNAME, self.PASSWORD,
                               read_timeout=self.TIMEOUT) as client:
                saved_path = client.collect_and_download_diagnostic_data(
                    output_path=os.path.join(self.LOG_DIR, 'diagnostic_bundle.tar'),
                    reuse_existing=False,
                )
                if not os.path.isfile(saved_path) or os.path.getsize(saved_path) == 0:
                    raise RuntimeError(f'下载的日志文件不存在或为空：{saved_path}')
                file_size = os.path.getsize(saved_path)
            all_pass = self._rec(steps, all_pass, 'one_click_log_sdk', True,
                f'采集下载成功，文件={saved_path}，大小={file_size} bytes')
        except Exception as e:
            all_pass = self._rec(steps, all_pass, 'one_click_log_sdk', False,
                f'{type(e).__name__}: {e}')

        self.command_check_result = 'PASS' if all_pass else 'FAIL'
        self._save(test, steps)

if __name__ == '__main__':
    obj = None
    exit_code = 1
    try:
        obj = WebOneClickLog();  obj.run()
        exit_code = 0 if obj.command_check_result == 'PASS' else 2
        time.sleep(5)
    except KeyboardInterrupt:
        exit_code = 130
    except Exception as e:
        CommonFunction.print_log('ERROR', str(e));  traceback.print_exc();  exit_code = 1
    finally:
        if obj:
            try: open(obj.ec_path, 'w').write(str(exit_code))
            except: pass
    sys.exit(exit_code)
