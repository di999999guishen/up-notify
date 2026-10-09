#!/usr/bin/env python3
"""
up-notify —— 抖音 / B站 UP 主新作品推送。

用法速查：
    python up_notify.py --check                # 自检：打印各 UP 当前状态，不写状态、不推送
    python up_notify.py --init                 # 首次建基线（把现有作品记为已见，不推送）
    python up_notify.py                        # 单次检查并推送新作品
    python up_notify.py --interval 600         # 值守：每 600 秒轮询一次
    python up_notify.py --interval 600 --run-for 21600   # 值守 6 小时后自动退出
    python up_notify.py --platform bilibili    # 只查指定平台
    python up_notify.py --stats                # 打印状态库
    python up_notify.py --outbox               # 列出待发送通知
    python up_notify.py --whois <链接>          # 反查 UP 主，产出 ups.json 条目

退出码：
    0  正常
    1  配置无可用 UP 主（干净失败，不空转）
    2  配置/参数错误
    3  已有实例在跑（单实例锁被占用）
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

from core.config import DOUYIN_COOKIE, STATE_DIR          # noqa: E402
from monitor.bilibili import BiliUpMonitor, BiliUpError   # noqa: E402
from monitor.douyin import DouyinUpMonitor, DouyinUpError  # noqa: E402
from store import SeenStore                               # noqa: E402
import notifier                                           # noqa: E402

LOCK_FILE = BASE / '.lock' / 'up_notify.lock'


def setup_stdio() -> None:
    """Windows 控制台默认 GBK，中文/emoji 会抛 UnicodeEncodeError。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass


def log(msg: str) -> None:
    print(f'[{time.strftime("%H:%M:%S")}] {msg}', flush=True)


# ------------------------------------------------------------------ 单实例锁
def _pid_alive(pid: int) -> bool:
    """跨平台判断 PID 是否存活。Windows 的 os.kill 不能做探测，走 Win32 API。"""
    if pid <= 0:
        return False
    if os.name == 'nt':
        import ctypes
        k32 = ctypes.windll.kernel32
        h = k32.OpenProcess(0x1000, False, pid)      # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        try:
            code = ctypes.c_ulong()
            if k32.GetExitCodeProcess(h, ctypes.byref(code)):
                return code.value == 259             # STILL_ACTIVE
            return True
        finally:
            k32.CloseHandle(h)
    try:
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def acquire_lock(interval: int) -> bool:
    """锁文件存 PID + 时间戳；PID 存活才算占用，死进程留下的锁自动接管。

    只在 PID 查不出来（文件损坏）时兜底看 mtime 新鲜度。
    """
    LOCK_FILE.parent.mkdir(exist_ok=True)
    if LOCK_FILE.exists():
        pid = 0
        try:
            pid = int(LOCK_FILE.read_text(encoding='utf-8').splitlines()[0])
        except Exception:
            pid = 0
        if pid and _pid_alive(pid):
            return False
        if not pid:
            age = time.time() - LOCK_FILE.stat().st_mtime
            if age < max(interval * 2, 120):
                return False
        log(f'  [锁] 清理陈旧锁（PID {pid or "未知"} 已退出）')
    LOCK_FILE.write_text(f'{os.getpid()}\n{time.strftime("%Y-%m-%d %H:%M:%S")}',
                         encoding='utf-8')
    return True


def touch_lock() -> None:
    try:
        LOCK_FILE.touch()
    except Exception:
        pass


def release_lock() -> None:
    try:
        LOCK_FILE.unlink(missing_ok=True)
    except Exception:
        pass


# ------------------------------------------------------------------ 配置
def load_config(path: Path) -> dict:
    if not path.exists():
        raise SystemExit(f'[错误] 找不到配置文件 {path}\n'
                         f'       可从 ups.example.json 复制一份改成 ups.json')
    try:
        cfg = json.loads(path.read_text(encoding='utf-8'))
    except Exception as exc:
        raise SystemExit(f'[错误] 配置文件解析失败: {exc}')
    cfg.setdefault('ups', [])
    cfg.setdefault('poll_interval', 600)
    cfg.setdefault('notify_on_first_run', False)
    return cfg


def enabled_ups(cfg: dict, platform: str = '') -> list:
    out = []
    for up in cfg.get('ups', []):
        if not up.get('enabled', True):
            continue
        if platform and up.get('platform') != platform:
            continue
        out.append(up)
    return out


