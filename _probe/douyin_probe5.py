# -*- coding: utf-8 -*-
"""抖音UP主投稿列表验证 v5

关键澄清项：
  A. www.douyin.com 首页预热后能否拿到可用的 web 端 UIFID（前轮 live 域拿到的
     是 UIFID_TEMP，被 Argus 判定 "Uifid Not Found"）
  B. 移动端免签名接口对一个**有大量作品**的账号返回什么（用于判定前轮空列表
     到底是「接口不通」还是「示例账号确实没投稿」）
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
MOBILE_UA = ('com.ss.android.ugc.aweme/110101 (Linux; U; Android 11; zh_CN; '
             'Pixel 5; Build/RQ3A.211001.001; Cronet/TTNetVersion:1e5f5b0d 2021-05-12)')

S = requests.Session()
S.headers.update({'User-Agent': WEB_UA})


def banner(t):
    print('\n' + '=' * 62)
    print(t)
    print('=' * 62)


def short(r, n=420):
    try:
        return json.dumps(r.json(), ensure_ascii=False)[:n]
    except Exception:
        return r.text[:n]


# ------------------------------------------------------ A. web 首页预热取 UIFID
banner('A) www.douyin.com 首页预热 → 观察 cookie')
try:
    S.get('https://www.douyin.com/', timeout=15,
          headers={'User-Agent': WEB_UA,
                   'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'})
    ck = {c.name: c.value for c in S.cookies}
    print(f'    cookies = {list(ck)}')
    print(f"    UIFID = {(ck.get('UIFID') or '')[:60]}")
    print(f"    ttwid = {(ck.get('ttwid') or '')[:40]}")
except Exception as exc:
    print(f'    [ERR] {exc}')

web_cookie = '; '.join(f'{c.name}={c.value}' for c in S.cookies)


def web_post(sec_uid, label):
    params = {
        'device_platform': 'webapp', 'aid': '6383', 'channel': 'channel_pc_web',
        'sec_user_id': sec_uid, 'max_cursor': '0', 'locate_query': 'false',
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
              headers={'User-Agent': WEB_UA, 'Cookie': web_cookie,
                       'Referer': 'https://www.douyin.com/'}, timeout=15)
    print(f'    [{label}] HTTP {r.status_code} len={len(r.content)}')
    print(f'    [{label}] {short(r, 320)}')


banner('B) web 投稿列表（预热后的 cookie）')
try:
    web_post('MS4wLjABAAAAEXAMPLE_ReplaceThisWithRealSecUid',
             '示例账号')
except Exception as exc:
    print(f'    [ERR] {exc}')


# --------------------------------------------- C. 移动端搜索找「有作品」的账号
banner('C) 移动端搜索接口（免签名）拉一个高产账号的 sec_uid')
found = []
for kw in ('人民日报', '央视新闻'):
    try:
        r = S.get('https://aweme.snssdk.com/aweme/v1/discover/search/',
                  params={'keyword': kw, 'count': '5', 'type': '1', 'aid': '1128',
                          'cursor': '0'},
                  headers={'User-Agent': MOBILE_UA}, timeout=15)
        print(f'    [搜索 {kw}] HTTP {r.status_code} len={len(r.content)}')
        j = r.json()
        users = j.get('user_list') or []
        print(f'      user_list 条数={len(users)}')
        for u in users[:3]:
            info = u.get('user_info') or u
            suid = info.get('sec_uid')
            print(f"      - {info.get('nickname')}  sec_uid={suid}")
            if suid:
                found.append((info.get('nickname'), suid))
    except Exception as exc:
        print(f'    [ERR {kw}] {exc}')


# ------------------------------------ D. 用高产账号验证移动端投稿列表
banner('D) 移动端投稿列表（高产账号，判定接口是否真通）')
if not found:
    print('    !! 未搜到账号')
for nick, suid in found[:2]:
    try:
        r = S.get('https://aweme.snssdk.com/aweme/v1/aweme/post/',
                  params={'sec_user_id': suid, 'max_cursor': '0', 'count': '20',
                          'aid': '1128', 'version_code': '110101',
                          'device_platform': 'android'},
                  headers={'User-Agent': MOBILE_UA}, timeout=15)
        j = r.json()
        lst = j.get('aweme_list') or []
        print(f'    [{nick}] status={j.get("status_code")} has_more={j.get("has_more")} '
              f'条数={len(lst)}')
        for a in lst[:3]:
            print(f"      - {a.get('desc','')[:40]!r} aweme_id={a.get('aweme_id')}")
    except Exception as exc:
        print(f'    [ERR {nick}] {exc}')
