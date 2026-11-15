# 蓝色大肥鱼 · 可插拔链路（dafeiyu-chain）

养一条**会说话、会发语音、会发截图、会刷 B 站、会读简介/热评并总结、会攒评论草稿**的电子大肥鱼。
图片来自 **HTML 渲染截图**（不是生图），QQ 侧走 **AstrBot + QQ 官方机器人 WebSocket**，
评论默认**只出草稿、绝不真发**。

> 仓库：[github.com/loveu521/dafeiyu-chain](https://github.com/loveu521/dafeiyu-chain) · MIT License

| 阶段 | 目标 | 状态 |
|---|---|---|
| ① 本地跑通 | 无需 QQ 账号，Mock 网关等价官机收件箱，全链路真实产出 | ✅ 已完成 |
| ② 落实服务器 | Debian 12 部署 AstrBot 4.29.4 + 插件常驻 + 定时任务 + 看门狗 | ✅ 已部署并验收到消息组件层 |
| ②-b 扫码授权 | QQ 官机已连通，实机收发消息 | ✅ 已连通 |
| ②-c 现刷修复 v0.3.0 | 每次真换一批 / 听懂关键词 / 语音截图动态化 / 消息链一次发全 | ✅ 已实机验收 |
| ②-d 读片总结 v0.4.0 | 读标题/简介/热门评论 → LLM 或本地摘要 → 文本+读片卡片+语音 | ✅ 已实机验收 |
| ③ 开源到 GitHub | fork 后按开关复制任意子链路 | ✅ 已推送 |

---

## 链路长什么样

```
                    ┌─────────────────────────────────────────┐
   QQ 消息 ───────▶ │  AstrBot 4.x (qq_official / WebSocket)   │
                    │  · WebUI 扫码一键创建，自动填 AppID      │
                    │  · msg_type=0 文本 / =7 富媒体           │
                    └───────────────┬─────────────────────────┘
                                    │ MessageChain 组件
        ┌───────────┬───────────┼───────────┬───────────┬──────────┐
        ▼           ▼           ▼           ▼           ▼          ▼
   ┌────────┐ ┌────────┐ ┌──────────┐ ┌────────┐ ┌────────┐ ┌────────┐
   │ chat   │ │ voice  │ │screenshot│ │bilibili│ │ digest │ │comment │
   │人设/说话│ │edge-tts│ │Playwright│ │只读取数│ │读片总结│ │ 草稿   │
   │        │ │mp3+wav │ │HTML→PNG  │ │        │ │LLM/本地│ │ dry_run│
   └────────┘ └────────┘ └──────────┘ └────────┘ └────────┘ └────────┘
        └───────────┴───────────┴───────────┴───────────┴──────────┘
                                    │
          完整巡游：刷站 → 读片总结(简介/热评) → 读片卡片 → 语音 → 评论 → 收尾
```

**每段都是一个独立 Skill**，`config.yaml` 里一个 `enabled` 开关。关掉任意一段，
其余照常跑（已实测 7 种组合）。这就是「可复制可选链路」：想要哪几段就复制哪几段。

## 用到的开源项目

| 项目 | 用途 | 许可 |
|---|---|---|
| [AstrBot](https://github.com/AstrBotDevs/AstrBot) | QQ 官机对接 / 插件框架 / 消息链 | AGPL-3.0 |
| [edge-tts](https://github.com/rany2/edge-tts) | 语音合成，免 API Key | GPL-3.0 |
| [bilibili-api-python](https://github.com/Nemo2011/bilibili-api) | B 站取数 / 可选发评论 | GPL-3.0 |
| [Playwright](https://github.com/microsoft/playwright) | HTML/网页渲染截图 | Apache-2.0 |
| [bilibili-API-collect](https://github.com/SocialSisterYi/bilibili-API-collect) | B 站接口字段对照 | CC-BY-NC-SA |
| 渲染思路参考 [HarukaBot](https://github.com/SK-415/HarukaBot) / [openclaw-onebot](https://github.com/LSTM-Kirigaya/openclaw-onebot) | 动态/HTML 转图 | — |

> 本仓库仅**编排调用**上述项目，未复制其源码；各项目许可与版权归原作者所有。
> 本仓库自身代码采用 MIT，但若二次分发组合后的整体，请自行核对上游许可
> （尤其 AGPL/GPL 的传染性约束）。

---

## 阶段一：本地跑通

```bash
pip install -r requirements.txt
playwright install chromium          # 或系统已装 chromium，设 DFY_CHROMIUM
python3.11 run_local.py
```

不需要 AppID / Secret / 域名 / B 站登录凭证。`MockGateway` 把消息按 QQ 官机字段
（`msg_type`、`file_type`、`file_info`）写入 `output/inbox.jsonl`。

实测：6 段能力全 OK（含 `digest` 读片），收件箱 16 条（12 文本 / 2 语音 / 2 图片），
产物含真实 PNG 截图（巡游卡片 + 读片报告）、真实 MP3/WAV 语音、B 站实时热门数据、
`digest.json`（简介/热评/总结）、评论草稿。详见 `output/REPORT.md`。

---

## 阶段二：服务器部署（已在 Debian 12 实机跑通）

### 为什么不用 Docker

目标机是 **2 核 / 1.9G 内存 / 无 swap / 宝塔面板**（nginx 占 80、MySQL、OpenList）的 VPS。
`docker.io` 未安装且 `/usr/bin/compose` 只是 `run-mailcap` 的软链（假的）。Docker daemon 在
1.9G 机器上白吃 200–300MB，因此改用 **venv + systemd**，并加 2G swap 兜底。
**如果你的机器 >= 2核4G，完全可以用 Docker，把 `deploy/*.service` 换成容器编排即可。**

### 两套 venv（必须）

| 环境 | Python | 用途 |
|---|---|---|
| `/opt/dafeiyu/venv` | 系统 3.11 | 链路本体、`run_local.py`、定时巡游 |
| `/opt/dafeiyu/astrbot_venv` | uv 托管的 3.12.16 | AstrBot 4.29.4 + 插件运行时 |

> **AstrBot 4.x 的 `requires_python` 是 `>=3.12`**，Debian 12 自带 3.11 装不上。
> 用 `uv python install 3.12` 单独拉一份，不动系统 Python。

### 一键部署

```bash
sudo bash deploy/install_server.sh      # 幂等，含 swap / apt / 两套 venv / systemd / 验收
/opt/dafeiyu/deploy/verify.sh           # 随时复验
```

### 目录与服务

```
/opt/dafeiyu/
├── app/                       # 本仓库（代码只留一份）
│   ├── core/ skills/ config.yaml / run_local.py
│   ├── astrbot_plugin_dafeiyu/        ← 软链进 AstrBot 插件目录
│   └── deploy/                        ← 服务单元 + 脚本
├── venv/                      # Py3.11 链路
├── astrbot_venv/              # Py3.12 AstrBot
├── astrbot_data/data/         # AstrBot 配置、DB、插件目录
├── logs/                      # astrbot.log / cruise.log / watchdog.log
└── deploy -> app/deploy
```

| systemd 单元 | 作用 |
|---|---|
| `astrbot.service` | AstrBot 常驻，`Restart=always` + `MemoryMax=900M` |
| `dafeiyu-cruise.timer` | 每天 09:00 / 20:00 实跑巡游并归档产物 |
| `dafeiyu-watchdog.timer` | 每 5 分钟探 WebUI，不通则重启 AstrBot |

WebUI 默认 `6185`（已放行 ufw）。WebSocket 是**出站**连接，不需要额外入站端口、不需要域名/备案。

### 实机验收结果（2026-11-14）

| 验收项 | 结果 |
|---|---|
| 服务器 `run_local.py` 全链路 | 5/5 能力 OK，13 条消息，PNG/MP3/WAV 文件头有效 |
| 截图中文字体 | 文泉驿正黑，中文与 🐟 均正常渲染 |
| AstrBot 启动 | v4.29.4，WebUI `0.0.0.0:6185`，公网 HTTP 200 |
| 插件加载 | 日志 `Loading plugin astrbot_plugin_dafeiyu`，自动生成插件配置 |
| **插件发送路径（AstrBot 3.12 环境实跑）** | 13 段 → `Plain 9 / Record 2 / Image 2`，语音指向 wav、图片为 `file://` URI |
| 定时 / 自愈 | 手动触发巡游成功；看门狗实测「FAIL → 重启 → OK」 |
| 内存 | AstrBot RSS ~250MB，可用 ~1.0G，swap 2G 未动 |

### QQ 官机接入（实机已连通，步骤留作复现）

1. 浏览器打开 `http://<服务器IP>:6185`，用日志里的初始账号密码登录，**立刻改密码**。
2. `机器人 → + 创建机器人 → QQ 官方机器人(WebSocket) → 扫码一键创建`。
3. 手机 QQ 扫码确认，AstrBot **自动写入 AppID / AppSecret**，勾选「启用」并保存。
4. 手机 QQ → 联系人 → 机器人 → 「扫码聊天」即可对话；进群需在群设置里打开
   「机器人可获取群内全部消息」+「允许主动发言」。

> 走**扫码一键创建**不需要手动去 q.qq.com 申请、也不需要配 IP 白名单（那是手动申请路径才要）。
> 实机日志已确认 `qq_official` 适配器正常收发消息（用户消息能进、图/语音能出）。
> 自由聊天还需在 WebUI 配一个 LLM（DeepSeek 等）；`/巡游` 这类指令是 `filter.command` 拦截，**不依赖 LLM**。

### 指令 / 自然语言（两种都能触发）

| 指令（带 `/`） | 也可以直接说（不带 `/`） | 作用 |
|---|---|---|
| `/巡游` | 「刷个B站」「刷视频」「看看热门」「巡游」 | 现刷 → 读片总结 → 读片卡片 → 语音 → 评论草稿 → 收尾（一次发全） |
| `/鱼读片`（别名 `/鱼总结` `/鱼读评`） | 「读读评论」「看看简介」「这条讲了啥」「总结一下」「讲讲这条」「评论区在说啥」 | **读标题 + 简介 + 按赞排序的热门评论 → 总结输出**（文本 + 读片报告截图 + 语音） |
| `/鱼语音` | 「来段语音」「说句话」「发语音」 | 只发语音（念本批结论，wav 兼容 AstrBot） |
| `/鱼截图` | 「发张图」「来个截图」「发报告图」 | 只发 HTML 渲染截图（带时间/来源/批次） |
| `/鱼刷站` | 「刷b站」「刷视频」「看看热门」 | 只刷 B 站并回报 |
| `/鱼评论` | 「拟个评论」「写个留言」 | 只出评论草稿（默认不真发） |
| `/鱼开关 voice off` | — | 运行时插拔某个能力 |

**读片专用说法**（v0.4.0）：刷完一批后说「读读评论」「总结一下」→ 读刚才那批的第 1 条；
「读一下第2条」「读读第3条视频」→ 按序号读清单里那一条；带关键词（如「读读雨落那条视频的评论」）
→ 真去 B 站搜索后读结果。指令同样支持参数：`/鱼读片 第2条`。

**现刷专用说法**（v0.3.0）：「再刷刷其他的」「换一批」「再来一批」→ 换一批并跳过发过的；
「刷刷 up 主雨落发的视频」「刷点游戏视频」→ 按关键词真去 B 站搜索；
「看看排行榜」→ 走排行榜接口（被风控时自动改刷热门页）。
指令也支持带参数，例如 `/鱼刷站 再刷刷其他的`。

> **为什么加了自然语言路由**：实机发现用户问「你可以刷b站吗」时，消息不带 `/`
> 触发不了 `@filter.command`，直接落到 LLM；而 LLM 用的是默认「Kiro AI 助手」人设，
> 于是回答「不行哦，我没有联网浏览能力」。插件本身是好的（`/鱼截图`、`/鱼语音`
> 都正常出图出声）。修复分两层：
> 1. `@filter.event_message_type(ALL)` 做关键词意图路由，匹配成功就跑真实 Skill、
>    `event.stop_event()` 拦住 LLM，直接回真实 B 站数据 + 截图卡片；
> 2. `@filter.on_llm_request` 往 `req.system_prompt` 注入大肥鱼人设，自由聊天时
>    也不会再否认自己会刷站。
>
> 两层都可在 `config.yaml` 的 `nlu.enabled` / `nlu.inject_persona` 关掉。
> 注意边界：能刷的是**热门列表 / 热评 / 数据截图卡片**，不是播放视频流本身。

### v0.3.0：为什么之前「怎么说都是那三条」

实机日志（2026-11-14 23:40–23:41）暴露的问题：连着问「你能刷b站吗」
「/鱼刷站 再刷刷其他的」「刷刷up主雨落发的视频」，三次都回同一批
「抽象新闻 / TF家族 / 冬日宿舍」，截图和语音也永远是同一张、同一句。
根因有四个，逐一修掉：

| # | 根因 | 修法 |
|---|---|---|
| 1 | `popular?pn=1` 写死，热门榜几小时不变 | 轮换热门榜 1–5 页 + 全站/分区排行榜 + 关键词搜索；`feed_state.json` 记游标与最近 aid，自动跳过发过的 |
| 2 | 完全忽略用户说的「再刷刷其他的」「刷刷雨落」 | `parse_intent()` 提取 `keyword` / `refresh` / `rid` / `ranking`，按意图选数据源 |
| 3 | 语音文本硬编码、卡片无时间戳、产物文件名固定 | 语音念本批真实标题+播放数；卡片印「现刷于/来源/批次」；`voice_*` / `card_*` 带批次号，避免富媒体按内容 hash 命中旧缓存 |
| 4 | **一个 handler 里多次 `yield` 只有第一条发出去** | 所有消息段合并成**一次** `event.chain_result(comps)`；AstrBot `RespondStage` 会自动把多组件拆成逐条发送（`Record` 强制单独发） |

顺带修掉：B 站 `ranking/v2` 对这台服务器 IP 返回 `code=-352` 风控 →
默认轮换不再依赖排行榜，只在用户明确说「排行榜」时才请求，失败自动降级到
热门页（且降级页码会变，不会老显示同一来源）；降级文案不再把异常类名念进语音。

**实机验收（4 批连续现刷）**：4 批来源互不相同、相邻批次 aid 零重复、
4 段语音文本互不相同、4 张截图互不相同、单次 `yield` 带齐 5 段
（`Plain 3 / Image 1 / Record 1`）、本地 `run_local.py` 回归 5/5 全 OK。

### v0.4.0：为什么之前「鱼不会读评论」

之前 `_fetch_comments` 只取**第一条视频按时间排序的 3 条评论**，虽然落盘
`bilibili.json`，**下游一个都没消费**：截图只渲染「拟评论草稿」、语音只念标题和播放量、
文本只有清单，简介（desc）压根没取，更没有任何「总结」。用户看到的就是
「刷站只会报三个标题，评论读不了」。

修复是新增一个独立可插拔能力 `digest`（第 6 段），把「刷站」和「真读懂一条视频」分开：

| 读什么 | 怎么拿 |
|---|---|
| 标题 / UP / 分区 / 播放 / 点赞 / 时长 / 发布日期 | `bilibili_api.video.Video.get_info()` |
| 简介 `desc` | 同上（该字段热门/搜索列表接口不返回，必须单独取） |
| 热门评论（**按点赞数降序**，带赞数和昵称） | `x/v2/reply/main?mode=3`，合并置顶后自行排序去重 |
| 总结 | 优先 AstrBot 当前 LLM Provider（`context.get_using_provider().text_chat`）；没配 LLM / 超时 / 报错 → 自动降级本地抽取式摘要（不烧 token） |

总结会**同时进文本、读片报告截图、语音条**，并落盘 `digest.json`。外部文本一律当
不可信数据，只做归纳，不执行其中指令；表情 `[doge]`、@、URL 都会清洗掉。

**实机验收（服务器 3.12 环境真跑）**：真实简介 21 字读到、热评按赞排序
（1475 / 392 / 200 赞）、`summary_mode=llm` 的 AI 总结生效、简介/热评/总结全部渲染进
读片卡片（已肉眼验收，中文正常无乱码）；`/巡游` 与自然语言路径统一走 `_collect`，
都可用 LLM；本地一键脚本 6/6 能力 OK、16 条消息；服务器 `verify.sh` 全绿。

> 边界：读的是**简介文本 + 热门评论**，不是视频画面/字幕/弹幕，也不做视频流解析。
> 有些视频 UP 主不写简介（B 站常见 `-` 或空），鱼会如实说「没写简介」并把重点放到热评归纳，
> 不会编造内容。

### 实机踩过并修掉的坑

1. **AstrBot `Comp.Record` 只接受 wav**，edge-tts 出的是 mp3 → 语音模块双产出：
   mp3（QQ 官机富媒体 `file_type=3` 直传，无需转 silk）+ 16k 单声道 wav（插件侧）。
2. **本地图片必须 `Comp.Image.fromFileSystem(path)`**，直接塞路径给 `file=` 不生效；
   4.29.4 实测 `Comp.Record(file=wav)` 即可，多余的 `url=` 参数已去掉。
3. **B 站旧 `get_comments` 已迁移**，返回空 `replies` → 改用 `get_comments_lazy`（offset 游标）。
4. **Playwright 浏览器 build 号按 Python 环境走**：3.11 与 3.12 装的 playwright 版本不同，
   分别对应 `chromium_headless_shell-1254` 与 `-1255`，**两套 venv 必须各跑一次
   `playwright install chromium`**，否则插件里截图直接报 `Executable doesn't exist`。
5. **1.9G 内存**：Chromium 加了 `--disable-dev-shm-usage`，另加 2G swap，避免 `/dev/shm` 64MB 撑爆。
6. `cmd_config.json` 带 UTF-8 BOM，脚本读它要用 `encoding="utf-8-sig"`。
7. 截图模板 CSS 花括号不能被 `str.format` 当占位符 → 用 `.replace()`。
8. **一个 handler 多次 `yield` 只发第一条**：`stop_event()` 后第一条消息发出即
   触发 `after_message_sent stopped event propagation`，后续 yield 的结果丢失。
   改成合并成一次 `chain_result([...])`，由 `RespondStage` 逐条 `event.send()`。
9. **B 站 `ranking/v2` 的 `-352` 风控**：同一 IP 连续请求会全量失败，
   `popular` 分页则稳定。默认轮换只用热门分页，排行榜按需请求并自动降级。
10. **富媒体缓存**：文件名与内容都固定时，QQ 官机按内容 hash 复用旧图/旧语音，
    看起来「永远是那一条」→ 产物带批次号 + 卡片/语音内容随批次变化。
11. **裸 `x/web-interface/view` 对服务器 IP 返回 `-412`（HTML 反爬页）**：加上
    `buvid3/buvid4`（从 `x/frontend/finger/spi` 取）即可 `code=0`；更简单是直接用
    `bilibili_api.video.Video.get_info()`，库内部已处理，简介字段 `desc` 实测能拿到
    21~372 字的实质内容。
12. **热门评论要用 `reply/main?mode=3`**，旧的 `get_comments` / 按 `TIME` 排序拿到的是
    最新灌水而不是热评；库里 `OrderType` 只有 `LIKE`/`TIME`（没有 `HOT`），
    所以直接读裸接口并自行按 `like` 降序 + 去重。
13. **`/巡游` 与自然语言必须走同一入口**：之前 `/巡游` 走 `Chain.run_pipeline`（拿不到
    AstrBot context，永远只能用本地摘要），自然语言走 `_collect`。已统一到 `_collect`，
    两条路径都能用 LLM 总结。
14. **意图解析的「一」字陷阱**：`INDEX_PAT` 若不限定量词，「换一批」「总结一下」里的
    「一」会被当成「第 1 条」；read 类语句还会残留「讲」「区」等单字当搜索关键词。
    现在序号必须带「条/个/部/支」，read 动作的单字关键词直接丢弃。

### 安全提醒

- WebUI 默认监听 `0.0.0.0`，**首次登录后立即改密码**；长期建议把
  `data/cmd_config.json` 的 `dashboard.host` 改成 `127.0.0.1`，用 SSH 隧道
  `ssh -L 6185:127.0.0.1:6185 root@<服务器IP>` 访问。
- 评论保持 `dry_run: true`。自动留言受平台规则约束，别拿去批量刷。
- 不要把 LLM API Key、QQ AppSecret、B 站登录凭证写进仓库或长期记忆。

---

## fork 之后：只复制你想要的链路

每个能力就是 `config.yaml` 里一个 `enabled`。关掉的段会被 `Chain` 干净跳过，
其余照常跑（本地 + 服务器共实测 7 种组合，含「全关」）。

例：**只保留语音 + 截图**，完全不碰 B 站和评论：

```yaml
capabilities: [voice, screenshot]
skills:
  chat:       {enabled: false}
  voice:      {enabled: true, voice_id: zh-CN-XiaoyiNeural, rate: "-8%"}
  screenshot: {enabled: true, mode: html_card}
  bilibili:   {enabled: false}
  comment:    {enabled: false}
```

`run_pipeline()` 里截图会读 `ctx["videos"]`；关掉 B 站时 `screenshot.py` 自动用兜底卡片，
不会因为缺数据崩掉。运行时还能用 `/鱼开关 voice off` 热插拔，不改配置、不重启。

**加自己的一段**：在 `skills/` 新建文件，继承 `Skill` 实现
`async run(ctx) -> SkillResult`（返回 `segments=[Segment(...)]`、`artifacts`、`data`、`note`），
再把类名加进 `skills/__init__.py` 的 `REGISTRY`，`config.yaml` 补一个同名 `enabled` 即可。
`Segment` 只有三种 `text` / `image` / `record`，`to_astrbot_comp()` 已封装好官机格式差异。

---

## 评论的边界（重要）

`comment` 默认 `dry_run: true`，**只生成草稿、绝不真发**。真发需要同时满足：
`allow_publish: true` + 完整登录凭证 + 隐私词检查通过，并受 `daily_limit` 限制。
自动留言受 B 站平台规则约束，社区共识是「先拟好内容给主人确认再发」。
本项目把这条做成默认安全值，请不要直接拿去批量刷评论。

> 本项目仅用于个人学习与自建机器人。使用 QQ 官方机器人、B 站接口时请遵守对应平台规则；
> 账号风控、LLM token 账单、凭证安全由使用者自行负责。

## 目录

```
config.yaml / config.example.yaml   可插拔开关
core/           models 消息段 / persona 人设 / gateway 网关 / chain 编排
skills/         chat voice screenshot bilibili digest comment 六个独立能力
astrbot_plugin_dafeiyu/            AstrBot 插件（含 metadata.yaml / _conf_schema.json）
deploy/         install_server.sh / *.service / *.timer / healthcheck.sh / verify.sh
run_local.py    一键跑通 + 验收报告
output/         真实产物（已 gitignore，含 read_*.png 读片卡片与 digest.json）
```
