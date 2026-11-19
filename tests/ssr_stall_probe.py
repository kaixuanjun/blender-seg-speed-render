# -*- coding: utf-8 -*-
"""停顿归因探针：同一场景、同一帧段，只把输出模式从 VIDEO 换成 PNG，
看主循环的最大停顿是否仍然等于单帧渲染时间。

VIDEO 模式实测 max_gap=2.22s（每帧 1.3s 左右）；
如果 PNG 模式仍 1.3s → 停顿来自 EEVEE 渲染本身；
如果 PNG 掉到 0.3s 以下 → 停顿来自 ffmpeg 编码，可以把编码挪到段后做。
"""
import json
import os
import time

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "stall_state.json")

HB = {"n": 0, "last": 0.0, "max_gap": 0.0, "gaps": [], "job_ticks": 0}


def beat():
    now = time.time()
    if HB["last"]:
        gap = now - HB["last"]
        if gap > HB["max_gap"]:
            HB["max_gap"] = gap
        if gap > 1.0:
            HB["gaps"].append(round(gap, 2))
    HB["last"] = now
    HB["n"] += 1
    try:
        if bpy.app.is_job_running("RENDER"):
            HB["job_ticks"] += 1
    except Exception:
        pass
    return 0.2


def quit_now():
    print("QUIT", flush=True)
    bpy.ops.wm.quit_blender()
    return None


def check():
    s = bpy.context.scene.ssr
    if s.running:
        return 0.5
    print("FINAL_TEXT %s" % s.progress_text, flush=True)
    print("HEARTBEAT ticks=%d job_ticks=%d max_gap=%.2f gaps_over_1s=%s" % (
        HB["n"], HB["job_ticks"], HB["max_gap"], HB["gaps"][:10]), flush=True)
    with open(STATE, "w", encoding="utf-8") as fh:
        json.dump({"final": s.progress_text, "heartbeat": {k: HB[k] for k in ("n", "job_ticks", "max_gap", "gaps")}},
                  fh, ensure_ascii=False, indent=2)
    bpy.app.timers.register(quit_now, first_interval=0.5)
    return None


def setup():
    if bpy.context.window is None:
        return 0.3
    s = bpy.context.scene.ssr
    s.output_mode = "PNG"
    s.out_dir = os.path.join(HERE, "tmp_stall") + os.sep
    seg = s.segments[0]
    seg.start, seg.end, seg.step = 100, 119, 1
    try:
        seg.auto_compose = False
    except AttributeError:
        pass
    s.auto_compose = False
    print("CONFIG mode=%s out_dir=%s" % (s.output_mode, s.out_dir), flush=True)
    bpy.app.timers.register(beat, first_interval=0.2)
    bpy.ops.seg_speed.render()
    bpy.app.timers.register(check, first_interval=0.5)
    return None


bpy.app.timers.register(setup, first_interval=0.5)
