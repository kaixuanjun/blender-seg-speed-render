# -*- coding: utf-8 -*-
"""真机 UI 响应性测试：debug.blend 跑 0–200 段，同时用独立 timer 打心跳。

关键指标 HEARTBEAT：渲染期间主循环还能被调到多少次、最大间隔多少秒。
旧版（阻塞渲染）这个间隔会等于整段渲染时长（约 270 秒）；
1.5.0 改成 Render job 之后应该稳定在 0.2~0.3 秒。
"""
import json
import os
import time

import bpy

_TEST_HERE = os.path.dirname(os.path.abspath(__file__))
ADDON = os.path.abspath(os.path.join(_TEST_HERE, "..", "src", "__init__.py"))
HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "real_ui_state.json")

if not hasattr(bpy.types.Scene, "ssr"):
    ns = {"__name__": "__main__", "__file__": ADDON}
    exec(compile(open(ADDON, encoding="utf-8").read(), ADDON, "exec"), ns)
    print("ADDON_EXEC_LOADED", flush=True)

HB = {"n": 0, "last": 0.0, "max_gap": 0.0, "gaps": [], "job_ticks": 0}
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
    # 顺手碰一下 UI：能改属性说明主线程有在跑
    try:
        bpy.context.scene.ssr.progress = bpy.context.scene.ssr.progress
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
    state["final"] = s.progress_text
    state["heartbeat"] = {k: HB[k] for k in ("n", "job_ticks", "max_gap", "gaps")}
    try:
        with open(STATE, "w", encoding="utf-8") as fh:
            json.dump(state, fh, ensure_ascii=False, indent=2)
    except OSError:
        pass
    bpy.app.timers.register(quit_now, first_interval=0.5)
    return None


def setup():
    if bpy.context.window is None:
        return 0.3
    sc = bpy.context.scene
    s = sc.ssr
    print("CONFIG segments=%s out_dir=%s video=%s audio=%s" % (
        [(g.start, g.end, g.step) for g in s.segments], s.out_dir, s.video_path, s.audio_file),
        flush=True)
    state["config"] = {
        "segments": [(g.start, g.end, g.step) for g in s.segments],
        "video": s.video_path,
        "audio": s.audio_file,
        "fps": sc.render.fps,
        "res": [sc.render.resolution_x, sc.render.resolution_y],
    }
    bpy.app.timers.register(beat, first_interval=0.2)
    bpy.ops.seg_speed.render()
    bpy.app.timers.register(check, first_interval=0.5)
    return None


bpy.app.timers.register(setup, first_interval=0.5)
