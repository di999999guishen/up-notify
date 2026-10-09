# 接口摸底结论（2026-10-10 实测）

本目录是一次性的探测脚本，**不参与运行**，只用于在平台风控变化时重新摸底。
下面记录的是结论 + 复现手法，改 `monitor/*.py` 前先读这里。

环境：Windows，纯 `requests`（无浏览器指纹注入、无第三方签名库），出口 IP 为中国大陆家宽。

---

## 一、B站：投稿列表

### 结论（可用）

| 项 | 值 |
|---|---|
| 接口 | `GET https://app.bilibili.com/x/v2/space/archive/cursor` |
| 鉴权 | **公开 appkey + md5 签名，无需 Cookie** |
| 实测 | 任意 uid 稳定 `code:0`；影视飓风(946974) `count=936`，单次拿 10–30 条 |
| 脚本 | `bili_probe5.py`（突破点）、`verify.py`（最终确认） |

签名算法（`monitor/bilibili.py::app_sign`）：

```
q = urllib.parse.urlencode(sorted(params.items()))
sign = md5(q + APPSEC).hexdigest()
```

参数集：`appkey / vmid / ps / pn / order=pubdate / ts` + `sign`。
公开凭证（B站 Android 客户端长期公开的一组，非私密）：

```
APPKEY = 1d8b6e7d45233436
APPSEC = 560c52ccd288fed045859ed18bffd973
```

返回字段实测确认：`title / bvid / param(=aid) / cover / ctime / duration / play / danmaku / tname / author`。

### 走过的死路（别再试）

| 路线 | 结果 |
|---|---|
| web 端 `api.bilibili.com/x/space/wbi/arc/search`（带 wbi 签名） | `-352 风控校验失败`，返回 `v_voucher` 人机验证 |
| 同上，补 `buvid3 / buvid4 / b_lsid / dm_img_*` 全套指纹 | 仍然 `-352`，或直接 `-412 request was banned` |
| 带 `SESSDATA`/`bili_jct` 登录态 Cookie | 不改善，风控判据是 IP/设备而非登录态 |
| `space.bilibili.com/<uid>` 主页 HTML | 无内嵌 SSR 投稿数据，且首屏被风控页替换 |

判定：web 端是 **IP 级**风控，纯 HTTP 客户端无解。App 端接口风控策略明显宽于 web 端，**这是当前唯一稳定链路**。
（脚本 `bili_probe.py` ~ `bili_probe4.py` 是这条死路的逐步记录。）

---

## 二、抖音：投稿列表（未打通）

### 现状：`403 Blocked by ArgusSecurityPlugin Uifid Not Found`

| 路线 | 结果 |
|---|---|
| `www.douyin.com/aweme/v1/web/aweme/post/` | **无论如何都 403**，见下方对照实验 |
| 移动端 `aweme.snssdk.com/aweme/v1/aweme/post/` | HTTP 200、`status_code:0`，但 `aweme_list` **恒为空**（该接口要 X-Gorgon 签名） |
| 用户主页 `www.douyin.com/user/<sec_uid>` HTML | 6421 字节 **JS 挑战页**，`RENDER_DATA` / `_ROUTER_DATA` 计数均为 0，无内嵌 `aweme_id` |
| `iesdouyin.com` 分享页 | 同样无内嵌数据 |
| 移动端搜索 `general/search/` | 响应 `len=0`，JSON 解析失败 |

#### 对照实验（`douyin_probe9.py`）—— 证明与签名无关

固定同一 sec_uid，逐项切换变量，**全部**返回 `403 Blocked by ArgusSecurityPlugin Uifid Not Found`：

- ✅ 带正确 a_bogus ／ ❌ 不带 a_bogus
- ✅ 带 msToken ／ ❌ 不带 msToken
- ✅ 全量浏览器参数（30+ 字段）／ ❌ 最小参数（3 字段）
- 换 UA、换 Referer、加 `Sec-Fetch-*` 全套

结论：**该接口的准入闸门是「会话里有没有浏览器执行 JS 生成的有效 Uifid」，与签名是否正确无关。**
`www.douyin.com` 首次访问只下发 `__ac_nonce`，**不下发 UIFID**（`douyin_probe5.py`）；
`live.douyin.com` 下发的 `UIFID_TEMP` 也不是接口认的那个 Uifid。

### 可用的降级链路（已落地）

| 项 | 值 |
|---|---|
| 接口 | `GET https://www.douyin.com/aweme/v1/web/user/profile/other/` |
| 条件 | 用**直播域 cookie**（`ttwid` + `UIFID_TEMP` + `UIFID`），无需登录 |
| 实测 | 连续 3 次稳定 `HTTP 200`，约 26826 字节，`status_code=0` |
| 拿到 | `nickname / sec_uid / unique_id / signature / aweme_count / dongtai_count / follower_count / following_count / total_favorited` |
| 脚本 | `douyin_probe8.py`、`verify.py` |

→ 因此 `up-notify` 的抖音侧默认走 **`profile` 模式（计数监测）**：比对 `aweme_count` 增量判定「发了新作品」，
能推通知 + 主页链接，但**拿不到标题**。

### 备注：反查 sec_uid

`douyin_probe4.py` 里用 live-recorder 的 `LiveWatcher` 打直播 `webcast/room/web/enter/`
拿到了真实 `sec_uid`——**这是绕开抖音主页反查的最省事办法**（主页反查同样被 Uifid 闸门挡住）。

### 备注：偶发空响应

`douyin_probe8.py` 曾出现同一 session 连续调用第 2、3 次返回 `len=0`；`verify.py` 用**全新 session**
复测 3 次均稳定。判定为会话级偶发频控，正式代码里已用 `DouyinUpError` 兜住并让上层回退。

---

## 三、如果以后要打通抖音完整投稿列表

按代价从低到高：

1. **人工提供浏览器登录态 Cookie**（已实现）：登录抖音网页版，F12 复制整条 Cookie 串写入 `.env` 的
   `DOUYIN_COOKIE`，配置 `"mode": "full"` 即走 web 投稿接口。缺点是 Cookie 会过期。
2. **无头浏览器驱动**：用 Playwright/CDP 让真浏览器跑一遍 JS 拿到 Uifid 与签名，再交给 `requests`。
   本机 Python 侧无 playwright（node 侧有 `ms-playwright/chromium-1232`，系统有 Chrome/Edge），
   属于「为抖音引一个重量级依赖」，暂缓。
3. **X-Gorgon 逆向**（移动端链路）：成本最高，不建议。

---

## 四、探测脚本索引

| 脚本 | 用途 |
|---|---|
| `bili_probe.py` ~ `bili_probe4.py` | B站 web 端 wbi/指纹路线的失败过程 |
| `bili_probe5.py` | **B站 App 端接口突破** |
| `douyin_probe.py` ~ `douyin_probe3.py` | 抖音接口/主页/搜索的初步摸底 |
| `douyin_probe4.py` | 用 `LiveWatcher` 取真实 sec_uid |
| `douyin_probe5.py` | www 首页 Cookie 下发情况（只有 `__ac_nonce`） |
| `douyin_probe6.py` | 主页 HTML / iesdouyin 分享页有无内嵌数据 |
| `douyin_probe7.py` | www 域 profile 接口的 Cookie 回填情况 |
| `douyin_probe8.py` | 抖音 profile 可用性 + `aweme_count=0` 确认 |
| `douyin_probe9.py` | **对照实验：证明 403 与签名无关** |
| `verify.py` | 最终确认（B站两 uid `code:0` + 抖音 profile 稳定） |
