---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: 56ee4d762339c717a466c7eb939f0e32_5deb09fbc9db11f18e0e52540064ee0f
    ReservedCode1: vtfjFw9TFYurGslAMhAgd2fYoTaEH6j9ivbduIBsrj+5+YDUIyMoUp3ErRo6/rV1GNrS0F584ae1KvNr71BxqTg6PvWZNkjWZh63T+CZlMw43ZLs4tfMhpMWpV803u9Xa8E/xi8jhG+kChKZWSIEe3LZ3/Rcw+eC2+jCxoXGVI9EuGNPd/lCaVKuu0U=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: 56ee4d762339c717a466c7eb939f0e32_5deb09fbc9db11f18e0e52540064ee0f
    ReservedCode2: vtfjFw9TFYurGslAMhAgd2fYoTaEH6j9ivbduIBsrj+5+YDUIyMoUp3ErRo6/rV1GNrS0F584ae1KvNr71BxqTg6PvWZNkjWZh63T+CZlMw43ZLs4tfMhpMWpV803u9Xa8E/xi8jhG+kChKZWSIEe3LZ3/Rcw+eC2+jCxoXGVI9EuGNPd/lCaVKuu0U=
---

# OWO -> HF8 桥接器 (OWO to HF8 Bridge)

将 **OWO 触觉背心**（游戏外设）的体感数据转换为 **Next Level Racing HF8**（游戏座椅震动垫）的驱动信号，让只支持 OWO 的游戏无需改装即可驱动 HF8 座椅马达。

本项目通过 UDP 监听游戏发出的 OWO SENSATION 文本协议，解析 10 个触点的强度数据，按映射表转换为 HF8 的 8 个震动马达指令，经 USB 串口下发到座椅。内置**事件化驱动策略**，解决"背景震动糊、撞击无区分度"的体验问题。

---

## 功能特性

- 零侵入：不改游戏、不装 OWO 官方驱动，仅监听 UDP 54020 数据包
- 双端兼容：HF8 座椅通过 USB 串口（默认 COM4 @ 115200 8N1.5）连接
- 事件化驱动：增量触发、强反馈保持、冲击全震、指数衰减、空闲归零
- 即插即用：提供 Windows 单文件可执行程序 `owo_to_hf8.exe`，无需安装 Python
- 命令行可调：死区、事件阈值、保持阈值、衰减、倍率等全部可调

---

## 工作原理

### 1. OWO UDP 54020 文本协议

OWO 游戏皮肤/游戏通过 UDP 向 `54020` 端口发送文本数据包，协议包含两类关键交互：

**握手/心跳**：
- 收到 `ping` 文本 -> 回复 `okay`
- 收到包含 `*auth*` 的文本 -> 回复 `pong`

**SENSATION 数据包**：

```
{id}*SENSATION*{speed},{dir},{intensity},0,0,0,|{c%p,...}*{tail}
```

- `speed` / `dir` / `intensity`：包头的速度、方向、整体强度（0-100）
- `c%p,...`：触点列表，`c` 为触点编号（0-9），`p` 为强度百分比（0-100）
- 示例：`12345*SENSATION*80,90,70,0,0,0,|0%100,1%100,6%60*0`

桥接器解析出触点强度后，按触点-马达映射表换算并下发到 HF8。

### 2. HF8 串口 115200 8N1.5 协议

HF8 通过虚拟串口（USB）接收指令，串口参数为 **115200 baud, 8 数据位, 无校验, 1.5 停止位**：

| 指令 | 说明 |
|---|---|
| `P` (回车) | 查询状态，HF8 响应 `E<scale>,A<mode>` |
| `M<M><I>` (回车) | 设置马达 `M`（0-7）强度 `I`（0-255），无分隔符，回车结尾 |

启动时先发送 `P` 探测并读取响应，确认串口与座椅正常。

### 3. 触点 -> 马达映射表

OWO 的 10 个触点（0-9）映射到 HF8 的 8 个马达（M0-M7）：

| OWO 触点 | 位置 | HF8 马达 | 位置 |
|---|---|---|---|
| 0 | 右胸 | M6 | 右肩 |
| 1 | 左胸 | M7 | 左肩 |
| 2 | 右腹 | M0 | 右大腿 |
| 3 | 左腹 | M1 | 左大腿 |
| 6 | 右背 | M4 | 右背 |
| 7 | 左背 | M5 | 左背 |
| 8 | 右腰 | M2 | 右臀（坐垫） |
| 9 | 左腰 | M3 | 左臀（坐垫） |

> 触点 4（右臂）、5（左臂）无对应马达，默认忽略。

---

## 事件化驱动策略

v3 核心思路：**稳定背景不驱动、突变事件全强度、余震指数衰减**。

1. **增量触发**（`--event-rise 20`）：触点强度相对上次**上升超过该阈值**时视为事件，全强度驱动。撞墙/碰撞时强度从 40 跳到 100，上升 60 远超阈值必然触发；稳定背景上升接近 0，不驱动。
2. **强反馈保留**（`--hold-int 60`）：触点强度持续高于该阈值时保持驱动，保留推背、高速颠簸等持续体感。
3. **冲击全震**：触点强度达到 80 直接全强度输出，让撞击"哐"一下。
4. **指数衰减**（`--decay 0.8`）：事件后旧值每包乘以 0.8 衰减，余震约 1 秒自然消退，不拖泥带水。
5. **空闲归零**（`--idle-timeout 2.0`）：超过该时长没有收到 SENSATION（游戏暂停/退出），全部马达归零，避免座椅空震。

