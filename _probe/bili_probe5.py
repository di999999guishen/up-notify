# -*- coding: utf-8 -*-
"""B站UP主投稿列表验证 v5 —— 试 App 端 appkey 签名接口

前几轮结论：web 端 wbi arc/search 被 IP 级风控（-352/-412）。
本轮换思路：走 App 端（appkey + appsec md5 签名），风控策略与 web 端不同。
"""
import hashlib
import json
import time
import urllib.parse

import requests

UA = ('Mozilla/5.0 BiliDroid/7.63.0 (bbcallen@gmail.com) os/android '
      'model/Pixel5 mobi/android')
S = requests.Session()
S.headers.update({'User-Agent': UA})

# B站 Android 端公开 appkey（社区长期公开，非私密凭证）
APPKEY = '1d8b6e7d45233436'
APPSEC = '560c52ccd288fed045859ed18bffd973'

TEST_MID = 946974      # 影视飓风


def banner(t):
    print('\n' + '=' * 62)
    print(t)
    print('=' * 62)


def short(r, n=350):
    try:
        return json.dumps(r.json(), ensure_ascii=False)[:n]
    except Exception:
        return r.text[:n]


def app_sign(params: dict) -> str:
    """B站 App 端签名：md5(sorted_query + appsec)。"""
    q = urllib.parse.urlencode(sorted(params.items()))
    return hashlib.md5((q + APPSEC).encode()).hexdigest()


# ------------------------------------------------ 1. App 端视频列表（newest）
banner('1) App 端 space/archive/cursor（appkey 签名）')
try:
    p = {'appkey': APPKEY, 'vmid': str(TEST_MID), 'ps': '20',
         'pn': '1', 'order': 'pubdate', 'ts': str(int(time.time()))}
    p['sign'] = app_sign(p)
    r = S.get('https://app.bilibili.com/x/v2/space/archive/cursor',
              params=p, timeout=15)
    print(f'    HTTP {r.status_code} len={len(r.content)}')
    print(f'    {short(r)}')
except Exception as exc:
    print(f'    [ERR] {exc}')

# ------------------------------------------------ 2. App 端用户动态（含投稿）
banner('2) App 端 space/dynamic 动态流')
try:
    p = {'appkey': APPKEY, 'vmid': str(TEST_MID), 'type': 'all',
         'page': '1', 'ps': '20', 'ts': str(int(time.time()))}
    p['sign'] = app_sign(p)
    r = S.get('https://app.bilibili.com/x/v2/space/archive', params=p, timeout=15)
    print(f'    HTTP {r.status_code} len={len(r.content)}')
    print(f'    {short(r)}')
except Exception as exc:
    print(f'    [ERR] {exc}')

# ------------------------------------------- 3. 移动端 api（非 app 签名，轻量）
banner('3) 移动端 api.bilibili.com space/archive/cursor（无签名裸试）')
try:
    r = S.get('https://api.bilibili.com/x/v2/space/archive/cursor',
              params={'vmid': str(TEST_MID), 'ps': '20', 'pn': '1',
                      'order': 'pubdate'},
              headers={'User-Agent': 'Mozilla/5.0 (Linux; Android 11) AppleWebKit/537.36'},
              timeout=15)
    print(f'    HTTP {r.status_code} len={len(r.content)}')
    print(f'    {short(r)}')
except Exception as exc:
    print(f'    [ERR] {exc}')

# ------------------------------------------- 4. 稍后再看式：合集接口（已验证）
banner('4) seasons_series_list 合集接口（前轮已验证成功，复测）')
try:
    r = S.get('https://api.bilibili.com/x/polymer/web-space/seasons_series_list',
              params={'mid': str(TEST_MID), 'page_num': '1', 'page_size': '20'},
              headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                                     'AppleWebKit/537.36 (KHTML, like Gecko) '
                                     'Chrome/124.0.0.0 Safari/537.36',
                       'Referer': f'https://space.bilibili.com/{TEST_MID}/'},
              timeout=15)
    print(f'    HTTP {r.status_code} len={len(r.content)}')
    j = r.json()
    print(f"    code={j.get('code')} msg={j.get('message')}")
    items = ((j.get('data') or {}).get('items_lists') or {})
    print(f"    seasons={len(items.get('seasons_list') or [])} "
          f"series={len(items.get('series_list') or [])}")
except Exception as exc:
    print(f'    [ERR] {exc}')

# ------------------------------------------- 5. 必剪/第三方镜像：bilibili-json
banner('5) 用户投稿 RSS（B站官方 feed 形式）')
try:
    r = S.get(f'https://rsshub.app/bilibili/user/video/{TEST_MID}', timeout=15)
    print(f'    HTTP {r.status_code} len={len(r.content)}')
    print(f'    {r.text[:200]}')
except Exception as exc:
    print(f'    [ERR] {exc}')
