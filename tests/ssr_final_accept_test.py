# -*- coding: utf-8 -*-
"""v1.6.0 最终验收：用户真实工程 debug.blend 0–200 帧，独立进程模式，全自动流程。

同时记录三件事：
1. 面板 progress_text 的时间序列（确认「段内 x/201」真的在动）
2. 0.2 s 心跳的最大间隔（确认主循环没被冻住）
3. 最终文案 + 产物信息
"""
import json
import os
import time

import bpy

_TEST_HERE = os.path.dirname(os.path.abspath(__file__))
ADDON = os.path.abspath(os.path.join(_TEST_HERE, "..", "src", "__init__.py"))
HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "final_accept_state.json")

if not hasattr(bpy.types.Scene, "ssr"):
    ns = {"__name__": "__main__", "__file__": ADDON}
    exec(compile(open(ADDON, encoding="utf-8").read(), ADDON, "exec"), ns)
    print("ADDON_EXEC_LOADED", flush=True)

HB = {"n": 0, "last": 0.0, "max_gap": 0.0, "gaps": [], "job_ticks": 0}
PROG = {"samples": [], "last": None, "t0": 0.0}
state = {}


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
    try:
        bpy.context.scene.ssr.progress = bpy.context.scene.ssr.progress
    except Exception:
        pass
    return 0.2


def sample():
    s = bpy.context.scene.ssr
    if not s.running:
        return None
    txt = s.progress_text
    if txt != PROG["last"]:
        PROG["last"] = txt
        PROG["samples"].append([round(time.time() - PROG["t0"], 1), txt])
        print("PROG %5.1fs  %s" % (time.time() - PROG["t0"], txt), flush=True)
    return 1.0


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
        HB["n"], HB["job_ticks"], HB["max_gap"], HB["gaps"][:12]), flush=True)
    print("PROG_SAMPLES %d" % len(PROG["samples"]), flush=True)
    state["final"] = s.progress_text
    state["heartbeat"] = {k: HB[k] for k in ("n", "job_ticks", "max_gap", "gaps")}
    state["progress"] = PROG["samples"]
    try:
        with open(STATE, "w", encoding="utf-8") as fh:
            json.dump(state, fh, ensure_ascii=False, indent=2)
    except OSError as exc:
        print("STATE_WRITE_FAILED %s" % exc, flush=True)
    bpy.app.timers.register(quit_now, first_interval=0.5)
    return None


def setup():
    if bpy.context.window is None:
        return 0.3
    sc = bpy.context.scene
    s = sc.ssr
    print("CONFIG segments=%s out_dir=%s video=%s audio=%s mode=%s" % (
        [(g.start, g.end, g.step) for g in s.segments], s.out_dir, s.video_path,
        s.audio_file, s.render_process), flush=True)
    state["config"] = {
        "segments": [(g.start, g.end, g.step) for g in s.segments],
        "video": s.video_path,
        "audio": s.audio_file,
        "render_process": s.render_process,
        "fps": sc.render.fps,
        "fps_base": sc.render.fps_base,
        "res": [sc.render.resolution_x, sc.render.resolution_y],
        "auto_compose": s.auto_compose,
        "keep_segments": s.keep_segments,
    }
    PROG["t0"] = time.time()
    bpy.app.timers.register(beat, first_interval=0.2)
    bpy.ops.seg_speed.render()
    bpy.app.timers.register(sample, first_interval=1.0)
    bpy.app.timers.register(check, first_interval=0.5)
    return None


bpy.app.timers.register(setup, first_interval=0.5)
