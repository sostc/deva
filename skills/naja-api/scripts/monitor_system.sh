#!/bin/bash

# 监控系统状态的脚本

while true; do
  echo "$(date) - 系统状态检查"
  curl -s http://localhost:8080/api/system/status | jq '.data.overall'
  sleep 60
done
