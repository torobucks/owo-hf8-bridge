# -*- coding: utf-8 -*-
"""
OWO -> HF8 桥接器 (事件化驱动)
================================

监听游戏外发的 OWO SENSATION 数据 (UDP 54020)，解析触点强度，
映射到 Next Level Racing HF8 的 8 个震动马达 (USB 串口 COM4 @ 115200 8N1.5)。

事件化策略 (解决"背景震动糊、撞击无区分度")：
1. 增量触发 --event-rise：触点强度相对上次上升 >= 该值视为事件，触发全强度驱动
   (撞墙/碰撞时强度从 40 跳到 100，rise=20 必触发；稳定背景 rise~0 不驱动)
2. 强反馈保留 --hold-int：触点强度 >= 该值(默认60)持续驱动，保留推背/高速颠簸感
3. 冲击全震：触点 >= 80 直接全强度，撞击"哐"一下
4. 指数衰减 --decay：事件后旧值逐包衰减 20%，余震约 1 秒，不糊
5. 空闲归零 --idle-timeout：游戏暂停/退出后无数据 2s 全部马达归零

HF8 协议 (Buttplug.io issue #36)：
  P           -> 查询状态，响应 E<scale>,A<mode>
  M<M><I>\r   -> 设置马达 M(0-7) 强度 I(0-255)，无分隔符，回车结尾
  M0右大腿 M1左大腿 M2右臀 M3左臀 M4右背 M5左背 M6右肩 M7左肩

OWO SENSATION 包: {id}*SENSATION*{speed},{dir},{intensity},0,0,0,|{c%p,...}*{tail}
触点 c: 0右胸 1左胸 2右腹 3左腹 4右臂 5左臂 6右背 7左背 8右腰 9左腰 (0-100%)

用法:
  python owo_to_hf8.py [--com COM4] [--port 54020] [--log owo_to_hf8.log]
                        [--scale 2.55] [--min-intensity 25] [--decay 0.8]
                        [--event-rise 20] [--hold-int 60] [--idle-timeout 2.0]
"""
import argparse
import socket
import serial
import sys
import time
from datetime import datetime

# OWO: 0右胸 1左胸 2右腹 3左腹 4右臂 5左臂 6右背 7左背 8右腰 9左腰
# HF8: M0右大腿 M1左大腿 M2右臀 M3左臀 M4右背 M5左背 M6右肩 M7左肩
DEFAULT_MAP = {
    0: 6,   # 右胸  -> M6 右肩
    1: 7,   # 左胸  -> M7 左肩
    2: 0,   # 右腹  -> M0 右大腿
    3: 1,   # 左腹  -> M1 左大腿
    6: 4,   # 右背  -> M4 右背
    7: 5,   # 左背  -> M5 左背
    8: 2,   # 右腰  -> M2 右臀(坐垫)
    9: 3,   # 左腰  -> M3 左臀(坐垫)
}


def log(msg, fh=None):
    """统一日志输出：控制台 + 可选文件。"""
    line = f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] {msg}"
    print(line, flush=True)
    if fh:
        fh.write(line + "\n")
        fh.flush()


