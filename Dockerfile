# 固定到易受攻击的 PHP 版本：8.2 分支的修复版是 8.2.35，8.2.34 仍在受影响范围。
# 不要用会浮动的 php:8.2-apache，它可能已指向修复后的版本。
FROM php:8.2.34-apache

# 故意脆弱的应用 + php.ini（开启 upload_progress、关掉 cleanup、固定会话目录）
COPY app/ /var/www/html/
COPY php.ini /usr/local/etc/php/conf.d/zz-php2shell.ini

# 会话文件目录（固定路径 + 可写，便于 LFI 用绝对路径包含）
RUN mkdir -p /tmp/sessions && chmod 777 /tmp/sessions
