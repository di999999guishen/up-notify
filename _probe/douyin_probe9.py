# -*- coding: utf-8 -*-
"""抖音 v9 —— 投稿接口是否被「错误的 a_bogus」误伤

对照实验：同样的直播域 cookie，分别带/不带 a_bogus 打 post 接口。
若不带 a_bogus 能过（或报不同错误），说明签名参数用错。
"""
import json
import sys
from pathlib import Path
import urllib.parse

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'live-recorder'))  # 探测脚本借用姊妹项目的 LiveWatcher
from monitor.watcher import LiveWatcher                   # noqa: E402
from core.signing import a_bogus_sign                     # noqa: E402
from core.config import COMMON_HEADERS                    # noqa: E402

SEC = 'MS4wLjABAAAAEXAMPLE_ReplaceThisWithRealSecUid'
UA = COMMON_HEADERS['User-Agent']

w = LiveWatcher('000000000000')
w.fetch()
ck = '; '.join(f'{c.name}={c.value}' for c in w.session.cookies)
print(f'cookies={ck[:80]}...')

BASE = {
    'device_platform': 'webapp', 'aid': '6383', 'channel': 'channel_pc_web',
    'sec_user_id': SEC, 'max_cursor': '0', 'locate_query': 'false',
    'show_live_replay_strategy': '1', 'count': '18',
    'publish_video_strategy_type': '2', 'pc_client_type': '1',
    'version_code': '290100', 'version_name': '29.1.0',
    'cookie_enabled': 'true', 'screen_width': '1536', 'screen_height': '864',
    'browser_language': 'zh-CN', 'browser_platform': 'Win32',
    'browser_name': 'Chrome', 'browser_version': '124.0.0.0',
    'browser_online': 'true', 'engine_name': 'Blink',
    'engine_version': '124.0.0.0', 'os_name': 'Windows', 'os_version': '10',
    'cpu_core_num': '8', 'device_memory': '8', 'platform': 'PC',
    'downlink': '10', 'effective_type': '4g', 'round_trip_time': '50',
    'webid': '7490000000000000000',
}
URL = 'https://www.douyin.com/aweme/v1/web/aweme/post/'


def call(label, with_sign, extra=None):
    params = dict(BASE)
    if extra:
        params.update(extra)
    if with_sign:
        qs = '&'.join(f'{k}={urllib.parse.quote(str(v))}' for k, v in params.items())
        params['a_bogus'] = a_bogus_sign(qs, UA)
    h = {**COMMON_HEADERS, 'Cookie': ck, 'Referer': 'https://www.douyin.com/'}
    try:
        r = requests.get(URL, params=params, headers=h, timeout=15)
        body = r.text[:200]
        print(f'  [{label}] HTTP {r.status_code} len={len(r.content)} :: {body}')
    except Exception as exc:
        print(f'  [{label}] [ERR] {exc}')


print('\n--- 对照实验 ---')
call('无签名·全参数', False)
call('带签名·全参数', True)
call('无签名·无msToken', False, {'msToken': ''})
call('带签名·有msToken', True, {'msToken': 'x' * 107})
call('无签名·最小参数', False, {k: v for k, v in BASE.items()
                                if k in ('device_platform', 'aid', 'sec_user_id',
                                         'max_cursor', 'count')})
