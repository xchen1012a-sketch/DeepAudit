# -*- coding: utf-8 -*-
"""
Gunicorn 生产环境配置文件
"""
import multiprocessing
import os

# 绑定地址和端口
bind = "0.0.0.0:5000"

# 工作进程数（建议：CPU核心数 * 2 + 1）
workers = multiprocessing.cpu_count() * 2 + 1

# 工作模式
worker_class = "sync"

# 每个工作进程的线程数
threads = 2

# 最大并发请求数
worker_connections = 1000

# 超时时间（秒）
timeout = 120
keepalive = 5

# 进程命名
proc_name = "deepaudit_pro"

# 日志配置
accesslog = "logs/gunicorn_access.log"
errorlog = "logs/gunicorn_error.log"
loglevel = "info"

# 访问日志格式
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s"'

# 守护进程（使用 PM2 或 systemd 时设为 False）
daemon = False

# 预加载应用
preload_app = True

# 优雅重启超时
graceful_timeout = 30

# PID 文件
pidfile = "logs/gunicorn.pid"

# 临时文件目录
worker_tmp_dir = "/dev/shm"

