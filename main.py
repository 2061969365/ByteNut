import time
import os
import sys
import json
import random
import requests
import platform
from datetime import datetime

if "DISPLAY" not in os.environ:
    if platform.system().lower() == "linux":
        try:
            from pyvirtualdisplay import Display
            display = Display(visible=False, size=(1920, 1080))
            display.start()
            os.environ["DISPLAY"] = display.new_display_var
        except:
            pass

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# ================= 配置区域 =================
PROXY = os.getenv("PROXY") or None
TG_TOKEN = os.getenv("TG_BOT_TOKEN")
TG_CHAT_ID = os.getenv("TG_CHAT_ID")
ACCOUNTS = os.getenv("BYTENUT", "")

URL_LOGIN_PANEL = "https://www.bytenut.com/auth/login"
URL_HOMEPAGE = "https://www.bytenut.com/homepage"
API_SERVER_LIST = "https://www.bytenut.com/game-panel/api/gpPanelServer/user/servers"
API_EXTENSION_INFO = "https://www.bytenut.com/game-panel/api/gp-free-server/extension-info/{}"
API_START_STATUS = "https://www.bytenut.com/game-panel/api/serverStartQueue/status/{}"

RENEW_MENU = '//li[contains(., "RENEW SERVER")]'
EXTEND_BTN = "button.extend-btn"
START_BTN = "button.start-btn"
START_VERIFY_DIALOG = "div.el-dialog"
MANAGEMENT_MENU = '//li[contains(@class,"el-sub-menu")]//span[text()="Management"]'
CONSOLE_MENU_ITEM = '//li[contains(@class,"el-menu-item")]//span[text()="Console"]'
START_STOP_MENU_ITEM = '//li[contains(@class,"el-menu-item")]//span[text()="Start / Stop"]'
PAGE_READY_INDICATOR = '//li[contains(@class,"el-menu-item")]'


def parse_accounts(raw: str):
    accounts = []
    for line in raw.strip().split("\n"):
        line = line.strip()
        if not line or "-----" not in line:
            continue
        parts = line.split("-----", 1)
        if len(parts) == 2:
            accounts.append((parts[0].strip(), parts[1].strip()))
    return accounts


