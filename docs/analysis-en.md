# In-depth Analysis (php2shell-lab)

This document is for readers who "want to fully understand how this vulnerability happens". Starting from PHP's session mechanism, it builds up to the full attack chain step by step, and makes clear which parts are the vulnerability itself and which parts are simplifications this lab makes for demonstration.

---

## Table of contents

1. [Overview](#1-overview)
2. [Prerequisites](#2-prerequisites)
3. [Root cause](#3-root-cause)
4. [The full Chain A](#4-the-full-chain-a)
5. [Detail 1: PHPSESSID bypasses use_only_cookies](#5-detail-1-phpsessid-bypasses-use_only_cookies)
6. [Detail 2: cleanup and the race window](#6-detail-2-cleanup-and-the-race-window)
7. [Comparing the three chains](#7-comparing-the-three-chains)
8. [Two deliberate simplifications in this lab](#8-two-deliberate-simplifications-in-this-lab)
9. [About privileges: why www-data, not root](#9-about-privileges-why-www-data-not-root)
10. [Detection](#10-detection)
11. [Fixing and mitigating](#11-fixing-and-mitigating)
12. [References](#12-references)

---

## 1. Overview

**php2shell** is a family of vulnerabilities in PHP's core (`session` module), with the official IDs:

- CVE-2026-109618
- CVE-2026-109619

Core characteristics:

| Dimension | Content |
|-----------|---------|
| Type | Pre-authentication (pre-auth) Remote Code Execution (RCE) |
| Score | CVSS 4.0 **9.2 (Critical)** |
| Root cause | How the `session.upload_progress` handler treats uploaded filenames |
| Affected | PHP **5.4.0 – 8.5.11** (spanning over a decade) |
| Fixed | 8.2.35 / 8.3.36 / 8.4.27 / 8.5.12 (released 2026-10-21 14:00 UTC) |

The public research [ikow/php2shell-poc](https://github.com/ikow/php2shell-poc) breaks it into three chains (A / B / C). This repository implements only **Chain A** — the most intuitive, most reliable, and the one that doesn't rely on memory corruption.

---

## 2. Prerequisites

### 2.1 How PHP stores sessions as files

PHP stores sessions in files by default. If the session ID is `abc123`, the session data lives (with default settings) at:

```
/tmp/sessions/sess_abc123
```

The file content is `key|serialized data`, e.g.:

```
login_user|s:5:"admin";csrf_token|s:32:"...";
```

Key point: **this file is a plain text file**. If you know the session ID, you can construct its full path.

### 2.2 What `session.upload_progress` does

Since PHP 5.4, PHP has a built-in "upload progress" feature (on by default):

- When it receives a multipart form upload, PHP records the upload progress in the session;
- the frontend can poll this progress to render a progress bar.

The data it writes to the session looks like this (simplified):

```
upload_progress_<name>|a:5:{
    start_time; content_length; bytes_processed; done;
    files: [ { field_name, name, tmp_name, error, ... } ]
}
```

Where:

- the `<name>` in `upload_progress_<name>` comes from the `PHP_SESSION_UPLOAD_PROGRESS` form field;
- `files[].name` is **the original filename of the file you uploaded**.

---

## 3. Root cause

In one sentence:

> **PHP treats "the uploaded file's filename" as plain text and writes it verbatim into the session file, without any filtering.**

And the session file is a plain-text file that PHP will parse and execute. So:

- if the filename is `shell.php`, nothing happens;
- if the filename is `<?php system('id'); ?>`, that PHP code gets written verbatim into the session file.

Once there's a way to make PHP "execute" this session file (e.g. the app has an LFI and includes it), the `<?php ... ?>` inside is treated as PHP code and executed → **Remote Code Execution**.

This explains the name **php2shell**: turn a php session file into a shell.

---

## 4. The full Chain A

Chain A needs two conditions to line up:

1. `session.upload_progress` is enabled (**on by default**);
2. the target app has a **Local File Inclusion (LFI)** vulnerability.

The full flow has three steps:

### Step 1: fix the session ID

The attacker first picks a session ID (e.g. `abc123`). To later include the session file precisely, they must make PHP write the session file under this ID.

### Step 2: upload + inject the filename

The attacker sends a multipart POST containing:

- a `PHP_SESSION_UPLOAD_PROGRESS` field (triggers upload-progress recording);
- a `PHPSESSID` field (fixes the session ID, see section 5);
- a file whose **filename is PHP code**:

```
<?php echo 'RCE OK'; system($_GET['c']); ?>
```

When PHP handles the upload, it writes this filename verbatim into the session file:

```
/tmp/sessions/sess_abc123
```

The file content becomes:

```
upload_progress_chainA|a:5:{...s:4:"name";s:48:"<?php echo 'RCE OK'; system($_GET['c']); ?>";...}
```

Now a piece of "live" PHP code is sitting inside the session file.

### Step 3: include the session file via LFI

The attacker uses the app's LFI:

```
http://target/index.php?page=/tmp/sessions/sess_abc123&c=id
```

`include('/tmp/sessions/sess_abc123')` parses the file as PHP:

1. the `upload_progress_chainA|a:5:{...` before `<?php` is output verbatim (that's the messy prefix in the PoC output);
2. `<?php echo 'RCE OK'; system($_GET['c']); ?>` executes → outputs `RCE OK` + the result of `id`;
3. the serialized tail after `?>` is output too.

The attacker gets command execution, with the identity being the user the PHP process runs as.

> `poc.py` does exactly these three steps: inject, then include via LFI, then `split` off the serialized prefix in the output and show only the command result.

---

## 5. Detail 1: PHPSESSID bypasses use_only_cookies

Normally PHP only reads the session ID from the **Cookie** (`session.use_only_cookies=1`, which is the default and the safe configuration). The attacker can't set a cookie on the victim, so it seems like they can't fix the session ID.

But a key point of php2shell is: **the `session.upload_progress` handler accepts a `PHPSESSID` sent directly in the POST body**, thus bypassing `use_only_cookies`.

The effect is **session fixation**:

- the attacker writes `PHPSESSID=abc123` in the request body;
- PHP uses `abc123` as the session ID when writing progress;
- the attacker **knows in advance** the session file path is `/tmp/sessions/sess_abc123`;
- so they can include it directly via LFI.

For safety, `poc.py` sends the same `PHPSESSID` in both the body **and** the Cookie (belt and suspenders).

---

## 6. Detail 2: cleanup and the race window

`session.upload_progress.cleanup` controls "whether to delete the progress data after the upload finishes":

- **default `cleanup=On`**: as soon as the upload finishes, PHP removes the `upload_progress_*` entry from the session. In other words, the injection is **fleeting**.
- How do real attackers cope? **They race**: upload a large file (slow upload) and, during the window where the file is still uploading and the progress data hasn't been cleaned up yet, use **concurrent requests** to include the session file.

To make this lab succeed **deterministically every time**, it sets `cleanup` to `Off` (see `php.ini`), so the injection stays in the session file and you don't need to race. The principle is exactly the same as the real attack; it just turns "you must race" into "guaranteed hit".

---

## 7. Comparing the three chains

The public research breaks php2shell into three chains with very different difficulty and dependencies:

| Chain | Principle | Complexity | Dependency | This repo |
|-------|-----------|------------|------------|-----------|
| **Chain A** | Filename injection + app LFI → RCE | Low, 100% reliable | App must have LFI | ✅ implemented |
| **Chain B** | `var_destroy` use-after-free (UAF) memory corruption → RCE | High | App `unserialize`s session data (ASAN verification) | ❌ not provided |
| **Chain C** | Session-handler mismatch + POP gadget (deserialization) | Medium-high | Specific multi-dir setup + deserialization gadget | ❌ not provided |

Notes:

- **Chain B** is the heavyweight 9.2 "memory corruption" one (UAF), but it requires the target to deserialize attacker-controlled session data, and the original repo only has an ASAN crash-verification script, not a turnkey exploit; turning UAF into stable RCE is weaponization, which this repo does not provide.
- **Chain C** depends on a deserialization gadget in a specific app; it's an "application-layer combo".

This repo picks **Chain A**: the principle is clearest, it best explains "what php2shell actually is", and it's best suited for teaching.

---

## 8. Two deliberate simplifications in this lab

To make "one-command reproduction" possible, this lab makes two simplifications (neither changes the essence of the vulnerability):

1. **`session.upload_progress.cleanup = 0`** (`php.ini`) — makes the injection persist deterministically, sparing you the concurrent race script (see section 6).
2. **Deliberately provide an LFI endpoint** (`?page=...` → `include` in `app/index.php`) — because Chain A's prerequisite is that the app has an LFI.

Both are clearly noted in the code and README, so readers don't mistake "real environments are this easy".

---

## 9. About privileges: why www-data, not root

Many readers ask: if I have RCE, did I "own the server"? The answer is — **it depends on what user the PHP process runs as**.

In this lab (and in the vast majority of production environments):

- the Apache master process starts as root (to bind port 80), but **forks child processes and drops to `www-data`** immediately (governed by `APACHE_RUN_USER`/`APACHE_RUN_GROUP`);
- mod_php runs inside Apache child processes, so PHP also runs as `www-data`;
- therefore the command-execution identity php2shell gives you is `www-data`, **not root**.

A bonus fun fact: Apache even **refuses to serve as root** — it's compiled with the `BIG_SECURITY_HOLE` guard, and setting `User` to `root` makes it refuse to start. This is also why this lab has no "root edition": that would require an additional local privilege-escalation vulnerability, a different class of problem.

**Conclusion**: php2shell gives you the web user (www-data). Going from www-data to root is the domain of "local privilege escalation" (kernel bugs, SUID binaries, misconfigurations, etc.), unrelated to this CVE and out of scope here.

---

## 10. Detection

Besides exploiting directly (on authorized targets), you can use a **black-box side channel** to judge whether the target has `session.upload_progress` enabled:

- send the target a request that triggers upload progress;
- observe whether the response headers **passively include `Set-Cookie: PHPSESSID=...`** (because upload_progress auto-starts a session, and PHP issues the session cookie).

This side effect — "the request carried no session, yet the response set a cookie" — can serve as a **non-intrusive** detection signal. But note: production environments are often interfered with by WAFs / CDNs / UA checks / static sites, so the phenomena in this local lab can't be transplanted to real sites directly.

---

## 11. Fixing and mitigating

In priority order:

1. **Upgrade to a fixed version** (most fundamental): 8.2.35 / 8.3.36 / 8.4.27 / 8.5.12 and above.
2. **Temporary mitigation**: set `session.upload_progress.enabled = 0`.
   - Note: this **reduces Chain A's injection surface**, but does **not fully fix** Chain B's UAF / serializer-leak issue; the official patch is still required.
3. **Application-layer hardening**:
   - fix the LFI (don't `include` user-controlled paths; use an allowlist);
   - don't accept `PHPSESSID` from the POST body;
   - put session files somewhere the web process can't include directly.

---

## 12. References

- [ikow/php2shell-poc](https://github.com/ikow/php2shell-poc) — original public research on the three chains
- PHP official security advisories and the fix commits for CVE-2026-109618 / CVE-2026-109619
- PHP manual: `session.upload_progress` configuration
