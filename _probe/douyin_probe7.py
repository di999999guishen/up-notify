# -*- coding: utf-8 -*-
"""抖音 v7 —— 定点排查 www 域 Uifid 获取链路

观察：www.douyin.com 的 user/profile/other/ 免签名可用（200/23KB），
     但 aweme/post/ 报 "Uifid Not Found"。
假设：www 域在访问其 API 时会种下属于自己的 UIFID，live 域的 UIFID 不被接受。
验证：全新 session 只访问 www 域接口，观察 cookie 演化，再重试 post。
"""
import json
import sys
from pathlib import Path
import urllib.parse

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'live-recorder'))  # 探测脚本借用姊妹项目的 LiveWatcher
from core.signing import a_bogus_sign                    # noqa: E402

WEB_UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
          '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36')
SEC = 'MS4wLjABAAAAEXAMPLE_ReplaceThisWithRealSecUid'

S = requests.Session()
S.headers.update({
    'User-Agent': WEB_UA,
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'zh-CN,zh;q=0.9',
    'Referer': 'https://www.douyin.com/',
})


def banner(t):
    print('\n' + '=' * 62)
    print(t)
    print('=' * 62)


def ck_str():
    return '; '.join(f'{c.name}={c.value}' for c in S.cookies)


def show_cookies(tag):
    print(f'    [{tag}] cookies = {[c.name for c in S.cookies]}')


def short(r, n=260):
    try:
        return json.dumps(r.json(), ensure_ascii=False)[:n]
    except Exception:
        return r.text[:n]


# 1) 只打 www 域的 profile 接口
banner('1) 只访问 www 域 profile 接口，观察是否种下 UIFID')
try:
    r = S.get('https://www.douyin.com/aweme/v1/web/user/profile/other/',
              params={'sec_user_id': SEC, 'device_platform': 'webapp',
                      'aid': '6383', 'publish_video_strategy_type': '2',
                      'version_code': '290100', 'version_name': '29.1.0'},
              timeout=15)
    print(f'    HTTP {r.status_code} len={len(r.content)}')
    print(f'    {short(r)}')
    show_cookies('profile后')
except Exception as exc:
    print(f'    [ERR] {exc}')

# 2) 再打 post 接口（带当前 cookie + a_bogus）
banner('2) post 接口（Referer=用户页 + a_bogus）')
try:
    params = {
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
        'webid': '7490000000000000000', 'msToken': 'x' * 107,
    }
    qs = '&'.join(f'{k}={urllib.parse.quote(str(v))}' for k, v in params.items())
    params['a_bogus'] = a_bogus_sign(qs, WEB_UA)
    r = S.get('https://www.douyin.com/aweme/v1/web/aweme/post/', params=params,
              headers={'Referer': f'https://www.douyin.com/user/{SEC}'}, timeout=15)
    print(f'    HTTP {r.status_code} len={len(r.content)}')
    print(f'    {short(r, 300)}')
    show_cookies('post后')
except Exception as exc:
    print(f'    [ERR] {exc}')

# 3) 移动端 post（换新参数形态再确认一次）
banner('3) 移动端 post（带 X-Gorgon 缺失时的典型返回）')
MOBILE_UA = ('com.ss.android.ugc.aweme/110101 (Linux; U; Android 11; zh_CN; '
             'Pixel 5; Build/RQ3A.211001.001)')
for extra in ({}, {'version_name': '11.1.0', 'os_version': '11', 'channel': 'googleplay'}):
    p = {'sec_user_id': SEC, 'max_cursor': '0', 'count': '20', 'aid': '1128',
         'version_code': '110101', 'device_platform': 'android'}
    p.update(extra)
    r = S.get('https://aweme.snssdk.com/aweme/v1/aweme/post/', params=p,
              headers={'User-Agent': MOBILE_UA}, timeout=15)
    print(f'    HTTP {r.status_code} len={len(r.content)} {r.text[:180]}')
