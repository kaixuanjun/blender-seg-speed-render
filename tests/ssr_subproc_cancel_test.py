# -*- coding: utf-8 -*-
"""停止语义：独立进程模式下点停止应当立刻断掉渲染进程（不再等本段渲完）。"""
import json
import os
import time

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "cancel_state.json")
st = {"t_start": 0.0, "t_cancel": 0.0, "t_stop": 0.0}


def watcher():
    s = bpy.context.scene.ssr
    now = time.time()
    if not st["t_cancel"] and s.running and now - st["t_start"] > 7.0:
        print("CANCEL_AT %.1fs 段内进度=%s" % (now - st["t_start"], s.progress_text), flush=True)
        st["t_cancel"] = now
        s.cancel_flag = True
        return 0.2
    if st["t_cancel"] and not s.running:
        st["t_stop"] = now
        print("STOPPED_AFTER_CANCEL %.2fs" % (now - st["t_cancel"]), flush=True)
        print("FINAL_TEXT %s" % s.progress_text, flush=True)
        tmp = os.path.join(s.out_dir, "_segments_tmp")
        print("TMP_LEFT %s" % sorted(os.path.basename(p) for p in __import__("glob").glob(os.path.join(tmp, "*"))), flush=True)
        with open(STATE, "w", encoding="utf-8") as fh:
            json.dump({"final": s.progress_text,
                       "stop_latency": round(st["t_stop"] - st["t_cancel"], 3)}, fh, ensure_ascii=False, indent=2)
        bpy.app.timers.register(lambda: (print("QUIT", flush=True), bpy.ops.wm.quit_blender(), None)[-1], first_interval=0.5)
        return None
    return 0.2


def setup():
    if bpy.context.window is None:
        return 0.3
    s = bpy.context.scene.ssr
    seg = s.segments[0]
    seg.start, seg.end, seg.step = 0, 200, 1
    s.render_process = "SUBPROC"
    s.auto_compose = False
    print("CONFIG proc=%s seg=%s" % (s.render_process, (seg.start, seg.end, seg.step)), flush=True)
    st["t_start"] = time.time()
    bpy.ops.seg_speed.render()
    bpy.app.timers.register(watcher, first_interval=0.2)
    return None


bpy.app.timers.register(setup, first_interval=0.5)
