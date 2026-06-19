---
name: troubleshooting
description: 故障诊断指南。当工具返回错误时参考此文档排查。
---

# 故障诊断

## 诊断策略
- **先查状态，再操作**：永远先用 `_get_status` 工具
- **从简单到复杂**：先查连接和供电，再深排硬件
- **给用户可操作的建议**，不只报错

## 水冷机无法连接
1. 检查可用的串口列表
2. 确认设备供电
3. 检查 MODBUS 地址和波特率

## 温度降不下来
1. 确认 chiller_start 已执行
2. 检查冷却液是否充足
3. 检查环境温度

## 探测器采集失败
1. 检查 receiver 是否运行 → detector_get_status
2. 检查探测器连接
3. 尝试 disconnect → load_config 重新连接

## 增益图异常
1. 确认使用了正确的基线文件
2. 抽查几个像素 → processing_fit_pixel
3. 对比不同区域的增益值
