# -*- coding: utf-8 -*-
"""抖音 v8 —— 验证「作品计数增量」降级方案可行性

目标：确认 user/profile/other/ 在【直播域 cookie】下能稳定返回，
      且响应里含 aweme_count（作品总数）→ 可作为「发了新视频」的判据。
"""
import json
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'live-recorder'))  # 探测脚本借用姊妹项目的 LiveWatcher
from monitor.watcher import LiveWatcher                   # noqa: E402
from core.config import COMMON_HEADERS                    # noqa: E402

SEC = 'MS4wLjABAAAAEXAMPLE_ReplaceThisWithRealSecUid'
WEB_UA = COMMON_HEADERS['User-Agent']


def banner(t):
    print('\n' + '=' * 62)
    print(t)
    print('=' * 62)


banner('1) 用直播域登录态换 cookie')
w = LiveWatcher('000000000000')
st = w.fetch()
print(f'    live ok={st.ok} nick={st.nickname}')
cookies = {c.name: c.value for c in w.session.cookies}
print(f'    cookies={list(cookies)}')
ck = '; '.join(f'{k}={v}' for k, v in cookies.items())

banner('2) profile/other/ 响应字段（找 aweme_count）')
s = requests.Session()
try:
    r = s.get('https://www.douyin.com/aweme/v1/web/user/profile/other/',
              params={'sec_user_id': SEC, 'device_platform': 'webapp',
                      'aid': '6383', 'publish_video_strategy_type': '2',
                      'version_code': '290100', 'version_name': '29.1.0'},
              headers={**COMMON_HEADERS, 'Cookie': ck,
                       'Referer': 'https://www.douyin.com/'}, timeout=15)
    print(f'    HTTP {r.status_code} len={len(r.content)}')
    j = r.json()
    u = j.get('user') or {}
    keys = ['nickname', 'unique_id', 'aweme_count', 'follower_count',
            'following_count', 'favoriting_count', 'total_favorited',
            'sec_uid', 'signature']
    for k in keys:
        v = u.get(k)
        if isinstance(v, str) and len(v) > 60:
            v = v[:60] + '...'
        print(f'      {k:20} = {v}')
    print(f'    [顶层 keys] {list(j)}')
    print(f'    [user keys] {list(u)[:40]}')
except Exception as exc:
    print(f'    [ERR] {exc}')

banner('3) 稳定性：连续 3 次调用')
for i in range(3):
    try:
        r = s.get('https://www.douyin.com/aweme/v1/web/user/profile/other/',
                  params={'sec_user_id': SEC, 'device_platform': 'webapp',
                          'aid': '6383'}, timeout=15)
        ok = False
        try:
            ok = (r.json().get('status_code') == 0)
        except Exception:
            pass
        print(f'    第{i+1}次: HTTP {r.status_code} len={len(r.content)} status_code_ok={ok}')
    except Exception as exc:
        print(f'    第{i+1}次 [ERR] {exc}')
