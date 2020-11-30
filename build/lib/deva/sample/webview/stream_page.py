# coding: utf-8
from deva.page import page, PageServer, render_template
from deva import *

# 系统日志监控
s = from_textfile('/var/log/system.log')
s1 = s.sliding_window(5).map(concat('<br>'), name='system.log日志监控')
s.start()


# 实时股票数据

s2 = timer(func=lambda: NB('sample')['df'].sample(
    5).to_html(), start=True, name='实时股票数据', interval=1)

# 系统命令执行
command_s = from_process(['ping', 'baidu.com'])
s3 = command_s.sliding_window(5).map(concat('<br>'), name='系统持续命令')
command_s.start()


# server = PageServer(host='127.0.0.1', port=9990)
s1.webview()
s2.webview()
s2.webview('/stock')
s3.webview()

Monitor().start()
Deva.run()
