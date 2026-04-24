#!/bin/bash

# 定期获取市场热点的脚本

while true; do
  echo "$(date) - 市场热点检查"
  curl -s http://localhost:8080/api/market/hotspot | jq '.data'
  sleep 300
done
