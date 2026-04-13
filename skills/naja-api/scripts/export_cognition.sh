#!/bin/bash

# 导出认知系统数据的脚本

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
curl -s http://localhost:8080/api/cognition/memory > "cognition_memory_${TIMESTAMP}.json"
echo "数据已导出到 cognition_memory_${TIMESTAMP}.json"
