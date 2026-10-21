<?php
// 故意脆弱的演示应用：含一个本地文件包含 (LFI) 端点。
// 配合 session.upload_progress 的「文件名注入」，构成 CVE-2026-109618/109619 的
// Chain A：会话文件注入 + LFI → RCE（见同目录 poc.py）。
$page = $_GET['page'] ?? '';
if ($page !== '') {
    // ↓↓↓ 危险写法：直接 include 用户路径，可包含任意本地文件（含会话文件）
    include($page);
    exit;
}
?>
<!doctype html><meta charset="utf-8"><title>php2shell Chain A 演示</title>
<h1>php2shell Chain A 演示（会话注入 + LFI → RCE）</h1>
<p>本页故意留了一个 LFI：<code>?page=/path/to/file</code></p>
<p>攻击者先通过 <code>session.upload_progress</code> 把 PHP 代码注入会话文件，
   再用本页的 LFI 包含它，即可执行任意命令。</p>
