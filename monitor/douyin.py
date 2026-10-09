"""
抖音 UP 主探测器。

抖音投稿接口的现状（2026-10 实测，详见 _probe/FINDINGS.md）：
    · `www.douyin.com/aweme/v1/web/aweme/post/` —— 无论是否携带正确的
      a_bogus，只要会话里没有**浏览器执行 JS 生成的 Uifid**，一律返回
      `403 Blocked by ArgusSecurityPlugin Uifid Not Found`。
    · 移动端 `aweme.snssdk.com/aweme/v1/aweme/post/` 返回 `status_code:0`
      但 `aweme_list` 恒为空 —— 该接口需要 X-Gorgon 签名。
    · 用户主页 HTML 是 JS 挑战页，无内嵌 SSR 数据可抓。

因此本模块提供两级能力：
    · profile 模式（默认，零配置）：打 `user/profile/other/` 拿
      `aweme_count / follower_count`，靠**计数增量**判定「发了新作品」。
      能推通知 + 主页链接，但拿不到标题。
    · full 模式（需 Cookie）：在 .env 里配好一份**浏览器登录态**的
      DOUYIN_COOKIE（至少含 ttwid 与 UIFID），即可走 web 投稿接口拿到
      完整列表（含标题、链接）。
"""
import time
from typing import Optional

import requests
import urllib3

from core.config import (
    DOUYIN_COOKIE,
    DOUYIN_LIVE_HOST,
    DOUYIN_WWW_HOST,
    DOUYIN_WEB_HEADERS,
    build_query,
)
from core.signing import a_bogus_sign

urllib3.disable_warnings()

URL_PROFILE = DOUYIN_WWW_HOST + '/aweme/v1/web/user/profile/other/'
URL_POST = DOUYIN_WWW_HOST + '/aweme/v1/web/aweme/post/'

# 投稿接口的真实参数集（从浏览器抓包形态还原）
_POST_PARAMS = {
    'device_platform': 'webapp', 'aid': '6383', 'channel': 'channel_pc_web',
    'max_cursor': '0', 'locate_query': 'false', 'show_live_replay_strategy': '1',
    'count': '18', 'publish_video_strategy_type': '2', 'pc_client_type': '1',
    'version_code': '290100', 'version_name': '29.1.0', 'cookie_enabled': 'true',
    'screen_width': '1536', 'screen_height': '864', 'browser_language': 'zh-CN',
    'browser_platform': 'Win32', 'browser_name': 'Chrome',
    'browser_version': '124.0.0.0', 'browser_online': 'true',
    'engine_name': 'Blink', 'engine_version': '124.0.0.0', 'os_name': 'Windows',
    'os_version': '10', 'cpu_core_num': '8', 'device_memory': '8',
    'platform': 'PC', 'downlink': '10', 'effective_type': '4g',
    'round_trip_time': '50', 'webid': '7490000000000000000',
}


class DouyinUpError(RuntimeError):
    pass