# ------------------------------------------------------------------ 渲染
def fmt_duration(sec) -> str:
    try:
        sec = int(sec)
    except Exception:
        return ''
    if sec <= 0:
        return ''
    return f'{sec // 60}:{sec % 60:02d}'


def render_bili(name: str, videos: list) -> str:
    lines = [f'【{name}】发布了 {len(videos)} 个新视频', '']
    for i, v in enumerate(videos, 1):
        lines.append(f'{i}. {v["title"]}')
        lines.append(f'   {v["url"]}')
        meta = []
        if v.get('created'):
            meta.append(time.strftime('%m-%d %H:%M', time.localtime(v['created'])))
        if fmt_duration(v.get('duration')):
            meta.append(f'时长 {fmt_duration(v["duration"])}')
        if v.get('play'):
            meta.append(f'播放 {v["play"]:,}')
        if meta:
            lines.append('   ' + ' · '.join(meta))
        lines.append('')
    return '\n'.join(lines).rstrip()


def render_douyin(name: str, videos: list) -> str:
    lines = [f'【{name}】发布了 {len(videos)} 条新作品', '']
    for i, v in enumerate(videos, 1):
        lines.append(f'{i}. {v["title"] or "(无标题)"}')
        lines.append(f'   {v["url"]}')
        lines.append('')
    return '\n'.join(lines).rstrip()


def render_douyin_count(name: str, old: int, new: int, homepage: str) -> str:
    return (f'【{name}】作品数 {old} → {new}（+{new - old}）\n\n'
            f'主页：{homepage}\n\n'
            f'当前为「计数监测」模式（抖音投稿列表需要浏览器登录态 Cookie）。\n'
            f'如需直接拿到视频标题，请在 .env 配置 DOUYIN_COOKIE。')


# ------------------------------------------------------------------ 检查逻辑
def check_bilibili(up: dict, store: SeenStore, dry: bool, init: bool) -> int:
    uid = str(up.get('uid') or '').strip()
    name = up.get('name') or f'B站 uid={uid}'
    if not uid:
        log(f'  [跳过] {name}: 缺 uid')
        return 0
    limit = int(up.get('limit', 20))
    mon = BiliUpMonitor()
    try:
        videos = mon.list_videos(uid, limit=limit)
    except BiliUpError as exc:
        log(f'  [失败] {name}: {exc}')
        notifier.notify('error', f'{name} 拉取失败：{exc}', title=name)
        return -1

    vids = [v['id'] for v in videos]
    has_base = store.known('bilibili', uid)

    if dry:
        if has_base:
            fresh = [v for v in videos if store.is_new('bilibili', uid, v['id'])]
            log(f'  [自检] {name}: 共 {len(videos)} 条，其中 {len(fresh)} 条未见过'
                + (f' → 最新 {fresh[0]["title"][:30]}' if fresh else ''))
        else:
            log(f'  [自检] {name}: 共 {len(videos)} 条（尚无基线，正式跑会全部记为已见）')
        return 0

    if not has_base:
        store.mark('bilibili', uid, vids, meta={'name': name, 'uid': uid})
        log(f'  [建基线] {name}: 记录 {len(vids)} 条（不推送历史存量）')
        return 0

    fresh = [v for v in videos if store.is_new('bilibili', uid, v['id'])]
    if fresh:
        body = render_bili(name, fresh)
        backend = notifier.notify('up_new_video', body, title=name)
        log(f'  [推送] {name}: {len(fresh)} 条新视频 → {backend}')
    else:
        log(f'  [无新] {name}')
    store.mark('bilibili', uid, vids, meta={'name': name, 'uid': uid})
    return len(fresh)


def _douyin_full(up: dict, store: SeenStore, dry: bool, name: str,
                 ident: str, videos: list) -> int:
    """抖音完整投稿列表模式（需登录态 Cookie）。逻辑与 B站分支同构。"""
    vids = [v['id'] for v in videos]
    has_base = store.known('douyin', ident)

    if dry:
        if has_base:
            fresh = [v for v in videos if store.is_new('douyin', ident, v['id'])]
            log(f'  [自检] {name}: 共 {len(videos)} 条，其中 {len(fresh)} 条未见过'
                + (f' → 最新 {fresh[0]["title"][:30]}' if fresh else ''))
        else:
            log(f'  [自检] {name}: 共 {len(videos)} 条（尚无基线，正式跑会全部记为已见）')
        return 0

    if not has_base:
        store.mark('douyin', ident, vids, meta={'name': name, 'mode': 'full'})
        log(f'  [建基线] {name}: 记录 {len(vids)} 条（不推送历史存量）')
        return 0

    fresh = [v for v in videos if store.is_new('douyin', ident, v['id'])]
    if fresh:
        backend = notifier.notify('up_new_video', render_douyin(name, fresh), title=name)
        log(f'  [推送] {name}: {len(fresh)} 条新作品 → {backend}')
    else:
        log(f'  [无新] {name}')
    store.mark('douyin', ident, vids, meta={'name': name, 'mode': 'full'})
    return len(fresh)


