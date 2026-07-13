"""
cron: 0 */6 * * *
new Env("Linux.Do 签到")
"""

import json
import os
import time
from dotenv import load_dotenv
from loguru import logger
from cloakbrowser import launch

import tasks

load_dotenv()  # 读取本地 .env 文件（青龙/GitHub Actions 无该文件时自动忽略）

os.environ.pop("DISPLAY", None)
os.environ.pop("DYLD_LIBRARY_PATH", None)

COOKIES = os.environ.get("LINUXDO_COOKIES", "").strip()  # 手动设置的 Cookie 字符串
# 本地调试用：是否无头；不设置时默认无头（CloakBrowser 使用自带隐身 Chromium，无需指定浏览器路径）
HEADLESS = os.environ.get("HEADLESS", "true").strip().lower() not in ("false", "0", "off")
# 可选：代理地址(http/https/socks5)，配合住宅代理可绕过数据中心 IP 的 CF 拦截；留空则直连
PROXY = os.environ.get("PROXY", "").strip()

HOME_URL = "https://linux.do/"


class LinuxDoBrowser:
    def __init__(self) -> None:
        # CloakBrowser：源码级隐身 Chromium，Cloudflare Turnstile 由二进制层面自动放行
        launch_kwargs = {"headless": HEADLESS, "humanize": True}
        if PROXY:
            launch_kwargs["proxy"] = PROXY
            host = PROXY.split("@")[-1] if "@" in PROXY else PROXY
            logger.info(f"使用代理: {host}")
        self.browser = launch(**launch_kwargs)
        self.page = self.browser.new_page()

    @staticmethod
    def parse_cookie_string(cookie_str: str) -> list[dict]:
        """
        解析浏览器复制的 Cookie 字符串格式: "name1=value1; name2=value2"
        返回 Playwright add_cookies 所需的 cookie 列表格式。
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

    def _on_cf_challenge(self) -> bool:
        """页面是否仍停在 Cloudflare 质询页（Just a moment / 请稍候）。"""
        try:
            title = (self.page.title() or "").lower()
        except Exception:
            return False
        return ("just a moment" in title) or ("请稍候" in title) or ("attention required" in title)

    def wait_for_homepage(self, timeout=45) -> bool:
        """等待真实首页加载完成（登录态：出现 current-user 或 avatar）。

        CloakBrowser 会在二进制层面自动通过 Cloudflare Turnstile，这里只负责等待首页出现。
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                if self.page.query_selector("#current-user"):
                    return True
                if self.page.query_selector("img.avatar, .avatar"):
                    return True
            except Exception:
                pass
            time.sleep(1)
        return False

    def login_with_cookies(self, cookie_str: str) -> bool:
        """使用手动设置的 Cookie 直接登录"""
        logger.info("检测到手动 Cookie，尝试 Cookie 登录...")
        dp_cookies = self.parse_cookie_string(cookie_str)
        if not dp_cookies:
            logger.error("Cookie 解析失败或为空，无法使用 Cookie 登录")
            return False

        logger.info(f"成功解析 {len(dp_cookies)} 个 Cookie 条目")
        self.page.context.add_cookies(dp_cookies)
        logger.info("Cookie 设置完成，导航至 linux.do...")
        self.page.goto(HOME_URL, wait_until="domcontentloaded")

        if self.wait_for_homepage(timeout=45):
            logger.info("Cookie 登录验证成功")
            return True
        if self._on_cf_challenge():
            logger.error("Cloudflare 质询未通过（CloakBrowser 未能自动放行），可能需要住宅代理")
        else:
            logger.error("登录验证失败：未进入登录态首页，Cookie 可能已过期")
        self._dump_debug("login_fail")
        return False

    def _fetch_json(self, url):
        """在已登录的页面上下文中用同步 XHR 请求 JSON 接口（自带 cookie）。"""
        try:
            text = self.page.evaluate(
                """(url) => {
                    const xhr = new XMLHttpRequest();
                    xhr.open('GET', url, false);
                    xhr.setRequestHeader('Accept', 'application/json, text/javascript, */*; q=0.01');
                    xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
                    xhr.send();
                    if (xhr.status !== 200) return 'HTTP_ERROR:' + xhr.status;
                    return xhr.responseText;
                }""",
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

    def _dump_debug(self, tag="debug"):
        """落盘调试快照（URL/标题/CF状态/HTML/截图），便于排查失败。"""
        debug_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug")
        try:
            os.makedirs(debug_dir, exist_ok=True)
        except Exception:
            return

        def _write(name, content):
            try:
                with open(os.path.join(debug_dir, name), "w", encoding="utf-8") as f:
                    f.write(str(content))
            except Exception:
                pass

        try:
            url = self.page.url
        except Exception:
            url = ""
        try:
            title = self.page.title() or ""
        except Exception as e:
            title = f"<title-error: {e}>"
        cfstate = "challenge" if self._on_cf_challenge() else "other"
        _write(f"{tag}_url.txt", url)
        _write(f"{tag}_title.txt", title)
        _write(f"{tag}_cfstate.txt", cfstate)
        try:
            _write(f"{tag}_page.html", (self.page.content() or "")[:200000])
        except Exception as e:
            _write(f"{tag}_page_error.txt", repr(e))
        try:
            self.page.screenshot(path=os.path.join(debug_dir, f"{tag}_screenshot.png"), full_page=True)
        except Exception as e:
            _write(f"{tag}_screenshot_error.txt", repr(e))
        logger.info(f"调试快照已保存到 {debug_dir} ({tag})")

    def run(self):
        try:
            login_res = self.login_with_cookies(COOKIES)
            if not login_res:
                logger.warning("登录验证失败")
                return
            self.fetch_user_summary()
            tasks.run_tasks(self.page)
        finally:
            try:
                self.browser.close()
            except Exception:
                pass


if __name__ == "__main__":
    if not COOKIES:
        print("请设置 LINUXDO_COOKIES（Cookie 登录）")
        exit(1)
    browser = LinuxDoBrowser()
    browser.run()
