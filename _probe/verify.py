# -*- coding: utf-8 -*-
"""最终字段确认：B站 App 接口 + 抖音 profile 接口"""
import hashlib
import json
import sys
from pathlib import Path
import time
import urllib.parse

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'live-recorder'))  # 探测脚本借用姊妹项目的 LiveWatcher
from monitor.watcher import LiveWatcher                   # noqa: E402
from core.config import COMMON_HEADERS                    # noqa: E402

APPKEY = '1d8b6e7d45233436'
APPSEC = '560c52ccd288fed045859ed18bffd973'
WUA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
       '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36')


def app_sign(p):
    q = urllib.parse.urlencode(sorted(p.items()))
    return hashlib.md5((q + APPSEC).encode()).hexdigest()


def banner(t):
    print('\n' + '=' * 62)
    print(t)
    print('=' * 62)


S = requests.Session()
S.headers.update({'User-Agent': 'Mozilla/5.0 BiliDroid/7.63.0 (bbcallen@gmail.com) os/android'})

for mid, name in ((946974, '影视飓风'), (2, 'bishi')):
    banner(f'B站 App 接口 · uid={mid} ({name})')
    p = {'appkey': APPKEY, 'vmid': str(mid), 'ps': '5', 'pn': '1',
         'order': 'pubdate', 'ts': str(int(time.time()))}
    p['sign'] = app_sign(p)
    r = S.get('https://app.bilibili.com/x/v2/space/archive/cursor', params=p, timeout=15)
    j = r.json()
    print(f"    code={j.get('code')} msg={j.get('message')}")
    data = j.get('data') or {}
    lst = data.get('item') or []
    print(f"    total={data.get('count')} 本页={len(lst)}")
    if lst:
        it = lst[0]
        print(f"    [首条字段] {list(it)[:25]}")
        for k in ('param', 'bvid', 'title', 'desc', 'created', 'length',
                  'play', 'comment', 'cover', 'uri', 'author'):
            v = it.get(k)
            if isinstance(v, str) and len(v) > 70:
                v = v[:70] + '...'
            print(f"      {k:10} = {v}")

banner('抖音 profile 接口稳定性（带 cookie，3 次）')
w = LiveWatcher('000000000000')
w.fetch()
ck = '; '.join(f'{c.name}={c.value}' for c in w.session.cookies)
for i in range(3):
    try:
        r = requests.get('https://www.douyin.com/aweme/v1/web/user/profile/other/',
                         params={'sec_user_id': 'MS4wLjABAAAAEXAMPLE_ReplaceThisWithRealSecUid',
                                 'device_platform': 'webapp', 'aid': '6383',
                                 'publish_video_strategy_type': '2',
                                 'version_code': '290100', 'version_name': '29.1.0'},
                         headers={**COMMON_HEADERS, 'Cookie': ck,
                                  'Referer': 'https://www.douyin.com/'}, timeout=15)
        j = r.json()
        u = j.get('user') or {}
        print(f"    第{i+1}次 HTTP {r.status_code} len={len(r.content)} "
              f"status={j.get('status_code')} "
              f"aweme_count={u.get('aweme_count')} follower={u.get('follower_count')}")
    except Exception as exc:
        print(f'    第{i+1}次 [ERR] {exc}')
