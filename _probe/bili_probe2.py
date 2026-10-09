# -*- coding: utf-8 -*-
"""B站投稿接口探测 v2：打印原始响应，并横向试多个备选接口。"""
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


def show(tag, resp, limit=300):
    txt = (resp.text or '')[:limit].replace('\n', ' ')
    print(f'    HTTP {resp.status_code}  len={len(resp.content)}  {txt}')


def main():
    mid = '946974'
    s = requests.Session()
    s.headers.update({
        'User-Agent': UA,
        'Referer': 'https://space.bilibili.com/',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'zh-CN,zh;q=0.9',
    })
    s.get('https://www.bilibili.com/', timeout=15)
    print(f'cookie: {list(s.cookies.keys())}')

    r = s.get('https://api.bilibili.com/x/web-interface/nav', timeout=15)
    wbi = ((r.json().get('data') or {}).get('wbi_img') or {})
    img_key = wbi.get('img_url', '').rsplit('/', 1)[-1].split('.')[0]
    sub_key = wbi.get('sub_url', '').rsplit('/', 1)[-1].split('.')[0]
    print(f'wbi keys: img={img_key[:12]}.. sub={sub_key[:12]}..\n')

    # A. 官方旧投稿接口（无需 wbi）
    print('[A] /x/space/arc/search  (旧接口, 无 wbi)')
    show('A', s.get('https://api.bilibili.com/x/space/arc/search',
                    params={'mid': mid, 'ps': 5, 'pn': 1, 'order': 'pubdate'},
                    timeout=15))

    # B. wbi 投稿接口
    print('\n[B] /x/space/wbi/arc/search (带 wbi 签名)')
    show('B', s.get('https://api.bilibili.com/x/space/wbi/arc/search',
                    params=enc_wbi({'mid': mid, 'ps': 5, 'pn': 1,
                                    'order': 'pubdate', 'platform': 'web',
                                    'web_location': 1550101}, img_key, sub_key),
                    timeout=15))

    # C. 空间动态流（也需要 wbi）
    print('\n[C] /x/polymer/web-dynamic/v1/feed/space (带 wbi)')
    show('C', s.get('https://api.bilibili.com/x/polymer/web-dynamic/v1/feed/space',
                    params=enc_wbi({'host_mid': mid, 'timezone_offset': -480,
                                    'platform': 'web', 'features':
                                    'itemOpusStyle,listOnlyfans,opusBigCover'},
                                   img_key, sub_key),
                    timeout=15))

    # D. 用户基本信息（探路用，应能通）
    print('\n[D] /x/web-interface/card (用户名片, 基准对照)')
    show('D', s.get('https://api.bilibili.com/x/web-interface/card',
                    params={'mid': mid}, timeout=15))

    # E. 用户投稿数（另一个入口）
    print('\n[E] /x/space/upstat')
    show('E', s.get('https://api.bilibili.com/x/space/upstat',
                    params={'mid': mid}, timeout=15))


if __name__ == '__main__':
    main()
