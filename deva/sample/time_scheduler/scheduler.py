
# coding: utf-8

# In[ ]:


from tornado import ioloop
from apscheduler.jobstores.redis import RedisJobStore
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.schedulers.tornado import TornadoScheduler
import pytz

from naja.tradetime import when_tradedate
import moment
from deva import bus, pmap, P

jobstores = {
    'redis': RedisJobStore(),
    'default': MemoryJobStore()
}
executors = {
    'default': ThreadPoolExecutor(50),
}
job_defaults = {
    'coalesce': False,
    'max_instances': 200
}

scheduler = TornadoScheduler(jobstores=jobstores, executors=executors,
                             job_defaults=job_defaults, timezone=pytz.timezone('Asia/Shanghai'))
try:
    scheduler.start()
except Exception as e:
    print(e)


# In[ ]:

# In[ ]:


@scheduler.scheduled_job('interval', name='open', days=1, start_date='2019-04-03 09:25:00',)
@when_tradedate
def _open():
    'open' >> bus


@scheduler.scheduled_job('interval', name='close', days=1, start_date='2019-04-03 15:30:00',)
@when_tradedate
def _close():
    'close' >> bus


# In[ ]:


# In[ ]:


scheduler.get_jobs() >> pmap(lambda x: x.next_run_time) >> list@P

ioloop.IOLoop.current().start()
