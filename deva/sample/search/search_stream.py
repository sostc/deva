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
# Loading model cost 1.132 seconds.
# DEBUG:jieba:Loading model cost 1.132 seconds.
# Prefix dict has been built succesfully.
# DEBUG:jieba:Prefix dict has been built succesfully.
# ['建设大众化']
# [2020-03-14 10:23:13.109616] INFO: log: exit
# bye bye, 39127