def parse_sensation(text):
    """解析 SENSATION 包，返回 (contacts, header) 或 (None, None)。

    contacts: {触点号: 强度0-100}; header: dict(speed, direction, intensity)
    """
    marker = "*SENSATION*"
    idx = text.find(marker)
    if idx < 0:
        return None, None
    body = text[idx + len(marker):]
    if "|" not in body:
        return None, None
    head_part, contacts_part = body.split("|", 1)
    contacts_part = contacts_part.split("*", 1)[0]
    header = {}
    fields = head_part.split(",")
    if len(fields) >= 3:
        try:
            header["speed"] = int(float(fields[0]))
            header["direction"] = int(float(fields[1]))
            header["intensity"] = int(float(fields[2]))
        except ValueError:
            pass
    contacts = {}
    for item in contacts_part.split(","):
        item = item.strip()
        if not item or "%" not in item:
            continue
        try:
            c, p = item.split("%", 1)
            contacts[int(c)] = max(0, min(100, int(float(p))))
        except ValueError:
            continue
    return contacts, header


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--com", default="COM4", help="HF8 串口，默认 COM4")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--bind", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=54020)
    ap.add_argument("--log", default="owo_to_hf8.log")
    ap.add_argument("--scale", type=float, default=2.55,
                    help="触点强度0-100 -> HF8 0-255 倍率，默认 2.55 (100%%)")
    ap.add_argument("--min-intensity", type=int, default=25,
                    help="死区阈值(%%): 低于此值的触点不驱动，默认 25")
    ap.add_argument("--event-rise", type=int, default=20,
                    help="增量阈值(%%): 触点强度相对上次上升超过此值视为事件并全强度驱动，默认 20")
    ap.add_argument("--hold-int", type=int, default=60,
                    help="持续保持阈值(%%): 触点强度持续高于此值则保持驱动(推背/颠簸)，默认 60")
    ap.add_argument("--decay", type=float, default=0.8,
                    help="衰减系数: 每次更新旧值乘以此系数，默认 0.8")
    ap.add_argument("--idle-timeout", type=float, default=2.0,
                    help="空闲归零秒数: 超过该时长无 SENSATION 则全部马达归零，默认 2.0")
    args = ap.parse_args()

    mapping = DEFAULT_MAP
    min_i = args.min_intensity
    event_rise = args.event_rise
    hold_int = args.hold_int
    decay = max(0.0, min(1.0, args.decay))

    # 串口
    ser = serial.Serial(port=args.com, baudrate=args.baud,
                        bytesize=serial.EIGHTBITS, parity=serial.PARITY_NONE,
                        stopbits=serial.STOPBITS_ONE_POINT_FIVE,
                        timeout=1, write_timeout=2)
    ser.reset_input_buffer()
    ser.write(b"P\r")
    time.sleep(0.3)
    resp = ser.read(64)

    # UDP
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    s.bind((args.bind, args.port))
    s.settimeout(0.3)

    with open(args.log, "a", encoding="utf-8") as fh:
        log(f"OWO->HF8 桥接器启动: UDP {args.bind}:{args.port} -> HF8({args.com}) "
            f"[P响应={resp!r}]", fh)
        log(f"映射={mapping} 死区={min_i}% 增量={event_rise}% 保持={hold_int}% "
            f"衰减={decay} 空闲归零={args.idle_timeout}s", fh)

        last_vals = {}    # motor -> 当前发送值
        last_pct = {}     # 触点 -> 上次强度
        last_pkt = time.monotonic()
        pkt_count = 0
        paused = False
        while True:
            now = time.monotonic()
            # 空闲归零检测
            if not paused and (now - last_pkt) > args.idle_timeout:
                for m in list(last_vals.keys()):
                    if last_vals.get(m, 0) != 0:
                        ser.write(f"M{m}0\r".encode("ascii"))
                        last_vals[m] = 0
                paused = True
                log(f"空闲 {args.idle_timeout}s 无数据，全部马达归零", fh)
            try:
                data, addr = s.recvfrom(4096)
            except socket.timeout:
                continue
            except KeyboardInterrupt:
                break
            try:
                text = data.decode("utf-8", errors="replace")
            except Exception:
                text = repr(data)

            low = text.lower()
            if low.strip() == "ping":
                s.sendto(b"okay", addr)
                continue
            if "*auth*" in low:
                s.sendto(b"pong", addr)
                continue
            if "*sensation*" not in low:
                continue

            pkt_count += 1
            last_pkt = time.monotonic()
            if paused:
                paused = False
                log(f"恢复数据流 (pkt#{pkt_count})", fh)

            contacts, header = parse_sensation(text)
            if contacts is None:
                continue

            # 事件化目标计算
            targets = {}
            for c, pct in contacts.items():
                m = mapping.get(c)
                if m is None:
                    continue
                prev = last_pct.get(c, 0)
                rise = pct - prev
                if pct >= min_i and (rise >= event_rise or pct >= hold_int or pct >= 80):
                    targets[m] = min(255, int(round(pct * args.scale)))
                else:
                    targets[m] = 0
                last_pct[c] = pct

            # 指数衰减: effective = max(target, old*decay)
            effective = {}
            for m, v in targets.items():
                old = last_vals.get(m, 0)
                eff = max(v, int(old * decay))
                effective[m] = eff

            # 变化检测 + 下发
            for m, v in effective.items():
                if last_vals.get(m) != v:
                    ser.write(f"M{m}{v}\r".encode("ascii"))
                    last_vals[m] = v

            if pkt_count % 20 == 1:
                hdr = header or {}
                log(f"#SENSATION pkt#{pkt_count} speed={hdr.get('speed')} "
                    f"dir={hdr.get('direction')} contacts={contacts} hf8={effective}", fh)

    ser.close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n已退出")
        sys.exit(0)
