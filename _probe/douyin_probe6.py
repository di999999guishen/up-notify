# -*- coding: utf-8 -*-
"""抖音UP主投稿列表验证 v6 —— 用户主页 HTML 内嵌数据

思路：绕开需要 Uifid 的 XHR 接口，直接抓 https://www.douyin.com/user/<sec_uid>
页面 HTML，看作品列表是否内嵌在 RENDER_DATA / _ROUTER_DATA / SSR 数据中。
"""
import json
import re
import sys

import requests

WEB_UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
          '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36')
SEC = 'MS4wLjABAAAAEXAMPLE_ReplaceThisWithRealSecUid'

S = requests.Session()
S.headers.update({
    'User-Agent': WEB_UA,
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9',
})


def banner(t):
    print('\n' + '=' * 62)
    print(t)
    print('=' * 62)


# 预热拿 __ac_nonce
try:
    S.get('https://www.douyin.com/', timeout=15)
except Exception:
    pass


def probe(url, label):
    banner(label)
    try:
        r = S.get(url, timeout=20)
        print(f'    HTTP {r.status_code} len={len(r.content)} '
              f'ct={r.headers.get("Content-Type","")[:40]}')
        html = r.text
        for key in ('RENDER_DATA', '_ROUTER_DATA', '__pace_f', 'aweme_id', 'itemList'):
            print(f'    contains {key!r}: {html.count(key)}')
        m = re.search(r'id="RENDER_DATA"[^>]*>(.*?)</script>', html, re.S)
        if m:
            import urllib.parse
            raw = urllib.parse.unquote(m.group(1))
            print(f'    RENDER_DATA 解码后 len={len(raw)}')
            print(f'    {raw[:300]}')
        # 找 aweme_id 片段
        ids = re.findall(r'"aweme_id":"(\d{15,})"', html)
        print(f'    HTML 中 aweme_id 数量 = {len(ids)}  样例={ids[:3]}')
        print(f'    HTML 头部: {html[:200]!r}')
    except Exception as exc:
        print(f'    [ERR] {exc}')


probe(f'https://www.douyin.com/user/{SEC}', '1) douyin 用户主页 HTML')
probe(f'https://www.iesdouyin.com/share/user/{SEC}', '2) iesdouyin 分享页 HTML')

banner('3) 移动端搜索（带完整参数重试）')
MOBILE_UA = ('com.ss.android.ugc.aweme/110101 (Linux; U; Android 11; zh_CN; '
             'Pixel 5; Build/RQ3A.211001.001; Cronet/TTNetVersion:1e5f5b0d 2021-05-12)')
try:
    r = S.get('https://aweme.snssdk.com/aweme/v1/user/profile/self/',
              params={'aid': '1128'}, headers={'User-Agent': MOBILE_UA}, timeout=15)
    print(f'    profile/self HTTP {r.status_code} len={len(r.content)} {r.text[:200]}')
except Exception as exc:
    print(f'    [ERR] {exc}')
