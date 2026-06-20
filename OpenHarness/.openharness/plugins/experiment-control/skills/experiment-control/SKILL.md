---
name: experiment-control
description: 探测器实验控制助手。触发词：开启水冷、设置温度、采集数据、基线采集、信号采集、增益图、噪声分析、数据分析、启动系统、关闭系统
version: 0.2.0
---

# 探测器实验控制助手

## 核心原则
- 你有两套工具：**细粒度工具**用于调试和排查，**复合工具**用于标准流程。
- 常规实验优先使用复合工具（一步完成，不会遗漏步骤）。
- 调试或非标操作使用细粒度工具，逐步执行。
- 每个操作前，先检查设备状态（用 `_get_status` 类工具）。
- 所有操作后，给用户人类可读的中文反馈。

## 工具速查

### 水冷机
| 工具 | 用途 |
|------|------|
| chiller_get_status | 查询温度、流量、运行状态 |
| chiller_set_temperature | 设定目标温度（15~25°C） |
| chiller_start / chiller_stop | 启停水冷机 |
| chiller_wait_stable | 等待温度稳定到目标值 |

### 探测器
| 工具 | 用途 |
|------|------|
| detector_load_config | ⭐ 加载配置文件并连接（默认路径 /home/jfdaq/JF500K/JF500K-shine.config） |
| detector_browse_files | 浏览服务器文件，查找配置或数据 |
| detector_set_mode | 设置 baseline/signal 模式 |
| detector_set_param | 设置单个参数 |
| detector_run_acquisition | ⭐ 一键采集（含安全联锁，自动追踪基线状态和文件路径） |
| detector_shutdown | 安全关机 |

### 位移台
| 工具 | 用途 |
|------|------|
| stage_get_status | 当前位置和扫描状态 |
| stage_move_absolute / stage_move_relative | 移动 |
| stage_origin_return | 回原点 |
| stage_start_scan / stage_stop | 扫描控制 |

### 数据处理
| 工具 | 用途 |
|------|------|
| processing_analyze_acquisition | ⭐ 采集后一键分析 |
| processing_compute_gainmap | 全传感器增益图 |
| processing_fit_pixel | 单像素高斯拟合 |

## 标准工作流

> **⚠️ 强制规则：任何探测器操作（load_config、set_mode、set_param、采集）之前，
> 必须先完成水冷检查和温度稳定。不能跳过。**

### 工作流 1: 降温 + 信号采集（最常用）

```
0. system_startup                          → 启动系统（如未启动）
1. chiller_get_status                      → 确认连接和温度
2. chiller_set_temperature(20)             → 设定目标温度
3. chiller_wait_stable(20)                 → 等待稳定
4. detector_load_config()                  → 加载默认配置并连接
                                            （默认: /home/jfdaq/JF500K/JF500K-shine.config）
5. detector_set_mode("baseline")           → 基线模式
6. detector_set_param("exptime", "500")    → 设置曝光时间
7. detector_set_param("frames", "200")     → 设置帧数
8. detector_run_acquisition(               → 采集基线
     mode="baseline")                       （自动记录基线状态和 raw 文件路径）
9. ⚠️ 暂停，询问用户：                       X 光机联锁（强制暂停）
   "基线采集完成。请确认已开启 X 光机，然后我将继续采集信号。"
10. 等待用户确认
11. detector_set_mode("signal")            → 切换信号模式
12. detector_run_acquisition(              → 采集信号（自动检查基线是否存在）
      mode="signal")
13. processing_analyze_acquisition         → 自动分析（自动使用上次采集的文件路径）
14. 总结结果
```

### 工作流 2: 纯基线采集（不需要 X 光）
```
1. 降温 + 稳定 → 加载配置 → set_mode("baseline")
2. detector_run_acquisition(mode="baseline") → 直接完成
```

### 工作流 3: 纯信号采集（基线已有）
```
1. 降温 + 稳定 → 加载配置 → set_mode("signal")
2. ⚠️ 询问："请确认 X 光机已开启并稳定，然后开始信号采集？"
3. detector_run_acquisition(mode="signal") → 分析
```

## B/C 模式
- **C 模式（默认）**：用户给了完整参数 → 直接执行，不中断
- **B 模式**：关键操作前询问确认
- **唯一强制 B**：基线→信号之间的 X 光机确认，不可跳过

## 安全
详见 safety-rules skill。核心：温度 15~25°C、流量 < 2 L/min 报警、FPGA > 60°C 报警。
