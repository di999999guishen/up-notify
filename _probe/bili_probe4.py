# -*- coding: utf-8 -*-
"""B站投稿接口探测 v4：补 2023 年后新增的 dm_* 设备指纹参数。

-352 风控校验失败的常见成因不是签名错，而是缺 dm_img_str / dm_cover_img_str
这组 WebGL 指纹参数。它们同样要被纳入 wbi 签名。
"""
import hashlib
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

# WebGL renderer / vendor 的 base64（去掉尾部 '='），模拟真实浏览器
DM_IMG_STR = 'V2ViR0wgMS4wIChPcGVuR0wgRVMgMi4wIENocm9taXVtKQ'
DM_COVER_IMG_STR = ('QU5HTEUgKEludGVsLCBJbnRlbChSKSBVSEQgR3JhcGhpY3MgKDB4MDAwMDQ2QTUpIERpcmVjdDNEMTEg'
                    'dnNfNV8wIHBzXzVfMCwgRDMxIFNoYWRlciBNb2RlbCA1LjAp')


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


def show(tag, resp, limit=600):
    txt = (resp.text or '')[:limit].replace('\n', ' ')
    print(f'    HTTP {resp.status_code}  len={len(resp.content)}\n    {txt}')


MID = '946974'


def main():
    print('等 45 秒让 IP 限流恢复...')
    time.sleep(45)

    s = requests.Session()
    s.headers.update({
        'User-Agent': UA,
        'Referer': f'https://space.bilibili.com/{MID}/video',
        'Origin': 'https://space.bilibili.com',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'zh-CN,zh;q=0.9',
        'sec-ch-ua': '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'sec-fetch-site': 'same-site',
        'sec-fetch-mode': 'cors',
        'sec-fetch-dest': 'empty',
    })
    s.get('https://www.bilibili.com/', timeout=15)
    r = s.get('https://api.bilibili.com/x/frontend/finger/spi', timeout=15)
    d = r.json().get('data') or {}
    for k, v in (('buvid3', d.get('b_3')), ('buvid4', d.get('b_4'))):
        if v:
            s.cookies.set(k, v, domain='.bilibili.com')
    s.cookies.set('b_nut', str(int(time.time())), domain='.bilibili.com')

    r = s.get('https://api.bilibili.com/x/web-interface/nav', timeout=15)
    wbi = ((r.json().get('data') or {}).get('wbi_img') or {})
    img_key = wbi.get('img_url', '').rsplit('/', 1)[-1].split('.')[0]
    sub_key = wbi.get('sub_url', '').rsplit('/', 1)[-1].split('.')[0]
    print(f'cookie={list(s.cookies.keys())}')

    print('\n[1] arc/search + dm_* 设备指纹')
    params = {
        'mid': MID, 'ps': 5, 'pn': 1, 'order': 'pubdate',
        'platform': 'web', 'web_location': 1550101, 'order_avoided': 'true',
        'index': 0, 'keyword': '',
        'dm_img_list': '[]',
        'dm_img_str': DM_IMG_STR,
        'dm_cover_img_str': DM_COVER_IMG_STR,
        'dm_img_inter': '{"ds":[],"wh":[0,0,0],"of":[0,0,0]}',
    }
    try:
        signed = enc_wbi(params, img_key, sub_key)
        resp = s.get('https://api.bilibili.com/x/space/wbi/arc/search',
                     params=signed, timeout=15)
        show('1', resp)
        j = resp.json()
        if j.get('code') == 0:
            data = j['data']
            vlist = (data.get('list') or {}).get('vlist') or []
            print(f"    ✅ 成功！总数={(data.get('page') or {}).get('count')}  本页 {len(vlist)} 条")
            for v in vlist:
                print(f"      - {v.get('bvid')} | {v.get('created')} | {str(v.get('title'))[:44]}")
    except Exception as exc:
        print(f'    !! {exc}')

    print('\n[2] 备选：合集/系列列表（通常风控更松）')
    try:
        resp = s.get('https://api.bilibili.com/x/polymer/web-space/seasons_series_list',
                     params={'mid': MID, 'page_num': 1, 'page_size': 10, 'web_location': 333.1387},
                     timeout=15)
        show('2', resp, 300)
    except Exception as exc:
        print(f'    !! {exc}')


if __name__ == '__main__':
    main()
