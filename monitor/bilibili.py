"""
B站 UP 主投稿列表探测器。

为什么走 App 端接口：
    web 端 `api.bilibili.com/x/space/wbi/arc/search` 即使 wbi 签名正确，
    仍会因 IP 级风控返回 `-352 风控校验失败`（带 v_voucher 人机验证）或
    `-412 request was banned`；补 buvid/dm_* 设备指纹均无法通过。
    App 端 `app.bilibili.com/x/v2/space/archive/cursor` 用公开 appkey + md5
    签名即可，实测对任意 uid 均稳定返回 `code:0`，且**无需 Cookie**。

返回字段（已实测确认）：title / bvid / param(=aid) / cover / ctime /
    duration / play / danmaku / tname / author
"""
import hashlib
import time
import urllib.parse
from typing import Optional

import requests
import urllib3

from core.config import (
    BILI_APP_HOST,
    BILI_APPKEY,
    BILI_APPSEC,
    BILI_APP_UA,
    build_query,
)

urllib3.disable_warnings()

API_CURSOR = BILI_APP_HOST + '/x/v2/space/archive/cursor'
PAGE_SIZE = 30          # 该接口单页上限（实测 30 可用）


class BiliUpError(RuntimeError):
    pass


def app_sign(params: dict) -> str:
    """B站 App 端签名：md5(sorted_query + appsec)。"""
    q = urllib.parse.urlencode(sorted(params.items()))
    return hashlib.md5((q + BILI_APPSEC).encode()).hexdigest()


class BiliUpMonitor:
    """按 uid 拉取投稿列表。"""

    def __init__(self, timeout: int = 15, session: Optional[requests.Session] = None):
        self.timeout = timeout
        self.session = session or requests.Session()
        self.session.headers.update({'User-Agent': BILI_APP_UA})

    # ---------------------------------------------------------------- 内部
    def _fetch_page(self, uid: str, pn: int) -> dict:
        params = {
            'appkey': BILI_APPKEY,
            'vmid': str(uid),
            'ps': str(PAGE_SIZE),
            'pn': str(pn),
            'order': 'pubdate',
            'ts': str(int(time.time())),
        }
        params['sign'] = app_sign(params)
        try:
            resp = self.session.get(API_CURSOR, params=params, timeout=self.timeout)
        except requests.RequestException as exc:
            raise BiliUpError(f'网络异常: {exc}') from exc
        if resp.status_code != 200:
            raise BiliUpError(f'HTTP {resp.status_code}（重试或降低频率）')
        try:
            data = resp.json()
        except Exception as exc:
            raise BiliUpError(f'响应非 JSON: {resp.text[:120]}') from exc
        code = data.get('code')
        if code != 0:
            raise BiliUpError(f"API code={code} msg={data.get('message')}")
        return data.get('data') or {}

    @staticmethod
    def _normalize(item: dict) -> dict:
        bvid = item.get('bvid') or ''
        aid = item.get('param')
        return {
            'id': bvid or str(aid or ''),
            'bvid': bvid,
            'aid': aid,
            'title': (item.get('title') or '').strip(),
            'url': f'https://www.bilibili.com/video/{bvid}' if bvid else '',
            'cover': item.get('cover') or '',
            'created': int(item.get('ctime') or 0),
            'duration': item.get('duration') or 0,
            'play': int(item.get('play') or 0),
            'danmaku': int(item.get('danmaku') or 0),
            'tname': item.get('tname') or '',
            'author': item.get('author') or '',
        }

    # ---------------------------------------------------------------- 对外
    def list_videos(self, uid: str, limit: int = 20) -> list:
        """取最新投稿，按发布时间倒序，最多 limit 条。"""
        out, pn = [], 1
        while len(out) < limit and pn <= 10:
            data = self._fetch_page(uid, pn)
            items = data.get('item') or []
            if not items:
                break
            out.extend(self._normalize(it) for it in items)
            if len(items) < PAGE_SIZE:
                break
            pn += 1
        out.sort(key=lambda x: x['created'], reverse=True)
        return out[:limit]

    def total(self, uid: str) -> int:
        """投稿总数（顺带可用于「作品数变化」粗判）。"""
        return int(self._fetch_page(uid, 1).get('count') or 0)

    def user_name(self, uid: str) -> str:
        """取 UP 主昵称（复用列表接口首页的 author 字段，不额外请求）。"""
        data = self._fetch_page(uid, 1)
        items = data.get('item') or []
        if items:
            return items[0].get('author') or ''
        # 无投稿时回退到用户名片接口
        try:
            r = self.session.get(BILI_APP_HOST + '/x/web-interface/card',
                                 params={'mid': str(uid)}, timeout=15,
                                 headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; '
                                                        'Win64; x64) AppleWebKit/537.36 '
                                                        '(KHTML, like Gecko) Chrome/124.0.0.0 '
                                                        'Safari/537.36'})
            return ((r.json().get('data') or {}).get('card') or {}).get('name') or ''
        except Exception:
            return ''


def parse_uid(text: str) -> str:
    """从各种形态里提取 B站 uid。

    支持：
      https://space.bilibili.com/946974
      https://space.bilibili.com/946974/video
      纯数字 uid
    """
    import re
    text = (text or '').strip()
    m = re.search(r'space\.bilibili\.com/(\d+)', text)
    if m:
        return m.group(1)
    if re.fullmatch(r'\d+', text):
        return text
    return ''
