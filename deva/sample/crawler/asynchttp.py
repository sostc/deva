from deva import *

h = http()
h.map(lambda r: (r.url, r.html.search('<title>{}</title>')[0])) >> log
'http://www.518.is' >> h


s = Stream()
s.rate_limit(1).http(workers=20).map(lambda r: (
    r.url, r.html.search('<title>{}</title>')[0])) >> warn
'http://www.518.is' >> s

Deva.run()
