# -*- coding: utf-8 -*-
"""抖音探测 v3：先反查一个真实有效的 sec_uid，再用它验证免签名投稿接口。

思路：热门视频榜 → 提取 author.sec_uid → 打 aweme/post
若拿到非空列表，则「免签名」这条路成立。
"""
import json
import urllib.parse

import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
MOBILE_UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
             "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")

s = requests.Session()
s.headers.update({'User-Agent': MOBILE_UA, 'Accept-Language': 'zh-CN,zh;q=0.9'})


def get_json(url, params=None, headers=None, tag=''):
    try:
        r = s.get(url, params=params, headers=headers, timeout=20)
        txt = r.text or ''
        print(f'  [{tag}] HTTP {r.status_code} len={len(r.content)}')
        try:
            return r.json()
        except Exception:
            print(f'       非 JSON: {txt[:200]}')
            return None
    except Exception as exc:
        print(f'  [{tag}] !! {exc}')
        return None


def main():
    candidates = []

    print('[A] 热门视频榜 iesdouyin/web/api/v2/hotsearch/billboard/aweme/')
    j = get_json('https://www.iesdouyin.com/web/api/v2/hotsearch/billboard/aweme/',
                 tag='A')
    if j:
        lst = j.get('aweme_list') or j.get('data') or []
        print(f'      条数={len(lst)}')
        for a in lst[:8]:
            au = (a.get('author') or {})
            if au.get('sec_uid'):
                candidates.append((au.get('nickname', '?'), au['sec_uid']))
        for n, u in candidates[:5]:
            print(f'      - {n[:18]}  {u}')

    print('\n[B] 关键词搜索用户 general/search/single/（取一个真实 sec_uid）')
    j = get_json('https://aweme.snssdk.com/aweme/v1/general/search/single/',
                 params={'keyword': '人民日报', 'count': 5, 'offset': 0,
                         'search_source': 'normal_search', 'aid': 1128,
                         'version_code': '296', 'device_platform': 'android'},
                 tag='B')
    if j:
        for d in (j.get('data') or [])[:5]:
            ui = (d.get('user_info') or {})
            if ui.get('sec_uid'):
                candidates.append((ui.get('nickname', '?'), ui['sec_uid']))
                print(f"      - {ui.get('nickname')}  {ui['sec_uid']}")

    if not candidates:
        print('\n!! 没能反查到任何 sec_uid，后续验证无法进行')
        return

    print(f'\n[C] 用 {len(candidates)} 个候选 sec_uid 逐个验证 aweme/post（移动端·免签名）')
    for name, uid in candidates[:4]:
        j = get_json('https://aweme.snssdk.com/aweme/v1/aweme/post/',
                     params={'sec_user_id': uid, 'max_cursor': 0, 'count': 20,
                             'version_code': '296', 'version_name': '2.9.6',
                             'device_platform': 'android', 'os_version': '13',
                             'aid': 1128},
                     tag=f'C:{name[:10]}')
        if not j:
            continue
        lst = j.get('aweme_list') or []
        print(f"      status_code={j.get('status_code')}  has_more={j.get('has_more')}  "
              f"视频数={len(lst)}")
        for a in lst[:3]:
            print(f"        * {a.get('aweme_id')} | create_time={a.get('create_time')} | "
                  f"{(a.get('desc') or '')[:36]}")
        if lst:
            print(f'      >>> ✅ 免签名链路可用！{name} 共取到 {len(lst)} 条')
            break


if __name__ == '__main__':
    main()
