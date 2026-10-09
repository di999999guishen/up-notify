# -*- coding: utf-8 -*-
"""抖音探测 v2：ttwid 注册 / 老 iesdouyin 接口 / 移动端接口 三条备选路。"""
import json
import time
import urllib.parse

import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
MOBILE_UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
             "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")


def show(tag, resp, limit=350):
    print(f'    HTTP {resp.status_code}  len={len(resp.content)}  '
          f'{(resp.text or "")[:limit]}')


def main():
    s = requests.Session()
    s.headers.update({'User-Agent': UA, 'Accept-Language': 'zh-CN,zh;q=0.9'})

    print('[1] ttwid 注册接口 ttwid.bytedance.com/ttwid/union/register/')
    try:
        payload = {
            'region': 'cn', 'aid': 1768, 'needFid': False,
            'service': 'www.ixigua.com',
            'migrate_info': {'ticket': '', 'source': 'node'},
            'cbUrlProtocol': 'https', 'union': True,
        }
        r = s.post('https://ttwid.bytedance.com/ttwid/union/register/',
                   json=payload, timeout=20,
                   headers={'Content-Type': 'application/json'})
        print(f'    HTTP {r.status_code}  cookies={list(s.cookies.keys())}')
        print(f'    body={(r.text or "")[:200]}')
    except Exception as exc:
        print(f'    !! {exc}')

    print('\n[2] 老 iesdouyin 接口 /web/api/v2/aweme/post/（不带签名）')
    try:
        r = s.get('https://www.iesdouyin.com/web/api/v2/aweme/post/',
                  params={'sec_uid': 'MS4wLjABAAAAEXAMPLE_ReplaceThisWithRealSecUid', 'count': 10,
                          'max_cursor': 0, 'aid': 1128, '_signature': ''},
                  timeout=20)
        show('2', r)
    except Exception as exc:
        print(f'    !! {exc}')

    print('\n[3] 移动端 aweme.snssdk.com /aweme/v1/aweme/post/')
    try:
        r = s.get('https://aweme.snssdk.com/aweme/v1/aweme/post/',
                  params={'sec_user_id': 'MS4wLjABAAAAEXAMPLE_ReplaceThisWithRealSecUid', 'max_cursor': 0,
                          'count': 20, 'version_code': '296',
                          'version_name': '2.9.6', 'device_platform': 'android',
                          'os_version': '13', 'aid': 1128},
                  headers={'User-Agent': MOBILE_UA}, timeout=20)
        show('3', r)
    except Exception as exc:
        print(f'    !! {exc}')

    print('\n[4] 抖音热搜榜（基准对照：完全不需签名的公开接口）')
    try:
        r = s.get('https://www.iesdouyin.com/web/api/v2/hotsearch/billboard/word/',
                  timeout=20)
        show('4', r, 200)
    except Exception as exc:
        print(f'    !! {exc}')

    print('\n[5] RSSHub 公共实例可达性（B站用户视频订阅）')
    try:
        r = requests.get('https://rsshub.app/bilibili/user/video/946974',
                         headers={'User-Agent': UA}, timeout=25)
        print(f'    HTTP {r.status_code}  len={len(r.content)}  '
              f'{(r.text or "")[:150]}')
    except Exception as exc:
        print(f'    !! {exc}')


if __name__ == '__main__':
    main()
