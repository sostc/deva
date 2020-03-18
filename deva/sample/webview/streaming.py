# coding: utf-8
from deva.page import page, Streaming, render_template
from deva import *

s = from_textfile('/var/log/system.log')
s1 = s.sliding_window(5).map(concat('<br>'), name='system.log')
s.start()


def sample_df_html(n=5):
    return NB('sample')['df'].sample(n).to_html()


s2 = timer(func=sample_df_html, start=True, name='每秒更新', interval=1)
s3 = timer(func=sample_df_html, start=True, name='每三秒更新', interval=3)


@page.route('/')
def get():
    streams = [s1, s2, s3]
    return render_template('./web/templates/streams.html', streams=streams)


Streaming().start()
Monitor().start()
Deva.run()