---

## 安装与使用

### 方式一：直接使用 exe（推荐，无需 Python）

下载 `owo_to_hf8.exe`，在 PowerShell / CMD 中运行：

```powershell
.\owo_to_hf8.exe
```

默认参数即可工作：UDP 监听 `0.0.0.0:54020`，串口 `COM4 @ 115200`。按 `Ctrl+C` 退出。

### 方式二：从源码运行

需要 Python 3.8+：

```bash
pip install -r requirements.txt
python owo_to_hf8.py
```

### 命令行参数

| 参数 | 默认值 | 说明 |
|---|---|---|
| `--com` | `COM4` | HF8 串口端口 |
| `--baud` | `115200` | 串口波特率 |
| `--bind` | `0.0.0.0` | UDP 监听地址 |
| `--port` | `54020` | UDP 监听端口（OWO 默认发送端口） |
| `--log` | `owo_to_hf8.log` | 日志文件路径 |
| `--scale` | `2.55` | 触点强度 0-100 到 HF8 0-255 的倍率（2.55 即满量程） |
| `--min-intensity` | `25` | 死区阈值（%），低于此值的触点不驱动 |
| `--event-rise` | `20` | 事件增量阈值（%），上升超过此值视为事件全强度驱动 |
| `--hold-int` | `60` | 保持阈值（%），触点强度持续高于此值则保持驱动 |
| `--decay` | `0.8` | 衰减系数，事件后旧值每包乘以此系数 |
| `--idle-timeout` | `2.0` | 空闲归零秒数，超过该时长无数据则全部马达归零 |

常用示例：

```powershell
# 指定串口与 UDP 端口
.\owo_to_hf8.exe --com COM7 --port 54020

# 降低死区，让轻微震动也能感知
.\owo_to_hf8.exe --min-intensity 10 --scale 2.0

# 更"跟手"的撞击反馈：提高事件阈值避免误触、加快衰减
.\owo_to_hf8.exe --event-rise 30 --decay 0.7
```

### 快速上手指南

1. 将 HF8 座椅 USB 连接电脑，确认设备管理器中出现的 COM 端口号（默认按 COM4，可用 `--com` 指定）
2. 启动桥接器：`.\owo_to_hf8.exe`（启动时会向 HF8 发送 `P` 查询，日志中可见响应）
3. 启动游戏并启用 OWO 触觉（如使用 OWO Skin 或支持 OWO 的游戏/皮肤插件）
4. 观察日志中的 `#SENSATION` 行，确认数据包与触点强度；坐上座椅感受震动

---

## 故障排查

| 现象 | 可能原因 | 解决办法 |
|---|---|---|
| 启动报 `SerialException` / 找不到串口 | HF8 未连接或 COM 端口不对 | 设备管理器确认 COM 号，用 `--com` 指定；检查 USB 线 |
| 日志中 `P响应=b''` | 串口连通但 HF8 未应答 | 确认座椅已通电、驱动正常；重启桥接器重试 |
| 完全没有数据包 | 游戏未开启 OWO 触觉 / UDP 端口不符 | 游戏内开启 OWO 输出；确认端口 54020；检查防火墙是否放行 |
| 有数据但座椅不震 | 映射触点未命中 / 强度低于死区 | 观察日志 contacts 值；调低 `--min-intensity`、调高 `--scale` |
| 座椅一直微震（糊） | 背景震动持续、衰减不够快 | 调高 `--event-rise`、调低 `--decay` |
| 撞击无爆发感 | 事件阈值过高或倍率不足 | 调低 `--event-rise`、调高 `--scale` 至 2.55 |
| 游戏退出后座椅仍震 | 数据流停止但未触发空闲归零 | 确认 `--idle-timeout` 生效（默认 2 秒）；手动 Ctrl+C 退出 |

---

## 项目结构

```
owo-hf8-bridge/
├── owo_to_hf8.py      # Python 源文件（全部命令行参数）
├── owo_to_hf8.exe     # Windows 单文件可执行程序（PyInstaller 打包，内置 pyserial）
├── requirements.txt   # Python 依赖
├── README.md          # 中文说明
└── README_EN.md       # English README
```

### 从源码自行打包 exe

```bash
pip install pyinstaller pyserial
pyinstaller --onefile --name owo_to_hf8 --hidden-import serial \
    --hidden-import serial.tools.list_ports owo_to_hf8.py
```

---

## 免责声明

- 本项目为个人开源爱好项目，与 OWO、Next Level Racing 均无任何官方关联。
- 使用本项目时请自行承担风险。请勿在驾驶、剧烈运动等危险场景中使用震动反馈。
- 长时间高频率震动可能引起不适，请适度使用；若出现身体不适请立即停止。
- 本项目仅用于合法、合规的个人娱乐用途，禁止用于任何违法或违规场景。

---

## License

MIT License. See [LICENSE](LICENSE) for details. *(如需，可自行添加 LICENSE 文件)*
*（内容由AI生成，仅供参考）*
