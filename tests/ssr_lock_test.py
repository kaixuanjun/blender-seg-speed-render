# -*- coding: utf-8 -*-
"""「锁定界面」开关验证 + 收益测量。

用法（环境变量控制）：
    $env:SSR_LOCK  = "1" | "0"       锁定界面开/关
    $env:SSR_PROC  = "SUBPROC" | "INPROC"
    $env:SSR_START = "100"           起始帧（默认 100，避开源音频开头的静音）
    $env:SSR_FRAMES = "30"

测什么：
1. 锁定是否真的落到视口上（渲染中 shading == "WIREFRAME"、overlay 关）
2. 渲染结束后是否原样还原
3. 同样的帧数，锁定开/关的墙上时间 + 父进程 CPU 时间
   （CPU 时间才是"界面重绘到底花了多少"的直接证据，wall 受 GPU 波动影响大）
4. 锁定期间面板进度文本是否照常更新
"""
import json
import os
import time

import bpy

_TEST_HERE = os.path.dirname(os.path.abspath(__file__))
ADDON = os.path.abspath(os.path.join(_TEST_HERE, "..", "src", "__init__.py"))
HERE = os.path.dirname(os.path.abspath(__file__))
LOCK = os.environ.get("SSR_LOCK", "1") == "1"
PROC = os.environ.get("SSR_PROC", "INPROC")
FRAMES = int(os.environ.get("SSR_FRAMES", "30"))
START = int(os.environ.get("SSR_START", "100"))
TAG = os.environ.get("SSR_TAG", "lock")
STATE = os.path.join(HERE, "lock_state_%s.json" % TAG)

if not hasattr(bpy.types.Scene, "ssr"):
    ns = {"__name__": "__main__", "__file__": ADDON}
    exec(compile(open(ADDON, encoding="utf-8").read(), ADDON, "exec"), ns)
    print("ADDON_EXEC_LOADED", flush=True)

REC = {"cpu0": 0.0, "cpu": 0.0, "t0": 0.0, "wall": 0.0,
       "during": [], "after": None, "before": None, "prog": [], "last": None}


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
                        out.append({
                            "shading": space.shading.type,
                            "overlay": bool(space.overlay.show_overlays),
                            "gizmo": bool(space.show_gizmo),
                        })
    except Exception as exc:
        out.append({"error": str(exc)})
    return out


def watch():
    s = bpy.context.scene.ssr
    if not s.running:
        return None
    st = vp_state()
    if st and (not REC["during"] or REC["during"][-1] != st):
        REC["during"].append(st)
        print("VP_DURING %s" % json.dumps(st, ensure_ascii=False), flush=True)
    if s.progress_text != REC["last"]:
        REC["last"] = s.progress_text
        REC["prog"].append(s.progress_text)
    return 0.4


def quit_now():
    print("QUIT", flush=True)
    bpy.ops.wm.quit_blender()
    return None


def check():
    s = bpy.context.scene.ssr
    if s.running:
        return 0.5
    REC["wall"] = round(time.time() - REC["t0"], 1)
    REC["cpu"] = round(time.process_time() - REC["cpu0"], 1)
    REC["after"] = vp_state()
    print("VP_AFTER %s" % json.dumps(REC["after"], ensure_ascii=False), flush=True)
    print("WALL %.1f s  CPU %.1f s  frames=%d  per_frame=%.2f s  cpu_per_frame=%.3f s"
          % (REC["wall"], REC["cpu"], FRAMES, REC["wall"] / max(1, FRAMES),
             REC["cpu"] / max(1, FRAMES)), flush=True)
    print("FINAL_TEXT %s" % s.progress_text, flush=True)
    data = {
        "tag": TAG, "lock": LOCK, "proc": PROC, "frames": FRAMES, "start": START,
        "wall": REC["wall"], "cpu": REC["cpu"],
        "per_frame": round(REC["wall"] / max(1, FRAMES), 3),
        "cpu_per_frame": round(REC["cpu"] / max(1, FRAMES), 3),
        "vp_before": REC["before"], "vp_during": REC["during"], "vp_after": REC["after"],
        "final": s.progress_text, "progress_samples": len(REC["prog"]),
        "progress_first": REC["prog"][:1], "progress_last": REC["prog"][-1:],
    }
    try:
        with open(STATE, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
    except OSError as exc:
        print("STATE_FAILED %s" % exc, flush=True)
    bpy.app.timers.register(quit_now, first_interval=0.5)
    return None


def setup():
    if bpy.context.window is None:
        return 0.3
    sc = bpy.context.scene
    s = sc.ssr
    REC["before"] = vp_state()
    print("VP_BEFORE %s" % json.dumps(REC["before"], ensure_ascii=False), flush=True)

    seg = s.segments[0]
    seg.start = START
    seg.end = START + max(1, FRAMES) - 1
    seg.step = 1
    s.render_process = PROC
    s.lock_ui = LOCK
    s.keep_segments = False
    s.auto_compose = True
    print("CONFIG tag=%s lock=%s proc=%s start=%d frames=%d shading_before=%s" % (
        TAG, LOCK, PROC, START, FRAMES,
        [x.get("shading") for x in REC["before"]]), flush=True)

    REC["cpu0"] = time.process_time()
    REC["t0"] = time.time()
    bpy.ops.seg_speed.render()
    bpy.app.timers.register(watch, first_interval=0.2)
    bpy.app.timers.register(check, first_interval=0.5)
    return None


bpy.app.timers.register(setup, first_interval=0.5)
