"""
通知模块：UP 主新作品提醒 / 异常告警。

两种后端（与 live-recorder 同构，便于统一处理）：
    smtp   —— 配好 SMTP_* 直接发邮件（QQ/163/Gmail 等）
    outbox —— 默认，写到 outbox/*.json 队列，由外部发信环节读取后发送

常驻轮询进程不适合内嵌发信逻辑，所以默认走 outbox 队列解耦：
up_notify 落盘 → 外部发信环节读取 → 发出后删除队列文件。
"""
import json
import os
import smtplib
import time
from email.header import Header
from email.mime.text import MIMEText
from pathlib import Path

BASE = Path(__file__).resolve().parent
OUTBOX = BASE / 'outbox'

EVENT_CN = {
    'up_new_video': 'UP主更新',
    'up_count_jump': '作品数变化',
    'error': '异常告警',
}

_CN_WEEK = ['一', '二', '三', '四', '五', '六', '日']


def _smtp_cfg() -> dict:
    return {
        'host': os.getenv('SMTP_HOST', ''),
        'port': int(os.getenv('SMTP_PORT', '465')),
        'user': os.getenv('SMTP_USER', ''),
        'password': os.getenv('SMTP_PASS', ''),
        'to': os.getenv('SMTP_TO', '') or os.getenv('SMTP_USER', ''),
    }


def _send_smtp(subject: str, body: str) -> bool:
    cfg = _smtp_cfg()
    if not (cfg['host'] and cfg['user'] and cfg['password']):
        return False
    msg = MIMEText(body, 'plain', 'utf-8')
    msg['Subject'] = Header(subject, 'utf-8')
    msg['From'] = cfg['user']
    msg['To'] = cfg['to']
    try:
        if cfg['port'] == 465:
            server = smtplib.SMTP_SSL(cfg['host'], cfg['port'], timeout=20)
        else:
            server = smtplib.SMTP(cfg['host'], cfg['port'], timeout=20)
            server.starttls()
        with server:
            server.login(cfg['user'], cfg['password'])
            server.sendmail(cfg['user'], [cfg['to']], msg.as_string())
        return True
    except Exception:
        return False


def _write_outbox(event: str, subject: str, body: str) -> Path:
    OUTBOX.mkdir(exist_ok=True)
    payload = {'ts': time.strftime('%Y-%m-%d %H:%M:%S'), 'event': event,
               'subject': subject, 'body': body}
    path = OUTBOX / f'{int(time.time())}_{event}.json'
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    return path


def notify(event: str, text: str, title: str = '') -> str:
    """发送通知，返回实际使用的后端名（smtp / outbox）。"""
    cn = EVENT_CN.get(event, event)
    subject = f'[UP更新] {cn}' + (f' - {title}' if title else '')
    if _send_smtp(subject, text):
        return 'smtp'
    _write_outbox(event, subject, text)
    return 'outbox'


def pending() -> list:
    if not OUTBOX.exists():
        return []
    return sorted(OUTBOX.glob('*.json'))


def clear(path) -> None:
    try:
        Path(path).unlink(missing_ok=True)
    except Exception:
        pass


if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == 'list':
        items = pending()
        print(f'待发送 {len(items)} 条')
        for p in items:
            data = json.loads(p.read_text(encoding='utf-8'))
            print(f"  [{data.get('ts', '?')}] {data.get('subject', '')}")
    else:
        print(__doc__)
