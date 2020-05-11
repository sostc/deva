from deva import *

s = Stream.IndexStream()

'建设大众化' >> s
'建伟不在家' >> s


s.search('建设') | ls | print


# python3 search_stream.py
# Building prefix dict from the default dictionary ...
# DEBUG:jieba:Building prefix dict from the default dictionary ...
# Loading model from cache /var/folders/7s/wk98z9d51p1b9_40kcp0d3c00000gp/T/jieba.cache
# DEBUG:jieba:Loading model from cache /var/folders/7s/wk98z9d51p1b9_40kcp0d3c00000gp/T/jieba.cache
# Loading model cost 1.615 seconds.
# DEBUG:jieba:Loading model cost 1.615 seconds.
# Prefix dict has been built succesfully.
# DEBUG:jieba:Prefix dict has been built succesfully.
# [<Hit {'content': '建设大众化', 'id': '1587356717.349557'}>]
# 2020-04-20 12:25:19.152478 : exit
# bye bye, 7553
