# -*- coding: utf-8 -*-
"""B站 UP 主投稿列表接口可行性探测。

测三个点：
  1) 免登录能否拿到 wbi 签名密钥（nav 接口）
  2) space/wbi/arc/search 是否可用、返回什么结构
  3) 不签名（裸接口）是否仍可用 —— 决定要不要背 wbi 这套复杂度
"""
import hashlib
import json
import sys
import time
import urllib.parse

import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
    33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40,
    61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11,
    36, 20, 34, 44, 52,
]


def get_mixin_key(orig: str) -> str:
    return ''.join(orig[i] for i in MIXIN_KEY_ENC_TAB)[:32]


def enc_wbi(params: dict, img_key: str, sub_key: str) -> dict:
    mixin_key = get_mixin_key(img_key + sub_key)
    params = dict(params)
    params['wts'] = int(time.time())
    params = {k: ''.join(c for c in str(v) if c not in "!'()*")
              for k, v in sorted(params.items())}
    query = urllib.parse.urlencode(params)
    params['w_rid'] = hashlib.md5((query + mixin_key).encode()).hexdigest()
    return params


def main():
    mid = sys.argv[1] if len(sys.argv) > 1 else '946974'
    s = requests.Session()
    s.headers.update({'User-Agent': UA, 'Referer': 'https://www.bilibili.com/'})

    print('=' * 60)
    print(f'[1] 预热拿 Cookie（buvid3 是投稿接口的硬性风控项）')
    try:
        r = s.get('https://www.bilibili.com/', timeout=15)
        print(f'    HTTP {r.status_code}   cookies={list(s.cookies.keys())}')
    except Exception as exc:
        print(f'    !! 失败: {exc}')
        return

    print('=' * 60)
    print('[2] 取 wbi 签名密钥（nav 接口，免登录）')
    try:
        r = s.get('https://api.bilibili.com/x/web-interface/nav', timeout=15)
        nav = r.json()
        print(f'    code={nav.get("code")}  message={nav.get("message")}')
        wbi = (nav.get('data') or {}).get('wbi_img') or {}
        img_url = wbi.get('img_url', '')
        sub_url = wbi.get('sub_url', '')
        print(f'    img_url={img_url}')
        print(f'    sub_url={sub_url}')
        img_key = img_url.rsplit('/', 1)[-1].split('.')[0] if img_url else ''
        sub_key = sub_url.rsplit('/', 1)[-1].split('.')[0] if sub_url else ''
        print(f'    img_key={img_key}  sub_key={sub_key}')
    except Exception as exc:
        print(f'    !! 失败: {exc}')
        img_key = sub_key = ''

    base_params = {'mid': mid, 'ps': 5, 'pn': 1, 'order': 'pubdate',
                   'platform': 'web', 'web_location': 1550101}

    print('=' * 60)
    print('[3a] 裸试 space/wbi/arc/search（不带签名）')
    try:
        r = s.get('https://api.bilibili.com/x/space/wbi/arc/search',
                  params=base_params, timeout=15)
        j = r.json()
        print(f'    HTTP {r.status_code}  code={j.get("code")}  message={j.get("message")}')
    except Exception as exc:
        print(f'    !! 失败: {exc}')

    if img_key and sub_key:
        print('=' * 60)
        print('[3b] 带 wbi 签名再试')
        try:
            signed = enc_wbi(base_params, img_key, sub_key)
            print(f'    w_rid={signed.get("w_rid")}  wts={signed.get("wts")}')
            r = s.get('https://api.bilibili.com/x/space/wbi/arc/search',
                      params=signed, timeout=15)
            j = r.json()
            print(f'    HTTP {r.status_code}  code={j.get("code")}  message={j.get("message")}')
            data = j.get('data') or {}
            page = data.get('page') or {}
            vlist = (data.get('list') or {}).get('vlist') or []
            print(f'    page.count={page.get("count")}  vlist={len(vlist)} 条')
            for v in vlist[:5]:
                print(f'      - bvid={v.get("bvid")}  title={str(v.get("title"))[:40]}  '
                      f'created={v.get("created")}')
        except Exception as exc:
            print(f'    !! 失败: {exc}')


if __name__ == '__main__':
    main()