def check_douyin(up: dict, store: SeenStore, dry: bool, init: bool) -> int:
    sec = str(up.get('sec_uid') or up.get('id') or '').strip()
    name = up.get('name') or f'抖音 sec_uid={sec[:16]}…'
    mode = up.get('mode') or 'profile'
    if not sec:
        log(f'  [跳过] {name}: 缺 sec_uid')
        return 0

    mon = DouyinUpMonitor(cookie=DOUYIN_COOKIE)
    ident = sec

    # ---- 完整投稿列表模式（需登录态 Cookie）
    if mode == 'full':
        if not mon.has_login_cookie:
            log(f'  [提示] {name}: 配置为 full 模式但无登录态 Cookie，回退计数监测')
        else:
            try:
                videos = mon.list_videos(sec, limit=int(up.get('limit', 18)))
            except DouyinUpError as exc:
                log(f'  [回退计数] {name}: {exc}')
            else:
                return _douyin_full(up, store, dry, name, ident, videos)

    # ---- 计数监测模式（零配置）
    try:
        prof = mon.profile(sec)
    except DouyinUpError as exc:
        log(f'  [失败] {name}: {exc}')
        notifier.notify('error', f'{name} 拉取失败：{exc}', title=name)
        return -1

    cur = prof['aweme_count']
    e = store.entry('douyin', ident)
    prev = (e.get('meta') or {}).get('aweme_count')
    if dry:
        nick = prof['nickname'] or name
        log(f'  [自检] {name}: 昵称={nick} 作品数={cur} '
            f'粉丝={prof["follower_count"]:,} 已记录={prev}')
        return 0
    if not store.known('douyin', ident):
        store.mark('douyin', ident, [], meta={'name': prof['nickname'] or name,
                                              'aweme_count': cur, 'mode': 'profile'})
        log(f'  [建基线] {name}: 作品数={cur}（不推送历史存量）')
        return 0
    if prev is not None and cur > prev:
        backend = notifier.notify('up_count_jump',
                                  render_douyin_count(prof['nickname'] or name, prev, cur,
                                                      prof['homepage']),
                                  title=prof['nickname'] or name)
        log(f'  [推送] {name}: 作品数 {prev} → {cur} → {backend}')
        delta = cur - prev
    else:
        log(f'  [无新] {name}: 作品数={cur}')
        delta = 0
    store.mark('douyin', ident, [], meta={'name': prof['nickname'] or name,
                                          'aweme_count': cur, 'mode': 'profile'})
    return delta


def run_round(cfg: dict, store: SeenStore, platform: str = '',
              dry: bool = False, init: bool = False) -> int:
    total = 0
    ups = enabled_ups(cfg, platform)
    for up in ups:
        plat = up.get('platform')
        if plat == 'bilibili':
            total += max(check_bilibili(up, store, dry, init), 0)
        elif plat == 'douyin':
            total += max(check_douyin(up, store, dry, init), 0)
        else:
            log(f'  [跳过] 未知平台: {plat}')
    if not dry:
        store.save()
    return total


