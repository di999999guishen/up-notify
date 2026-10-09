# -*- coding: utf-8 -*-
"""抖音 UP 主视频列表接口探测。

链路：ttwid 预热 → a_bogus 签名 → aweme/post 取投稿列表。
先不纠结 sec_uid 是否有效，重点看返回的错误码是
「签名被拒」还是「参数无效」—— 后者说明签名链路是通的。
"""
import json
import sys
from pathlib import Path
import time
import urllib.parse

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'live-recorder'))  # 探测脚本借用姊妹项目的 LiveWatcher
try:
    from core.signing import a_bogus_sign
    print('[ok] 已加载 live-recorder 的 a_bogus 实现')
except Exception as exc:
    print(f'[!!] a_bogus 加载失败: {exc}')
    sys.exit(1)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

BASE_COMMON = {
    'device_platform': 'webapp',
    'aid': '6383',
    'channel': 'channel_pc_web',
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
    'round_trip_time': '100',
}


def build_qs(params: dict) -> str:
    return '&'.join(f'{k}={urllib.parse.quote(str(v), safe="")}'
                    for k, v in params.items())


def main():
    s = requests.Session()
    s.headers.update({
        'User-Agent': UA,
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'zh-CN,zh;q=0.9',
        'Referer': 'https://www.douyin.com/',
    })

    print('\n[1] 预热 www.douyin.com 取 ttwid')
    try:
        r = s.get('https://www.douyin.com/', timeout=20)
        print(f'    HTTP {r.status_code}  cookies={list(s.cookies.keys())}')
        ttwid = s.cookies.get('ttwid', '')
        print(f'    ttwid={ttwid[:40]}...' if ttwid else '    !! 没拿到 ttwid')
    except Exception as exc:
        print(f'    !! {exc}')

    print('\n[2] 推荐流 tab/feed（带 a_bogus）—— 顺便捞一个真实 sec_uid')
    sec_uid = ''
    try:
        p = dict(BASE_COMMON)
        p.update({'count': '10', 'refresh_index': '1', 'refer_type': '10',
                  'pull_type': '2', 'type': '5', 'is_auto_play': '0',
                  'cookie_enabled': 'true'})
        qs = build_qs(p)
        p['a_bogus'] = a_bogus_sign(qs, UA)
        r = s.get('https://www.douyin.com/aweme/v1/web/tab/feed/', params=p, timeout=20)
        print(f'    HTTP {r.status_code}  len={len(r.content)}')
        try:
            j = r.json()
            print(f"    status_code={j.get('status_code')}  aweme 数={len(j.get('aweme_list') or [])}")
            for a in (j.get('aweme_list') or [])[:3]:
                au = a.get('author') or {}
                if au.get('sec_uid') and not sec_uid:
                    sec_uid = au['sec_uid']
                print(f"      - {(au.get('nickname') or '?')[:16]} | sec_uid={(au.get('sec_uid') or '')[:24]}..")
        except Exception:
            print(f'    非 JSON: {(r.text or "")[:200]}')
    except Exception as exc:
        print(f'    !! {exc}')

    print(f'\n[3] aweme/post 投稿列表（sec_uid={sec_uid[:24] if sec_uid else "无，用占位"}...）')
    test_uid = sec_uid or 'MS4wLjABAAAA_test_invalid_uid'
    try:
        p = dict(BASE_COMMON)
        p.update({
            'sec_user_id': test_uid,
            'max_cursor': '0',
            'locate_query': 'false',
            'show_live_replay_strategy': '1',
            'need_time_list': '1',
            'time_list_query': '0',
            'whale_cut_token': '',
            'cut_version': '1',
            'count': '18',
            'publish_video_strategy_type': '2',
        })
        qs = build_qs(p)
        p['a_bogus'] = a_bogus_sign(qs, UA)
        r = s.get('https://www.douyin.com/aweme/v1/web/aweme/post/', params=p, timeout=20)
        print(f'    HTTP {r.status_code}  len={len(r.content)}')
        try:
            j = r.json()
            print(f"    status_code={j.get('status_code')}  "
                  f"status_msg={j.get('status_msg')}  has_more={j.get('has_more')}")
            lst = j.get('aweme_list') or []
            print(f'    返回 {len(lst)} 条视频')
            for a in lst[:5]:
                print(f"      - {a.get('aweme_id')} | {a.get('create_time')} | "
                      f"{(a.get('desc') or '')[:40]}")
        except Exception:
            print(f'    非 JSON: {(r.text or "")[:300]}')
    except Exception as exc:
        print(f'    !! {exc}')


if __name__ == '__main__':
    main()
