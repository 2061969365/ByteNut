import os
import json
import shutil
import time


class SessionManager:
    """Cookie + localStorage token 管理器，加速登录"""

    SESSION_DIR = "session_cache"

    @staticmethod
    def save(driver, log_fn=print):
        """保存 cookies + yl-token"""
        try:
            cookies = driver.get_cookies()
            token = driver.execute_script(
                "return localStorage.getItem('yl-token') || ''") or ""

            os.makedirs(SessionManager.SESSION_DIR, exist_ok=True)

            with open(os.path.join(SessionManager.SESSION_DIR, "cookies.json"), "w") as f:
                json.dump(cookies, f)

            with open(os.path.join(SessionManager.SESSION_DIR, "token.txt"), "w") as f:
                f.write(token)

            log_fn(f"[OK] Session 已保存（{len(cookies)} cookies, token={len(token)} chars）")
            return True
        except Exception as e:
            log_fn(f"  Session 保存失败: {e}")
            return False

    @staticmethod
    def load(driver, homepage_url, log_fn=print):
        """加载 cookies + token，访问首页验证是否仍有效"""
        cookie_file = os.path.join(SessionManager.SESSION_DIR, "cookies.json")
        token_file = os.path.join(SessionManager.SESSION_DIR, "token.txt")

        if not os.path.exists(cookie_file) or not os.path.exists(token_file):
            log_fn("  Session 缓存不存在")
            return False

        try:
            # 先访问域名，才能设置 cookie
            driver.get(homepage_url)
            time.sleep(1)

            # 加载 cookies
            with open(cookie_file) as f:
                cookies = json.load(f)

            valid_cookies = 0
            for c in cookies:
                try:
                    driver.add_cookie(c)
                    valid_cookies += 1
                except Exception:
                    continue

            log_fn(f"  已加载 {valid_cookies}/{len(cookies)} cookies")

            # 加载 token
            with open(token_file) as f:
                token = f.read().strip()

            # 刷新页面，让 cookie 生效
            driver.get(homepage_url)
            time.sleep(3)

            # 检查是否被重定向到登录页
            if "/auth/login" in driver.current_url:
                log_fn("  Session 已过期（被重定向到登录页）")
                SessionManager.clear()
                return False

            # 恢复 localStorage token
            if token:
                driver.execute_script(
                    f"localStorage.setItem('yl-token', arguments[0])", token)

            log_fn("[OK] ✅ Session 登录成功")
            return True

        except Exception as e:
            log_fn(f"  Session 加载异常: {e}")
            return False

    @staticmethod
    def clear(log_fn=print):
        """清空 session 缓存"""
        try:
            if os.path.exists(SessionManager.SESSION_DIR):
                shutil.rmtree(SessionManager.SESSION_DIR)
                log_fn("  Session 缓存已清空")
        except Exception:
            pass
