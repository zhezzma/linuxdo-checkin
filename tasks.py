"""
浏览 + 点赞任务模块。

由 main.py 在登录后调用 run_tasks(page)，行为参数复刻旧版 DrissionPage 实现：
- 随机抽 10 个主题
- 每个主题 30% 概率点赞
- 滚动 550-650px，最多 10 次，3% 概率随机退出，每次等 2-4s
- 单主题失败重试 3 次（5-10s 随机延迟）
"""

import functools
import random
import time
from urllib.parse import urljoin

from loguru import logger

HOME_URL = "https://linux.do/"
NUM_TOPICS = 10
LIKE_PROB = 0.3
SCROLL_MIN = 550
SCROLL_MAX = 650
SCROLL_TIMES = 10
EXIT_PROB = 0.03
WAIT_MIN = 2
WAIT_MAX = 4


def _retry(retries=3, min_delay=5, max_delay=10):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    logger.warning(
                        f"{func.__name__} 第 {attempt + 1}/{retries} 次尝试失败: {e}"
                    )
                    if attempt < retries - 1:
                        sleep_s = random.uniform(min_delay, max_delay)
                        logger.info(f"将在 {sleep_s:.2f}s 后重试")
                        time.sleep(sleep_s)
            logger.error(f"{func.__name__} 重试 {retries} 次均失败")
            return None

        return wrapper

    return decorator


def _get_topic_hrefs(page):
    """抓取首页 #list-area 下所有主题链接，补全为绝对 URL。"""
    items = page.query_selector_all("#list-area a.title")
    hrefs = []
    for el in items:
        href = el.get_attribute("href")
        if href:
            hrefs.append(urljoin(HOME_URL, href))
    return hrefs


def _maybe_like(page):
    """点第一个未点赞按钮；成功返回 True，否则 False。"""
    try:
        btn = page.query_selector(".discourse-reactions-reaction-button")
        if btn:
            logger.info("找到未点赞的帖子，准备点赞")
            btn.click()
            logger.info("点赞成功")
            time.sleep(random.uniform(1, 2))
            return True
        logger.info("帖子可能已经点过赞了")
    except Exception as e:
        logger.error(f"点赞失败: {e}")
    return False


def _browse_post(page):
    """模拟阅读：随机滚动若干次，遇到底部或随机命中则退出。"""
    prev_url = None
    for _ in range(SCROLL_TIMES):
        distance = random.randint(SCROLL_MIN, SCROLL_MAX)
        logger.info(f"向下滚动 {distance} 像素...")
        page.evaluate(f"window.scrollBy(0, {distance})")
        logger.info(f"已加载页面: {page.url}")

        if random.random() < EXIT_PROB:
            logger.success("随机退出浏览")
            break

        at_bottom = page.evaluate(
            "window.scrollY + window.innerHeight >= document.body.scrollHeight"
        )
        current_url = page.url
        if current_url != prev_url:
            prev_url = current_url
        elif at_bottom and prev_url == current_url:
            logger.success("已到达页面底部，退出浏览")
            break

        wait_time = random.uniform(WAIT_MIN, WAIT_MAX)
        logger.info(f"等待 {wait_time:.2f} 秒...")
        time.sleep(wait_time)


@_retry()
def _browse_one_topic(page, href):
    """在已登录 page 上导航浏览单个主题，返回是否点了赞；重试耗尽返回 None。

    复用同一个 page（不开新标签）：cloakbrowser 禁用 context.new_page()，
    而 browser.new_page()/new_context() 会创建新 context、不共享登录 Cookie。
    """
    liked = False
    page.goto(href, wait_until="domcontentloaded")
    if random.random() < LIKE_PROB:
        liked = _maybe_like(page)
    _browse_post(page)
    return liked


def run_tasks(page):
    """在已登录 page 上跑浏览+点赞，返回 {"topics_browsed": n, "topics_liked": m}。"""
    hrefs = _get_topic_hrefs(page)
    if not hrefs:
        logger.error("未找到主题帖")
        return {"topics_browsed": 0, "topics_liked": 0}

    pick = random.sample(hrefs, min(NUM_TOPICS, len(hrefs)))
    logger.info(f"发现 {len(hrefs)} 个主题帖，随机选择 {len(pick)} 个")

    browsed = 0
    liked = 0
    for href in pick:
        result = _browse_one_topic(page, href)
        if result is None:
            continue
        browsed += 1
        if result:
            liked += 1

    summary = {"topics_browsed": browsed, "topics_liked": liked}
    logger.info(f"任务完成: {summary}")
    return summary
