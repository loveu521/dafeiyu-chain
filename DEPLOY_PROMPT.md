# 给其他 AI 的部署提示词

> 下面整段可直接复制，粘贴给另一个 AI（ChatGPT / Claude / Codex / WorkBuddy 等）。
> 提示词本身**不含任何凭据**，也不要求你提供凭据。

---

## 可直接复制的提示词

```text
你要帮我把一个开源项目部署到一台我自己的 Linux 服务器上。请严格按下面执行。

【项目】
仓库：https://github.com/loveu521/dafeiyu-chain （公开，MIT，main 分支）
名称：dafeiyu-chain / 蓝色大肥鱼
意图：一个可插拔的 QQ 聊天机器人，基于 AstrBot 4.x + QQ 官方机器人 WebSocket，
      会说话、发语音、发 HTML 渲染截图、实时刷 B 站、读单条视频的标题/简介/
      热门评论并总结输出、生成评论草稿（默认不真发）。
      6 个能力各自独立开关，fork 后可任意复制子链路。

【第一步：必须先读，不要跳过】
1. 拉取仓库（git 协议不通就改用 GitHub REST contents API 下载，或让我打包上传）。
2. 完整阅读仓库根目录的 AGENTS.md —— 那是专门给 AI 读的机器可读部署规范，
   包含意图、架构、目录地图、部署决策树、精确命令、验收标准、凭据红线、踩坑速查。
3. 再读 README.md 了解人类向的说明与实机验收结果。
4. 读 deploy/install_server.sh 与 deploy/*.service，确认它实际会做什么再执行。
   读完先用自己的话复述一遍「这个项目做什么、分成哪几段、部署后会起哪些服务」，
   我确认你理解对了再往下走。

【第二步：只问机器信息，绝不问密钥】
你只能向我询问这些：服务器系统版本、CPU/内存/磁盘、是否有 root、
是否已装 Docker、目标端口是否可用、以及你打算把代码放在哪个目录。
严禁向我索要或要求我粘贴：任何 token、密码、API Key、Cookie、SESSDATA、
AppSecret、SSH 私钥、WebUI 初始密码。若我主动贴了，提醒我这些值已被对话记录，
建议我轮换，并且你不得把它们写进任何文件、日志、命令回显或提交信息。

【第三步：选方案并执行】
- 内存 < 4G 或没装 Docker → 用仓库默认方案：venv + systemd + 2G swap，
  执行 `sudo bash deploy/install_server.sh`（幂等，可重复跑）。
- 内存 >= 4G 且已有 Docker → 若我明确要求容器化，再基于 deploy/*.service
  自行设计 compose；否则仍用默认方案，不要擅自换技术栈。
- 关键硬约束（AGENTS.md §4/§5）：AstrBot 4.x 要求 Python >= 3.12，链路本体用
  系统 3.11，必须两套 venv 隔离；两套 venv 要各跑一次
  `playwright install chromium`（浏览器 build 号不同，否则插件截图直接失败）。
- 不要覆盖已有的 AstrBot 配置（cmd_config.json）。

【第四步：验收（必须真跑，不要只说"应该可以"）】
1. `bash deploy/check-secrets.sh` → 退出码必须为 0（输出「✅ 未发现」）。
2. 本地模式：`python3.11 run_local.py` → 退出码 0、6 段能力全 OK、
   output/ 下 PNG/MP3/WAV 文件头有效、生成 output/REPORT.md。
3. 服务器模式：`/opt/dafeiyu/deploy/verify.sh` → 全部能力 OK。
4. 检查 `systemctl is-active astrbot.service` == active、两个 timer 已 enable、
   `curl -o /dev/null -w '%{http_code}' http://127.0.0.1:6185/` == 200、
   日志出现 `Loading plugin astrbot_plugin_dafeiyu` 且无 Traceback。
5. 任一项不通过，按 AGENTS.md §8「常见失败速查」定位并修复，最多重试 3 次；
   仍失败就如实报告卡在哪一步，不要假装成功。

【第五步：明确列出我做的事（你做不了）】
必须单独列一节「需要人类完成」：
- 手机 QQ 扫码：WebUI → 机器人 → +创建 → QQ 官方机器人(WebSocket) → 扫码一键创建。
- 首次登录 WebUI 后立即修改初始密码（初始密码只在服务器日志里，你不要读取或复述它的值）。
- 可选：在 WebUI 配置 LLM API Key；可选：如需真发 B 站评论，自行准备登录凭证。
- 在 QQ 里实际发一句话（如「刷个B站」「读读评论」「读一下第2条」）验证收发。
不要替我扫码，也不要把 WebUI 密码写进任何交付文件。

【安全红线（违反即视为任务失败）】
- 不得把任何真实凭据写入仓库内文件、注释、提交信息、日志或对话回复。
- 提交/推送前必须跑 deploy/check-secrets.sh 且退出码 0。
- 不得 git add：output/、*.env、config.local.yaml、secrets/、cmd_config.json、
  astrbot_data/、*.log、*.pem、*.key。
- 不得把 config.yaml 里的 comment.dry_run 改成 false 或 allow_publish 改成 true。
  本项目默认只生成评论草稿、绝不自动发评论。
- 不得把 WebUI 长期暴露在公网且不改密码；建议提醒我把 dashboard.host 改 127.0.0.1
  并用 `ssh -L 6185:127.0.0.1:6185` 隧道访问。
- 若你需要推送到我的 GitHub 仓库，只允许使用我在本地环境变量里提供的凭据，
  不得把它写进任何文件；推送后做一次远端全库敏感信息扫描并给我结果。

【输出格式】
最后给我一份结构化报告：
1) 项目意图复述（一句话 + 6 段能力清单）
2) 目标机器配置与所选部署方案、理由
3) 实际执行过的命令（逐条，含真实输出摘要）
4) 验收结果表（每项：命令 / 预期 / 实际 / 是否通过）
5) 部署后的目录、服务、端口、日志路径
6) 遇到的问题与修复（对照 AGENTS.md §8）
7) 需要人类完成的步骤（清单，含扫码与改密码）
8) 安全确认：check-secrets.sh 结果 + 远端扫描结果 + 明确声明仓库内无任何凭据
```

---

## 使用建议

- 粘贴前把「目标机器」信息一并给它（系统 / 内存 / 是否 root），能少一轮来回。
- 若那台机器 **git 协议连不上**（`api.github.com` 通但 `github.com:443` 超时），
  提示词里已允许改用 REST contents API 或本地打包上传。
- 提示词第 2 步的「复述意图」是防呆：AI 若把项目理解成「自动刷评论机器人」
  或「AI 生图机器人」，说明它没读 AGENTS.md，应让它重读再继续。
- 本文件与 `AGENTS.md` 都是**纯文本、零凭据**，可安全提交到公开仓库。
