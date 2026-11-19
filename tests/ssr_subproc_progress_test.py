# -*- coding: utf-8 -*-
"""独立进程模式：进度是否在动 + 收尾清理是否干净（30 帧小段，约 50 秒）。"""
import json
import os
import time

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "subproc_progress_state.json")
seen = []


def watch():
    s = bpy.context.scene.ssr
    if s.running:
        seen.append((round(time.time() - t0, 1), s.progress_text))
        return 1.0
    print("FINAL_TEXT %s" % s.progress_text, flush=True)
    for t, txt in seen:
        print("PROG %5.1fs %s" % (t, txt), flush=True)
    tmp = os.path.join(s.out_dir, "_segments_tmp")
    print("TMP_LEFT %s" % sorted(os.path.basename(p) for p in __import__("glob").glob(os.path.join(tmp, "*"))), flush=True)
    with open(STATE, "w", encoding="utf-8") as fh:
        json.dump({"final": s.progress_text, "samples": seen}, fh, ensure_ascii=False, indent=2)
    bpy.app.timers.register(lambda: (print("QUIT", flush=True), bpy.ops.wm.quit_blender(), None)[-1], first_interval=0.5)
    return None


def setup():
    if bpy.context.window is None:
        return 0.3
    global t0
    s = bpy.context.scene.ssr
    seg = s.segments[0]
    seg.start, seg.end, seg.step = 100, 129, 1
    s.auto_compose = False
    s.keep_segments = True
    print("CONFIG mode=%s proc=%s out=%s" % (s.output_mode, s.render_process, s.out_dir), flush=True)
    t0 = time.time()
    bpy.ops.seg_speed.render()
    bpy.app.timers.register(watch, first_interval=1.0)
    return None


bpy.app.timers.register(setup, first_interval=0.5)
