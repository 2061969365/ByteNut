import time
import os
import sys
import random
import zipfile
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

from seleniumbase import SB

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
PAGE_READY_INDICATOR = '//li[contains(@class,"el-menu-item")]'
NOPECHA_EXT_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "nopecha_ext"
)


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

    def _ensure_nopecha_extension(self):
        if os.path.exists(NOPECHA_EXT_DIR):
            self.log("[OK] NopeCHA 扩展已存在")
            return NOPECHA_EXT_DIR
        self.log("⏳ 下载 NopeCHA 扩展...")
        url = "https://github.com/NopeCHALLC/nopecha-extension/releases/latest/download/chromium.zip"
        try:
            resp = requests.get(url, timeout=60)
            zip_path = os.path.join(self.BASE_DIR, "chromium.zip")
            with open(zip_path, "wb") as f:
                f.write(resp.content)
            with zipfile.ZipFile(zip_path, "r") as z:
                z.extractall(NOPECHA_EXT_DIR)
            os.remove(zip_path)
            self.log(f"[OK] NopeCHA 扩展已下载 ({len(resp.content) // 1024} KB)")
            return NOPECHA_EXT_DIR
        except Exception as e:
            self.log(f"[FAIL] NopeCHA 扩展下载失败: {e}")
            return None

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

    def shot(self, sb, name):
        path = os.path.join(self.screenshot_dir, name)
        sb.save_screenshot(path)
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

    def set_token_in_browser(self, sb, token):
        """在浏览器中设置登录 token"""
        sb.execute_script(f"""
            localStorage.setItem('yl-token', '{token}');
            sessionStorage.setItem('yl-token', '{token}');
        """)
        self.log("  Token 已写入浏览器")

    # ========== 浏览器内 fetch（变量嵌入脚本）==========
    def fetch_api(self, sb, url, method="GET", referer=None):
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
            result = sb.execute_async_script(script)
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

    def fetch_api_post(self, sb, url, referer=None):
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
            result = sb.execute_async_script(script)
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
    def get_servers_data(self, sb):
        return self.fetch_api(sb, API_SERVER_LIST, referer=URL_HOMEPAGE)

    def get_extension_data(self, sb, server_id):
        ref = f"https://www.bytenut.com/free-gamepanel/{server_id}"
        return self.fetch_api(sb, API_EXTENSION_INFO.format(server_id),
                              referer=ref)

    def get_start_status(self, sb, server_id):
        ref = f"https://www.bytenut.com/free-gamepanel/{server_id}"
        return self.fetch_api(sb, API_START_STATUS.format(server_id),
                              referer=ref)

    # ========== 等待页面就绪 ==========
    def wait_for_panel_ready(self, sb, server_id, timeout=30):
        self.log("⏳ 等待页面加载...")
        try:
            sb.wait_for_element_present(PAGE_READY_INDICATOR, timeout=timeout)
        except Exception:
            self.log("⚠️ 侧边栏未出现，继续...")

        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                if sb.is_element_present(RENEW_MENU):
                    self.log("✅ 页面就绪（RENEW SERVER 可见）")
                    return True
            except Exception:
                pass
            self.remove_overlay_ads(sb)
            time.sleep(1)
        self.log("⚠️ RENEW SERVER 等待超时")
        return False

    # ========== 轮询开机队列 ==========
    def poll_start_status(self, sb, server_id, timeout=300, interval=5):
        deadline = time.time() + timeout
        while time.time() < deadline:
            data = self.get_start_status(sb, server_id)
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

    def wait_until_running(self, sb, server_id, timeout=120, interval=10):
        deadline = time.time() + timeout
        while time.time() < deadline:
            servers = self.get_servers_data(sb)
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

    def wait_until_not_expired(self, sb, server_id, timeout=120, interval=10):
        deadline = time.time() + timeout
        while time.time() < deadline:
            ext_info = self.get_extension_data(sb, server_id)
            if ext_info and ext_info.get("minutesUntilExpiration", 0) > 0:
                return True
            time.sleep(interval)
        return False

    # ========== Stealth 指纹增强 ==========
    def _inject_stealth(self, sb):
        try:
            sb.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
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
    def dismiss_cookie_consent(self, sb):
        try:
            sb.execute_script("""
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
                        if (el.textContent.indexOf('Continue with Recommended') !== -1)
                            el.click();
                    });
                    // 隐藏整个 dialog
                    var dialog = document.querySelector('.fc-dialog-wrapper, .fc-consent-root, .fc-dialog-overlay');
                    if (dialog) dialog.style.display = 'none';
                })();
            """)
        except Exception:
            pass

    # ========== 广告清理 ==========
    def remove_overlay_ads(self, sb):
        try:
            sb.execute_script("""
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
                })();
            """)
        except Exception:
            pass
    
    # ========== Captcha 通用处理 ==========
    def is_hcaptcha_present(self, sb):
        try:
            return sb.execute_script("""
                return !!(document.querySelector('.h-captcha')
                    || document.querySelector('.hcaptcha')
                    || document.querySelector('iframe[src*="hcaptcha"]')
                    || document.querySelector('div[data-sitekey*="hcaptcha"]'));
            """)
        except Exception:
            return False

    def is_turnstile_present(self, sb):
        try:
            return sb.execute_script("""
                return !!(document.querySelector('.cf-turnstile')
                    || document.querySelector(
                        'iframe[src*="challenges.cloudflare"]')
                    || document.querySelector(
                        'input[name="cf-turnstile-response"]'));
            """)
        except Exception:
            return False

    def is_captcha_present(self, sb):
        """检测任意类型验证码"""
        try:
            return self.is_hcaptcha_present(sb) or self.is_turnstile_present(sb)
        except Exception:
            return False

    def _try_click_hcaptcha(self, sb):
        """尝试点击 hCaptcha checkbox"""
        try:
            # 找到 hCaptcha iframe 坐标
            info = sb.execute_script("""
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
                cmd = sb.driver.execute_cdp_cmd
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
                for f in sb.driver.find_elements('css selector', 'iframe[src*="hcaptcha"]'):
                    sb.driver.switch_to.frame(f)
                    for sel in ['#checkbox', '.checkbox', '[role="checkbox"]', 'div[tabindex]']:
                        els = sb.driver.find_elements('css selector', sel)
                        for el in els:
                            if el.is_displayed() and el.is_enabled():
                                el.click()
                                self.log(f"  iframe click: {sel}")
                                sb.driver.switch_to.default_content()
                                return True
                    sb.driver.switch_to.default_content()
            except Exception:
                try: sb.driver.switch_to.default_content()
                except: pass

            # 再降级: uc_gui_click_captcha
            sb.uc_gui_click_captcha()
            return True
        except Exception as e:
            self.log(f"hCaptcha click 异常: {e}")
            return False

    def resolve_captcha(self, sb, timeout=90):
        """通用验证码处理，支持 hCaptcha 和 Turnstile（NopeCHA 扩展自动解）"""
        hc = self.is_hcaptcha_present(sb)
        tc = self.is_turnstile_present(sb)

        if not hc and not tc:
            self.log("[OK] 无验证码，跳过")
            return True

        has_nopecha = os.path.exists(NOPECHA_EXT_DIR)
        captcha_type = "hCaptcha" if hc else "Turnstile"
        self.log(f"⏳ 检测到 {captcha_type}，等待 NopeCHA 扩展自动解决..."
                 if has_nopecha else
                 f"⏳ 检测到 {captcha_type}，开始处理...")
        start = time.time()
        last_click = 0

        # 如果装了 NopeCHA，前 20 秒不手动点击，让扩展工作
        quiet_until = start + 20 if has_nopecha else start

        while time.time() - start < timeout:
            self.remove_overlay_ads(sb)

            # 滚动到验证码区域
            try:
                sb.execute_script("""
                    var e = document.querySelector('.h-captcha, .hcaptcha, .cf-turnstile');
                    if (e) e.scrollIntoView({block:'center'});
                """)
            except Exception:
                pass

            # 检查 hCaptcha token
            if self.is_hcaptcha_present(sb):
                try:
                    val = sb.execute_script("""
                        var i = document.querySelector(
                            'textarea[name="h-captcha-response"],'
                          + 'input[name="h-captcha-response"]');
                        return i ? i.value : '';
                    """)
                    if len(val) > 20:
                        self.log("[OK] ✅ hCaptcha 完成")
                        return True
                except Exception:
                    pass

            # 检查 Turnstile token
            if self.is_turnstile_present(sb):
                try:
                    val = sb.execute_script(
                        "return document.querySelector("
                        "\"input[name='cf-turnstile-response']\")?.value || '';"
                    )
                    if len(val) > 20:
                        self.log("[OK] ✅ Turnstile 完成")
                        return True
                except Exception:
                    pass

            # NopeCHA 安静期过后，降级到手动点击
            now = time.time()
            if now > quiet_until and now - last_click > 3:
                try:
                    sb.uc_gui_click_captcha()
                    last_click = now
                except Exception:
                    pass
                if self.is_hcaptcha_present(sb):
                    self._try_click_hcaptcha(sb)

            time.sleep(1)

        # 超时：再检查一次
        if self.is_hcaptcha_present(sb):
            try:
                val = sb.execute_script(
                    "return (document.querySelector('textarea[name=\"h-captcha-response\"]')"
                    "|| document.querySelector('input[name=\"h-captcha-response\"]'))?.value||'';"
                )
                if len(val) > 20:
                    self.log("[OK] ✅ hCaptcha 超时后完成")
                    return True
            except Exception:
                pass
        print(f"::error::{captcha_type} 验证超时", flush=True)
        self.log(f"[FAIL] ⚠️ {captcha_type} 超时")
        return False

    def wait_turnstile(self, sb, timeout=90):
        """保留旧接口，内部委托 resolve_captcha"""
        return self.resolve_captcha(sb, timeout)

    def _wait_dialog_turnstile(self, sb, timeout=30):
        self.log("⏳ 等待弹窗验证码（最多 30s）...")
        start = time.time()
        last_click = 0
        while time.time() - start < timeout:
            self.remove_overlay_ads(sb)
            if sb.execute_script(
                    "return !document.querySelector('div.el-dialog');"):
                self.log("✅ 弹窗已消失，验证自动完成")
                return True
            if sb.execute_script("""
                var btn = document.querySelector(
                    'div.el-dialog__footer button.el-button--primary');
                return btn && !btn.disabled
                    && !btn.classList.contains('is-disabled');
            """):
                self.log("✅ Continue 已启用，验证自动完成")
                return True
            # 检查弹窗内的 Turnstile token
            try:
                val = sb.execute_script("""
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
                val = sb.execute_script("""
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
                    sb.uc_gui_click_captcha()
                    last_click = now
                except Exception:
                    try:
                        sb.execute_script("""
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
        if sb.execute_script(
                "return !document.querySelector('div.el-dialog');"):
            self.log("✅ 超时后弹窗已消失")
            return True
        if sb.execute_script("""
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
    def handle_ad_verification(self, sb):
        try:
            if not sb.execute_script(
                "return !!document.querySelector("
                "'div.adsterra-rewarded-dialog');"
            ):
                return True
            self.log("🛡️ 处理广告验证...")
            time.sleep(1)
            sb.execute_script("""
                var btn = document.querySelector(
                    'div.adsterra-rewarded-dialog button.el-button--primary');
                if (btn) btn.click();
            """)
            time.sleep(3)
            orig = sb.driver.current_window_handle
            if len(sb.driver.window_handles) > 1:
                for h in sb.driver.window_handles:
                    if h != orig:
                        sb.driver.switch_to.window(h)
                        break
                time.sleep(12)
                sb.driver.close()
                sb.driver.switch_to.window(orig)
                time.sleep(2)
            sb.execute_script("""
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
    def navigate_to_panel(self, sb, server_id):
        url = f"https://www.bytenut.com/free-gamepanel/{server_id}"
        sb.uc_open_with_reconnect(url, reconnect_time=6)
        time.sleep(5)
        self.remove_overlay_ads(sb)
        return self.wait_for_panel_ready(sb, server_id, timeout=30)

    # ========== 点击 RENEW SERVER（带重试）==========
    def click_renew_menu(self, sb, server_id, idx, max_retry=3):
        for attempt in range(1, max_retry + 1):
            try:
                sb.wait_for_element_present(RENEW_MENU, timeout=15)
                sb.wait_for_element_visible(RENEW_MENU, timeout=10)
                self.remove_overlay_ads(sb)
                sb.click(RENEW_MENU)
                time.sleep(3)
                self.log(f"✅ RENEW SERVER 已点击 (attempt {attempt})")
                return True
            except Exception as e:
                self.log(f"⚠️ RENEW SERVER 失败 (attempt {attempt}): {e}")
                if attempt < max_retry:
                    self.shot(sb, f"renew_fail_{idx}_a{attempt}.png")
                    self.log("🔄 重新导航...")
                    self.navigate_to_panel(sb, server_id)
        self.log("❌ RENEW SERVER 最终失败")
        return False

    # ========== 续期 ==========
    def try_extend_and_verify(self, sb, server_id, old_expiry):
        if not self.resolve_captcha(sb):
            return False, ""
        self.remove_overlay_ads(sb)
        self.log("⏳ 点击续期按钮...")
        try:
            if sb.is_element_visible(EXTEND_BTN):
                sb.execute_script("arguments[0].click();",
                                  sb.find_element(EXTEND_BTN))
            else:
                self.log("⚠️ 续期按钮不可见")
                return False, ""
        except Exception as e:
            self.log(f"续期按钮点击失败: {e}")
            return False, ""

        time.sleep(2)
        self.handle_ad_verification(sb)
        time.sleep(5)

        for _ in range(6):
            new_ext = self.get_extension_data(sb, server_id)
            if new_ext:
                new_expiry = new_ext.get("expiredTime", "")
                if new_expiry and new_expiry != old_expiry:
                    self.log(f"✅ 续期生效: {self.format_expiry(new_expiry)}")
                    return True, self.format_expiry(new_expiry)
            time.sleep(5)

        if (sb.is_element_present(EXTEND_BTN)
                and not sb.is_element_enabled(EXTEND_BTN)):
            return "cooldown", ""
        return False, ""

    # ========== UI 开机 ==========
    def ui_start_server(self, sb, server_id, idx):
        self.log("🖥️ 导航到 Console 页面...")
        self.navigate_to_panel(sb, server_id)

        # Step 1: 展开 Management
        self.log("📂 展开 Management...")
        try:
            sb.click(MANAGEMENT_MENU)
            time.sleep(2)
        except Exception:
            try:
                sb.execute_script("""
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

        # Step 2: 点击 Console
        self.log("🖥️ 点击 Console...")
        try:
            sb.click(CONSOLE_MENU_ITEM)
            time.sleep(3)
        except Exception:
            try:
                sb.execute_script("""
                    document.querySelectorAll('.el-menu-item span')
                    .forEach(function(el){
                        if (el.textContent.trim() === 'Console')
                            el.closest('.el-menu-item').click();
                    });
                """)
                time.sleep(3)
            except Exception as e:
                self.log(f"Console 点击失败: {e}")

        # Step 3: 等待 Start 按钮
        try:
            sb.wait_for_element_present(START_BTN, timeout=15)
            self.log("✅ Console 页面就绪")
        except Exception as e:
            self.log(f"⚠️ 等待 Start 超时: {e}")
            self.shot(sb, f"no_start_btn_{idx}.png")
            return False, "no_start_btn"

        # Step 4: 点击 Start
        self.log("▶️ 点击 Start...")
        self.remove_overlay_ads(sb)
        try:
            btn = sb.find_element(START_BTN)
            if btn.get_attribute("disabled"):
                self.log("⚠️ Start disabled")
                return False, "start_disabled"
            sb.execute_script(
                "arguments[0].scrollIntoView({block:'center'});", btn)
            time.sleep(0.5)
            sb.execute_script("arguments[0].click();", btn)
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
                if sb.is_element_visible(START_VERIFY_DIALOG):
                    dialog_appeared = True
                    break
            except Exception:
                pass
            data = self.get_start_status(sb, server_id)
            if data and not data.get("inQueue") and data.get("canStart"):
                self.log("✅ 无弹窗，直接开机成功")
                return True, "running"
            time.sleep(1)

        if not dialog_appeared:
            self.log("⚠️ 弹窗未出现，轮询状态...")
            ok, state = self.poll_start_status(sb, server_id, timeout=60)
            return (True, state) if ok else (False, "dialog_not_appeared")

        self.log("✅ 验证弹窗出现")

        # Step 6: 等待 Turnstile
        self._wait_dialog_turnstile(sb, timeout=30)

        # Step 7: 点击 Continue（最多 60s）
        self.log("▶️ 等待并点击 Continue...")
        continue_clicked = False
        for attempt in range(30):
            if sb.execute_script(
                    "return !document.querySelector('div.el-dialog');"):
                self.log("✅ 弹窗已自动消失")
                continue_clicked = True
                break
            if sb.execute_script("""
                var btn = document.querySelector(
                    'div.el-dialog__footer button.el-button--primary');
                return btn && !btn.disabled
                    && !btn.classList.contains('is-disabled');
            """):
                sb.execute_script("""
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
            self.shot(sb, f"continue_fail_{idx}.png")
            return False, "continue_fail"

        time.sleep(3)

        # Step 8: 处理排队弹窗
        self._handle_queue_dialog(sb)

        # Step 9: 轮询开机状态
        self.log("⏳ 轮询开机状态...")
        ok, state = self.poll_start_status(
            sb, server_id, timeout=300, interval=5)
        if ok:
            self.log("⏳ 确认运行状态...")
            is_running, final_state = self.wait_until_running(
                sb, server_id, timeout=120, interval=10)
            return True, "running" if is_running else f"started({final_state})"
        return False, "start_timeout"

    def _handle_queue_dialog(self, sb):
        try:
            has_q = False
            for _ in range(5):
                has_q = sb.execute_script(
                    "return !!document.querySelector("
                    "'div.el-message-box.queue-dialog-styled');"
                )
                if has_q:
                    break
                time.sleep(1)
            if has_q:
                self.log("📋 排队弹窗，点击 OK...")
                sb.execute_script("""
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

        for idx, (user, pwd) in enumerate(accounts, 1):
            masked_user = self.mask_account(user)
            self.log(f"==== 账号 [{idx}] {masked_user} ====")

            ext_dir = self._ensure_nopecha_extension()
            with SB(
                uc=True, test=True, headed=True,
                chromium_arg=(
                    "--no-sandbox,--disable-dev-shm-usage,"
                    "--disable-gpu,--window-size=1280,753,"
                    "--disable-blink-features=AutomationControlled,"
                    "--disable-automation,"
                    "--no-first-run,--no-default-browser-check"
                    + (f",--load-extension={ext_dir}" if ext_dir else "")
                ),
                proxy=PROXY,
            ) as sb:
                self._inject_stealth(sb)
                try:
                    logged_in = False
                    # --- API 登录 ---
                    self.log("--- 尝试 API 登录 ---")
                    token = self.api_login(user, pwd)
                    if token:
                        self.set_token_in_browser(sb, token)
                        time.sleep(1)
                        sb.uc_open_with_reconnect(URL_HOMEPAGE, reconnect_time=6)
                        time.sleep(5)
                        current_token = sb.execute_script("""
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
                        sb.uc_open_with_reconnect(URL_LOGIN_PANEL, reconnect_time=5)
                        time.sleep(3)
                        self.dismiss_cookie_consent(sb)
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
                                sb.wait_for_element_visible(sel, timeout=5)
                                el = sb.find_element(sel)
                                sb.execute_script("arguments[0].focus(); arguments[0].select();", el)
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
                            self.shot(sb, f"login_no_username_{idx}.png")
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
                                sb.wait_for_element_visible(sel, timeout=3)
                                el = sb.find_element(sel)
                                sb.execute_script("arguments[0].focus(); arguments[0].select();", el)
                                for ch in pwd:
                                    el.send_keys(ch)
                                    time.sleep(random.uniform(0.04, 0.12))
                                sb.execute_script("arguments[0].blur();", el)
                                self.log(f"  密码输入框: {sel}")
                                break
                            except Exception:
                                continue
                        # 提交登录
                        time.sleep(1)
                        self.shot(sb, f"pre_login_{idx}.png")
                        submitted = False
                        for btn_sel in [
                            '//button[contains(., "Sign In")]',
                            '//button[contains(text(), "Sign In")]',
                            '.el-button--primary',
                            'button[type="submit"]',
                        ]:
                            try:
                                btn = sb.find_element(btn_sel)
                                sb.execute_script("arguments[0].click();", btn)
                                self.log(f"  提交: JS click {btn_sel}")
                                submitted = True
                                break
                            except Exception:
                                continue
                        if not submitted:
                            try:
                                sb.find_element('input[type="password"]').send_keys('\n')
                                self.log("  提交: Enter 键")
                                submitted = True
                            except Exception:
                                pass
                        if not submitted:
                            try:
                                sb.execute_script("""
                                    var form = document.querySelector('.el-form') || document.querySelector('form');
                                    if (form) form.dispatchEvent(new Event('submit', {bubbles: true}));
                                """)
                                self.log("  提交: JS form submit")
                            except Exception:
                                pass
                        time.sleep(10)
                        self.shot(sb, f"post_login_{idx}.png")
                        if "/auth/login" in sb.get_current_url():
                            has_token = sb.execute_script("""
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
                                             screenshot=self.shot(sb, f"login_fail_{idx}.png"))
                                has_error = True
                                continue
                        else:
                            logged_in = True
                        self.log("[OK] ✅ 登录成功")
                        # 停留 homepage
                        sb.uc_open_with_reconnect(URL_HOMEPAGE, reconnect_time=6)
                        time.sleep(8)

                    # --- 获取服务器信息 ---
                    servers = self.get_servers_data(sb)
                    if not servers:
                        self.log("[FAIL] ⚠️ API 请求失败，无服务器数据")
                        print("::error::" + masked_user + " API 请求失败", flush=True)
                        self.send_tg("⚠️", "警告", user, "未知",
                                     "未知", "API 请求失败",
                                     screenshot=self.shot(
                                         sb, f"no_server_{idx}.png"))
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
                                         sb, f"invalid_id_{idx}.png"))
                        has_error = True
                        continue

                    ext_info = self.get_extension_data(sb, server_id)
                    if not ext_info:
                        self.log("[FAIL] ❌ 无法获取扩展信息")
                        print("::error::" + masked_user + " 无法获取扩展信息", flush=True)
                        self.send_tg("❌", "失败", user, server_id,
                                     state, expiry_str,
                                     extra="无法获取扩展信息",
                                     screenshot=self.shot(
                                         sb, f"ext_info_fail_{idx}.png"))
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
                            ready = self.navigate_to_panel(sb, server_id)
                            if not ready:
                                self.log("[FAIL] ❌ 面板加载失败")
                                print("::error::" + masked_user + " 面板加载失败", flush=True)
                                self.send_tg("❌", "面板加载失败", user,
                                             server_id, "offline", expiry_str,
                                             screenshot=self.shot(
                                                 sb, f"panel_fail_{idx}.png"))
                                has_error = True
                                continue
                            if not self.click_renew_menu(sb, server_id, idx):
                                self.log("[FAIL] ❌ 续期菜单失败")
                                print("::error::" + masked_user + " 续期菜单失败", flush=True)
                                self.send_tg("❌", "续期菜单失败", user,
                                             server_id, "offline", expiry_str,
                                             screenshot=self.shot(
                                                 sb, f"renew_fail_{idx}.png"))
                                has_error = True
                                continue
                            result, new_time = self.try_extend_and_verify(
                                sb, server_id, expired_time)
                            if result is True:
                                if not self.wait_until_not_expired(
                                        sb, server_id):
                                    self.log("[FAIL] ⚠️ 续期成功但状态未更新")
                                    print("::error::" + masked_user + " 续期成功但状态未更新", flush=True)
                                    self.send_tg(
                                        "⚠️", "续期成功但状态未更新",
                                        user, server_id, "offline", expiry_str,
                                        "无法开机，请稍后重试",
                                        screenshot=self.shot(
                                            sb, f"start_fail_{idx}.png"))
                                    has_error = True
                                    continue
                                ok, final = self.ui_start_server(
                                    sb, server_id, idx)
                                self.log(f"[OK] ✅ 续期并开机 {'成功' if ok else '未确认'}: {final}")
                                self.send_tg(
                                    "✅" if ok else "⚠️",
                                    "续期并开机成功" if ok else "续期成功，开机未确认",
                                    user, server_id,
                                    f"offline -> {final}",
                                    f"{expiry_str} -> {new_time}",
                                    screenshot=self.shot(sb, f"ok_{idx}.png"))
                                if not ok:
                                    has_error = True
                            elif result == "cooldown":
                                self.log("[OK] ⏳ 续期后冷却")
                                self.send_tg("⏳", "续期后冷却", user,
                                             server_id, "offline", expiry_str,
                                             screenshot=self.shot(
                                                 sb, f"cooldown_{idx}.png"))
                            else:
                                self.log("[FAIL] ❌ 续期失败")
                                print("::error::" + masked_user + " 续期失败", flush=True)
                                self.send_tg("❌", "续期失败", user,
                                             server_id, "offline", expiry_str,
                                             screenshot=self.shot(
                                                 sb, f"extend_fail_{idx}.png"))
                                has_error = True
                        else:
                            if expired:
                                self.log("[FAIL] 🚫 已过期且冷却中，无法操作")
                                self.send_tg(
                                    "🚫", "无法操作", user, server_id,
                                    state, expiry_str,
                                    "服务器已过期且处于冷却期",
                                    screenshot=self.shot(
                                        sb, f"expired_cooldown_{idx}.png"))
                            else:
                                self.log("🔴 离线冷却中，直接开机（UI）")
                                ok, final = self.ui_start_server(
                                    sb, server_id, idx)
                                self.log(f"[OK] 开机{'成功' if ok else '失败'}: {final}")
                                self.send_tg(
                                    "✅" if ok else "❌",
                                    "开机成功" if ok else "开机失败",
                                    user, server_id,
                                    f"offline -> {final}", expiry_str,
                                    screenshot=self.shot(
                                        sb,
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
                                         sb, f"cooldown_{idx}.png"))
                        continue

                    self.log("[OK] ✅ 可续期，执行续期")
                    ready = self.navigate_to_panel(sb, server_id)
                    if not ready:
                        self.log("[FAIL] ❌ 面板加载失败")
                        print("::error::" + masked_user + " 面板加载失败", flush=True)
                        self.send_tg("❌", "面板加载失败", user, server_id,
                                     state, expiry_str,
                                     screenshot=self.shot(
                                         sb, f"panel_fail_{idx}.png"))
                        has_error = True
                        continue
                    if not self.click_renew_menu(sb, server_id, idx):
                        self.log("[FAIL] ❌ 续期菜单失败")
                        print("::error::" + masked_user + " 续期菜单失败", flush=True)
                        self.send_tg("❌", "续期菜单失败", user, server_id,
                                     state, expiry_str,
                                     screenshot=self.shot(
                                         sb, f"renew_fail_{idx}.png"))
                        has_error = True
                        continue
                    result, new_time = self.try_extend_and_verify(
                        sb, server_id, expired_time)
                    if result is True:
                        self.log("[OK] ✅ 续期成功")
                        self.send_tg("✅", "续期成功", user, server_id,
                                     state, f"{expiry_str} -> {new_time}",
                                     screenshot=self.shot(sb, f"ok_{idx}.png"))
                    elif result == "cooldown":
                        self.log("[OK] ⏳ 续期后冷却")
                        self.send_tg("⏳", "续期后冷却", user, server_id,
                                     state, expiry_str,
                                     screenshot=self.shot(
                                         sb, f"cooldown_{idx}.png"))
                    else:
                        self.log("[FAIL] ❌ 续期失败")
                        print("::error::" + masked_user + " 续期失败", flush=True)
                        self.send_tg("❌", "续期失败", user, server_id,
                                     state, expiry_str,
                                     screenshot=self.shot(
                                         sb, f"extend_fail_{idx}.png"))
                        has_error = True

                except Exception as e:
                    self.log(f"[FAIL] ❌ 异常: {e}")
                    print("::error::" + masked_user + " 异常: " + str(e), flush=True)
                    has_error = True
                    try:
                        self.send_tg("❌", "异常", user, "未知",
                                     "未知", str(e),
                                     screenshot=self.shot(
                                         sb, f"error_{idx}.png"))
                    except Exception:
                        self.send_tg("❌", "异常", user, "未知",
                                     "未知", str(e))

        if has_error:
            self.log("[FAIL] ❌ 存在失败，退出码 1")
            sys.exit(1)
        else:
            self.log("[OK] ✅ 所有账号处理完毕")


if __name__ == "__main__":
    BytenutRenewal().run()
