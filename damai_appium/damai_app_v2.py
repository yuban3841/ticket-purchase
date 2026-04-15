# -*- coding: UTF-8 -*-
"""
__Author__ = "BlueCestbon"
__Version__ = "2.0.0"
__Description__ = "大麦app抢票自动化 - 优化版"
__Created__ = 2025/09/13 19:27
"""

import time
import subprocess
from appium import webdriver
from appium.options.common.base import AppiumOptions
from appium.webdriver.common.appiumby import AppiumBy
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException

from config import Config


APPIUM_UNICODE_IME = "io.appium.settings/.UnicodeIME"


class DamaiBot:
    def __init__(self):
        self.config = Config.load_config()
        self.driver = None
        self.wait = None
        self.device_name = None
        self.original_ime = None
        print(
            "当前配置: "
            f"keyword={self.config.keyword}, city={self.config.city}, "
            f"date={self.config.date}, price={self.config.price}, "
            f"if_commit_order={self.config.if_commit_order}"
        )
        self._setup_driver()

    def _setup_driver(self):
        """初始化驱动配置"""
        config_device_name = (self.config.device_name or "").strip()
        if config_device_name:
            device_name = self._assert_device_online(config_device_name)
        else:
            device_name = self._detect_device_name()

        self.device_name = device_name
        self._check_runtime_compatibility()
        self._remember_current_ime()

        app_package = "cn.damai"
        app_activity = self._resolve_main_activity(app_package)

        print(f"使用设备: {device_name}")
        print(f"检测到启动 Activity: {app_activity}")

        capabilities = {
            "platformName": "Android",  # 操作系统
            "deviceName": device_name,  # 设备名称
            "appPackage": app_package,  # app 包名
            "appActivity": app_activity,  # app 启动 Activity
            "unicodeKeyboard": True,  # 支持 Unicode 输入
            "resetKeyboard": True,  # 隐藏键盘
            "noReset": True,  # 不重置 app
            "newCommandTimeout": 6000,  # 超时时间
            "automationName": "UiAutomator2",  # 使用 uiautomator2
            "skipServerInstallation": False,  # 跳过服务器安装
            "ignoreHiddenApiPolicyError": True,  # 忽略隐藏 API 策略错误
            "disableWindowAnimation": True,  # 禁用窗口动画
            # 优化性能配置
            "mjpegServerFramerate": 1,  # 降低截图帧率
            "shouldTerminateApp": False,
            "adbExecTimeout": 20000,
        }

        self.driver = self._create_driver_with_fallback(capabilities)

        # 更激进的性能优化设置。部分设备会在此调用超时，失败时降级为默认设置继续执行。
        try:
            self.driver.update_settings({
                "waitForIdleTimeout": 0,  # 空闲时间，0 表示不等待，让 UIAutomator2 不等页面“空闲”再返回
                "actionAcknowledgmentTimeout": 0,  # 禁止等待动作确认
                "keyInjectionDelay": 0,  # 禁止输入延迟
                "waitForSelectorTimeout": 300,  # 从500减少到300ms
                "ignoreUnimportantViews": False,  # 保持false避免元素丢失
                "allowInvisibleElements": True,
                "enableNotificationListener": False,  # 禁用通知监听
            })
        except Exception as exc:
            print(f"警告: update_settings 失败，已降级继续执行: {exc}")

        # 极短的显式等待，抢票场景下速度优先
        self.wait = WebDriverWait(self.driver, 2)  # 从5秒减少到2秒

    def _create_driver_with_fallback(self, capabilities):
        """创建会话，若 realme 等机型上 io.appium.settings 初始化不稳定则自动降级重试。"""
        device_app_info = AppiumOptions()
        device_app_info.load_capabilities(capabilities)

        try:
            return webdriver.Remote(self.config.server_url, options=device_app_info)
        except WebDriverException as exc:
            if "Appium Settings app is not running" not in str(exc):
                self._restore_device_ime()
                raise

            print("警告: Appium Settings 初始化超时，自动启用 skipDeviceInitialization 进行重试")
            fallback_capabilities = dict(capabilities)
            fallback_capabilities["skipDeviceInitialization"] = True
            fallback_options = AppiumOptions()
            fallback_options.load_capabilities(fallback_capabilities)
            try:
                return webdriver.Remote(self.config.server_url, options=fallback_options)
            except Exception:
                self._restore_device_ime()
                raise

    @staticmethod
    def _run_command(command, timeout=10):
        """执行系统命令并返回结果"""
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
        return result.returncode, (result.stdout or "").strip(), (result.stderr or "").strip()

    def _adb_command(self, args):
        """生成 adb 命令，优先固定到当前设备。"""
        if self.device_name:
            return ["adb", "-s", self.device_name] + args
        return ["adb"] + args

    def _remember_current_ime(self):
        """记录脚本启动前的默认输入法。"""
        code, ime, _ = self._run_command(
            self._adb_command(["shell", "settings", "get", "secure", "default_input_method"]),
            timeout=8,
        )
        ime = (ime or "").strip()
        if code == 0 and ime and ime.lower() != "null":
            self.original_ime = ime
            print(f"记录初始输入法: {self.original_ime}")
        else:
            self.original_ime = None
            print("警告: 未能读取初始输入法，后续将尝试回退到非 Appium 输入法")

    def _list_enabled_imes(self):
        """读取设备已启用输入法列表。"""
        code, stdout, _ = self._run_command(self._adb_command(["shell", "ime", "list", "-s"]), timeout=8)
        if code != 0:
            return []
        return [line.strip() for line in stdout.splitlines() if line.strip()]

    def _restore_device_ime(self):
        """恢复默认输入法，防止 Appium UnicodeIME 残留。"""
        enabled_imes = self._list_enabled_imes()
        if not enabled_imes:
            print("警告: 未读取到输入法列表，跳过输入法恢复")
            return

        target_ime = None
        if self.original_ime and self.original_ime in enabled_imes and self.original_ime != APPIUM_UNICODE_IME:
            target_ime = self.original_ime
        else:
            for ime in enabled_imes:
                if ime != APPIUM_UNICODE_IME:
                    target_ime = ime
                    break

        if not target_ime:
            print("警告: 未找到可恢复的非 Appium 输入法")
            return

        code, current_ime, _ = self._run_command(
            self._adb_command(["shell", "settings", "get", "secure", "default_input_method"]),
            timeout=8,
        )
        current_ime = (current_ime or "").strip()
        if code == 0 and current_ime == target_ime:
            return

        self._run_command(self._adb_command(["shell", "ime", "enable", target_ime]), timeout=8)
        set_code, _, set_err = self._run_command(self._adb_command(["shell", "ime", "set", target_ime]), timeout=8)
        if set_code == 0:
            print(f"已恢复默认输入法: {target_ime}")
        else:
            print(f"警告: 恢复输入法失败: {set_err}")

    def _detect_device_name(self):
        """自动检测在线设备，优先使用首个 device 状态设备"""
        devices = self._get_online_devices()
        if not devices:
            raise RuntimeError("未检测到在线 Android 设备，请先启动模拟器或连接真机")
        return devices[0]

    def _get_online_devices(self):
        """获取所有在线设备序列号"""
        try:
            code, stdout, _ = self._run_command(["adb", "devices"], timeout=8)
        except FileNotFoundError:
            raise RuntimeError("未找到 adb，请确认 Android SDK platform-tools 已加入 PATH")

        if code != 0:
            raise RuntimeError("执行 adb devices 失败，请检查 Android SDK 环境")

        devices = []
        for line in stdout.splitlines()[1:]:
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) >= 2 and parts[1] == "device":
                devices.append(parts[0])

        return devices

    def _assert_device_online(self, target_device):
        """校验指定设备是否在线"""
        devices = self._get_online_devices()
        if target_device in devices:
            return target_device

        # 兼容无线调试场景：在线设备序列号可能为 adb-<serial>... 形式
        fuzzy_matches = [d for d in devices if target_device in d or d in target_device]
        if len(fuzzy_matches) == 1:
            matched_device = fuzzy_matches[0]
            print(f"配置设备 {target_device} 已匹配在线设备 {matched_device}")
            return matched_device

        raise RuntimeError(
            f"配置的 device_name={target_device} 未在线，当前在线设备: {', '.join(devices) if devices else '无'}"
        )

    def _check_runtime_compatibility(self):
        """在已知不兼容的模拟器环境提前失败，避免进入流程后才闪退。"""
        code_abi, abi, _ = self._run_command(
            self._adb_command(["shell", "getprop", "ro.product.cpu.abi"]),
            timeout=8,
        )
        code_qemu, qemu, _ = self._run_command(
            self._adb_command(["shell", "getprop", "ro.kernel.qemu"]),
            timeout=8,
        )

        if code_abi != 0 or code_qemu != 0:
            print("警告: 无法读取设备 ABI/QEMU 属性，跳过兼容性检查")
            return

        abi = (abi or "").strip().lower()
        qemu = (qemu or "").strip()
        is_emulator = qemu == "1"
        is_x86_family = "x86" in abi

        if is_emulator and is_x86_family:
            raise RuntimeError(
                "当前为 x86 模拟器环境，已确认大麦在点击同意后会发生 Native 崩溃(SIGSEGV/libsgmainso)。"
                "请改用 ARM64 真机，或切换到 ARM64 模拟器/MuMu 的 ARM 兼容实例。"
            )

    def _resolve_main_activity(self, package_name):
        """自动解析应用主启动 Activity，避免版本升级后 Activity 变更导致启动失败"""
        code, packages, _ = self._run_command(
            self._adb_command(["shell", "pm", "list", "packages"]),
            timeout=10,
        )
        if code != 0 or f"package:{package_name}" not in packages:
            raise RuntimeError(f"未检测到应用 {package_name}，请先在设备安装大麦 APP")

        code, stdout, stderr = self._run_command(
            self._adb_command(["shell", "cmd", "package", "resolve-activity", "--brief", package_name]),
            timeout=10,
        )
        resolved_output = f"{stdout}\n{stderr}".strip()

        if code != 0 or "No activity found" in resolved_output:
            raise RuntimeError(f"无法解析 {package_name} 的启动 Activity，请确认 APP 可正常打开")

        for line in resolved_output.splitlines():
            line = line.strip()
            if "/" not in line:
                continue
            component = line.split()[-1]
            if "/" not in component:
                continue
            pkg, activity = component.split("/", 1)
            if pkg == package_name:
                return activity
            return component

        raise RuntimeError(f"解析 {package_name} 启动 Activity 失败，原始输出: {resolved_output}")

    def ultra_fast_click(self, by, value, timeout=1.5):
        """超快速点击 - 适合抢票场景"""
        try:
            # 直接查找并点击，不等待可点击状态
            el = WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((by, value))
            )
            # 使用坐标点击更快
            rect = el.rect
            x = rect['x'] + rect['width'] // 2
            y = rect['y'] + rect['height'] // 2
            self.driver.execute_script("mobile: clickGesture", {
                "x": x,
                "y": y,
                "duration": 50  # 极短点击时间
            })
            return True
        except TimeoutException:
            return False

    def batch_click(self, elements_info, delay=0.1):
        """批量点击操作"""
        for by, value in elements_info:
            if self.ultra_fast_click(by, value):
                if delay > 0:
                    time.sleep(delay)
            else:
                print(f"点击失败: {value}")

    def ultra_batch_click(self, elements_info, timeout=2):
        """超快批量点击 - 带等待机制"""
        coordinates = []
        # 批量收集坐标，带超时等待
        for by, value in elements_info:
            try:
                # 等待元素出现
                el = WebDriverWait(self.driver, timeout).until(
                    EC.presence_of_element_located((by, value))
                )
                rect = el.rect
                x = rect['x'] + rect['width'] // 2
                y = rect['y'] + rect['height'] // 2
                coordinates.append((x, y, value))
            except TimeoutException:
                print(f"超时未找到用户: {value}")
            except Exception as e:
                print(f"查找用户失败 {value}: {e}")
        print(f"成功找到 {len(coordinates)} 个用户")
        # 快速连续点击
        for i, (x, y, value) in enumerate(coordinates):
            self.driver.execute_script("mobile: clickGesture", {
                "x": x,
                "y": y,
                "duration": 30
            })
            if i < len(coordinates) - 1:
                time.sleep(0.01)
            print(f"点击用户: {value}")

        return len(coordinates)

    def smart_wait_and_click(self, by, value, backup_selectors=None, timeout=1.5):
        """智能等待和点击 - 支持备用选择器"""
        selectors = [(by, value)]
        if backup_selectors:
            selectors.extend(backup_selectors)

        for selector_by, selector_value in selectors:
            try:
                el = WebDriverWait(self.driver, timeout).until(
                    EC.presence_of_element_located((selector_by, selector_value))
                )
                rect = el.rect
                x = rect['x'] + rect['width'] // 2
                y = rect['y'] + rect['height'] // 2
                self.driver.execute_script("mobile: clickGesture", {"x": x, "y": y, "duration": 50})
                return True
            except TimeoutException:
                continue
        return False

    def _wait_for_any_element(self, selectors, timeout=1.2):
        """按顺序查找第一个可用元素。"""
        for by, value in selectors:
            try:
                return WebDriverWait(self.driver, timeout).until(
                    EC.presence_of_element_located((by, value))
                )
            except TimeoutException:
                continue
        return None

    def _is_on_target_event_detail(self, keyword):
        """校验当前是否在目标演出详情页，避免误购。"""
        keyword = (keyword or "").strip()
        detail_marker_ids = [
            "cn.damai:id/trade_project_detail_purchase_status_bar_container_fl",
            "cn.damai:id/project_detail_perform_price_flowlayout",
            "cn.damai:id/tv_tour_city",
        ]
        has_detail_marker = any(self.driver.find_elements(By.ID, marker) for marker in detail_marker_ids)
        if not has_detail_marker:
            return False

        if not keyword:
            return has_detail_marker

        keyword_selectors = [
            (AppiumBy.ANDROID_UIAUTOMATOR, f'new UiSelector().textContains("{keyword}")'),
            (By.XPATH, f'//*[contains(@text,"{keyword}")]'),
        ]
        keyword_element = self._wait_for_any_element(keyword_selectors, timeout=0.6)
        return keyword_element is not None

    def _open_search_entry(self, max_back_steps=3):
        """打开搜索入口；若不在首页会尝试回退。"""
        search_entry_selectors = [
            (By.ID, "cn.damai:id/homepage_header_search_btn"),
            (By.ID, "homepage_header_search_btn"),
            (AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().descriptionContains("搜索")'),
            (AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().textContains("搜索")'),
        ]

        for _ in range(max_back_steps + 1):
            if self.smart_wait_and_click(*search_entry_selectors[0], search_entry_selectors[1:], timeout=1.0):
                return True

            try:
                self.driver.back()
                time.sleep(0.4)
            except Exception:
                pass

            self.dismiss_startup_popups()

        return False

    def _search_and_open_target_event(self):
        """强制按 keyword 定位目标演出并进入详情页。"""
        keyword = (self.config.keyword or "").strip()
        if not keyword:
            print("安全拦截: keyword 为空，已停止本次尝试")
            return False

        if self._is_on_target_event_detail(keyword):
            print(f"已在目标演出详情页: {keyword}")
            return True

        print(f"定位目标演出: {keyword}")
        print("步骤1/4: 打开搜索入口")
        if not self._open_search_entry():
            print("安全拦截: 无法打开搜索入口，已停止本次尝试")
            return False

        print("步骤2/4: 输入关键词")
        search_input_selectors = [
            (By.ID, "cn.damai:id/header_search_v2_input"),
            (By.ID, "header_search_v2_input"),
            (By.XPATH, '//*[@resource-id="cn.damai:id/header_search_v2_input"]'),
        ]
        search_input = self._wait_for_any_element(search_input_selectors, timeout=1.5)
        if not search_input:
            print("安全拦截: 未找到搜索输入框，已停止本次尝试")
            return False

        try:
            search_input.clear()
        except Exception:
            pass

        search_input.send_keys(keyword)
        try:
            self.driver.press_keycode(66)  # Enter
        except Exception:
            try:
                self.driver.execute_script("mobile: performEditorAction", {"action": "search"})
            except Exception:
                pass

        time.sleep(0.6)

        print("步骤3/4: 点击匹配结果")
        keyword_result_selectors = [
            (By.XPATH, f'(//*[@resource-id="cn.damai:id/ll_search_item"]//*[contains(@text,"{keyword}")]/ancestor::*[@resource-id="cn.damai:id/ll_search_item"])[1]'),
            (By.XPATH, f'(//*[@resource-id="cn.damai:id/ll_search_item"]//*[contains(@text,"{keyword}")])[1]'),
            (By.XPATH, '(//*[@resource-id="cn.damai:id/ll_search_item"])[1]'),
            (By.XPATH, '//androidx.recyclerview.widget.RecyclerView[@resource-id="cn.damai:id/search_v2_suggest_recycler"]/android.widget.RelativeLayout[1]'),
        ]
        clicked_any = self.smart_wait_and_click(*keyword_result_selectors[0], keyword_result_selectors[1:], timeout=1.5)
        if clicked_any:
            time.sleep(0.5)

        if not self._is_on_target_event_detail(keyword):
            first_result_selectors = [
                (By.XPATH, '(//*[@resource-id="cn.damai:id/ll_search_item"])[1]'),
                (By.XPATH, '(//android.widget.LinearLayout[@resource-id="cn.damai:id/ll_search_item"])[1]'),
            ]
            clicked_any = self.smart_wait_and_click(*first_result_selectors[0], first_result_selectors[1:], timeout=2.0) or clicked_any
            if clicked_any:
                time.sleep(0.8)

        if not clicked_any:
            print(f"安全拦截: 未找到目标演出[{keyword}]搜索结果，已停止本次尝试")
            return False

        print("步骤4/4: 校验是否进入目标详情页")
        if not self._is_on_target_event_detail(keyword):
            print(f"安全拦截: 未能确认进入目标演出[{keyword}]详情页，已停止本次尝试")
            return False

        print(f"已确认目标演出详情页: {keyword}")
        return True

    def run_ticket_grabbing(self):
        """执行抢票主流程"""
        try:
            print("开始抢票流程...")
            start_time = time.time()

            self.dismiss_startup_popups()

            if not self._search_and_open_target_event():
                return False

            if not self._is_on_target_event_detail(self.config.keyword):
                print(f"安全拦截: 当前页面不属于目标演出[{self.config.keyword}]，停止本次尝试")
                return False

            # 1. 城市选择 - 准备多个备选方案
            print("选择城市...")
            city_selectors = [
                (AppiumBy.ANDROID_UIAUTOMATOR, f'new UiSelector().text("{self.config.city}")'),
                (AppiumBy.ANDROID_UIAUTOMATOR, f'new UiSelector().textContains("{self.config.city}")'),
                (By.XPATH, f'//*[@text="{self.config.city}"]')
            ]
            if not self.smart_wait_and_click(*city_selectors[0], city_selectors[1:]):
                print("城市选择失败")
                return False

            # 2. 点击预约按钮 - 多种可能的按钮文本
            print("点击预约按钮...")
            book_selectors = [
                (By.ID, "cn.damai:id/trade_project_detail_purchase_status_bar_container_fl"),
                (AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().textMatches(".*预约.*|.*购买.*|.*立即.*")'),
                (By.XPATH, '//*[contains(@text,"预约") or contains(@text,"购买")]')
            ]
            if not self.smart_wait_and_click(*book_selectors[0], book_selectors[1:]):
                print("预约按钮点击失败")
                return False

            # 3. 票价选择 - 优化查找逻辑
            print("选择票价...")
            try:
                # 直接尝试点击，不等待容器，实际每次都失败，只能等待
                price_container = self.driver.find_element(By.ID, 'cn.damai:id/project_detail_perform_price_flowlayout')
                # price_container = self.wait.until(  # 等待找到容器
                #     EC.presence_of_element_located((By.ID, 'cn.damai:id/project_detail_perform_price_flowlayout')))
                # 在容器内找 index=1 且 clickable="true" 的 FrameLayout【因为799元的票价是排在第二的，但是page里text是空的被隐藏了】
                target_price = price_container.find_element(
                    AppiumBy.ANDROID_UIAUTOMATOR,
                    f'new UiSelector().className("android.widget.FrameLayout").index({self.config.price_index}).clickable(true)'
                )
                self.driver.execute_script('mobile: clickGesture', {'elementId': target_price.id})
            except Exception as e:
                print(f"票价选择失败，启动备用方案: {e}")
                # 备用方案
                # 先找到大容器
                price_container = self.wait.until(
                    EC.presence_of_element_located((By.ID, 'cn.damai:id/project_detail_perform_price_flowlayout')))
                # 在容器内找 index=1 且 clickable="true" 的 FrameLayout【因为799元的票价是排在第二的，但是page里text是空的被隐藏了】
                target_price = price_container.find_element(
                    AppiumBy.ANDROID_UIAUTOMATOR,
                    f'new UiSelector().className("android.widget.FrameLayout").index({self.config.price_index}).clickable(true)'
                )
                self.driver.execute_script('mobile: clickGesture', {'elementId': target_price.id})

                # if not self.ultra_fast_click(AppiumBy.ANDROID_UIAUTOMATOR,
                #                              'new UiSelector().textMatches(".*799.*|.*\\d+元.*")'):
                #     return False

            # 4. 数量选择
            print("选择数量...")
            if self.driver.find_elements(by=By.ID, value='layout_num'):
                clicks_needed = len(self.config.users) - 1
                if clicks_needed > 0:
                    try:
                        plus_button = self.driver.find_element(By.ID, 'img_jia')
                        for i in range(clicks_needed):
                            rect = plus_button.rect
                            x = rect['x'] + rect['width'] // 2
                            y = rect['y'] + rect['height'] // 2
                            self.driver.execute_script("mobile: clickGesture", {
                                "x": x,
                                "y": y,
                                "duration": 50
                            })
                            time.sleep(0.02)
                    except Exception as e:
                        print(f"快速点击加号失败: {e}")

            # if self.driver.find_elements(by=By.ID, value='layout_num') and self.config.users is not None:
            #     for i in range(len(self.config.users) - 1):
            #         self.driver.find_element(by=By.ID, value='img_jia').click()

            # 5. 确定购买
            print("确定购买...")
            confirm_clicked = self.ultra_fast_click(By.ID, "btn_buy_view")
            if not confirm_clicked:
                # 备用按钮文本
                confirm_clicked = self.ultra_fast_click(
                    AppiumBy.ANDROID_UIAUTOMATOR,
                    'new UiSelector().textMatches(".*确定.*|.*购买.*")'
                )

            if not confirm_clicked:
                print("确定购买失败")
                return False

            # 6. 批量选择用户
            print("选择用户...")
            user_clicks = [(AppiumBy.ANDROID_UIAUTOMATOR, f'new UiSelector().text("{user}")') for user in
                           self.config.users]
            # self.batch_click(user_clicks, delay=0.05)  # 极短延迟
            selected_count = self.ultra_batch_click(user_clicks)
            if self.config.users and selected_count == 0:
                print("未选择到任何观演人，流程失败")
                return False

            # 7. 提交订单
            if self.config.if_commit_order:
                print("提交订单...")
                submit_selectors = [
                    (AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().text("立即提交")'),
                    (AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().textMatches(".*提交.*|.*确认.*")'),
                    (By.XPATH, '//*[contains(@text,"提交")]')
                ]
                if not self.smart_wait_and_click(*submit_selectors[0], submit_selectors[1:]):
                    print("提交订单按钮未找到")
                    return False
            else:
                print("测试模式: 已到达提交订单步骤，按配置跳过实际提交")

            end_time = time.time()
            print(f"抢票流程完成，耗时: {end_time - start_time:.2f}秒")
            return True

        except Exception as e:
            print(f"抢票过程发生错误: {e}")
            return False
        finally:
            time.sleep(1)  # 给最后的操作一点时间
            try:
                if self.driver:
                    self.driver.quit()
            finally:
                self._restore_device_ime()
                self.driver = None

    def run_with_retry(self, max_retries=3):
        """带重试机制的抢票"""
        for attempt in range(max_retries):
            print(f"第 {attempt + 1} 次尝试...")
            if self.run_ticket_grabbing():
                print("抢票成功！")
                return True
            else:
                print(f"第 {attempt + 1} 次尝试失败")
                if attempt < max_retries - 1:
                    print("2秒后重试...")
                    time.sleep(2)
                    # 重新初始化驱动
                    try:
                        self.driver.quit()
                    except:
                        pass
                    self._setup_driver()

        print("所有尝试均失败")
        return False

    def dismiss_startup_popups(self):
        """处理首启隐私协议、权限授权等常见弹窗"""
        popup_selectors = [
            (AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().text("同意")'),
            (By.XPATH, '//*[contains(@text,"同意")]'),
            (AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().textMatches(".*允许.*")'),
            (By.XPATH, '//*[contains(@text,"允许")]'),
            (AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().textMatches(".*我知道了.*|.*知道了.*")'),
        ]

        handled = 0
        for _ in range(3):
            clicked_this_round = False
            for by, value in popup_selectors:
                try:
                    if self.smart_wait_and_click(by, value, timeout=0.8):
                        handled += 1
                        clicked_this_round = True
                        print(f"已处理启动弹窗: {value}")
                        break
                except Exception:
                    continue
            if not clicked_this_round:
                break

        if handled > 0:
            print(f"启动弹窗处理完成，共点击 {handled} 次")


# 使用示例
if __name__ == "__main__":
    bot = DamaiBot()
    bot.run_with_retry(max_retries=3)
