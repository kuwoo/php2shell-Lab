# php2shell-lab

基于 Docker 的本地靶场，用于复现和学习 PHP 高危漏洞 **php2shell**（CVE-2026-109618 / CVE-2026-109619）的第一条攻击链（Chain A）：

> `session.upload_progress` 文件名注入 + 应用本地文件包含（LFI）→ 远程命令执行（RCE）

参考公开研究 [ikow/php2shell-poc](https://github.com/ikow/php2shell-poc) 改造，代码刻意写得**最少、注释最多**，方便中文读者边跑边学。

---

## ⚠️ 免责声明（必读）

- 本项目**仅用于本地靶场、安全学习与授权测试**。
- 请**不要**对未授权的系统运行 `poc.py`，也不要把本仓库的载荷用于任何真实目标。
- 本仓库只包含 **Chain A**（应用层 LFI 组合链），**不包含** Chain B 的 UAF 内存破坏利用（原仓库也只有 ASAN 验证脚本），也**不包含**任何提权 / 反弹 shell 的现成武器化代码。
- 使用者对自身行为负全部责任。

---

## 一、漏洞背景（一句话版）

| 项目 | 内容 |
|------|------|
| 漏洞名 | php2shell |
| CVE | CVE-2026-109618、CVE-2026-109619 |
| 类型 | 无需认证（pre-auth）的远程代码执行（RCE） |
| 评分 | CVSS 4.0 **9.2（严重）** |
| 影响版本 | PHP **5.4.0 ~ 8.5.11** |
| 修复版本 | 8.2.35 / 8.3.36 / 8.4.27 / 8.5.12（2026-10-21 发布） |
| 根因位置 | PHP 核心的 `session.upload_progress` 处理器 |

> 详细原理见 [docs/原理分析.md](docs/原理分析.md)。

---

## 二、快速开始（三步）

```bash
# 1. 构建并启动靶场（唯一的服务，8082 端口）
docker compose up -d --build

# 2. 运行 PoC（默认跑「展示载荷」，一次证明命令执行 + 身份 + 系统信息 + 读文件）
python poc.py --target http://localhost:8082

# 3. 只跑一条自定义命令
python poc.py --target http://localhost:8082 --cmd "id"
```

看到输出里的 `uid=33(www-data)` 即代表复现成功。

---

## 三、效果展示

`python poc.py --target http://localhost:8082` 的输出：

```
[1] 已注入，会话文件应为 /tmp/sessions/sess_xxxxxxxxxxxxxxxxxxxxxxxxxx
[2] LFI 包含并执行: http://localhost:8082/index.php?page=/tmp/sessions/sess_xxx

uid=33(www-data) gid=33(www-data) groups=33(www-data)
=== WHOAMI ===
www-data
=== UNAME ===
Linux a3ab81efaa32 6.18.54.1-microsoft-standard-WSL2 #1 SMP PREEMPT_DYNAMIC ... x86_64 GNU/Linux
=== PASSWD ===
root:x:0:0:root:/root:/bin/bash
daemon:x:1:1:daemon:/usr/sbin:/usr/sbin/nologin
...
```

`--cmd "whoami"` 的输出：

```
www-data
```

> 注意：php2shell 拿到的是 **web 运行用户（www-data）**，**不是 root**。从 www-data 到 root
> 需要额外的本地提权，那是另一类问题，本靶场不涉及（见 [docs/原理分析.md](docs/原理分析.md)）。

---

## 四、目录结构

```
.
├── app/
│   └── index.php          # 故意脆弱的应用：含一个 LFI 端点（Chain A 的前提）
├── docs/
│   ├── 操作手册.md          # 手把手的操作手册（环境、复现、自定义、FAQ）
│   └── 原理分析.md          # 从 PHP session 机制到完整攻击链的深度分析
├── Dockerfile             # 固定到受影响版本 php:8.2.34-apache
├── docker-compose.yml     # 定义唯一的 php2shell 服务（8082）
├── php.ini                # 靶场专用配置（开 upload_progress、关 cleanup、固定会话目录）
├── poc.py                 # Chain A 复现脚本（含「展示载荷」和 --cmd 两种用法）
└── README.md
```

---

## 五、文档导航

| 文档 | 适合谁 | 内容 |
|------|--------|------|
| [docs/操作手册.md](docs/操作手册.md) | 想先跑起来的人 | 环境要求 → 启动 → 复现 → 自定义 → 停止/清理 → FAQ |
| [docs/原理分析.md](docs/原理分析.md) | 想弄懂原理的人 | 前置知识 → 根因 → Chain A 逐步拆解 → 三条链对比 → 检测与修复 |

---

## 六、原理速览（30 秒版）

```
攻击者上传文件，把 PHP 代码塞进「文件名」
        ↓
PHP 的 session.upload_progress 把文件名原样写进会话文件
        ↓
攻击者用 POST body 里的 PHPSESSID 固定会话 ID（绕过 use_only_cookies）
        ↓
目标应用存在 LFI，include 这个会话文件
        ↓
会话文件里的 PHP 代码被执行 → RCE
```

关键点：
1. **文件名没过滤** → PHP 把它当纯文本写进会话文件，你的 `<?php ... ?>` 就「潜伏」进去了；
2. **`PHPSESSID` 能从 POST body 传** → 绕过 `session.use_only_cookies=1`，攻击者可以预知会话文件路径；
3. **应用有 LFI** → 包含会话文件时，PHP 会解析执行其中的 `<?php ... ?>`。

---

## 七、常见问题（简版）

| 问题 | 答案 |
|------|------|
| 启动报端口占用？ | 改 `docker-compose.yml` 里的 `8082:80`，或 `docker compose down` 后重试。详见操作手册 |
| 构建报 `/app not found`？ | `app/` 目录被误删了，确认 `app/index.php` 存在后重新 `--build` |
| 输出中文乱码？ | Windows 终端是 GBK，先 `chcp 65001`，见操作手册 |
| 想要浏览器里换行？ | 把载荷里的 `PHP_EOL` 换成 `<br>` 或用 `<pre>` 包住，见操作手册 |
| 能直接拿 root 吗？ | 不能。php2shell 给的是 www-data，提权是另一个问题，见原理分析 |

---

## 八、参考

- [ikow/php2shell-poc](https://github.com/ikow/php2shell-poc) —— 原始公开研究（三条攻击链 + ASAN 验证）
- CVE-2026-109618 / CVE-2026-109619 官方公告与 PHP 修复提交

---

## 九、许可证

本项目使用 [MIT License](LICENSE)，Copyright (c) 2026 ronins。