class BytenutRenewal:

    def __init__(self):
        self.BASE_DIR = os.path.dirname(os.path.abspath(__file__))
        self.screenshot_dir = os.path.join(self.BASE_DIR, "artifacts")
        os.makedirs(self.screenshot_dir, exist_ok=True)

    # ========== 脱敏工具 ==========
    def mask_account(self, u):
        if not u:
            return "Unknown"
        u = u.strip()
        if "@" in u:
            local, domain = u.split("@", 1)
            masked_local = (
                local[:2] + "*" * (len(local) - 2)
                if len(local) > 2
                else local[0] + "*"
            )
            return f"{masked_local}@{domain}"
        return u[:2] + "*" * (len(u) - 2) if len(u) > 2 else u[0] + "*"

    def mask_server_id(self, sid):
        return "[server]"

    def log(self, msg):
        print(f"[{time.strftime('%H:%M:%S')}] [INFO] {msg}", flush=True)

    def _by(self, selector):
        """自动识别 CSS 选择器还是 XPath"""
        return By.XPATH if selector.startswith("/") or selector.startswith("(") else By.CSS_SELECTOR

    def find(self, driver, selector, timeout=10):
        """找元素，超时抛出"""
        return WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((self._by(selector), selector)))

    def click(self, driver, selector, timeout=10):
        """点元素"""
        el = self.find(driver, selector, timeout)
        el.click()
        return el

    def wait_present(self, driver, selector, timeout=10):
        """等元素出现"""
        return WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((self._by(selector), selector)))

    def wait_visible(self, driver, selector, timeout=10):
        """等元素可见"""
        return WebDriverWait(driver, timeout).until(
            EC.visibility_of_element_located((self._by(selector), selector)))

    def is_present(self, driver, selector):
        """检查元素是否存在"""
        try:
            driver.find_element(self._by(selector), selector)
            return True
        except NoSuchElementException:
            return False

    def is_visible(self, driver, selector):
        """检查元素是否可见"""
        try:
            el = WebDriverWait(driver, 3).until(
                EC.visibility_of_element_located((self._by(selector), selector)))
            return el.is_displayed()
        except Exception:
            return False

    def is_enabled(self, driver, selector):
        """检查元素是否启用"""
        try:
            el = driver.find_element(self._by(selector), selector)
            return el.is_enabled()
        except NoSuchElementException:
            return False

    def shot(self, driver, name):
        path = os.path.join(self.screenshot_dir, name)
        driver.save_screenshot(path)
        return path

    # ========== TG 通知 ==========
    def send_tg(self, icon, title, account_name, server_id,
                state_str, expiry_str, extra="", screenshot=None):
        if not TG_TOKEN or not TG_CHAT_ID:
            return
        msg = (
            f"{icon} {title}\n\n"
            f"账号: {account_name}\n"
            f"服务器: {server_id}\n"
            f"状态: {state_str}\n"
            f"到期时间: {expiry_str}\n"
        )
        if extra:
            msg += f"\n{extra}\n"
        msg += "\nByteNut Auto Renew"
        try:
            if screenshot and os.path.exists(screenshot):
                url = f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto"
                with open(screenshot, "rb") as f:
                    requests.post(
                        url,
                        data={"chat_id": TG_CHAT_ID, "caption": msg},
                        files={"photo": f},
                    )
            else:
                url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
                requests.post(url, data={"chat_id": TG_CHAT_ID, "text": msg})
        except Exception as e:
            self.log(f"TG发送失败: {e}")

    # ========== API 登录 ==========
    API_LOGIN = "https://www.bytenut.com/api/auth/login"

    def api_login(self, user, pwd):
        """直接調用 API 登錄，返回 token；失敗返回 None"""
        try:
            sess = requests.Session()
            sess.proxies.update({"http": PROXY, "https": PROXY}) if PROXY else None
            sess.headers.update({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
                "Origin": "https://www.bytenut.com",
                "Referer": "https://www.bytenut.com/auth/login",
            })
            sess.get("https://www.bytenut.com/auth/login", timeout=15)
            resp = sess.post(
                self.API_LOGIN,
                json={"username": user, "password": pwd, "rememberMe": True},
                timeout=30,
            )
            self.log(f"  API 响应状态码: {resp.status_code}")
            body_text = resp.text[:1000]
            self.log(f"  API 响应体: {body_text}")
            data = resp.json()
            code = data.get("code") or data.get("status")
            if code and code == 200:
                token = data.get("data", {}).get("token") or data.get("data", {}).get("yl-token")
                if token:
                    self.log(f"  API 登录成功，token 长度: {len(token)}")
                    return token
            self.log(f"  API 登录失败: {data.get('message', data.get('error', resp.status_code))}")
        except Exception as e:
            self.log(f"  API 登录异常: {e}")
        return None

    def set_token_in_browser(self, driver, token):
        """在浏览器中设置登录 token"""
        driver.execute_script(f"""
            localStorage.setItem('yl-token', '{token}');
            sessionStorage.setItem('yl-token', '{token}');
        """)
        self.log("  Token 已写入浏览器")

    # ========== 浏览器内 fetch（变量嵌入脚本）==========
    def fetch_api(self, driver, url, method="GET", referer=None):
        """
        在浏览器上下文执行 fetch，变量直接嵌入脚本字符串。
        返回解析后的 data，失败返回 None。
        """
        if referer is None:
            referer = URL_HOMEPAGE

        # 用 json.dumps 确保字符串正确转义
        import json
        url_js = json.dumps(url)
        method_js = json.dumps(method)
        referer_js = json.dumps(referer)

        script = f"""
        var callback = arguments[0];
        var token = localStorage.getItem('yl-token')
                 || sessionStorage.getItem('yl-token') || '';
        var headers = {{
            'Accept': 'application/json, text/plain, */*',
            'Referer': {referer_js}
        }};
        if (token) {{ headers['Yl-Token'] = token; }}
        fetch({url_js}, {{
            method: {method_js},
            headers: headers,
            credentials: 'include'
        }})
        .then(function(r) {{ return r.json(); }})
        .then(function(data) {{ callback({{ok: true, data: data}}); }})
        .catch(function(e) {{ callback({{ok: false, error: e.toString()}}); }});
        """
        try:
            result = driver.execute_async_script(script)
            if result and result.get("ok"):
                resp = result["data"]
                if resp.get("code") == 200:
                    return resp.get("data")
                self.log(f"API 业务错误: {resp.get('message')}")
            else:
                err = result.get("error") if result else "None"
                self.log(f"fetch 失败: {err}")
        except Exception as e:
            self.log(f"fetch_api 异常: {e}")
        return None

    def fetch_api_post(self, driver, url, referer=None):
        """POST 版本"""
        if referer is None:
            referer = URL_HOMEPAGE

        import json
        url_js = json.dumps(url)
        referer_js = json.dumps(referer)

        script = f"""
        var callback = arguments[0];
        var token = localStorage.getItem('yl-token')
                 || sessionStorage.getItem('yl-token') || '';
        var headers = {{
            'Accept': 'application/json, text/plain, */*',
            'Content-Type': 'application/x-www-form-urlencoded',
            'Referer': {referer_js}
        }};
        if (token) {{ headers['Yl-Token'] = token; }}
        fetch({url_js}, {{
            method: 'POST',
            headers: headers,
            credentials: 'include'
        }})
        .then(function(r) {{ return r.json(); }})
        .then(function(data) {{ callback({{ok: true, data: data}}); }})
        .catch(function(e) {{ callback({{ok: false, error: e.toString()}}); }});
        """
        try:
            result = driver.execute_async_script(script)
            if result and result.get("ok"):
                resp = result["data"]
                if resp.get("code") == 200:
                    return resp.get("data")
                self.log(f"API 业务错误: {resp.get('message')}")
            else:
                err = result.get("error") if result else "None"
                self.log(f"fetch POST 失败: {err}")
        except Exception as e:
            self.log(f"fetch_api_post 异常: {e}")
        return None

    # ========== API 封装 ==========
    def get_servers_data(self, driver):
        return self.fetch_api(driver, API_SERVER_LIST, referer=URL_HOMEPAGE)

    def get_extension_data(self, driver, server_id):
        ref = f"https://www.bytenut.com/free-gamepanel/{server_id}"
        return self.fetch_api(driver, API_EXTENSION_INFO.format(server_id),
                              referer=ref)

    def get_start_status(self, driver, server_id):
        ref = f"https://www.bytenut.com/free-gamepanel/{server_id}"
        return self.fetch_api(driver, API_START_STATUS.format(server_id),
                              referer=ref)

    # ========== 等待页面就绪 ==========
    def wait_for_panel_ready(self, driver, server_id, timeout=30):
        self.log("⏳ 等待页面加载...")
        try:
            self.wait_present(driver, PAGE_READY_INDICATOR, timeout=timeout)
        except Exception:
            self.log("⚠️ 侧边栏未出现，继续...")

        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                if self.is_present(driver, RENEW_MENU):
                    self.log("✅ 页面就绪（RENEW SERVER 可见）")
                    return True
            except Exception:
                pass
            self.remove_overlay_ads(driver)
            time.sleep(1)
        self.log("⚠️ RENEW SERVER 等待超时")
        return False

    # ========== 轮询开机队列 ==========
    def poll_start_status(self, driver, server_id, timeout=300, interval=5):
        deadline = time.time() + timeout
        while time.time() < deadline:
            data = self.get_start_status(driver, server_id)
            if data:
                in_queue = data.get("inQueue", True)
                can_start = data.get("canStart", False)
                pos = data.get("queuePosition", 0)
                wait_sec = data.get("estimatedWaitSeconds")
                msg = data.get("statusMessage", "")
                self.log(f"  队列: inQueue={in_queue}, pos={pos}, "
                         f"wait={wait_sec}s, msg={msg}")
                if not in_queue and can_start:
                    self.log("✅ 服务器启动成功（队列完成）")
                    return True, "running"
            time.sleep(interval)
        return False, "timeout"

    def wait_until_running(self, driver, server_id, timeout=120, interval=10):
        deadline = time.time() + timeout
        while time.time() < deadline:
            servers = self.get_servers_data(driver)
            if servers:
                for srv in servers:
                    if str(srv.get("id")) == str(server_id):
                        state = (srv.get("serverInfo") or {}).get(
                            "state", "unknown")
                        self.log(f"  server state: {state}")
                        if state == "running":
                            return True, state
            time.sleep(interval)
        return False, "unknown"

    def wait_until_not_expired(self, driver, server_id, timeout=120, interval=10):
        deadline = time.time() + timeout
        while time.time() < deadline:
            ext_info = self.get_extension_data(driver, server_id)
            if ext_info and ext_info.get("minutesUntilExpiration", 0) > 0:
                return True
            time.sleep(interval)
        return False

    # ========== Stealth 指纹增强 ==========
    def _setup_console_log_capture(self, driver):
        """通过 CDP 启用浏览器日志捕获"""
        try:
            driver.execute_cdp_cmd('Log.enable', {})
            self.log("[OK] CDP Log 已启用")
        except Exception as e:
            self.log(f"  Log.enable 失败: {e}")

    def _print_extension_logs(self, driver):
        """打印浏览器控制台日志（含扩展输出）"""
        try:
            logs = driver.get_log('browser')
            for entry in logs:
                msg = entry.get('message', '')
                level = entry.get('level', '')
                # 只打印与 nopecha / captcha 相关的日志
                if any(kw in msg.lower() for kw in ['nopecha', 'captcha', 'hcaptcha',
                                                       'token', 'error', 'fail', 'ban',
                                                       'api', 'solve', 'recogni']):
                    self.log(f"  [CONSOLE {level}] {msg[:200]}")
        except Exception:
            pass

    def _inject_stealth(self, driver):
        try:
            driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                "source": """
                (function() {
                    // 1. 覆盖 navigator.webdriver
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined,
                        configurable: true,
                    });

                    // 2. 模拟 chrome.runtime
                    window.chrome = window.chrome || {};
                    window.chrome.runtime = {
                        onMessage: { addListener: function() {} },
                        onConnect: { addListener: function() {} },
                        onInstalled: { addListener: function() {} },
                        sendMessage: function() {},
                        connect: function() {
                            return { onMessage: { addListener: function() {} } };
                        },
                        id: 'aohjdmifjbbilmlibpbjggmpoemapnaj',
                    };
                    window.chrome.loadTimes = function() { return {}; };
                    window.chrome.csi = function() { return {}; };
                    window.chrome.app = {
                        isInstalled: false,
                        InstallState: { DISABLED: 'disabled', INSTALLED: 'installed', NOT_INSTALLED: 'not_installed' },
                        RunningState: { CANNOT_RUN: 'cannot_run', READY_TO_RUN: 'ready_to_run', RUNNING: 'running' },
                    };

                    // 3. navigator.plugins — 模拟真实插件数量
                    Object.defineProperty(navigator, 'plugins', {
                        get: () => [
                            { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' },
                            { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' },
                            { name: 'Native Client', filename: 'internal-nacl-plugin' },
                        ],
                        configurable: true,
                    });

                    // 4. 设置真实语言列表
                    Object.defineProperty(navigator, 'languages', {
                        get: () => ['en-US', 'en'],
                        configurable: true,
                    });

                    // 5. CPU 核心数 / 内存
                    Object.defineProperty(navigator, 'hardwareConcurrency', {
                        get: () => 8,
                        configurable: true,
                    });
                    Object.defineProperty(navigator, 'deviceMemory', {
                        get: () => 8,
                        configurable: true,
                    });

                    // 6. 删除 CDP 注入痕迹
                    for (var key in window) {
                        if (key.startsWith('$cdc_') || key.startsWith('$chrome_')) {
                            try { delete window[key]; } catch(e) {}
                        }
                    }

                    // 7. WebGL 伪装
                    try {
                        var getParameter = WebGLRenderingContext.prototype.getParameter;
                        WebGLRenderingContext.prototype.getParameter = function(param) {
                            if (param === 37445) return 'Intel Inc.';
                            if (param === 37446) return 'Intel Iris OpenGL Engine';
                            return getParameter.call(this, param);
                        };
                    } catch(e) {}
                })();
                """
            })
            self.log("[OK] Stealth 指纹注入完成")
        except Exception as e:
            self.log(f"[WARN] Stealth 注入失败: {e}")

    # ========== Cookie 弹窗处理 ==========
    def dismiss_cookie_consent(self, driver):
        try:
            driver.execute_script("""
                (function(){
                    // Google Funding Choices / Ezoic cookie consent
                    var selectors = [
                        'button.fc-button-label',
                        'button.fc-cta-consent',
                        '.fc-dialog button',
                        '[aria-label="Continue with Recommended Cookies"]',
                        '.fc-primary-button',
                        'button[title="Continue with Recommended Cookies"]'
                    ];
                    for (var i = 0; i < selectors.length; i++) {
                        var btn = document.querySelector(selectors[i]);
                        if (btn) { btn.click(); return; }
                    }
                    // 尝试直接找包含 "Continue with Recommended" 文字的按钮
                    document.querySelectorAll('button').forEach(function(el){
                        var txt = el.textContent.trim();
                        if (txt.indexOf('Continue with Recommended') !== -1
                            || txt === 'Dismiss'
                            || txt === 'Opt out')
                            el.click();
                    });
                    // Ezoic 弹窗: 直接点关闭或隐藏
                    var closeBtn = document.querySelector('#ez-cookie-dismiss, [data-ezcb="1"], .ez-cookie-close');
                    if (closeBtn) closeBtn.click();
                    // 隐藏整个 dialog
                    var dialog = document.querySelector('.fc-dialog-wrapper, .fc-consent-root, .fc-dialog-overlay, .ez-cookie-dialog');
                    if (dialog) dialog.style.display = 'none';
                })();
            """)
        except Exception:
            pass

    # ========== 广告清理 ==========
    def remove_overlay_ads(self, driver):
        try:
            driver.execute_script("""
                (function(){
                    var a = document.getElementById('ez-accept-all');
                    if (a) a.click();
                    var keep = ['turnstile','cf-turnstile','extend-btn',
                                'adsterra-rewarded','Claim Reward','Watch Ad',
                                'start-btn','Start','Continue',
                                'RENEW SERVER','el-menu'];
                    ['ins.adsbygoogle','iframe[id^="aswift"]',
                     'div[id^="google_ads"]',
                     'div[class*="ad-"]:not([class*="adsterra-rewarded"])',
                     'div[class*="ads-"]',
                     'div[id*="ad-"]:not([id*="adsterra"])',
                     'div[id*="ads-"]','.ad-container','.ads-wrapper',
                     '.fixed-bottom-banner','.ezoic-floating-bottom',
                     '.fc-ab-root'
                    ].forEach(function(s){
                        document.querySelectorAll(s).forEach(function(el){
                            if (keep.some(function(k){
                                return el.innerHTML.indexOf(k) !== -1;
                            })) return;
                            el.style.cssText += 'display:none!important;'
                                + 'visibility:hidden!important;'
                                + 'height:0!important;width:0!important;';
                        });
                    });
                    document.body.style.overflow = 'auto';
                    document.body.style.position = 'static';

                    // 移除全屏透明覆盖层（阻挡点击的元凶）
                    document.querySelectorAll('div').forEach(function(el) {
                        var s = window.getComputedStyle(el);
                        if (s.position === 'fixed'
                            && parseFloat(s.opacity) < 0.1
                            && el.innerHTML.trim() === '') {
                            el.remove();
                        }
                    });
                })();
            """)
        except Exception:
            pass
    
    # ========== Captcha 通用处理 ==========
    def is_hcaptcha_present(self, driver):
        try:
            return driver.execute_script("""
                return !!(document.querySelector('.h-captcha')
                    || document.querySelector('.hcaptcha')
                    || document.querySelector('iframe[src*="hcaptcha"]')
                    || document.querySelector('div[data-sitekey*="hcaptcha"]'));
            """)
        except Exception:
            return False

    def is_turnstile_present(self, driver):
        try:
            return driver.execute_script("""
                return !!(document.querySelector('.cf-turnstile')
                    || document.querySelector(
                        'iframe[src*="challenges.cloudflare"]')
                    || document.querySelector(
                        'input[name="cf-turnstile-response"]'));
            """)
        except Exception:
            return False

    def is_captcha_present(self, driver):
        """检测任意类型验证码"""
        try:
            return self.is_hcaptcha_present(driver) or self.is_turnstile_present(driver)
        except Exception:
            return False

    def _try_click_hcaptcha(self, driver):
        """尝试点击 hCaptcha checkbox"""
        try:
            # 找到 hCaptcha iframe 坐标
            info = driver.execute_script("""
                var h = document.querySelector('.h-captcha iframe, .hcaptcha iframe, iframe[src*="hcaptcha"], .h-captcha, .hcaptcha');
                if (!h) return null;
                var r = h.getBoundingClientRect();
                if (r.width === 0 || r.height === 0) return null;
                return { x: r.left + r.width/2, y: r.top + r.height/2 };
            """)
            if not info:
                self.log("  hCaptcha 元素不可见")
                return False
            x, y = int(info['x']), int(info['y'])
            self.log(f"  hCaptcha @ {x},{y}")

            # 用 CDP 发送真实鼠标事件（和 Falix 一样）
            try:
                import time
                cmd = driver.execute_cdp_cmd
                cmd('Input.dispatchMouseEvent', {'type': 'mouseMoved', 'x': x, 'y': y, 'button': 'none', 'buttons': 0, 'modifiers': 0, 'clickCount': 0})
                time.sleep(0.05)
                cmd('Input.dispatchMouseEvent', {'type': 'mousePressed', 'x': x, 'y': y, 'button': 'left', 'buttons': 1, 'modifiers': 0, 'clickCount': 1})
                time.sleep(0.05)
                cmd('Input.dispatchMouseEvent', {'type': 'mouseReleased', 'x': x, 'y': y, 'button': 'left', 'buttons': 0, 'modifiers': 0, 'clickCount': 1})
                self.log("  CDP click 完成")
                return True
            except Exception as e:
                self.log(f"  CDP click 失败: {e}")

            # 降级: 切换到 iframe 点击
            try:
                for f in driver.find_elements(By.CSS_SELECTOR, 'iframe[src*="hcaptcha"]'):
                    driver.switch_to.frame(f)
                    for sel in ['#checkbox', '.checkbox', '[role="checkbox"]', 'div[tabindex]']:
                        els = driver.find_elements(By.CSS_SELECTOR, sel)
                        for el in els:
                            if el.is_displayed() and el.is_enabled():
                                el.click()
                                self.log(f"  iframe click: {sel}")
                                driver.switch_to.default_content()
                                return True
                    driver.switch_to.default_content()
            except Exception:
                try: driver.switch_to.default_content()
                except: pass

            # 再降级: uc_gui_click_captcha
            self.log("  扩展已自动处理 captcha 点击")
            return True
        except Exception as e:
            self.log(f"hCaptcha click 异常: {e}")
            return False

    def _setup_nopecha_extension(self):
        """下载并配置 NopeCHA graphical build 扩展（无需 API key）"""
        ext_dir = "nopecha_ext"
        if os.path.isdir(ext_dir) and os.path.isfile(os.path.join(ext_dir, "manifest.json")):
            self.log(f"  NopeCHA 扩展已存在: {ext_dir}")
            return ext_dir
        try:
            url = ("https://github.com/NopeCHALLC/nopecha-extension/"
                   "releases/latest/download/chromium.zip")
            self.log("  NopeCHA: 下载 graphical build...")
            r = requests.get(url, timeout=30)
            zip_path = "nopecha_ext.zip"
            with open(zip_path, "wb") as f:
                f.write(r.content)
            import zipfile
            with zipfile.ZipFile(zip_path, "r") as z:
                z.extractall(ext_dir)
            os.remove(zip_path)
            self.log(f"[OK] NopeCHA 扩展已下载: {ext_dir}")
            return ext_dir
        except Exception as e:
            self.log(f"  NopeCHA 扩展下载失败: {e}")
            return None

    def _detect_chrome_version(self):
        """自动检测 Chrome 主版本号，防止 ChromeDriver 版本不匹配"""
        try:
            import subprocess, re
            if platform.system().lower() == "windows":
                for key_path in [
                    r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe",
                    r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe",
                ]:
                    try:
                        import winreg
                        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as k:
                            chrome_path = winreg.QueryValue(k, None)
                            if chrome_path and os.path.isfile(chrome_path):
                                cmd = ['powershell', '-c',
                                       f'(Get-Item "{chrome_path}").VersionInfo.FileVersion']
                                result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                                m = re.search(r"(\d+)", result.stdout or "")
                                if m:
                                    v = int(m.group(1))
                                    self.log(f"  Chrome 版本: {v}")
                                    return v
                    except:
                        continue
            else:
                paths = ["google-chrome", "google-chrome-stable", "chromium-browser", "chromium"]
                for p in paths:
                    try:
                        result = subprocess.run([p, "--version"], capture_output=True, text=True, timeout=5)
                        m = re.search(r"(\d+)\.", result.stdout or "")
                        if m:
                            v = int(m.group(1))
                            self.log(f"  Chrome 版本: {v}")
                            return v
                    except:
                        continue
        except:
            pass
        self.log("  Chrome 版本检测失败，使用默认")
        return None

    def _is_visual_challenge_open(self, driver):
        """检测 hCaptcha visual challenge 是否已打开"""
        try:
            return driver.execute_script("""
                var iframe = document.querySelector('.h-captcha iframe, iframe[src*="hcaptcha"]');
                if (!iframe) return false;
                try {
                    var doc = iframe.contentDocument || iframe.contentWindow.document;
                    return !!(doc.querySelector('.challenge-container')
                        || doc.querySelector('.task-image')
                        || doc.querySelector('.image-grid')
                        || doc.querySelector('[class*="grid"]')
                        || doc.querySelector('#center')
                        || doc.querySelector('td'));
                } catch(e) {
                    return iframe.src && iframe.src.indexOf('checkbox') === -1;
                }
            """)
        except Exception:
            return False

    def resolve_captcha(self, driver, timeout=120):
        """通用验证码处理 — 扩展加载后不做任何点击，只轮询 token"""
        hc = self.is_hcaptcha_present(driver)
        tc = self.is_turnstile_present(driver)

        if not hc and not tc:
            self.log("[OK] 无验证码，跳过")
            return True

        captcha_type = "hCaptcha" if hc else "Turnstile"
        self.log(f"⏳ 检测到 {captcha_type}，扩展将自动处理...")

        # 扩展有 hcaptcha_auto_open: true + hcaptcha_auto_solve: true
        # 它会自动点击 checkbox 并解题，我们只需轮询 token
        self.log("  NopeCHA 扩展已加载，等待自动解题（不做任何点击）...")

        start = time.time()
        check_interval = 2  # 每2秒检查一次 token

        while time.time() - start < timeout:
            # 检查 hCaptcha token
            if self.is_hcaptcha_present(driver):
                try:
                    val = driver.execute_script("""
                        var i = document.querySelector(
                            'textarea[name="h-captcha-response"],'
                          + 'input[name="h-captcha-response"]');
                        return i ? i.value : '';
                    """)
                    if len(val) > 20:
                        elapsed = int(time.time() - start)
                        self.log(f"[OK] hCaptcha 完成（耗时 {elapsed}s）")
                        return True
                except Exception:
                    pass

            # 检查 Turnstile token
            if self.is_turnstile_present(driver):
                try:
                    val = driver.execute_script(
                        "return document.querySelector("
                        "\"input[name='cf-turnstile-response']\")?.value || '';"
                    )
                    if len(val) > 20:
                        self.log("[OK] Turnstile 完成")
                        return True
                except Exception:
                    pass

            # 每10秒输出一次等待状态并打印扩展日志
            elapsed = int(time.time() - start)
            if elapsed > 0 and elapsed % 10 == 0:
                self.log(f"  等待扩展解题中... {elapsed}s/{timeout}s")
                self._print_extension_logs(driver)

            time.sleep(check_interval)

        # 超时后再检查一次
        if self.is_hcaptcha_present(driver):
            try:
                val = driver.execute_script(
                    "return (document.querySelector('textarea[name=\"h-captcha-response\"]')"
                    "|| document.querySelector('input[name=\"h-captcha-response\"]'))?.value||'';"
                )
                if len(val) > 20:
                    self.log("[OK] hCaptcha 超时后完成")
                    return True
            except Exception:
                pass

        # Fallback: 最后尝试 CDP 点击一次
        self.log("  扩展超时，尝试一次 CDP 点击...")
        try:
            self.log("  扩展已自动处理 captcha 点击")
            self._try_click_hcaptcha(driver)
        except Exception:
            pass

        # 再等10秒
        for _ in range(5):
            try:
                val = driver.execute_script(
                    "return document.querySelector('textarea[name=\"h-captcha-response\"]')?.value||'';"
                )
                if len(val) > 20:
                    self.log("[OK] hCaptcha CDP 点击后完成")
                    return True
            except Exception:
                pass
            time.sleep(2)

        print(f"::error::{captcha_type} 验证超时", flush=True)
        self.log(f"[FAIL] {captcha_type} 超时")
        return False

    def wait_turnstile(self, driver, timeout=90):
        """保留旧接口，内部委托 resolve_captcha"""
        return self.resolve_captcha(driver, timeout)

    # ========== NopeTCHA 验证码检测与处理 ==========
    def detect_nopecha_captcha(self, driver):
        """检测 NopeTCHA 视觉验证码（非 hCaptcha/Turnstile）"""
        try:
            return driver.execute_script("""
                return !!(document.querySelector('[class*="nopecha"]')
                    || document.querySelector('[id*="nopecha"]')
                    || document.querySelector('div[style*="position: fixed"][style*="z-index"]')
                    || document.querySelector('.task-image')
                    || document.querySelector('.image-grid')
                    || document.querySelector('[class*="challenge"]'));
            """)
        except Exception:
            return False

    def wait_nopecha_solve(self, driver, timeout=90):
        """等待 NopeTCHA 验证码被扩展自动解决"""
        start = time.time()
        self.log("⏳ 等待 NopeTCHA 验证码解决...")
        while time.time() - start < timeout:
            # 检查验证码是否已消失
            if not self.detect_nopecha_captcha(driver):
                self.log("[OK] NopeTCHA 验证码已解决")
                return True
            # 每 15 秒检查一次
            time.sleep(5)
            elapsed = int(time.time() - start)
            if elapsed % 15 == 0 and elapsed > 0:
                self.log(f"  NopeTCHA 等待中... {elapsed}s/{timeout}s")
                self._print_extension_logs(driver)
        self.log("[FAIL] NopeTCHA 验证码超时")
        return False

    def _wait_dialog_turnstile(self, driver, timeout=30):
        self.log("⏳ 等待弹窗验证码（最多 30s）...")
        start = time.time()
        last_click = 0
        while time.time() - start < timeout:
            self.remove_overlay_ads(driver)
            if driver.execute_script(
                    "return !document.querySelector('div.el-dialog');"):
                self.log("✅ 弹窗已消失，验证自动完成")
                return True
            if driver.execute_script("""
                var btn = document.querySelector(
                    'div.el-dialog__footer button.el-button--primary');
                return btn && !btn.disabled
                    && !btn.classList.contains('is-disabled');
            """):
                self.log("✅ Continue 已启用，验证自动完成")
                return True
            # 检查弹窗内的 Turnstile token
            try:
                val = driver.execute_script("""
                    var d = document.querySelector('div.el-dialog');
                    if (!d) return '';
                    var i = d.querySelector(
                        'input[name="cf-turnstile-response"]');
                    return i ? i.value : '';
                """)
                if val and len(val) > 20:
                    self.log("✅ 弹窗 Turnstile token 已填充")
                    return True
            except Exception:
                pass
            # 检查弹窗内的 hCaptcha token
            try:
                val = driver.execute_script("""
                    var d = document.querySelector('div.el-dialog');
                    if (!d) return '';
                    var i = d.querySelector(
                        'textarea[name="h-captcha-response"],'
                      + 'input[name="h-captcha-response"]');
                    return i ? i.value : '';
                """)
                if val and len(val) > 20:
                    self.log("✅ 弹窗 hCaptcha token 已填充")
                    return True
            except Exception:
                pass
            now = time.time()
            if now - last_click > 3:
                try:
                    self.log("  扩展已自动处理 captcha 点击")
                    last_click = now
                except Exception:
                    try:
                        driver.execute_script("""
                            var d = document.querySelector('div.el-dialog');
                            if (d) {
                                var ts = d.querySelector('.cf-turnstile, .h-captcha, .hcaptcha');
                                if (ts) ts.click();
                            }
                        """)
                        last_click = now
                    except Exception:
                        pass
            time.sleep(1)

        # 超时后最终检查
        if driver.execute_script(
                "return !document.querySelector('div.el-dialog');"):
            self.log("✅ 超时后弹窗已消失")
            return True
        if driver.execute_script("""
            var btn = document.querySelector(
                'div.el-dialog__footer button.el-button--primary');
            return btn && !btn.disabled
                && !btn.classList.contains('is-disabled');
        """):
            self.log("✅ 超时后 Continue 已启用")
            return True
        self.log("⚠️ 验证等待结束，尝试继续")
        return True

    # ========== 广告验证弹窗 ==========
    def handle_ad_verification(self, driver):
        try:
            if not driver.execute_script(
                "return !!document.querySelector("
                "'div.adsterra-rewarded-dialog');"
            ):
                return True
            self.log("🛡️ 处理广告验证...")
            time.sleep(1)
            driver.execute_script("""
                var btn = document.querySelector(
                    'div.adsterra-rewarded-dialog button.el-button--primary');
                if (btn) btn.click();
            """)
            time.sleep(3)
            orig = driver.current_window_handle
            if len(driver.window_handles) > 1:
                for h in driver.window_handles:
                    if h != orig:
                        driver.switch_to.window(h)
                        break
                time.sleep(12)
                driver.close()
                driver.switch_to.window(orig)
                time.sleep(2)
            driver.execute_script("""
                var btn = document.querySelector(
                    'div.adsterra-rewarded-dialog button.el-button--success');
                if (btn) btn.click();
            """)
            time.sleep(3)
            self.log("✅ 广告验证完成")
            return True
        except Exception as e:
            self.log(f"广告验证异常: {e}")
            return True

    # ========== 导航 + 等待就绪 ==========
    def navigate_to_panel(self, driver, server_id):
        url = f"https://www.bytenut.com/free-gamepanel/{server_id}"
        driver.get(url)
        time.sleep(6)
        time.sleep(5)
        self.remove_overlay_ads(driver)
        return self.wait_for_panel_ready(driver, server_id, timeout=30)

    # ========== 点击 RENEW SERVER（带重试）==========
    def click_renew_menu(self, driver, server_id, idx, max_retry=3):
        for attempt in range(1, max_retry + 1):
            try:
                self.wait_present(driver, RENEW_MENU, timeout=15)
                self.wait_visible(driver, RENEW_MENU, timeout=10)
                self.remove_overlay_ads(driver)
                # 额外移除可能残留的透明覆盖层
                driver.execute_script("""
                    document.querySelectorAll('div').forEach(function(el) {
                        var s = window.getComputedStyle(el);
                        if (s.position === 'fixed'
                            && parseFloat(s.opacity) < 0.1
                            && el.innerHTML.trim() === '') {
                            el.remove();
                        }
                    });
                """)
                el = self.find(driver, RENEW_MENU)
                driver.execute_script("arguments[0].click();", el)
                time.sleep(3)
                self.log(f"✅ RENEW SERVER 已点击 (attempt {attempt})")
                self._setup_console_log_capture(driver)
                # 等待并处理可能出现的 NopeTCHA 验证码
                if self.detect_nopecha_captcha(driver):
                    self.wait_nopecha_solve(driver, timeout=90)
                return True
            except Exception as e:
                self.log(f"⚠️ RENEW SERVER 失败 (attempt {attempt}): {e}")
                if attempt < max_retry:
                    self.shot(driver, f"renew_fail_{idx}_a{attempt}.png")
                    self.log("🔄 重新导航...")
                    self.navigate_to_panel(driver, server_id)
        self.log("❌ RENEW SERVER 最终失败")
        return False

    # ========== 续期 ==========
    def try_extend_and_verify(self, driver, server_id, old_expiry):
        if not self.resolve_captcha(driver):
            return False, ""
        self.remove_overlay_ads(driver)
        self.log("⏳ 点击续期按钮...")
        try:
            if self.is_visible(driver, EXTEND_BTN):
                driver.execute_script("arguments[0].click();",
                                  self.find(driver, EXTEND_BTN))
            else:
                self.log("⚠️ 续期按钮不可见")
                return False, ""
        except Exception as e:
            self.log(f"续期按钮点击失败: {e}")
            return False, ""

        time.sleep(2)
        self.handle_ad_verification(driver)
        time.sleep(5)

        for _ in range(6):
            new_ext = self.get_extension_data(driver, server_id)
            if new_ext:
                new_expiry = new_ext.get("expiredTime", "")
                if new_expiry and new_expiry != old_expiry:
                    self.log(f"✅ 续期生效: {self.format_expiry(new_expiry)}")
                    return True, self.format_expiry(new_expiry)
            time.sleep(5)

        if (self.is_present(driver, EXTEND_BTN)
                and not self.is_enabled(driver, EXTEND_BTN)):
            return "cooldown", ""
        return False, ""

    # ========== UI 开机 ==========
    def ui_start_server(self, driver, server_id, idx):
        self.log("🖥️ 导航到 Start/Stop 页面...")
        self.navigate_to_panel(driver, server_id)

        # Step 1: 展开 Management
        self.log("📂 展开 Management...")
        try:
            self.click(driver, MANAGEMENT_MENU)
            time.sleep(2)
        except Exception:
            try:
                driver.execute_script("""
                    document.querySelectorAll('.el-sub-menu__title span')
                    .forEach(function(el){
                        if (el.textContent.trim() === 'Management')
                            el.closest('.el-sub-menu__title').click();
                    });
                """)
                time.sleep(2)
            except Exception as e:
                self.log(f"Management 展开失败: {e}")
                return False, "management_fail"

        # Step 2: 点击 Start / Stop
        self.log("🖥️ 点击 Start / Stop...")
        try:
            self.click(driver, START_STOP_MENU_ITEM)
            time.sleep(3)
        except Exception:
            try:
                driver.execute_script("""
                    document.querySelectorAll('.el-menu-item span')
                    .forEach(function(el){
                        if (el.textContent.trim() === 'Start / Stop')
                            el.closest('.el-menu-item').click();
                    });
                """)
                time.sleep(3)
            except Exception as e:
                self.log(f"Start/Stop 点击失败: {e}")

        # Step 3: 等待 Start 按钮
        try:
            self.wait_present(driver, START_BTN, timeout=15)
            self.log("✅ Start/Stop 页面就绪")
        except Exception as e:
            self.log(f"⚠️ 等待 Start 超时: {e}")
            self.shot(driver, f"no_start_btn_{idx}.png")
            return False, "no_start_btn"

        # Step 4: 点击 Start
        self.log("▶️ 点击 Start...")
        self.remove_overlay_ads(driver)
        try:
            btn = self.find(driver, START_BTN)
            if btn.get_attribute("disabled"):
                self.log("⚠️ Start disabled")
                return False, "start_disabled"
            driver.execute_script(
                "arguments[0].scrollIntoView({block:'center'});", btn)
            time.sleep(0.5)
            driver.execute_script("arguments[0].click();", btn)
            self.log("  Start 已点击")
            time.sleep(2)
        except Exception as e:
            self.log(f"Start 点击失败: {e}")
            return False, "start_click_fail"

        # Step 5: 等待验证弹窗（最多 10s）
        self.log("⏳ 等待验证弹窗...")
        dialog_appeared = False
        for _ in range(10):
            try:
                if self.is_visible(driver, START_VERIFY_DIALOG):
                    dialog_appeared = True
                    break
            except Exception:
                pass
            data = self.get_start_status(driver, server_id)
            if data and not data.get("inQueue") and data.get("canStart"):
                self.log("✅ 无弹窗，直接开机成功")
                return True, "running"
            time.sleep(1)

        if not dialog_appeared:
            self.log("⚠️ 弹窗未出现，轮询状态...")
            ok, state = self.poll_start_status(driver, server_id, timeout=60)
            return (True, state) if ok else (False, "dialog_not_appeared")

        self.log("✅ 验证弹窗出现")

        # Step 6: 等待 Turnstile
        self._wait_dialog_turnstile(driver, timeout=30)

        # Step 7: 点击 Continue（最多 60s）
        self.log("▶️ 等待并点击 Continue...")
        continue_clicked = False
        for attempt in range(30):
            if driver.execute_script(
                    "return !document.querySelector('div.el-dialog');"):
                self.log("✅ 弹窗已自动消失")
                continue_clicked = True
                break
            if driver.execute_script("""
                var btn = document.querySelector(
                    'div.el-dialog__footer button.el-button--primary');
                return btn && !btn.disabled
                    && !btn.classList.contains('is-disabled');
            """):
                driver.execute_script("""
                    document.querySelector(
                        'div.el-dialog__footer button.el-button--primary'
                    ).click();
                """)
                self.log(f"  Continue 已点击 (attempt {attempt + 1})")
                continue_clicked = True
                break
            if attempt % 5 == 0:
                self.log(f"  等待 Continue 启用... ({attempt + 1}/30)")
            time.sleep(2)

        if not continue_clicked:
            self.log("❌ Continue 未启用")
            self.shot(driver, f"continue_fail_{idx}.png")
            return False, "continue_fail"

        time.sleep(3)

        # Step 8: 处理排队弹窗
        self._handle_queue_dialog(driver)

        # Step 9: 轮询开机状态
        self.log("⏳ 轮询开机状态...")
        ok, state = self.poll_start_status(
            driver, server_id, timeout=300, interval=5)
        if ok:
            self.log("⏳ 确认运行状态...")
            is_running, final_state = self.wait_until_running(
                driver, server_id, timeout=120, interval=10)
            return True, "running" if is_running else f"started({final_state})"
        return False, "start_timeout"

    def _handle_queue_dialog(self, driver):
        try:
            has_q = False
            for _ in range(5):
                has_q = driver.execute_script(
                    "return !!document.querySelector("
                    "'div.el-message-box.queue-dialog-styled');"
                )
                if has_q:
                    break
                time.sleep(1)
            if has_q:
                self.log("📋 排队弹窗，点击 OK...")
                driver.execute_script("""
                    document.querySelectorAll(
                        'div.el-message-box.queue-dialog-styled '
                        '.el-message-box__btns button'
                    ).forEach(function(btn){
                        if (btn.textContent.trim() === 'OK') btn.click();
                    });
                """)
                time.sleep(2)
                self.log("✅ 排队弹窗已关闭")
            else:
                self.log("ℹ️ 无排队弹窗")
        except Exception as e:
            self.log(f"排队弹窗异常: {e}")

    def format_expiry(self, dt_str):
        if not dt_str:
            return ""
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.strptime(dt_str, fmt).strftime(
                    "%b %d, %Y, %I:%M %p UTC")
            except ValueError:
                continue
        return dt_str

    # ========== 主流程 ==========
    def run(self):
        self.log("🚀 开始执行 ByteNut 续期与开机")
        has_error = False
        accounts = parse_accounts(ACCOUNTS)
        if not accounts:
            self.log("[FAIL] ❌ 无账号")
            sys.exit(1)

        # 下载 NopeCHA automation build 扩展
        ext_path = self._setup_nopecha_extension()
        if ext_path:
            ext_abspath = os.path.abspath(ext_path)
            self.log(f"  NopeCHA 扩展路径: {ext_abspath}")
        else:
            ext_abspath = None
            self.log("[WARN] NopeCHA 扩展加载失败，仅用 CDP 点击")

        for idx, (user, pwd) in enumerate(accounts, 1):
            masked_user = self.mask_account(user)
            self.log(f"==== 账号 [{idx}] {masked_user} ====")

            chrome_options = uc.ChromeOptions()
            for arg in [
                "--no-sandbox", "--disable-dev-shm-usage",
                "--disable-gpu", "--window-size=1280,753",
                "--disable-blink-features=AutomationControlled",
                "--disable-automation",
                "--no-first-run", "--no-default-browser-check",
                "--enable-logging=stderr",
            ]:
                chrome_options.add_argument(arg)
            if PROXY:
                chrome_options.add_argument(f"--proxy-server={PROXY}")
            if ext_abspath:
                chrome_options.add_argument(f"--load-extension={ext_abspath}")
            chrome_version = self._detect_chrome_version()
            driver = uc.Chrome(options=chrome_options, version_main=chrome_version)
            self._inject_stealth(driver)
            try:
                logged_in = False
                # --- API 登录 ---
                self.log("--- 尝试 API 登录 ---")
                token = self.api_login(user, pwd)
                if token:
                    self.set_token_in_browser(driver, token)
                    time.sleep(1)
                    driver.get(URL_HOMEPAGE)
                    time.sleep(6)
                    time.sleep(5)
                    current_token = driver.execute_script("""
                        return localStorage.getItem('yl-token') 
                            || sessionStorage.getItem('yl-token') || '';
                    """)
                    if len(current_token) > 10:
                        self.log("[OK] ✅ API 登录成功")
                        logged_in = True
                    else:
                        self.log("[FAIL] ⚠️ Token 设置未生效")
                        has_error = True
                if not logged_in:
                    # --- 浏览器登录 ---
                    self.log("--- 浏览器登录 ---")
                    driver.get(URL_LOGIN_PANEL)
                    time.sleep(5)
                    time.sleep(3)
                    self.dismiss_cookie_consent(driver)
                    time.sleep(1)
                    # 找用户名输入框
                    username_selectors = [
                        'input[placeholder="Username"]',
                        'input[placeholder*="username" i]',
                        'input[placeholder*="Username"]',
                        '.el-input__inner[type="text"]',
                        'input[type="text"]',
                    ]
                    username_found = False
                    for sel in username_selectors:
                        try:
                            self.wait_visible(driver, sel, timeout=5)
                            el = self.find(driver, sel)
                            driver.execute_script("arguments[0].focus(); arguments[0].select();", el)
                            for ch in user:
                                el.send_keys(ch)
                                time.sleep(random.uniform(0.04, 0.12))
                            username_found = True
                            self.log(f"  用户名输入框: {sel}")
                            break
                        except Exception:
                            continue
                    if not username_found:
                        self.log("[FAIL] ❌ 找不到用户名输入框")
                        self.shot(driver, f"login_no_username_{idx}.png")
                        has_error = True
                        continue
                    # 找密码输入框
                    password_selectors = [
                        'input[placeholder="Password"]',
                        'input[placeholder*="password" i]',
                        'input[placeholder*="Password"]',
                        'input[type="password"]',
                    ]
                    for sel in password_selectors:
                        try:
                            self.wait_visible(driver, sel, timeout=3)
                            el = self.find(driver, sel)
                            driver.execute_script("arguments[0].focus(); arguments[0].select();", el)
                            for ch in pwd:
                                el.send_keys(ch)
                                time.sleep(random.uniform(0.04, 0.12))
                            driver.execute_script("arguments[0].blur();", el)
                            self.log(f"  密码输入框: {sel}")
                            break
                        except Exception:
                            continue
                    # 提交登录
                    time.sleep(1)
                    self.shot(driver, f"pre_login_{idx}.png")
                    submitted = False
                    for btn_sel in [
                        '//button[contains(., "Sign In")]',
                        '//button[contains(text(), "Sign In")]',
                        '.el-button--primary',
                        'button[type="submit"]',
                    ]:
                        try:
                            btn = self.find(driver, btn_sel)
                            driver.execute_script("arguments[0].click();", btn)
                            self.log(f"  提交: JS click {btn_sel}")
                            submitted = True
                            break
                        except Exception:
                            continue
                    if not submitted:
                        try:
                            self.find(driver, 'input[type="password"]').send_keys('\n')
                            self.log("  提交: Enter 键")
                            submitted = True
                        except Exception:
                            pass
                    if not submitted:
                        try:
                            driver.execute_script("""
                                var form = document.querySelector('.el-form') || document.querySelector('form');
                                if (form) form.dispatchEvent(new Event('submit', {bubbles: true}));
                            """)
                            self.log("  提交: JS form submit")
                        except Exception:
                            pass
                    time.sleep(10)
                    self.shot(driver, f"post_login_{idx}.png")
                    if "/auth/login" in driver.current_url:
                        has_token = driver.execute_script("""
                            var t = localStorage.getItem('yl-token') || sessionStorage.getItem('yl-token') || '';
                            return t.length > 10;
                        """)
                        if has_token:
                            self.log("[OK] ✅ 有 token，认为登录成功")
                            logged_in = True
                        else:
                            self.log("[FAIL] ❌ 浏览器登录失败")
                            print("::error::" + masked_user + " 登录失败", flush=True)
                            self.send_tg("❌", "登录失败", user, "未知",
                                         "未知", "",
                                         screenshot=self.shot(driver, f"login_fail_{idx}.png"))
                            has_error = True
                            continue
                    else:
                        logged_in = True
                    self.log("[OK] ✅ 登录成功")
                    # 停留 homepage
                    driver.get(URL_HOMEPAGE)
                    time.sleep(6)
                    time.sleep(8)

                # --- 获取服务器信息 ---
                servers = self.get_servers_data(driver)
                if not servers:
                    self.log("[FAIL] ⚠️ API 请求失败，无服务器数据")
                    print("::error::" + masked_user + " API 请求失败", flush=True)
                    self.send_tg("⚠️", "警告", user, "未知",
                                 "未知", "API 请求失败",
                                 screenshot=self.shot(
                                     driver, f"no_server_{idx}.png"))
                    has_error = True
                    continue

                server = servers[0]
                server_id = str(server.get("id") or "")
                server_info = server.get("serverInfo") or {}
                state = server_info.get("state", "running")
                expired_time = server.get("expiredTime") or ""
                expiry_str = self.format_expiry(expired_time)
                log_sid = self.mask_server_id(server_id)
                self.log(f"服务器 {log_sid}: 状态={state}, 到期={expiry_str}")

                if not server_id:
                    self.log("[FAIL] ❌ 服务器ID无效")
                    print("::error::" + masked_user + " 服务器ID无效", flush=True)
                    self.send_tg("❌", "失败", user, "未知",
                                 state, expiry_str, "服务器ID无效",
                                 screenshot=self.shot(
                                     driver, f"invalid_id_{idx}.png"))
                    has_error = True
                    continue

                ext_info = self.get_extension_data(driver, server_id)
                if not ext_info:
                    self.log("[FAIL] ❌ 无法获取扩展信息")
                    print("::error::" + masked_user + " 无法获取扩展信息", flush=True)
                    self.send_tg("❌", "失败", user, server_id,
                                 state, expiry_str,
                                 extra="无法获取扩展信息",
                                 screenshot=self.shot(
                                     driver, f"ext_info_fail_{idx}.png"))
                    has_error = True
                    continue

                can_extend = ext_info.get("canExtend", False)
                cooldown_min = ext_info.get("minutesUntilNextExtension", 0)
                mins_until_exp = ext_info.get("minutesUntilExpiration", 9999)
                expired = mins_until_exp <= 0
                self.log(f"可续期={can_extend}, 冷却={cooldown_min}分, "
                         f"距过期={mins_until_exp}分")

                # ===== 离线处理 =====
                if state == "offline":
                    if can_extend:
                        self.log("🔴 离线可续期，先续期再开机...")
                        ready = self.navigate_to_panel(driver, server_id)
                        if not ready:
                            self.log("[FAIL] ❌ 面板加载失败")
                            print("::error::" + masked_user + " 面板加载失败", flush=True)
                            self.send_tg("❌", "面板加载失败", user,
                                         server_id, "offline", expiry_str,
                                         screenshot=self.shot(
                                             driver, f"panel_fail_{idx}.png"))
                            has_error = True
                            continue
                        if not self.click_renew_menu(driver, server_id, idx):
                            self.log("[FAIL] ❌ 续期菜单失败")
                            print("::error::" + masked_user + " 续期菜单失败", flush=True)
                            self.send_tg("❌", "续期菜单失败", user,
                                         server_id, "offline", expiry_str,
                                         screenshot=self.shot(
                                             driver, f"renew_fail_{idx}.png"))
                            has_error = True
                            continue
                        result, new_time = self.try_extend_and_verify(
                            driver, server_id, expired_time)
                        if result is True:
                            if not self.wait_until_not_expired(
                                    driver, server_id):
                                self.log("[FAIL] ⚠️ 续期成功但状态未更新")
                                print("::error::" + masked_user + " 续期成功但状态未更新", flush=True)
                                self.send_tg(
                                    "⚠️", "续期成功但状态未更新",
                                    user, server_id, "offline", expiry_str,
                                    "无法开机，请稍后重试",
                                    screenshot=self.shot(
                                        driver, f"start_fail_{idx}.png"))
                                has_error = True
                                continue
                            ok, final = self.ui_start_server(
                                driver, server_id, idx)
                            self.log(f"[OK] ✅ 续期并开机 {'成功' if ok else '未确认'}: {final}")
                            self.send_tg(
                                "✅" if ok else "⚠️",
                                "续期并开机成功" if ok else "续期成功，开机未确认",
                                user, server_id,
                                f"offline -> {final}",
                                f"{expiry_str} -> {new_time}",
                                screenshot=self.shot(driver, f"ok_{idx}.png"))
                            if not ok:
                                has_error = True
                        elif result == "cooldown":
                            self.log("[OK] ⏳ 续期后冷却")
                            self.send_tg("⏳", "续期后冷却", user,
                                         server_id, "offline", expiry_str,
                                         screenshot=self.shot(
                                             driver, f"cooldown_{idx}.png"))
                        else:
                            self.log("[FAIL] ❌ 续期失败")
                            print("::error::" + masked_user + " 续期失败", flush=True)
                            self.send_tg("❌", "续期失败", user,
                                         server_id, "offline", expiry_str,
                                         screenshot=self.shot(
                                             driver, f"extend_fail_{idx}.png"))
                            has_error = True
                    else:
                        if expired:
                            self.log("[FAIL] 🚫 已过期且冷却中，无法操作")
                            self.send_tg(
                                "🚫", "无法操作", user, server_id,
                                state, expiry_str,
                                "服务器已过期且处于冷却期",
                                screenshot=self.shot(
                                    driver, f"expired_cooldown_{idx}.png"))
                        else:
                            self.log("🔴 离线冷却中，直接开机（UI）")
                            ok, final = self.ui_start_server(
                                driver, server_id, idx)
                            self.log(f"[OK] 开机{'成功' if ok else '失败'}: {final}")
                            self.send_tg(
                                "✅" if ok else "❌",
                                "开机成功" if ok else "开机失败",
                                user, server_id,
                                f"offline -> {final}", expiry_str,
                                screenshot=self.shot(
                                    driver,
                                    f"{'started' if ok else 'start_fail'}"
                                    f"_{idx}.png"))
                            if not ok:
                                has_error = True
                    continue

                # ===== 运行中处理 =====
                if not can_extend:
                    extra = "服务器已过期但处于冷却期" if expired else ""
                    self.log(f"[OK] ⏳ 冷却中 ({cooldown_min}分钟)")
                    self.send_tg("⏳", "冷却中", user, server_id,
                                 state, expiry_str, extra,
                                 screenshot=self.shot(
                                     driver, f"cooldown_{idx}.png"))
                    continue

                self.log("[OK] ✅ 可续期，执行续期")
                ready = self.navigate_to_panel(driver, server_id)
                if not ready:
                    self.log("[FAIL] ❌ 面板加载失败")
                    print("::error::" + masked_user + " 面板加载失败", flush=True)
                    self.send_tg("❌", "面板加载失败", user, server_id,
                                 state, expiry_str,
                                 screenshot=self.shot(
                                     driver, f"panel_fail_{idx}.png"))
                    has_error = True
                    continue
                if not self.click_renew_menu(driver, server_id, idx):
                    self.log("[FAIL] ❌ 续期菜单失败")
                    print("::error::" + masked_user + " 续期菜单失败", flush=True)
                    self.send_tg("❌", "续期菜单失败", user, server_id,
                                 state, expiry_str,
                                 screenshot=self.shot(
                                     driver, f"renew_fail_{idx}.png"))
                    has_error = True
                    continue
                result, new_time = self.try_extend_and_verify(
                    driver, server_id, expired_time)
                if result is True:
                    self.log("[OK] ✅ 续期成功")
                    self.send_tg("✅", "续期成功", user, server_id,
                                 state, f"{expiry_str} -> {new_time}",
                                 screenshot=self.shot(driver, f"ok_{idx}.png"))
                elif result == "cooldown":
                    self.log("[OK] ⏳ 续期后冷却")
                    self.send_tg("⏳", "续期后冷却", user, server_id,
                                 state, expiry_str,
                                 screenshot=self.shot(
                                     driver, f"cooldown_{idx}.png"))
                else:
                    self.log("[FAIL] ❌ 续期失败")
                    print("::error::" + masked_user + " 续期失败", flush=True)
                    self.send_tg("❌", "续期失败", user, server_id,
                                 state, expiry_str,
                                 screenshot=self.shot(
                                     driver, f"extend_fail_{idx}.png"))
                    has_error = True

            except Exception as e:
                self.log(f"[FAIL] ❌ 异常: {e}")
                print("::error::" + masked_user + " 异常: " + str(e), flush=True)
                has_error = True
                try:
                    self.send_tg("❌", "异常", user, "未知",
                                 "未知", str(e),
                                 screenshot=self.shot(
                                     driver, f"error_{idx}.png"))
                except Exception:
                    self.send_tg("❌", "异常", user, "未知",
                                  "未知", str(e))
            finally:
                driver.quit()

        if has_error:
            self.log("[FAIL] ❌ 存在失败，退出码 1")
            sys.exit(1)
        else:
            self.log("[OK] ✅ 所有账号处理完毕")


if __name__ == "__main__":
    BytenutRenewal().run()
