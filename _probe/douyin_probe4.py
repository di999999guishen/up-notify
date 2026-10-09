# -*- coding: utf-8 -*-
"""抖音UP主投稿列表验证 v4

思路修正：不再反查 sec_uid，改用**直播 enter 接口**直接取房间主的 sec_uid
（该接口在生产环境已验证长期可用），再用它去验证投稿列表接口。
"""
import json
import sys
from pathlib import Path
import time
import urllib.parse

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'live-recorder'))  # 探测脚本借用姊妹项目的 LiveWatcher

from monitor.watcher import LiveWatcher          # noqa: E402
from core.config import COMMON_HEADERS, DOUYIN_COOKIE  # noqa: E402

UA = COMMON_HEADERS['User-Agent']
S = requests.Session()
S.headers.update({'User-Agent': UA})


def banner(t):
    print('\n' + '=' * 62)
    print(t)
    print('=' * 62)


def short(r, n=300):
    try:
        j = r.json()
        return json.dumps(j, ensure_ascii=False)[:n]
    except Exception:
        return r.text[:n]


# ---------------------------------------------------------------- 1. sec_uid
banner('1) 从直播间 enter 接口取真实 sec_uid')
sec_uid = ''
nickname = ''
try:
    w = LiveWatcher('000000000000')            # 被探测的账号（房间号取自直播链接的 live_web_rid）
    st = w.fetch()
    print(f'    ok={st.ok} live={st.live} status={st.status} nick={st.nickname}')
    sec_uid = st.sec_uid
    nickname = st.nickname
    print(f'    sec_uid = {sec_uid}')
except Exception as exc:
    print(f'    [ERR] {exc}')

if not sec_uid:
    print('!! 未取到 sec_uid，退出')
    sys.exit(0)

# 顺手拿一份会话 cookie（enter 请求过程中 session 里可能有 ttwid 等）
cookies = {c.name: c.value for c in w.session.cookies}
print(f'    cookies = {list(cookies)}')


# --------------------------------------------------- 2. 移动端免签名投稿列表
banner('2) aweme.snssdk.com 移动端投稿列表（免签名）')
MOBILE_UA = ('com.ss.android.ugc.aweme/110101 (Linux; U; Android 11; zh_CN; '
             'Pixel 5; Build/RQ3A.211001.001; Cronet/TTNetVersion:1e5f5b0d 2021-05-12)')
try:
    r = S.get('https://aweme.snssdk.com/aweme/v1/aweme/post/',
              params={
                  'sec_user_id': sec_uid,
                  'max_cursor': '0',
                  'count': '20',
                  'aid': '1128',
                  'version_code': '110101',
                  'device_platform': 'android',
              },
              headers={'User-Agent': MOBILE_UA}, timeout=15)
    print(f'    HTTP {r.status_code} len={len(r.content)}')
    print(f'    {short(r, 400)}')
except Exception as exc:
    print(f'    [ERR] {exc}')


# ------------------------------------------- 3. www.douyin.com + a_bogus 投稿
banner('3) www.douyin.com 投稿列表（a_bogus 签名 + ttwid cookie）')
try:
    from core.signing import a_bogus_sign
    params = {
        'device_platform': 'webapp',
        'aid': '6383',
        'channel': 'channel_pc_web',
        'sec_user_id': sec_uid,
        'max_cursor': '0',
        'locate_query': 'false',
        'show_live_replay_strategy': '1',
        'count': '18',
        'publish_video_strategy_type': '2',
        'pc_client_type': '1',
        'version_code': '290100',
        'version_name': '29.1.0',
        'cookie_enabled': 'true',
        'screen_width': '1536',
        'screen_height': '864',
        'browser_language': 'zh-CN',
        'browser_platform': 'Win32',
        'browser_name': 'Chrome',
        'browser_version': '124.0.0.0',
        'browser_online': 'true',
        'engine_name': 'Blink',
        'engine_version': '124.0.0.0',
        'os_name': 'Windows',
        'os_version': '10',
        'cpu_core_num': '8',
        'device_memory': '8',
        'platform': 'PC',
        'downlink': '10',
        'effective_type': '4g',
        'round_trip_time': '50',
        'webid': '7490000000000000000',
        'msToken': 'x' * 107,
    }
    qs = '&'.join(f'{k}={urllib.parse.quote(str(v))}' for k, v in params.items())
    params['a_bogus'] = a_bogus_sign(qs, UA)
    ck = '; '.join(f'{k}={v}' for k, v in cookies.items()) or DOUYIN_COOKIE
    r = S.get('https://www.douyin.com/aweme/v1/web/aweme/post/',
              params=params,
              headers={**COMMON_HEADERS, 'Cookie': ck,
                       'Referer': 'https://www.douyin.com/'}, timeout=15)
    print(f'    HTTP {r.status_code} len={len(r.content)}')
    print(f'    {short(r, 400)}')
except Exception as exc:
    print(f'    [ERR] {exc}')


# ------------------------------------------------------ 4. 该 UP 主用户主页信息
banner('4) 用户主页信息接口（拿昵称/粉丝数，确认 sec_uid 有效）')
try:
    r = S.get('https://www.douyin.com/aweme/v1/web/user/profile/other/',
              params={'sec_user_id': sec_uid, 'device_platform': 'webapp',
                      'aid': '6383', 'publish_video_strategy_type': '2'},
              headers={**COMMON_HEADERS,
                       'Cookie': '; '.join(f'{k}={v}' for k, v in cookies.items())},
              timeout=15)
    print(f'    HTTP {r.status_code} len={len(r.content)}')
    print(f'    {short(r, 400)}')
except Exception as exc:
    print(f'    [ERR] {exc}')
