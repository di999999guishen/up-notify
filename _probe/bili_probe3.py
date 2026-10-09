# -*- coding: utf-8 -*-
"""B站投稿接口探测 v3：补全指纹 Cookie / App 端接口 / 空间页 HTML 三条路。"""
import hashlib
import json
import re
import time
import urllib.parse
import uuid

import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
    33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40,
    61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11,
    36, 20, 34, 44, 52,
]


def get_mixin_key(orig):
    return ''.join(orig[i] for i in MIXIN_KEY_ENC_TAB)[:32]


def enc_wbi(params, img_key, sub_key):
    mixin_key = get_mixin_key(img_key + sub_key)
    params = dict(params)
    params['wts'] = int(time.time())
    params = {k: ''.join(c for c in str(v) if c not in "!'()*")
              for k, v in sorted(params.items())}
    query = urllib.parse.urlencode(params)
    params['w_rid'] = hashlib.md5((query + mixin_key).encode()).hexdigest()
    return params


def show(tag, resp, limit=400):
    txt = (resp.text or '')[:limit].replace('\n', ' ')
    print(f'    HTTP {resp.status_code}  len={len(resp.content)}\n    {txt}')


MID = '946974'


def main():
    s = requests.Session()
    s.headers.update({
        'User-Agent': UA,
        'Referer': 'https://space.bilibili.com/%s/video' % MID,
        'Origin': 'https://space.bilibili.com',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'zh-CN,zh;q=0.9',
        'sec-ch-ua': '"Chromium";v="124", "Google Chrome";v="124"',
        'sec-fetch-site': 'same-site',
        'sec-fetch-mode': 'cors',
        'sec-fetch-dest': 'empty',
    })
    s.get('https://www.bilibili.com/', timeout=15)

    # 补全指纹 cookie
    print('[0] 补全指纹 Cookie')
    try:
        r = s.get('https://api.bilibili.com/x/frontend/finger/spi', timeout=15)
        d = r.json().get('data') or {}
        b3, b4 = d.get('b_3', ''), d.get('b_4', '')
        if b3:
            s.cookies.set('buvid3', b3, domain='.bilibili.com')
        if b4:
            s.cookies.set('buvid4', b4, domain='.bilibili.com')
        s.cookies.set('_uuid', str(uuid.uuid4()).upper(), domain='.bilibili.com')
        s.cookies.set('b_lsid', '%X_%X' % (int(time.time()), int(time.time() * 997)),
                      domain='.bilibili.com')
        s.cookies.set('CURRENT_FNVAL', '4048', domain='.bilibili.com')
        print(f'    b_3={b3[:20]}..  b_4={b4[:20]}..  cookies={list(s.cookies.keys())}')
    except Exception as exc:
        print(f'    !! {exc}')
        b3 = b4 = ''

    r = s.get('https://api.bilibili.com/x/web-interface/nav', timeout=15)
    wbi = ((r.json().get('data') or {}).get('wbi_img') or {})
    img_key = wbi.get('img_url', '').rsplit('/', 1)[-1].split('.')[0]
    sub_key = wbi.get('sub_url', '').rsplit('/', 1)[-1].split('.')[0]

    print('\n[1] wbi 投稿接口（补全指纹后重试）')
    try:
        p = enc_wbi({'mid': MID, 'ps': 5, 'pn': 1, 'order': 'pubdate',
                     'platform': 'web', 'web_location': 1550101,
                     'order_avoided': 'true'}, img_key, sub_key)
        show('1', s.get('https://api.bilibili.com/x/space/wbi/arc/search',
                        params=p, timeout=15))
    except Exception as exc:
        print(f'    !! {exc}')

    print('\n[2] App 端 /x/v2/space/archive/cursor（不要 access_key 试一下）')
    try:
        show('2', s.get('https://app.bilibili.com/x/v2/space/archive/cursor',
                        params={'vmid': MID, 'ps': 5, 'pn': 1}, timeout=15))
    except Exception as exc:
        print(f'    !! {exc}')

    print('\n[3] 抓空间页 HTML，找 __INITIAL_STATE__ / embedded JSON')
    try:
        r = s.get(f'https://space.bilibili.com/{MID}/video', timeout=20)
        html = r.text or ''
        print(f'    HTTP {r.status_code}  len={len(html)}')
        for key in ('__INITIAL_STATE__', 'window.__playinfo__', 'vlist',
                    '__NEPTUNE_IS_MY_WAIFU__'):
            print(f'    contains {key}: {key in html}')
        m = re.search(r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\});', html, re.S)
        if m:
            print(f'    INITIAL_STATE 片段: {m.group(1)[:500]}')
        bvids = re.findall(r'BV[0-9A-Za-z]{10}', html)
        print(f'    页内 bvid 命中 {len(set(bvids))} 个: {list(set(bvids))[:5]}')
    except Exception as exc:
        print(f'    !! {exc}')

    print('\n[4] 单视频详情接口基准对照 /x/web-interface/view')
    try:
        show('4', s.get('https://api.bilibili.com/x/web-interface/view',
                        params={'bvid': 'BV1GJ411x7h7'}, timeout=15), 200)
    except Exception as exc:
        print(f'    !! {exc}')


if __name__ == '__main__':
    main()
