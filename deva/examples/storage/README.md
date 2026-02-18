# Signal Store Replay

## 说明
这个示例演示 deva 的存储能力：

- 使用 `NB('signals', key_mode='time')` 持久化实时信号
- 使用 `append()` 以时间键写入事件
- 按时间窗口回放最近数据

## 文件
- `/Users/spark/pycharmproject/deva/deva/examples/storage/signal_store_replay.py`

## 运行
在仓库根目录执行：

```bash
python3 deva/examples/storage/signal_store_replay.py
```

## 你会看到
- 实时日志：每秒一条 `RT ...`
- 告警日志：当 score > 0.9
- 回放日志：每 10 秒回放最近 8 秒信号

## 备注
- 数据默认写入 deva 的 SQLite 存储（通常在 `~/.deva/nb.sqlite`）
- 事件流场景建议使用 `key_mode='time'` + `append()`
- 配置类数据建议使用默认 `key_mode='explicit'`
