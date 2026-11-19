# -*- coding: utf-8 -*-
"""v1.7.0 最终验收：用户真实工程 debug.blend 0–200 帧 + 锁定界面开启。

在 v1.6.0 验收脚本基础上多测三件事：
1. 渲染中 3D 视图确实被换成线框、叠加层关闭（VP_DURING）
2. 收尾之后视口原样还回来（VP_AFTER == VP_BEFORE）
3. 锁定期间面板 progress_text 仍照常刷新（面板是唯一进度来源）
"""
import json
import os
import time

import bpy

_TEST_HERE = os.path.dirname(os.path.abspath(__file__))
ADDON = os.path.abspath(os.path.join(_TEST_HERE, "..", "src", "__init__.py"))
HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "final_lock_state.json")
LOCK = os.environ.get("SSR_LOCK", "1") == "1"
PROC = os.environ.get("SSR_PROC", "SUBPROC")

if not hasattr(bpy.types.Scene, "ssr"):
    ns = {"__name__": "__main__", "__file__": ADDON}
    exec(compile(open(ADDON, encoding="utf-8").read(), ADDON, "exec"), ns)
    print("ADDON_EXEC_LOADED", flush=True)

HB = {"n": 0, "last": 0.0, "max_gap": 0.0, "gaps": [], "job_ticks": 0}
PROG = {"samples": [], "last": None, "t0": 0.0}
VP = {"before": None, "during": None, "after": None}
state = {}


def vp_state():
    out = []
    try:
        for win in bpy.context.window_manager.windows:
            screen = getattr(win, "screen", None)
            if screen is None:
                continue
            for area in screen.areas:
                if area.type != "VIEW_3D":
                    continue
                for space in area.spaces:
                    if space.type == "VIEW_3D":
                        out.append({"shading": space.shading.type,
                                    "overlay": bool(space.overlay.show_overlays),
                                    "gizmo": bool(space.show_gizmo)})
    except Exception as exc:
        out.append({"error": str(exc)})
    return out


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
    if VP["during"] is None:
        st = vp_state()
        if st:
            VP["during"] = st
            print("VP_DURING %s" % json.dumps(st, ensure_ascii=False), flush=True)
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
    VP["after"] = vp_state()
    print("VP_AFTER %s" % json.dumps(VP["after"], ensure_ascii=False), flush=True)
    print("VP_RESTORED %s" % (VP["after"] == VP["before"]), flush=True)
    print("FINAL_TEXT %s" % s.progress_text, flush=True)
    print("HEARTBEAT ticks=%d job_ticks=%d max_gap=%.2f gaps_over_1s=%s" % (
        HB["n"], HB["job_ticks"], HB["max_gap"], HB["gaps"][:12]), flush=True)
    print("PROG_SAMPLES %d" % len(PROG["samples"]), flush=True)
    state["final"] = s.progress_text
    state["heartbeat"] = {k: HB[k] for k in ("n", "job_ticks", "max_gap", "gaps")}
    state["progress"] = PROG["samples"]
    state["vp"] = VP
    state["lock"] = LOCK
    state["proc"] = PROC
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
    VP["before"] = vp_state()
    print("VP_BEFORE %s" % json.dumps(VP["before"], ensure_ascii=False), flush=True)
    s.lock_ui = LOCK
    s.render_process = PROC
    print("CONFIG segments=%s out_dir=%s video=%s audio=%s mode=%s lock=%s" % (
        [(g.start, g.end, g.step) for g in s.segments], s.out_dir, s.video_path,
        s.audio_file, s.render_process, s.lock_ui), flush=True)
    state["config"] = {
        "segments": [(g.start, g.end, g.step) for g in s.segments],
        "video": s.video_path,
        "audio": s.audio_file,
        "render_process": s.render_process,
        "lock_ui": s.lock_ui,
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