class DouyinUpMonitor:
    def __init__(self, cookie: str = '', timeout: int = 15,
                 session: Optional[requests.Session] = None):
        self.timeout = timeout
        self.session = session or requests.Session()
        self._cookie = cookie or DOUYIN_COOKIE
        self._warmed = False

    # ---------------------------------------------------------------- 会话
    @property
    def cookie(self) -> str:
        """优先用配置的登录态 Cookie；没有则用现场拿到的临时 Cookie。"""
        if self._cookie:
            return self._cookie
        if not self._warmed:
            self.warm()
        return '; '.join(f'{c.name}={c.value}' for c in self.session.cookies)

    def warm(self) -> str:
        """访问直播首页拿临时 Cookie（ttwid / UIFID），满足 profile 接口。"""
        self._warmed = True
        try:
            self.session.get(DOUYIN_LIVE_HOST + '/', timeout=self.timeout,
                             headers={'User-Agent': DOUYIN_WEB_HEADERS['User-Agent']})
        except Exception:
            pass
        return '; '.join(f'{c.name}={c.value}' for c in self.session.cookies)

    @property
    def has_login_cookie(self) -> bool:
        """判断当前 Cookie 是否具备走「完整投稿列表」的条件。"""
        ck = self.cookie
        return bool(ck) and ('UIFID=' in ck or 'UIFID_TEMP=' in ck)

    def _headers(self, referer: str = '') -> dict:
        h = dict(DOUYIN_WEB_HEADERS)
        if referer:
            h['Referer'] = referer
        ck = self.cookie
        if ck:
            h['Cookie'] = ck
        return h

    # ------------------------------------------------------------ profile
    def profile(self, sec_uid: str) -> dict:
        """取用户资料。返回含 aweme_count / follower_count 的字典。"""
        params = {
            'sec_user_id': sec_uid,
            'device_platform': 'webapp',
            'aid': '6383',
            'publish_video_strategy_type': '2',
            'version_code': '290100',
            'version_name': '29.1.0',
        }
        try:
            resp = self.session.get(URL_PROFILE, params=params,
                                    headers=self._headers(DOUYIN_WWW_HOST + '/'),
                                    timeout=self.timeout)
        except requests.RequestException as exc:
            raise DouyinUpError(f'网络异常: {exc}') from exc
        if resp.status_code != 200 or not resp.content:
            raise DouyinUpError(f'HTTP {resp.status_code}，响应为空（Cookie 可能已失效）')
        try:
            data = resp.json()
        except Exception as exc:
            raise DouyinUpError(f'响应非 JSON: {resp.text[:120]}') from exc
        code = data.get('status_code')
        if code not in (0, None):
            raise DouyinUpError(f"status_code={code} {data.get('status_msg') or ''}")
        u = data.get('user') or {}
        if not u:
            raise DouyinUpError('响应中无 user 字段')
        return {
            'sec_uid': u.get('sec_uid') or sec_uid,
            'nickname': u.get('nickname') or '',
            'unique_id': u.get('unique_id') or '',
            'signature': u.get('signature') or '',
            'aweme_count': int(u.get('aweme_count') or 0),
            'dongtai_count': int(u.get('dongtai_count') or 0),
            'follower_count': int(u.get('follower_count') or 0),
            'following_count': int(u.get('following_count') or 0),
            'total_favorited': int(u.get('total_favorited') or 0),
            'homepage': f'https://www.douyin.com/user/{u.get("sec_uid") or sec_uid}',
        }

    # --------------------------------------------------------- 完整投稿列表
    def list_videos(self, sec_uid: str, limit: int = 18) -> list:
        """取最新投稿（需有效浏览器登录态 Cookie，见模块文档）。"""
        if not self.has_login_cookie:
            raise DouyinUpError(
                '缺少可用的登录态 Cookie（ttwid / UIFID）。'
                '请在 .env 配置 DOUYIN_COOKIE，或改用 profile 模式。')
        params = dict(_POST_PARAMS)
        params['sec_user_id'] = sec_uid
        params['count'] = str(min(limit, 18))
        qs = build_query(params)
        params['a_bogus'] = a_bogus_sign(qs, DOUYIN_WEB_HEADERS['User-Agent'])
        try:
            resp = self.session.get(URL_POST, params=params, timeout=self.timeout,
                                    headers=self._headers(f'{DOUYIN_WWW_HOST}/user/{sec_uid}'))
        except requests.RequestException as exc:
            raise DouyinUpError(f'网络异常: {exc}') from exc
        if resp.status_code == 403:
            raise DouyinUpError('403 被 Argus 拦截：Cookie 缺有效 Uifid（需浏览器登录态）')
        if resp.status_code != 200 or not resp.content:
            raise DouyinUpError(f'HTTP {resp.status_code}，响应为空')
        try:
            data = resp.json()
        except Exception as exc:
            raise DouyinUpError(f'响应非 JSON: {resp.text[:120]}') from exc
        code = data.get('status_code')
        if code not in (0, None):
            raise DouyinUpError(f"status_code={code} {data.get('status_msg') or ''}")
        out = []
        for a in data.get('aweme_list') or []:
            stat = a.get('statistics') or {}
            out.append({
                'id': a.get('aweme_id') or '',
                'title': (a.get('desc') or '').strip(),
                'url': f"https://www.douyin.com/video/{a.get('aweme_id')}"
                       if a.get('aweme_id') else '',
                'cover': ((a.get('video') or {}).get('cover') or {}).get('url_list', [''])[0]
                         if isinstance((a.get('video') or {}).get('cover'), dict) else '',
                'created': int(a.get('create_time') or 0),
                'duration': int((a.get('video') or {}).get('duration') or 0) // 1000,
                'play': int(stat.get('play_count') or 0),
                'digg': int(stat.get('digg_count') or 0),
                'comment': int(stat.get('comment_count') or 0),
            })
        out.sort(key=lambda x: x['created'], reverse=True)
        return out[:limit]


def parse_sec_uid(text: str) -> str:
    """从抖音主页链接或纯 sec_uid 中提取 sec_uid。"""
    import re
    text = (text or '').strip()
    m = re.search(r'douyin\.com/user/([\w\-]+)', text)
    if m:
        return m.group(1)
    if re.fullmatch(r'MS4wLjABAAAA[\w\-]+', text):
        return text
    return text if text.startswith('MS4w') else ''
