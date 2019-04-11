
# coding: utf-8

# In[ ]:


from apscheduler.jobstores.redis import RedisJobStore
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.schedulers.tornado import TornadoScheduler
import pytz

from tradetime import when_tradedate, when_tradetime,is_holiday_today
import moment
from deva import *

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

scheduler = TornadoScheduler(jobstores=jobstores, executors=executors, job_defaults=job_defaults,timezone=pytz.timezone('Asia/Shanghai'))
try:
    scheduler.start()
except:
    pass


# In[ ]:

# In[ ]:


@scheduler.scheduled_job('interval', name='open', seconds=60,start_date='2019-04-03 09:25:00',)
@when_tradedate
def _open():
    'open'>>bus
      
@scheduler.scheduled_job('interval', name='close', seconds=60,start_date='2019-04-03 01:25:30',)
@when_tradedate
def _close():
    'close'>>bus


# In[ ]:


# In[ ]:


scheduler.get_jobs()>>pmap(lambda x:x.next_run_time)>>to_list

from tornado import ioloop
ioloop.IOLoop.current().start()
