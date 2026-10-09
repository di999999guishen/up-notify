"""
up-notify 请求配置。

集中管理各平台的 UA、公共头、公开凭证常量。
平台风控策略会变，改动优先收敛到本文件与各 monitor 模块。
"""
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / '.env')
except Exception:
    pass

BASE_DIR = Path(__file__).resolve().parent.parent
STATE_DIR = BASE_DIR / 'state'
LOG_DIR = BASE_DIR / 'logs'
for _d in (STATE_DIR, LOG_DIR):
    _d.mkdir(exist_ok=True)

# ------------------------------------------------------------------ 通用
WEB_UA = os.getenv(
    'WEB_UA',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
)

# ------------------------------------------------------------ B站（App 端）
# 走 App 端接口，风控策略明显宽于 web 端（web 端 space/wbi/arc/search 实测
# 被 IP 级风控拦截：-352 风控校验失败 / -412 request was banned）。
# 下列 appkey/appsec 是 B站 Android 客户端长期公开的一组，非私密凭证。
BILI_APP_HOST = 'https://app.bilibili.com'
BILI_APPKEY = os.getenv('BILI_APPKEY', '1d8b6e7d45233436')
BILI_APPSEC = os.getenv('BILI_APPSEC', '560c52ccd288fed045859ed18bffd973')
BILI_APP_UA = ('Mozilla/5.0 BiliDroid/7.63.0 (bbcallen@gmail.com) '
               'os/android model/Pixel5 mobi/android')

# ------------------------------------------------------------ 抖音
DOUYIN_LIVE_HOST = os.getenv('DOUYIN_LIVE_HOST', 'https://live.douyin.com')
DOUYIN_WWW_HOST = os.getenv('DOUYIN_WWW_HOST', 'https://www.douyin.com')

# 从 .env 注入。留空则自动到 live.douyin.com 取临时 Cookie（可用但能力受限）。
# 若要用「完整投稿列表」模式，需要一份**浏览器登录态**的 Cookie
# （至少含 ttwid 与 UIFID），从浏览器开发者工具复制整条 Cookie 串即可。
DOUYIN_COOKIE = os.getenv('DOUYIN_COOKIE', '')

DOUYIN_WEB_HEADERS = {
    'User-Agent': WEB_UA,
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'zh-CN,zh;q=0.9',
    'Referer': DOUYIN_WWW_HOST + '/',
    'Sec-Fetch-Dest': 'empty',
    'Sec-Fetch-Mode': 'cors',
    'Sec-Fetch-Site': 'same-origin',
}

DOUYIN_MOBILE_UA = ('com.ss.android.ugc.aweme/110101 (Linux; U; Android 11; zh_CN; '
                    'Pixel 5; Build/RQ3A.211001.001)')


def build_query(params: dict) -> str:
    """按插入顺序拼 query string（a_bogus 签名要求与请求参数顺序一致）。"""
    import urllib.parse
    return '&'.join(f'{k}={urllib.parse.quote(str(v))}' for k, v in params.items())