# ------------------------------------------------------------------ 反查
def cmd_whois(text: str) -> int:
    """给链接或 ID，打印出可粘进 ups.json 的条目。"""
    from monitor.bilibili import parse_uid
    from monitor.douyin import parse_sec_uid

    uid = parse_uid(text)
    if uid:
        mon = BiliUpMonitor()
        name = mon.user_name(uid)
        try:
            n = mon.total(uid)
        except BiliUpError:
            n = -1
        print(json.dumps({'platform': 'bilibili', 'uid': uid,
                          'name': name or f'B站 uid={uid}',
                          'enabled': True, 'limit': 20},
                         ensure_ascii=False, indent=2))
        print(f'\n# B站 uid={uid} 昵称={name or "（取不到）"} 投稿数={n}', file=sys.stderr)
        return 0

    sec = parse_sec_uid(text)
    if sec:
        mon = DouyinUpMonitor(cookie=DOUYIN_COOKIE)
        try:
            prof = mon.profile(sec)
        except DouyinUpError as exc:
            print(f'[错误] 抖音资料拉取失败：{exc}', file=sys.stderr)
            return 1
        print(json.dumps({'platform': 'douyin', 'sec_uid': sec,
                          'name': prof['nickname'] or '抖音UP主',
                          'mode': 'profile', 'enabled': True},
                         ensure_ascii=False, indent=2))
        print(f'\n# 抖音 {prof["nickname"]} 作品数={prof["aweme_count"]} '
              f'粉丝={prof["follower_count"]:,}', file=sys.stderr)
        return 0

    print(f'[错误] 认不出这是哪个平台：{text}\n'
          f'        B站示例：https://space.bilibili.com/946974\n'
          f'        抖音示例：https://www.douyin.com/user/MS4wLjABAAAA…',
          file=sys.stderr)
    return 2


# ------------------------------------------------------------------ 入口
def main() -> int:
    setup_stdio()
    ap = argparse.ArgumentParser(description='抖音/B站 UP 主新作品推送',
                                 formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog=__doc__)
    ap.add_argument('--config', default=str(BASE / 'ups.json'), help='UP 主配置（默认 ups.json）')
    ap.add_argument('--interval', type=int, default=0, help='轮询间隔秒；>0 则常驻值守')
    ap.add_argument('--run-for', type=int, default=0, help='值守总时长秒，到时退出')
    ap.add_argument('--platform', default='', help='只处理指定平台 bilibili/douyin')
    ap.add_argument('--check', action='store_true', help='自检：只看不写状态、不推送')
    ap.add_argument('--init', action='store_true', help='只建基线，不推送')
    ap.add_argument('--stats', action='store_true', help='打印状态库')
    ap.add_argument('--outbox', action='store_true', help='列出待发送通知')
    ap.add_argument('--whois', metavar='链接或ID',
                    help='反查 UP 主，直接产出可粘进 ups.json 的条目')
    args = ap.parse_args()

    if args.whois:
        return cmd_whois(args.whois)

    store = SeenStore()

    if args.stats:
        print('状态库:' if store.path.exists() else '状态库（空）:')
        print(store.stats())
        return 0
    if args.outbox:
        items = notifier.pending()
        print(f'待发送 {len(items)} 条')
        for p in items:
            print(f'  {p.name}')
        return 0

    cfg = load_config(Path(args.config))
    ups = enabled_ups(cfg, args.platform)
    if not ups:
        log('配置里没有可用的 UP 主（enabled=false 或列表为空），退出。')
        return 1

    if args.check:
        log(f'自检模式：{len(ups)} 个 UP 主')
        run_round(cfg, store, args.platform, dry=True)
        return 0

    if args.init:
        log(f'建基线模式：{len(ups)} 个 UP 主')
        run_round(cfg, store, args.platform, init=True)
        log('基线已建立。')
        return 0

    # 只有显式给 --interval / --run-for 才进值守；否则单次检查后退出。
    # （不加这层判断的话，配置里的 poll_interval 会把普通调用拖进守护循环）
    if args.interval <= 0 and args.run_for <= 0:
        log(f'单次检查：{len(ups)} 个 UP 主')
        n = run_round(cfg, store, args.platform)
        log(f'本轮发现 {n} 条新作品。')
        return 0

    interval = args.interval or int(cfg.get('poll_interval') or 600)

    # ---- 值守模式
    if not acquire_lock(interval):
        log('已有实例在运行（单实例锁被占用），退出。')
        return 3
    deadline = time.time() + args.run_for if args.run_for else 0
    log(f'值守启动：{len(ups)} 个 UP 主，间隔 {interval}s'
        + (f'，运行 {args.run_for}s' if args.run_for else ''))
    try:
        while True:
            t0 = time.time()
            n = run_round(cfg, store, args.platform)
            touch_lock()
            log(f'本轮发现 {n} 条新作品。')
            if deadline and time.time() >= deadline:
                log('已到运行时长上限，退出。')
                break
            time.sleep(max(interval - (time.time() - t0), 5))
    except KeyboardInterrupt:
        log('收到中断，退出。')
    finally:
        release_lock()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
