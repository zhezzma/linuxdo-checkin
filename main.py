"""
cron: 0 */6 * * *
new Env("Linux.Do 签到")
"""

import json
import os
import time
from dotenv import load_dotenv
from loguru import logger
from DrissionPage import ChromiumOptions, Chromium

load_dotenv()  # 读取本地 .env 文件（青龙/GitHub Actions 无该文件时自动忽略）

os.environ.pop("DISPLAY", None)
os.environ.pop("DYLD_LIBRARY_PATH", None)

COOKIES = os.environ.get("LINUXDO_COOKIES", "").strip()  # 手动设置的 Cookie 字符串
# 本地调试用：指定浏览器路径（如 Edge）、是否无头；不设置时默认无头 + 自动探测 Chrome
BROWSER_PATH = os.environ.get("BROWSER_PATH", "").strip()
HEADLESS = os.environ.get("HEADLESS", "true").strip().lower() not in ("false", "0", "off")

HOME_URL = "https://linux.do/"

# turnstilePatch 扩展：自动求解 Cloudflare Turnstile 质询
EXTENSION_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "turnstilePatch")
)


class LinuxDoBrowser:
    def __init__(self) -> None:
        from sys import platform

        if platform == "linux" or platform == "linux2":
            platformIdentifier = "X11; Linux x86_64"
        elif platform == "darwin":
            platformIdentifier = "Macintosh; Intel Mac OS X 10_15_7"
        elif platform == "win32":
            platformIdentifier = "Windows NT 10.0; Win64; x64"
        else:
            platformIdentifier = "X11; Linux x86_64"

        co = (
            ChromiumOptions()
            .headless(HEADLESS)
            .auto_port(True)
            .set_argument("--no-sandbox")
        )
        if BROWSER_PATH:
            co.set_browser_path(BROWSER_PATH)
        # 加载 turnstilePatch 扩展以自动通过 Cloudflare Turnstile 质询
        # 注意：扩展在无痕模式下不会生效，故改用 auto_port 的临时配置目录隔离每次运行
        if os.path.exists(EXTENSION_PATH):
            co.add_extension(EXTENSION_PATH)
        co.set_user_agent(
            f"Mozilla/5.0 ({platformIdentifier}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
        )
        self.browser = Chromium(co)
        self.page = self.browser.new_tab()

    @staticmethod
    def parse_cookie_string(cookie_str: str) -> list[dict]:
        """
        解析浏览器复制的 Cookie 字符串格式: "name1=value1; name2=value2"
        返回 DrissionPage 所需的 cookie 列表格式。
        """
        cookies = []
        for part in cookie_str.strip().split(";"):
            part = part.strip()
            if "=" in part:
                name, _, value = part.partition("=")
                cookies.append(
                    {
                        "name": name.strip(),
                        "value": value.strip(),
                        "domain": ".linux.do",
                        "path": "/",
                    }
                )
        return cookies

    def _detect_cloudflare(self) -> str:
        """检测当前页面 Cloudflare 质询状态：none / waiting / solved。"""
        try:
            return self.page.run_js(
                r"""
const cfInput = document.querySelector('input[name="cf-turnstile-response"]');
const cfPresent = !!cfInput
  || !!document.querySelector('iframe[src*="turnstile"], iframe[src*="/cdn-cgi/challenge-platform/"], div.cf-turnstile, [data-sitekey]');
if (!cfPresent) return 'none';
const token = String((cfInput && cfInput.value) || '').trim();
return token.length >= 80 ? 'solved' : 'waiting';
                """
            )
        except Exception:
            return "none"

    def _solve_turnstile(self):
        """主动复用 Turnstile 组件求解：reset 后点击复选框 iframe。"""
        try:
            self.page.run_js(
                "try { if (window.turnstile && typeof turnstile.reset === 'function') turnstile.reset(); } catch(e) {}"
            )
        except Exception:
            pass
        try:
            challenge_input = self.page.ele("@name=cf-turnstile-response", timeout=1)
        except Exception:
            challenge_input = None
        if challenge_input:
            try:
                iframe = challenge_input.parent().shadow_root.ele("tag:iframe")
                if iframe:
                    iframe.click()
                    time.sleep(1)
            except Exception:
                pass
        else:
            # 兜底：点击可见的 turnstile / 质询平台 iframe
            try:
                self.page.run_js(
                    r"""
const n = document.querySelector('iframe[src*="turnstile"], iframe[src*="/cdn-cgi/challenge-platform/"]');
if (n && n.click) n.click();
                    """
                )
            except Exception:
                pass

    def wait_for_cloudflare(self, timeout=30) -> bool:
        """等待 Cloudflare Turnstile 质询通过。

        依赖 turnstilePatch 扩展自动求解；卡住时主动复用 Turnstile 组件重试。
        返回 True 表示质询已通过或不存在，False 表示超时仍在质询中。
        """
        time.sleep(2)  # 等待质询平台 iframe 加载，避免误判为无质询
        deadline = time.time() + timeout
        last_solve_at = 0.0
        while time.time() < deadline:
            state = self._detect_cloudflare()
            if state in ("none", "solved"):
                if state == "solved":
                    logger.success("Cloudflare Turnstile 质询已通过")
                return True
            if time.time() - last_solve_at >= 5:
                logger.info("Cloudflare 质询进行中，尝试主动求解...")
                self._solve_turnstile()
                last_solve_at = time.time()
            time.sleep(1)
        still = self._detect_cloudflare()
        logger.warning(f"Cloudflare 质询等待超时，当前状态: {still}")
        return still in ("none", "solved")

    def login_with_cookies(self, cookie_str: str) -> bool:
        """使用手动设置的 Cookie 直接登录"""
        logger.info("检测到手动 Cookie，尝试 Cookie 登录...")
        dp_cookies = self.parse_cookie_string(cookie_str)
        if not dp_cookies:
            logger.error("Cookie 解析失败或为空，无法使用 Cookie 登录")
            return False

        logger.info(f"成功解析 {len(dp_cookies)} 个 Cookie 条目")

        # 设置 Cookie 到 DrissionPage
        self.page.set.cookies(dp_cookies)
        logger.info("Cookie 设置完成，导航至 linux.do...")
        self.page.get(HOME_URL)

        # 处理 Cloudflare Turnstile 质询
        self.wait_for_cloudflare(timeout=30)

        # 验证登录状态
        try:
            user_ele = self.page.ele("@id=current-user")
        except Exception as e:
            logger.warning(f"Cookie 登录验证异常: {str(e)}")
            return True
        if not user_ele:
            if "avatar" in self.page.html:
                logger.info("Cookie 登录验证成功 (通过 avatar)")
                return True
            logger.error("Cookie 登录验证失败 (未找到 current-user)，Cookie 可能已过期")
            return False
        else:
            logger.info("Cookie 登录验证成功")
            return True

    def _fetch_json(self, url):
        """在已登录的页面上下文中用同步 XHR 请求 JSON 接口（自带 cookie 与 CF 放行）。"""
        try:
            text = self.page.run_js(
                r"""
const url = arguments[0];
const xhr = new XMLHttpRequest();
xhr.open('GET', url, false);
xhr.setRequestHeader('Accept', 'application/json, text/javascript, */*; q=0.01');
xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
xhr.send();
if (xhr.status !== 200) return 'HTTP_ERROR:' + xhr.status;
return xhr.responseText;
                """,
                url,
            )
        except Exception as e:
            logger.warning(f"请求 {url} 失败: {e}")
            return None
        if isinstance(text, str) and text.startswith("HTTP_ERROR:"):
            logger.warning(f"{url} 返回异常: {text}")
            return None
        try:
            return json.loads(text)
        except Exception as e:
            logger.warning(f"解析 JSON 失败 ({url}): {e}")
            return None

    @staticmethod
    def _fmt_duration(seconds):
        """把秒数格式化为 'X天Y小时' / 'Y小时Z分' / 'Z分钟'。"""
        seconds = int(seconds or 0)
        days, rem = divmod(seconds, 86400)
        hours, rem = divmod(rem, 3600)
        minutes = rem // 60
        if days:
            return f"{days}天{hours}小时"
        if hours:
            return f"{hours}小时{minutes}分"
        return f"{minutes}分钟"

    def fetch_user_summary(self):
        """登录后请求用户信息接口，打印账号信息与数据摘要。"""
        current = self._fetch_json("https://linux.do/session/current.json")
        if not isinstance(current, dict) or not current.get("current_user"):
            logger.warning("获取当前用户失败，跳过数据摘要")
            return
        username = current["current_user"].get("username") or ""

        data = (
            self._fetch_json(f"https://linux.do/u/{username}/summary.json")
            if username
            else None
        )
        if not isinstance(data, dict):
            logger.warning("获取用户摘要失败，跳过数据摘要")
            return

        users = data.get("users") or []
        user_info = next(
            (u for u in users if u.get("username") == username), None
        ) or (users[0] if users else {})
        summary = data.get("user_summary") or {}

        name = user_info.get("name") or username
        trust = user_info.get("trust_level")

        logger.info("============== 用户信息 ==============")
        logger.info(f"用户名: {username}")
        if name and name != username:
            logger.info(f"昵称  : {name}")
        if trust is not None:
            logger.info(f"信任等级: Lv{trust}")

        logger.info("============== 数据摘要 ==============")
        rows = [
            ("访问天数", summary.get("days_visited", 0)),
            ("阅读时间", self._fmt_duration(summary.get("time_read"))),
            ("最近阅读时间", self._fmt_duration(summary.get("recent_time_read"))),
            ("浏览的话题", summary.get("topics_entered", 0)),
            ("已读帖子", summary.get("posts_read_count", 0)),
            ("已送出(赞)", summary.get("likes_given", 0)),
            ("已收到(赞)", summary.get("likes_received", 0)),
            ("书签", summary.get("bookmark_count", 0)),
            ("创建的话题", summary.get("topic_count", 0)),
            ("创建的帖子", summary.get("post_count", 0)),
            ("解决方案", summary.get("solved_count", 0)),
        ]
        for k, v in rows:
            logger.info(f"{k}: {v}")

    def run(self):
        try:
            login_res = self.login_with_cookies(COOKIES)
            if not login_res:
                logger.warning("登录验证失败")
                return
            self.fetch_user_summary()
        finally:
            try:
                self.page.close()
            except Exception:
                pass
            try:
                self.browser.quit()
            except Exception:
                pass


if __name__ == "__main__":
    if not COOKIES:
        print("请设置 LINUXDO_COOKIES（Cookie 登录）")
        exit(1)
    browser = LinuxDoBrowser()
    browser.run()
