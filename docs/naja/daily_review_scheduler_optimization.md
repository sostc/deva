# DailyReviewScheduler 调度优化

> 2026-04-22 精准等待优化

## 背景

DailyReviewScheduler 负责在市场盘后自动触发复盘任务：
- A股盘后：15:30 后（北京时间）
- 美股盘后：04:00/05:00 后（北京时间，夏令时/冬令时）

## 优化前问题

旧的 `_run_loop` 实现采用轮询检查模式：
```python
while self._running:
    self._check_and_trigger_replay(market='a_share', now=now)
    self._check_and_trigger_replay(market='us_share', now=now)
    sleep_time = min(60, (next_check - now).total_seconds())
    log.info(f"下次检查: {next_check}, 等待{sleep_time:.0f}秒")
    self._stop_event.wait(max(10, sleep_time))
```

**问题**：
1. 每 60 秒检查一次，产生大量无意义日志
2. 美股复盘完成后仍继续轮询等待 A 股时间
3. 日志噪音干扰正常运维监控

## 优化后方案

采用精准等待模式：

### 核心方法 `_calculate_next_target`
```python
def _calculate_next_target(self, now: datetime):
    """计算下一个复盘目标时间"""
    targets = []
    
    # A 股复盘目标（工作日 15:30）
    if not self._check_already_replayed_today(market='a_share'):
        if now.weekday() < 5:
            target_a = now.replace(hour=15, minute=30, second=0, microsecond=0)
            if target_a <= now:
                target_a = now + timedelta(seconds=1)
            targets.append((target_a, 'a_share'))
    
    # 美股复盘目标（04:00，保守值覆盖夏令时）
    if not self._check_already_replayed_today(market='us_share'):
        target_us = now.replace(hour=4, minute=0, second=0, microsecond=0)
        if target_us <= now:
            target_us += timedelta(days=1)
        targets.append((target_us, 'us_share'))
    
    if not targets:
        return None, None
    
    targets.sort(key=lambda x: x[0])
    return targets[0]
```

### 新主循环
```python
def _run_loop(self):
    while self._running and not self._stop_event.is_set():
        now = datetime.now()
        target_time, market = self._calculate_next_target(now)
        
        if target_time is None:
            # 今天两个市场都已复盘，等待到明天凌晨
            tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            wait_seconds = (tomorrow - now).total_seconds()
            log.info(f"今天复盘已完成，等待到 {tomorrow.strftime('%Y-%m-%d %H:%M')}")
            self._stop_event.wait(min(wait_seconds, 3600))
            continue
        
        wait_seconds = (target_time - now).total_seconds()
        log.info(f"精准等待: 目标时间={target_time.strftime('%H:%M')}, "
                 f"市场={market}, 等待={wait_seconds:.0f}秒")
        self._stop_event.wait(wait_seconds)
        
        # 到达目标时间，触发复盘
        log.info(f"到达目标时间，触发 {market} 复盘")
        self._trigger_replay(market=market, phase='post_market')
```

## 日志对比

### 优化前
```
[05:16:47] [INFO] 下次检查: 2026-04-22 15:30:00, 等待 60 秒
[05:17:47] [INFO] 下次检查: 2026-04-22 15:30:00, 等待 60 秒
[05:18:47] [INFO] 下次检查: 2026-04-22 15:30:00, 等待 60 秒
...（每分钟一条）
```

### 优化后
```
[05:16:47] [INFO] 精准等待: 目标时间=15:30, 市场=a_share, 等待 37200 秒
# 直接 sleep 到 15:30，期间无日志噪音
[15:30:00] [INFO] 到达目标时间，触发 a_share 复盘
```

## 架构设计

### 状态持久化
复盘状态通过 `naja_daily_review_state` 表持久化：
```python
REPLAY_STATE_TABLE = "naja_daily_review_state"

# 存储键
last_a_share_post_market_review_date  # A 股复盘日期
last_us_share_post_market_review_date  # 美股复盘日期
```

### 中断恢复机制
1. **系统重启**：从持久化状态恢复，检查今天是否已复盘
2. **时钟事件触发**：保留 `_on_trading_clock_event` 作为事件触发补充
3. **复盘失败**：不标记为已复盘，下次唤醒时重试

### 事件驱动补充
```python
def _on_trading_clock_event(self, event: dict):
    """处理交易时钟事件"""
    phase = event.get('phase')
    market = event.get('market', 'CN')
    
    if phase == 'post_market':
        self._schedule_replay(market=market, phase='post_market', delay_seconds=30)
```

## 文件变更

- `deva/naja/strategy/daily_review_scheduler.py`
  - 新增 `_calculate_next_target` 方法
  - 重构 `_run_loop` 为精准等待模式
  - 移除 `_check_and_trigger_replay` 和 `_get_next_check_time`
  - 优化日志级别，减少噪音

## 测试要点

1. **正常流程**：A 股/美股盘后自动触发复盘
2. **中断恢复**：系统重启后从持久化状态恢复
3. **日志验证**：确认不再有每分钟轮询日志
4. **夏令时处理**：美股时间保守取 04:00 覆盖夏令时