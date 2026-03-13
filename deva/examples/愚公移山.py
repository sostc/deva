#初级程序员认为的愚公移山

# while 山还在:
#     盘它
    

    #现实中的愚公移山
# 你瞅那座山，给我好好挖土，记得每天打卡
# 周末该休息休息，每天给我写日报，把前三天工作汇总一下发出来
# 挖到里程碑做个报告，挖完搞个大庆祝
# 挖出问题及时汇报


# 代码特点分析
# 1. 使用了lambda函数定义了一些操作，例如挖土、打卡、周末放假等，这使得代码更加简洁和灵活。
# 2. 使用了流式处理（Stream）来处理挖土项目，能够实时地处理和响应挖土过程中的事件。
# 3. 代码中使用了多种数据结构，例如列表（山）和流（挖土项目、异常管理），这使得代码能够更好地处理不同类型的数据。
# 4. 代码中使用了条件语句和过滤器来处理不同的情况，例如挖土时遇到不同的材料（土、碑、平等），这使得代码能够根据不同的情况执行不同的操作。
# 5. 代码中使用了print语句来输出信息，例如打卡、周末放假、移山成功等，这使得代码能够提供实时的反馈信息。
# 6. 代码中使用了异常处理机制，例如当挖土时遇到非土的材料时，代码会抛出异常，这使得代码能够更好地处理错误情况。
# 7. 代码中使用了时间模块（time）来模拟挖土过程中的时间流逝，这使得代码能够更好地模拟实际的挖土过程。


from deva import Stream,concat,print,stdout,warn
import asyncio
import time
import random

# 1. 将山的数据结构改为生成器，节省内存
山 = ['土','土',' 黄金','土','土','碑','土','土','土','土','墓','土','土','土','土','平']
def 生成山():
    for 材料 in ['土','土',' 黄金','土','土','碑','土','土','土','土','墓','土','土','土','土','平']:
        yield 材料

# 2. 将lambda函数改为命名函数，提高可读性
def 挖土(x):
    if x == '土':
        '挖土土ing' >> print
    else:
        # 不抛出异常，而是直接处理
        '发现非土材料: ' + x >> print

def 处理异常(x):
    if '墓' in str(x) or '黄金' in str(x):
        '⚠️⚠️⚠️挖出异常，警察叔叔吗，挖到个国宝' >> print
        # mixer.music.play()

def 打卡(x):
    '<日常打卡>' >> stdout
    return x

def 周末放假(x):
    '🍺🍺周末' >> print

def 移山成功(x):
    '🎉🎉🎈🎈🎉🎉🎈🎈山挖空了' >> print

def 打110(x):
    '⚠️⚠️⚠️挖出异常，警察叔叔吗，挖到个国宝' >> print

def 里程碑(x):
    '😺🐱🐯挖到一块碑，叫做里程碑' >> print

异常管理 = Stream()
挖土项目 = Stream()
日常工作 = 挖土项目.map(打卡)>>(挖土^异常管理)
挖土项目.partition(5)>>周末放假

挖土项目.filter(lambda x:'碑' in x)>>里程碑
挖土项目.filter(lambda x:'平' in x)>>移山成功



异常管理.filter(处理异常) >> warn


def 日报(x):
    '日报：' + (x >> concat('|')) >> print

挖土项目.sliding_window(3)>>日报





# 2. 添加AI辅助决策
def AI分析(x):
    if '黄金' in str(x):
        return '建议：停止挖掘，保护文物'
    return '继续挖掘'

挖土项目.map(AI分析) >> print

# 3. 添加团队协作
团队成员 = ['愚公', '儿子', '孙子', '邻居']

def 分配任务(x):
    执行人 = random.choice(团队成员)
    return f"{执行人}正在处理：{x}"

挖土项目.map(分配任务) >> print

# 4. 添加资源管理系统
资源 = {'铁锹': 3, '推车': 2, '水': 100}

def 消耗资源(x):
    资源['水'] -= 1
    if 资源['水'] < 20:
        '⚠️ 水资源不足，需要补充' >> print

挖土项目 >> 消耗资源

# 5. 添加天气系统

def 模拟天气():
    天气 = random.choice(['晴天', '雨天', '大风'])
    f"今日天气：{天气}" >> print
    return 天气 == '雨天'  # 是否影响工作

def 天气影响(x):
    if 模拟天气():
        '由于天气原因，今日工作效率降低50%' >> print
        time.sleep(2)  # 模拟效率降低

挖土项目.sliding_window(5) >> 天气影响

# 6. 添加成就系统
成就 = set()

def 检查成就(x):
    if '碑' in str(x) and '里程碑' not in 成就:
        成就.add('里程碑')
        '🎖️ 获得成就：发现里程碑' >> print
    if '平' in str(x) and '移山成功' not in 成就:
        成就.add('移山成功')
        '🏆 获得成就：移山成功' >> print

挖土项目 >> 检查成就



# from pygame import mixer # type: ignore
# mixer.init()
# mixer.music.load('wolf.mp3')
# 播放声音 = lambda x:mixer.music.play()
# 异常管理.filter(lambda x:'墓' in str(x))>>播放声音
异常管理>>warn
# 


# 3. 主循环改为异步
async def 主循环():
    for 土 in 生成山():
        土 >> 挖土项目
        await asyncio.sleep(1)

if __name__ == '__main__':
    asyncio.run(主循环())
