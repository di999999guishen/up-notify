# up-notify · 抖音 / B站 UP 主新作品推送

盯住指定 UP 主，一有新作品就通知你。抖音、B站双平台，零依赖（只有 `requests`）。

与姊妹项目 [live-recorder](https://github.com/di999999guishen/live-recorder) 的分工：

| 项目 | 盯什么 | 产物 |
|---|---|---|
| **up-notify**（本项目） | UP 主的**新作品** | 通知（邮件 / outbox 队列） |
| live-recorder | 主播的**直播内容** | 录音 + 转写 + 总结 md |

两者共用 `notifier` 的双后端设计（SMTP 直发 / outbox 队列解耦），可以接到同一个发信环节上。

---

## 能力一览

| 平台 | 能力 | 状态 |
|---|---|---|
| **B站** | 投稿列表（标题 / 链接 / 时长 / 播放 / 分区），**免 Cookie** | ✅ 稳定 |
| **抖音** | 「作品数变化」监测（能推通知 + 主页链接，拿到不标题） | ✅ 可用 |
| **抖音** | 完整投稿列表（含标题） | ⚠️ 需**浏览器登录态 Cookie** |

> 抖音为什么这么憋屈：其 web 投稿接口的准入门槛是「会话里有没有浏览器执行 JS 生成的有效 Uifid」，
> 纯 `requests` 无论如何签名都是 `403 Blocked by ArgusSecurityPlugin Uifid Not Found`。
> 完整的对照实验与绕过思路见 [`_probe/FINDINGS.md`](_probe/FINDINGS.md)。

---

## 快速开始

```bash
pip install -r requirements.txt

cp ups.example.json ups.json      # 填要监控的 UP 主
cp .env.example .env              # 可选：配通知、配抖音 Cookie（.env 可以不建）

python up_notify.py --whois https://space.bilibili.com/946974   # 反查，产出配置片段
python up_notify.py --check       # 自检：只打印，不写状态、不推送
python up_notify.py --init        # 建基线（把现有作品记为已见，不推送历史存量）
python up_notify.py               # 单次检查并推送
python up_notify.py --interval 600 --run-for 21600   # 值守 6 小时，每 10 分钟一轮
```

**第一次务必先 `--init`**，否则第一次正式跑会把该 UP 的全部历史作品当成新作品轰一遍。

---

## 命令速查

| 命令 | 作用 | 退出码 |
|---|---|---|
| `up_notify.py` | 单次检查并推送 | 0 |
| `up_notify.py --check` | 自检，不写状态不推送 | 0 |
| `up_notify.py --init` | 建基线，只记不推 | 0 |
| `up_notify.py --interval 600` | 值守，每 600 秒一轮 | 0 |
| `up_notify.py --interval 600 --run-for 21600` | 值守并在 6 小时后自动退出 | 0 |
| `up_notify.py --platform bilibili` | 只处理指定平台 | 0 |
| `up_notify.py --stats` | 打印状态库 | 0 |
| `up_notify.py --outbox` | 列出待发送通知 | 0 |
| `up_notify.py --whois <链接>` | 反查 UP 主 → 配置片段 | 0/1/2 |

退出码约定：

| 码 | 含义 |
|---|---|
| 0 | 正常 |
| 1 | 配置里没有可用 UP 主（干净失败，不空转） |
| 2 | 配置/参数错误 |
| 3 | 已有实例在跑（单实例锁被占用） |

> `--interval` / `--run-for` 都**不传**时是单次检查。配置里的 `poll_interval` 只是值守时长的默认值，
> 不会把普通调用拖进守护循环。

---

## 配置

### `ups.json`（复制自 `ups.example.json`）

```jsonc
{
  "poll_interval": 600,          // 值守默认间隔（仅 --interval 未指定时生效）
  "notify_on_first_run": false,  // true = 首次也推送历史存量（默认 false）
  "ups": [
    {
      "platform": "bilibili",
      "uid": "946974",           // space.bilibili.com/<uid> 里的数字
      "name": "影视飓风",         // 仅用于通知标题；留空则自动取昵称
      "enabled": true,
      "limit": 20                // 每轮拉多少条（够覆盖两次检查间的更新即可）
    },
    {
      "platform": "douyin",
      "sec_uid": "MS4wLjABAAAA…", // douyin.com/user/<sec_uid> 里的那串
      "name": "示例抖音UP主",
      "mode": "profile",         // profile = 计数监测（零配置）
                                 // full    = 完整列表（需 .env 配 DOUYIN_COOKIE）
      "enabled": true
    }
  ]
}
```

`enabled: false` 的条目会被跳过（留着不删，方便临时停用）。

### `.env`（复制自 `.env.example`，可留空）

| 变量 | 说明 |
|---|---|
| `DOUYIN_COOKIE` | 抖音**浏览器登录态** Cookie。不填则抖音只能走计数监测 |
| `WEB_UA` | 覆盖默认桌面 UA（一般不用改） |
| `BILI_APPKEY` / `BILI_APPSEC` | B站 App 端公开凭证，一般不用改 |
| `SMTP_HOST/PORT/USER/PASS/TO` | 配齐 `HOST+USER+PASS` 即走 SMTP 直发 |

**抖音 Cookie 怎么拿**：浏览器打开 `www.douyin.com` 并登录 → F12 → Network → 点任意请求 →
复制整条 Cookie 请求头（**至少含 `ttwid` 与 `UIFID`**）→ 粘进 `DOUYIN_COOKIE`。
缺 `UIFID` 时 `full` 模式会自动**回退**到计数监测，不会崩。

---

## 通知后端

`notifier.py` 两种后端，自动择一（与 live-recorder 同构）：

| 后端 | 触发条件 | 行为 |
|---|---|---|
| `smtp` | `.env` 配齐 `SMTP_HOST` + `SMTP_USER` + `SMTP_PASS` | 直接发邮件 |
| `outbox` | 上述未配齐（**默认**） | 落 `outbox/<ts>_<event>.json` 队列 |

事件类型：

| event | 中文名 | 触发场景 |
|---|---|---|
| `up_new_video` | UP主更新 | 拉到新视频/新作品 |
| `up_count_jump` | 作品数变化 | 抖音计数监测发现 `aweme_count` 增长 |
| `error` | 异常告警 | 拉取失败（网络/风控/接口变更） |

outbox 队列交给外部发信环节消费（读 → 发 → 删）。这样常驻轮询进程不必内嵌发信逻辑，
发信失败也不会拖住监控。查看队列：`python up_notify.py --outbox`。

---

## 增量判定与状态库

`state/seen.json` 记住「每个来源已见过的作品 id」（每个来源保留最近 200 条）：

- **首次见到某来源** → 把当前列表**全部记为已见**，不推送（避免历史存量轰炸）；
- 之后每轮 → 列表里出现未见过的 id 即为新作品，推送后写回；
- 抖音计数监测模式没有「id」可比，改为比对 `meta.aweme_count` 的**增量**。

状态文件损坏时不静默重置：备份成 `seen.json.corrupt.json` 后从空起步。

---

## 双平台技术要点

### B站：走 App 端接口（关键）

| 项 | 值 |
|---|---|
| 接口 | `https://app.bilibili.com/x/v2/space/archive/cursor` |
| 鉴权 | 公开 appkey + `md5(sorted_query + appsec)`，**无需 Cookie** |
| 实测 | 影视飓风 uid=946974 → `code:0`，投稿总数 936，单页最多 30 条 |

**不要**改回 web 端的 `api.bilibili.com/x/space/wbi/arc/search`：该接口是 **IP 级风控**，
即使 wbi 签名正确、即使补齐 `buvid3/buvid4/b_lsid/dm_img_*` 全套指纹、即使带登录态 Cookie，
仍然 `-352 风控校验失败` 或 `-412 request was banned`。死路过程记录在 `_probe/FINDINGS.md`。

### 抖音：计数监测为默认，完整列表需 Cookie

| 路线 | 结果 |
|---|---|
| `www.douyin.com/aweme/v1/web/aweme/post/`（投稿列表） | **403 Uifid Not Found**，与签名无关（对照实验见 FINDINGS） |
| `aweme.snssdk.com/aweme/v1/aweme/post/`（移动端） | `status_code:0` 但 `aweme_list` 恒空（需 X-Gorgon） |
| 用户主页 HTML | JS 挑战页，无内嵌 SSR 数据 |
| **`www.douyin.com/aweme/v1/web/user/profile/other/`** | ✅ 直播域 cookie 下稳定返回全量资料 → 计数监测的基石 |

抖音计数监测靠的是 `aweme_count` 字段的增量。**局限**：拿不到新作品的标题，
且若 UP 主删一条同时发一条，计数不变 → 漏报。对更新频率高的账号，建议配 Cookie 走 `full` 模式。

---

## 目录结构

```
up-notify/
├── up_notify.py            # 入口：自检 / 建基线 / 单次 / 值守 / 反查 / 状态
├── store.py                # SeenStore：增量状态（state/seen.json）
├── notifier.py             # 通知双后端：smtp / outbox
├── core/
│   ├── config.py           # UA、公开凭证、路径、build_query()
│   └── signing.py          # 抖音 a_bogus 纯 Python 实现（SM3+RC4+自定义 Base64）
├── monitor/
│   ├── bilibili.py         # B站 App 端投稿接口
│   └── douyin.py           # 抖音 profile / 投稿接口
├── _probe/                 # 一次性接口摸底脚本 + FINDINGS.md（不参与运行）
├── ups.example.json        # 配置模板
├── .env.example            # 环境变量模板
├── state/                  # 运行期：seen.json（gitignore）
├── logs/                   # 运行期：日志（gitignore）
├── outbox/                 # 运行期：待发通知队列（gitignore）
└── .lock/                  # 运行期：单实例锁（gitignore）
```

---

## 坑位清单（都踩过）

1. **B站 web 端投稿接口是 IP 级风控**，补指纹、补 Cookie 都无效 → 必须走 App 端。
2. **B站 App 签名 = `md5(urlencode(sorted(params)) + appsec)`**，`sorted()` 不能省，参数顺序或编码差一点就错。
3. **抖音 403 与签名无关**：a_bogus 全对也照 403，闸门是 Uifid。别在签名上浪费时间。
4. **`www.douyin.com` 首次访问只下发 `__ac_nonce`，不下发 UIFID**；`live.douyin.com` 的 `UIFID_TEMP` 也不是接口要的那个。
5. **抖音 profile 接口偶发空响应**：同一 session 连续调用可能第 2 次返回 `len=0`，换新 session 即恢复 → 代码里用 `DouyinUpError` 兜住并回退。
6. **`params` 字典顺序影响 a_bogus** → 用 `build_query()` 按插入顺序拼，别用 `requests` 的 `params=`。
7. **首次跑必须先 `--init`**，否则历史作品会被当成新作品全部推送。
8. **Windows 控制台 GBK**：中文/emoji 会抛 `UnicodeEncodeError` → 入口统一 `setup_stdio()` 转 UTF-8。
9. **单实例锁用 PID 存活判断**，不能只看 mtime 新鲜度：进程被强杀（SIGTERM）时锁文件会残留，
   只看 mtime 会让下次启动被白白阻塞一个间隔。Windows 上 `os.kill` 不能做存活探测，走 `OpenProcess`。
10. **`poll_interval` 不该触发守护模式**：只在显式传 `--interval/--run-for` 时才常驻，否则普通调用会被拖进死循环。
11. **`ups.json` 与 `.env` 必须 gitignore**，里面是真实监控对象与 Cookie。

---

## 已知限制

- **抖音拿不到新作品标题**（除配 Cookie 走 `full` 模式）：这是平台风控决定的，非实现缺陷。
- **抖音计数监测会漏报**「删一条 + 发一条」这类净增为 0 的更新。
- **B站接口无官方文档承诺**：App 端接口可能随时变更，变更时先跑 `_probe/bili_probe5.py` 复测。
- **值守需要外部托管**：常驻进程建议交给 Windows 计划任务 / systemd / cron，
  不要指望单次会话能挂住几小时（会话结束子进程会被清理）。

---

## License

MIT © 2026 di999999guishen
