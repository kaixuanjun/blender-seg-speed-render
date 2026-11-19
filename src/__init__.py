# -*- coding: utf-8 -*-
"""分段倍速渲染 —— Blender 插件

在一条时间线上按段使用不同帧步长（如 1 / 4），实现局部倍速并减少渲染时间。

两种输出模式：
  - 视频直出：每段直接编码成 mp4，最后 ffmpeg 无损拼接成一条成片（省磁盘）
  - PNG 序列：连续编号的图片，便于中断续渲与后期调色

位置：3D 视图 → 按 N → 侧栏标签「分段倍速」
"""

VERSION = "1.8.0"

import atexit
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time

import bpy
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    EnumProperty,
    FloatProperty,
    IntProperty,
    StringProperty,
)

bl_info = {
    "name": "分段倍速渲染 Segment Speed Render",
    "author": "Lumina",
    "version": (1, 1, 0),
    "blender": (4, 2, 0),
    "location": "3D 视图 > 侧栏(N) > 分段倍速",
    "description": "同一条时间线分段使用不同帧步长，实现局部倍速并减少渲染时间",
    "category": "Render",
}

ADDON_ID = "seg_speed_render"

# ----------------------------------------------------------------------------
# 数据结构
# ----------------------------------------------------------------------------


class SSRSegment(bpy.types.PropertyGroup):
    start: IntProperty(name="起始帧", default=1, soft_min=-100000, soft_max=100000)
    end: IntProperty(name="结束帧", default=24, soft_min=-100000, soft_max=100000)
    step: IntProperty(name="帧步长", default=1, min=1, max=1000)

    def frame_count(self):
        if self.end < self.start:
            return 0
        return len(range(self.start, self.end + 1, max(1, self.step)))


def _scene_items(self, context):
    items = [("", "当前场景", "使用当前活动场景的序列编辑器")]
    try:
        for sc in bpy.data.scenes:
            items.append((sc.name, sc.name, "从场景 %s 取音轨" % sc.name))
    except Exception:
        pass
    return items

class SSRSettings(bpy.types.PropertyGroup):
    segments: CollectionProperty(type=SSRSegment)
    active_index: IntProperty(default=0)

    output_mode: EnumProperty(
        name="输出模式",
        items=[
            ("VIDEO", "视频直出", "每段直接编码成 mp4，最后拼接成一条，最省磁盘"),
            ("PNG", "PNG 序列", "连续编号图片，可中断续渲、便于后期"),
        ],
        default="VIDEO",
    )

    render_process: EnumProperty(
        name="渲染执行方式",
        description="独立进程：另开一个 Blender 后台渲染，界面完全不卡，可随时中断；本进程更省内存，但每帧渲染时会短暂卡一下",
        items=[
            ("SUBPROC", "独立进程", "后台 Blender 渲染，界面零卡顿，停止立即生效（单段略慢）"),
            ("INPROC", "本进程", "在界面进程里渲染，不额外占内存，每渲染一帧界面停顿一下"),
        ],
        default="SUBPROC",
    )

    lock_ui: BoolProperty(
        name="锁定界面",
        description="渲染期间关掉 3D 视图的实时显示（切成线框 + 取消叠加层 + 只重绘侧栏），"
                    "把 GPU 和重绘时间全留给渲染；渲染结束自动还原",
        default=False,
    )

    out_dir: StringProperty(
        name="输出目录",
        description="成片与临时段文件的放置位置",
        default="//render_seq",
        subtype="DIR_PATH",
    )
    prefix: StringProperty(name="文件名前缀", default="shot")
    fps: IntProperty(
        name="播放帧率",
        description="成片帧率。与场景不一致时以这里为准",
        default=24, min=1, max=240,
    )
    fps_base: FloatProperty(
        name="帧率基数",
        description="用于 23.976 这类非整数帧率。24/1.001 = 23.976",
        default=1.0, min=0.01, max=10.0, precision=4,
    )
    auto_shutter: BoolProperty(
        name="自动缩放运动模糊快门",
        description="快放段的快门时间按 1/步长 缩小，避免跨多帧糊成一片",
        default=True,
    )
    auto_compose: BoolProperty(name="完成后合成视频", default=True)
    quality: EnumProperty(
        name="画质",
        description="H.264 恒定质量（CRF）。数值越小画质越好、文件越大",
        items=[
            ("PERC_LOSSLESS", "几乎无损 CRF17", "肉眼无差，文件大"),
            ("HIGH", "高质量 CRF20", "默认，适合成片交付"),
            ("MEDIUM", "标准 CRF23", "体积与画质平衡"),
            ("LOW", "小体积 CRF26", "预览、草稿用"),
            ("VERYLOW", "极小 CRF29", "只求能看"),
        ],
        default="HIGH",
    )
    keep_segments: BoolProperty(
        name="保留分段文件",
        description="拼接完成后不删除中间段文件，便于单独检查某一段",
        default=False,
    )
    video_path: StringProperty(
        name="成片路径",
        default="//seg_speed.mp4",
        subtype="FILE_PATH",
    )
    ffmpeg_path: StringProperty(
        name="ffmpeg 路径",
        description="留空则自动查找：系统 PATH、~/bin、C:\\ffmpeg\\bin",
        default="",
        subtype="FILE_PATH",
    )

    audio_mode: EnumProperty(
        name="音频来源",
        items=[
            ("AUTO", "自动", "有 VSE 音轨就用它，没有再退回音频文件，都没有就不加音轨"),
            ("NONE", "无音频", "成片不带音轨"),
            ("FILE", "音频文件", "指定一个音频文件，按时间线对齐并随段变速"),
            ("SCENE", "场景混音", "从视频序列编辑器(VSE)的音轨混出音频，再随段变速"),
        ],
        default="AUTO",
    )
    audio_scene: EnumProperty(
        name="音频场景",
        description="从哪个场景的序列编辑器取音轨",
        items=_scene_items,
    )
    audio_file: StringProperty(
        name="音频文件",
        description="配乐或对白；第 1 帧对应音频开头（可用偏移微调）",
        default="",
        subtype="FILE_PATH",
    )
    audio_offset: FloatProperty(
        name="起始偏移(秒)",
        description="音频整体相对时间线起点的偏移，正数=音频推后",
        default=0.0,
        soft_min=-60.0,
        soft_max=60.0,
    )
    audio_volume: FloatProperty(
        name="音量",
        default=1.0, min=0.0, max=4.0, soft_min=0.0, soft_max=2.0,
    )
    audio_follow_speed: BoolProperty(
        name="随段变速",
        description="快放段的音频同步加速，保持与画面口型/节奏对齐",
        default=True,
    )

    # 运行时状态（不存文件）
    running: BoolProperty(default=False, options={"SKIP_SAVE"})
    cancel_flag: BoolProperty(default=False, options={"SKIP_SAVE"})
    progress: FloatProperty(default=0.0, min=0.0, max=1.0, options={"SKIP_SAVE"})
    progress_text: StringProperty(default="", options={"SKIP_SAVE"})
    est_seconds: FloatProperty(default=0.0, options={"SKIP_SAVE"})


# ----------------------------------------------------------------------------
# 工具函数
# ----------------------------------------------------------------------------


def _abs_dir(path):
    p = bpy.path.abspath(path)
    if not p:
        p = "render_seq"
    if not os.path.isabs(p):
        base = os.path.dirname(bpy.data.filepath) if bpy.data.filepath else os.getcwd()
        p = os.path.join(base, p)
    return os.path.normpath(p)


def _abs_file(path, fallback="seg_speed.mp4"):
    p = bpy.path.abspath(path or fallback)
    if not p:
        p = fallback
    if not os.path.isabs(p):
        base = os.path.dirname(bpy.data.filepath) if bpy.data.filepath else os.getcwd()
        p = os.path.join(base, p)
    if not os.path.splitext(p)[1]:
        p += ".mp4"
    return os.path.normpath(p)


def _segment_frames(seg):
    if seg.end < seg.start:
        return []
    return list(range(seg.start, seg.end + 1, max(1, seg.step)))


def _total_frames(settings):
    return sum(len(_segment_frames(s)) for s in settings.segments)


def _find_exe(name, explicit=""):
    if explicit:
        p = bpy.path.abspath(explicit)
        if p and os.path.isfile(p):
            return p
        p2 = p if p.lower().endswith(".exe") else p + ".exe"
        if os.path.isfile(p2):
            return p2
    p = shutil.which(name)
    if p:
        return p
    for cand in (
        os.path.join(os.path.expanduser("~"), "bin", name + ".exe"),
        r"C:\ffmpeg\bin\ffmpeg.exe",
        os.path.join(
            os.path.dirname(bpy.app.binary_path), "ffmpeg.exe"
        ),
    ):
        if os.path.isfile(cand):
            return cand
    return None


def _python_exe():
    """Blender 自带的 python.exe（看门狗用它，比再起一个 Blender 轻得多）。

    Blender 5.x 的布局：<安装目录>/<版本>/python/bin/python.exe，sys.prefix 指向前者。
    """
    prefix = getattr(sys, "prefix", "") or ""
    cands = [os.path.join(prefix, "bin", "python.exe"),
             os.path.join(prefix, "bin", "python3.exe")]
    base = os.path.dirname(bpy.app.binary_path or "")
    if base:
        cands.append(os.path.join(base, "python", "bin", "python.exe"))
    for cand in cands:
        if cand and os.path.isfile(cand):
            return cand
    return sys.executable


def _tag_redraw(context=None, panel_only=None):
    """让界面刷新。

    panel_only=True（「锁定界面」模式）时只重绘侧栏 / 属性编辑器 / 标题栏，
    3D 视图的内容区一个像素都不重画 —— 视口里的 EEVEE 实时显示就不会被
    每次进度更新带着跑一遍，GPU 全留给渲染进程。

    panel_only=None 表示自动：跟着当前会话的 ui_locked 走，调用点不用改。
    """
    if panel_only is None:
        try:
            sess = _RenderSession._active
            panel_only = bool(sess is not None and getattr(sess, "ui_locked", False))
        except Exception:
            panel_only = False
    try:
        windows = bpy.context.window_manager.windows
    except Exception:
        return
    for win in windows:
        screen = getattr(win, "screen", None)
        if screen is None:
            continue
        for area in screen.areas:
            if not panel_only:
                if area.type == "VIEW_3D":
                    area.tag_redraw()
                continue
            if area.type == "PROPERTIES":
                area.tag_redraw()
                continue
            if area.type != "VIEW_3D":
                continue
            for region in area.regions:
                if region.type in {"UI", "HEADER", "TOOL_HEADER"}:
                    try:
                        region.tag_redraw()
                    except Exception:
                        pass


def _hide_console_flag():
    return 0x08000000 if os.name == "nt" else 0


CRF_TABLE = {
    "LOSSLESS": 0,
    "PERC_LOSSLESS": 17,
    "HIGH": 20,
    "MEDIUM": 23,
    "LOW": 26,
    "VERYLOW": 29,
    "LOWEST": 32,
}


def _real_fps(s):
    try:
        base = float(s.fps_base) or 1.0
    except Exception:
        base = 1.0
    return max(0.001, float(s.fps) / base)


def _crf_of(quality):
    return CRF_TABLE.get(quality, 20)


def _configure_video(scene, quality="HIGH", fps=None):
    r = scene.render
    iset = r.image_settings
    # Blender 4.5+ / 5.x：先切 media_type 为 VIDEO，file_format 才会出现 FFMPEG
    try:
        iset.media_type = "VIDEO"
    except Exception:
        pass
    try:
        iset.file_format = "FFMPEG"
    except Exception:
        pass
    try:
        r.ffmpeg.format = "MPEG4"
        r.ffmpeg.codec = "H264"
        r.ffmpeg.constant_rate_factor = quality
        r.ffmpeg.ffmpeg_preset = "GOOD"
        r.ffmpeg.audio_codec = "NONE"
        # 关键帧间隔：Blender 默认 18 帧（0.75 秒）过于密集，纯属浪费码率。
        # 每段渲染都从 IDR 起，段内拉长到 4 秒不影响拼接。
        use_fps = float(fps or r.fps or 24)
        r.ffmpeg.gopsize = max(12, int(round(use_fps * 4)))
    except Exception:
        pass
    r.use_file_extension = True


def _configure_png(scene):
    r = scene.render
    iset = r.image_settings
    try:
        iset.media_type = "IMAGE"
    except Exception:
        pass
    try:
        iset.file_format = "PNG"
        iset.color_mode = "RGB"
    except Exception:
        pass
    r.use_file_extension = True


_DRIVER_SRC = r'''# -*- coding: utf-8 -*-
"""seg_speed_render 后台渲染驱动（由扩展自动生成，勿手改）。

用法：blender -b <临时副本.blend> --python _bg_driver.py -- job.json

只做三件事：按 job.json 设置帧范围/步长/快门/帧率/输出路径 -> 渲染动画 -> 退出。
渲染完视频名仍由 Blender 决定（前缀+帧范围），交给父进程按目录内容认领。
"""
import json
import sys

import bpy

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
if not argv:
    raise SystemExit("seg-speed driver: 缺少 job.json")
with open(argv[0], encoding="utf-8") as fh:
    job = json.load(fh)

# 孤儿兜底不在这里做：bpy.ops.render.render(animation=True) 整个渲染循环握着 Python 的
# GIL，本进程里的看门狗线程根本轮不到执行（实测父进程被杀 10 秒后子进程还在渲）。
# 真正的看门狗是父进程另起的独立小进程 _bg_watch.py，见扩展里的 _watch_loop。

scene = bpy.data.scenes.get(job.get("scene") or "") or bpy.context.scene
r = scene.render
scene.frame_start = int(job["start"])
scene.frame_end = int(job["end"])
scene.frame_step = max(1, int(job.get("step", 1)))
if job.get("fps"):
    r.fps = int(job["fps"])
    r.fps_base = float(job.get("fps_base") or 1.0) or 1.0
shutter = job.get("shutter")
if shutter is not None:
    try:
        r.motion_blur_shutter = float(shutter)
    except Exception:
        pass
    try:
        scene.cycles.motion_blur_shutter = float(shutter)
    except Exception:
        pass
r.filepath = job["filepath"]
print("SEGSPEED_JOB %s scene=%r start=%d end=%d step=%d fps=%s/%s path=%r" % (
    bpy.app.version_string, scene.name, scene.frame_start, scene.frame_end,
    scene.frame_step, r.fps, r.fps_base, r.filepath), flush=True)
with bpy.context.temp_override(scene=scene):
    bpy.ops.render.render(animation=True)
print("SEGSPEED_DONE", flush=True)
'''

# 独立看门狗：父进程（Blender 界面）被关掉/崩掉时，把后台渲染进程一起收掉。
# 必须是独立进程 —— 渲染循环握着 GIL，子进程里的线程跑不起来（实测过）。
_WATCH_SRC = r'''# -*- coding: utf-8 -*-
"""seg_speed_render 看门狗（由扩展自动生成，勿手改）。

用法：python _bg_watch.py <parent_pid> <child_pid> [<日志路径>]

每 0.5 秒看一眼：
- 父进程没了 -> 杀掉渲染子进程，自己退出
- 子进程自己结束了 -> 自己退出（不留常驻进程）
"""
import ctypes
import os
import sys
import time

STILL_ACTIVE = 259


def alive(pid):
    if os.name != "nt":
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    k32 = ctypes.windll.kernel32
    handle = k32.OpenProcess(0x1000, False, int(pid))   # QUERY_LIMITED_INFORMATION
    if not handle:
        return False
    code = ctypes.c_ulong(0)
    ok = k32.GetExitCodeProcess(handle, ctypes.byref(code))
    k32.CloseHandle(handle)
    return bool(ok) and code.value == STILL_ACTIVE


def kill(pid):
    if os.name != "nt":
        try:
            os.kill(pid, 9)
        except OSError:
            pass
        return
    k32 = ctypes.windll.kernel32
    handle = k32.OpenProcess(0x0001, False, int(pid))   # PROCESS_TERMINATE
    if handle:
        k32.TerminateProcess(handle, 1)
        k32.CloseHandle(handle)


def main():
    if len(sys.argv) < 3:
        return 2
    parent, child = int(sys.argv[1]), int(sys.argv[2])
    log = sys.argv[3] if len(sys.argv) > 3 else ""
    while True:
        if not alive(child):
            return 0
        if not alive(parent):
            kill(child)
            if log:
                try:
                    with open(log, "a", encoding="utf-8") as fh:
                        fh.write("[seg-speed] 父进程 %d 已消失，后台渲染 %d 已被看门狗收掉\n"
                                 % (parent, child))
                except OSError:
                    pass
            return 0
        time.sleep(0.5)


if __name__ == "__main__":
    sys.exit(main())
'''

_RE_FRAME = re.compile(
    r"(?:fra:|append frame|appending frame|saved:)\D{0,40}?(\d{1,7})", re.IGNORECASE)


def _pump_child(stream, sink, log_path):
    """子线程读渲染进程输出：只记录最新帧号与最近几行日志，不碰 RNA。"""
    try:
        with open(log_path, "a", encoding="utf-8") as log:
            for line in stream:
                line = line.rstrip("\r\n")
                if not line:
                    continue
                sink["lines"].append(line)
                if len(sink["lines"]) > 400:
                    del sink["lines"][:200]
                m = _RE_FRAME.search(line)
                if m:
                    try:
                        sink["frame"] = int(m.group(1))
                    except ValueError:
                        pass
                try:
                    log.write(line + "\n")
                    log.flush()
                except OSError:
                    pass
    except Exception:
        pass
    finally:
        try:
            stream.close()
        except Exception:
            pass


def _atempo_chain(speed):
    """把 >2 或 <0.5 的变速拆成多级 atempo，兼容老版 ffmpeg 的 0.5~2.0 限制。"""
    s = float(speed)
    parts = []
    if s <= 0:
        return "atempo=1.0"
    while s > 2.0:
        parts.append("atempo=2.0")
        s /= 2.0
    while s < 0.5:
        parts.append("atempo=0.5")
        s /= 0.5
    parts.append("atempo=%.6f" % s)
    return ",".join(parts)


def _ffmpeg_run(ffmpeg, args, timeout=1800):
    cmd = [ffmpeg] + args
    try:
        res = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            creationflags=_hide_console_flag(),
            timeout=timeout,
        )
        return res.returncode == 0, res.stdout.decode("utf-8", "ignore")
    except Exception as exc:
        return False, str(exc)


def _audio_stats(ffmpeg, path, duration=None):
    """返回 (mean_dB, max_dB)，读不到返回 (None, None)。"""
    if not ffmpeg or not os.path.isfile(path):
        return None, None
    try:
        args = [ffmpeg, "-hide_banner", "-nostats"]
        if duration and duration > 0:
            args += ["-t", "%.3f" % float(duration)]
        args += ["-i", path, "-af", "volumedetect", "-f", "null", "-"]
        res = subprocess.run(
            args,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            creationflags=_hide_console_flag(),
        )
        txt = res.stdout.decode("utf-8", "ignore")
        mean = re.search(r"mean_volume:\s*(-?[\d.]+) dB", txt)
        peak = re.search(r"max_volume:\s*(-?[\d.]+) dB", txt)
        return (
            float(mean.group(1)) if mean else None,
            float(peak.group(1)) if peak else None,
        )
    except Exception:
        return None, None



def target_scene(s):
    name = getattr(s, "audio_scene", "")
    if name:
        sc = bpy.data.scenes.get(name)
        if sc is not None:
            return sc
    return bpy.context.scene


def _final_check(ffmpeg, video):
    """成片体检：是否有音频流、多大声、时长多少。"""
    if not ffmpeg or not os.path.isfile(video):
        return "未体检"
    try:
        res = subprocess.run(
            [ffmpeg, "-hide_banner", "-nostats", "-nostdin", "-i", video,
             "-vn", "-af", "volumedetect", "-f", "null", "-"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            creationflags=_hide_console_flag(),
        )
        txt = res.stdout.decode("utf-8", "ignore")
        has_audio = "Audio:" in txt
        dur = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", txt)
        secs = 0.0
        if dur:
            secs = (int(dur.group(1)) * 3600 + int(dur.group(2)) * 60
                    + float(dur.group(3)))
        mean = re.search(r"mean_volume:\s*(-?[\d.]+) dB", txt)
        if not has_audio:
            return "时长 %.2f 秒 ｜ 无音轨" % secs
        if mean:
            mv = float(mean.group(1))
            flag = "音轨 ✓" if mv > -60.0 else "音轨是静音!"
            return "时长 %.2f 秒 ｜ %s mean %s dB" % (secs, flag, mean.group(1))
        return "时长 %.2f 秒 ｜ 有音轨" % secs
    except Exception as exc:
        return "体检失败：%s" % exc


def _vse_report(scene):
    """描述一个场景的 VSE 内容，用于诊断。"""
    se = getattr(scene, "sequence_editor", None)
    strips = getattr(se, "strips", None) if se is not None else None
    if strips is None:
        return "无序列编辑器"
    if not len(strips):
        return "序列编辑器为空"
    parts = []
    for st in strips:
        try:
            parts.append("%s[ch%d]%d-%d" % (
                st.type, st.channel, st.frame_start, st.frame_final_end))
        except Exception:
            parts.append(st.type)
    return "%d 条：%s" % (len(strips), " ".join(parts))


def _mixdown_scene_audio(path, scene=None, ffmpeg=None, frame_range=None, expect_duration=None,
                         allow_silence=False):
    """从 VSE 混出整条时间线的音频到 wav。

    注意：bpy.ops.sound.mixdown 是异步写盘，调用返回时文件还没生成，
    必须轮询等待文件大小稳定。混音取的是「当前窗口的场景」，
    所以要临时切场景。

    allow_silence=True 时不做「几乎静音」判定 —— 单段音频可能正好落在
    源素材的静音区间（例如开场留白），那不是错误。
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        os.remove(path)
    except Exception:
        pass

    scene = scene or bpy.context.scene
    se = getattr(scene, "sequence_editor", None)
    strips = getattr(se, "strips", None) if se is not None else None
    if strips is None or not len(strips):
        return False, "场景「%s」的序列编辑器里没有条带" % scene.name

    win = bpy.context.window
    old_scene = win.scene if win else None
    old_range = (scene.frame_start, scene.frame_end)
    try:
        if frame_range:
            scene.frame_start = int(frame_range[0])
            scene.frame_end = int(frame_range[1])
        if win is not None and old_scene is not scene:
            win.scene = scene
    except Exception:
        win = None

    called = False
    try:
        for kwargs in (
            dict(filepath=path, check_existing=False, container="WAV",
                 codec="PCM", format="S16", mixrate=48000),
            dict(filepath=path, check_existing=False),
        ):
            try:
                bpy.ops.sound.mixdown(**kwargs)
                called = True
                break
            except Exception:
                continue
    finally:
        try:
            if win is not None and old_scene is not None:
                win.scene = old_scene
        except Exception:
            pass
        try:
            scene.frame_start, scene.frame_end = old_range
        except Exception:
            pass

    if not called:
        return False, "混音调用失败"

    deadline = time.time() + 90
    last = -1
    ok_size = False
    while time.time() < deadline:
        if os.path.isfile(path):
            sz = os.path.getsize(path)
            if sz > 1024 and sz == last:
                ok_size = True
                break
            last = sz
        time.sleep(0.15)
    if not ok_size:
        return False, "混音超时，没有生成文件"

    mean_db, peak_db = _audio_stats(ffmpeg, path, expect_duration)
    if allow_silence:
        return True, ("mean %s dB" % mean_db) if mean_db is not None else ""
    if mean_db is not None and mean_db < -60.0:
        return False, ("成片时间范围内几乎是静音（mean %s dB）。"
                       "音频条带可能没有覆盖第 %s 帧到第 %s 帧" % (
                           mean_db, frame_range[0] if frame_range else "?",
                           frame_range[1] if frame_range else "?"))
    if mean_db is not None:
        return True, "mean %s dB" % mean_db
    return True, ""


def _concat_videos(ffmpeg, files, out_path, quality="HIGH", keep_audio=False):
    """把多个 mp4 拼成一条；先尝试流复制，失败再重编码。

    keep_audio=False（默认）会丢掉段里的音轨：成片最后统一贴一条连续音轨，
    避免每段各自编码的 AAC 在接缝处出现 priming 空隙。
    """
    tmp_list = os.path.join(os.path.dirname(files[0]), "_concat.txt")
    with open(tmp_list, "w", encoding="utf-8") as f:
        for p in files:
            f.write("file '%s'\n" % p.replace("\\", "/").replace("'", "'\\''"))

    base = [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", tmp_list]
    an = [] if keep_audio else ["-an"]
    tries = [
        base + an + ["-c", "copy", out_path],
        base + an + ["-c:v", "libx264", "-crf", str(_crf_of(quality)),
                     "-pix_fmt", "yuv420p", out_path],
    ]
    last_err = ""
    for cmd in tries:
        try:
            res = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                creationflags=_hide_console_flag(),
            )
            if res.returncode == 0 and os.path.isfile(out_path) and os.path.getsize(out_path) > 0:
                try:
                    os.remove(tmp_list)
                except Exception:
                    pass
                return True, ""
            last_err = res.stdout.decode("utf-8", "ignore")[-800:]
        except Exception as exc:
            last_err = str(exc)
    return False, last_err


# ----------------------------------------------------------------------------
# 段管理操作
# ----------------------------------------------------------------------------


class SSR_OT_add_segment(bpy.types.Operator):
    bl_idname = "seg_speed.add_segment"
    bl_label = "添加段"
    bl_description = "添加一个渲染段"

    step: IntProperty(name="步长", default=1, min=1, max=1000)

    def execute(self, context):
        s = context.scene.ssr
        seg = s.segments.add()
        if len(s.segments) > 1:
            prev = s.segments[-2]
            seg.start = prev.end + 1
        else:
            seg.start = context.scene.frame_start
        span = 24 * self.step
        seg.end = seg.start + min(span, max(1, context.scene.frame_end - seg.start)) - 1
        seg.step = self.step
        s.active_index = len(s.segments) - 1
        _tag_redraw(context)
        return {"FINISHED"}


class SSR_OT_remove_segment(bpy.types.Operator):
    bl_idname = "seg_speed.remove_segment"
    bl_label = "删除段"

    def execute(self, context):
        s = context.scene.ssr
        if not len(s.segments):
            return {"CANCELLED"}
        i = min(max(0, s.active_index), len(s.segments) - 1)
        s.segments.remove(i)
        s.active_index = max(0, min(i, len(s.segments) - 1))
        _tag_redraw(context)
        return {"FINISHED"}


class SSR_OT_move_segment(bpy.types.Operator):
    bl_idname = "seg_speed.move_segment"
    bl_label = "移动段"

    direction: EnumProperty(
        items=[("UP", "上移", ""), ("DOWN", "下移", "")], default="UP"
    )

    def execute(self, context):
        s = context.scene.ssr
        n = len(s.segments)
        if n < 2:
            return {"CANCELLED"}
        i = s.active_index
        j = i - 1 if self.direction == "UP" else i + 1
        if j < 0 or j >= n:
            return {"CANCELLED"}
        s.segments.move(i, j)
        s.active_index = j
        _tag_redraw(context)
        return {"FINISHED"}


class SSR_OT_reset_from_scene(bpy.types.Operator):
    bl_idname = "seg_speed.reset_from_scene"
    bl_label = "用场景帧范围重置"
    bl_description = "清空现有段，生成一段覆盖整个场景帧范围的正常速段"

    def execute(self, context):
        s = context.scene.ssr
        s.segments.clear()
        seg = s.segments.add()
        seg.start = context.scene.frame_start
        seg.end = context.scene.frame_end
        seg.step = 1
        s.active_index = 0
        _tag_redraw(context)
        return {"FINISHED"}


# ----------------------------------------------------------------------------
# 渲染会话
# ----------------------------------------------------------------------------


def _on_render_post(scene, depsgraph=None):
    """渲染回调：只记账。

    渲染 job 跑在 Blender 的渲染线程里，这里碰 RNA（写 scene.ssr.*）会造成
    跨线程写属性。所有面板更新都留给主线程的 timer 做。
    """
    sess = _RenderSession._active
    if sess is not None and not sess.finished:
        sess.rendered_frames += 1


def _on_render_progress(text=None, depsgraph=None):
    """缓存 render_stats 的状态文本（如 "Time: 00:01.23"），主线程轮询时再上屏。

    注意：render_stats 的第一个参数是状态文本字符串，不是 scene。
    """
    sess = _RenderSession._active
    if sess is None or sess.finished:
        return
    try:
        sess.stats_text = text if isinstance(text, str) else ""
    except Exception:
        pass


class _RenderSession:
    """用 bpy.app.timers 推进：视频模式每次 tick 渲一段，PNG 模式每次渲一帧。"""

    _active = None

    def __init__(self, scene, outdir, mode):
        self.scene = scene
        self.s = scene.ssr
        self.outdir = outdir
        self.mode = mode
        self.t0 = time.time()
        self.finished = False
        self.tmpdir = os.path.join(outdir, "_segments_tmp")
        # 每次渲染用独立的原始输出目录：Blender 的视频文件名只由「前缀+帧范围」决定，
        # 上一轮中断留下的 seg_000000-0200.mp4 会被原样覆盖 —— 用目录快照差集会误判
        # 「本段没有产出视频文件」。独立目录 + 时间戳保证本轮文件必然是新文件。
        self.rawdir = os.path.join(
            self.tmpdir, "_raw_%s_%d" % (time.strftime("%Y%m%d_%H%M%S"), os.getpid()))
        self.raw_stamp = 0.0
        self.seg_files = []
        self.done_frames = 0
        self.done_before = 0
        self.cur_frames = 1
        self.seg_index = 0
        self.frame_index = 0
        self.cur_step = 0
        self.eta_s = None            # 剩余时间 EMA 状态，每段开头清零

        # 视频模式改成「把渲染丢进 Blender 的 Render job」再轮询，
        # 这样主循环不被占住，渲染几个小时的片界面也不会假死（Windows 不会标"未响应"）。
        self.job_phase = "idle"      # idle | render
        self.job_seen = False
        self.job_t0 = 0.0
        self.job_miss = 0
        self.stats_text = ""
        self.rendered_frames = 0

        # 锁定界面：渲染期间视口切线框、面板只重绘侧栏（见 _lock_ui）
        self.ui_locked = False
        self.ui_saved = []

        # 独立进程模式：子进程渲染，父进程只轮询，界面彻底不参与渲染
        self.use_subproc = False
        self.subproc_failed = 0
        self.child = None
        self.child_sink = {"frame": 0, "lines": []}
        self.child_rc = None
        self.bgblend = None
        self.driver = None
        self.watcher = None
        self.watch_proc = None
        self.job_json = None
        self.bglog = None

        self.seg_list = []
        self.frame_jobs = []

        # v1.8.0：每段渲完就把「这一段自己的音轨」合进段文件，
        # 段文件单独拷出去也有声音；最后拼接时再统一重贴一条连续音轨。
        self.ffmpeg = None
        self.audio_notes = []
        self.audio_mode_used = None
        self.audio_fail = ""
        self.seg_audio_ok = []
        idx = 0
        for seg in self.s.segments:
            frames = _segment_frames(seg)
            if not frames:
                continue
            self.seg_list.append((seg.start, seg.end, max(1, seg.step), idx))
            for f in frames:
                self.frame_jobs.append(
                    (f, max(1, seg.step),
                     os.path.join(outdir, "%s_%05d" % (self.s.prefix, idx)))
                )
                idx += 1
        self.total = len(self.frame_jobs)

        r = scene.render
        self.saved = {
            "frame": scene.frame_current,
            "frame_start": scene.frame_start,
            "frame_end": scene.frame_end,
            "frame_step": scene.frame_step,
            "filepath": r.filepath,
            "format": r.image_settings.file_format,
            "media_type": getattr(r.image_settings, "media_type", None),
            "fps": r.fps,
            "fps_base": r.fps_base,
        }
        try:
            self.saved["eevee_shutter"] = r.motion_blur_shutter
        except Exception:
            self.saved["eevee_shutter"] = 0.5
        try:
            self.saved["cycles_shutter"] = scene.cycles.motion_blur_shutter
        except Exception:
            self.saved["cycles_shutter"] = 0.5

    # -- 启动 ---------------------------------------------------------------
    def start(self):
        os.makedirs(self.outdir, exist_ok=True)
        self.ffmpeg = _find_exe("ffmpeg", self.s.ffmpeg_path)
        if self.mode == "VIDEO":
            os.makedirs(self.tmpdir, exist_ok=True)
            os.makedirs(self.rawdir, exist_ok=True)
            s = self.scene.ssr
            _configure_video(self.scene, s.quality, _real_fps(s))
            # 分段片段的编码帧率必须与面板帧率一致，否则拼接后时长、音频全部错位
            try:
                self.scene.render.fps = int(s.fps)
                self.scene.render.fps_base = float(s.fps_base) or 1.0
            except Exception:
                pass
            bpy.app.handlers.render_post.append(_on_render_post)
            if _on_render_progress not in bpy.app.handlers.render_stats:
                bpy.app.handlers.render_stats.append(_on_render_progress)
            if s.render_process == "SUBPROC":
                try:
                    self._prepare_subproc()
                except Exception as exc:
                    print("[seg-speed] 独立进程准备失败，退回本进程渲染:", exc)
                    self.use_subproc = False
        else:
            _configure_png(self.scene)
        if self.s.lock_ui:
            self._lock_ui()
        bpy.app.timers.register(self.tick, first_interval=0.05)

    # -- 进度 ---------------------------------------------------------------
    def _eta_seconds(self, done, total, elapsed):
        """剩余秒数。

        段内前几帧的单帧耗时波动很大（首帧要建缓存、子进程要启动），
        直接用 elapsed/done 算，面板「剩余约 x 分」会 15→9→11 来回跳。
        这里对累计估计做一次 EMA（0.75 旧 + 0.25 新），数字才稳。
        """
        if done <= 0:
            return 0.0
        raw = max(0.0, elapsed / done * (total - done))
        if self.eta_s is None or done < 3:
            self.eta_s = raw
        else:
            self.eta_s = self.eta_s * 0.75 + raw * 0.25
        return self.eta_s

    def _publish(self):
        s = self.s
        done = self.done_frames
        total = max(1, self.total)
        elapsed = time.time() - self.t0
        eta = self._eta_seconds(done, total, elapsed)
        s.progress = min(1.0, done / float(total))
        s.progress_text = "%d/%d 帧  |  已用 %.1f 分  剩余约 %.1f 分" % (
            done, total, elapsed / 60.0, eta / 60.0,
        )
        try:
            bpy.context.window_manager.progress_update(done)
        except Exception:
            pass
        _tag_redraw()

    # -- 主循环 -------------------------------------------------------------
    def tick(self):
        s = self.s
        # 渲染 job 还在跑时不能直接 _finish：那是从渲染线程底下抽掉场景设置。
        # 这时候交给 _poll_video_job 等本段渲完再收尾（面板会提示"会在本段渲完后停下"）。
        # 独立进程模式没有这个顾虑：杀掉子进程即可立刻停。
        if s.cancel_flag:
            if self.use_subproc:
                return self._finish(
                    cancelled=True,
                    message="第 %d 段渲染已停止（后台进程已结束，半截文件丢弃）"
                            % (self.seg_index + 1 if self.seg_list else 0))
            if self.job_phase != "render":
                return self._finish(cancelled=True)
        try:
            if self.mode == "VIDEO":
                return self._tick_video()
            return self._tick_png()
        except Exception as exc:
            print("[seg-speed] 渲染异常:", exc)
            self._finish(cancelled=True, message="渲染异常：%s" % exc)
            return None

    def _apply_shutter(self, step):
        if step == self.cur_step:
            return
        self.cur_step = step
        if not self.s.auto_shutter:
            return
        factor = 1.0 / float(max(1, step))
        try:
            self.scene.render.motion_blur_shutter = self.saved["eevee_shutter"] * factor
        except Exception:
            pass
        try:
            self.scene.cycles.motion_blur_shutter = self.saved["cycles_shutter"] * factor
        except Exception:
            pass

    # -- 独立进程模式 --------------------------------------------------------
    def _prepare_subproc(self):
        """把当前场景另存一份临时 .blend，供后台 Blender 渲染。

        copy=True 只写磁盘副本，不动用户正在编辑的文件，也不改当前文件路径；
        relative_remap=True 保证副本里的相对路径（贴图、声音）仍指向原位置。
        """
        exe = bpy.app.binary_path
        if not exe or not os.path.isfile(exe):
            raise RuntimeError("找不到 Blender 可执行文件")
        stamp = time.strftime("%Y%m%d_%H%M%S")
        self.bgblend = os.path.join(self.tmpdir, "_bg_%s_%d.blend" % (stamp, os.getpid()))
        self.driver = os.path.join(self.tmpdir, "_bg_driver.py")
        self.watcher = os.path.join(self.tmpdir, "_bg_watch.py")
        self.job_json = os.path.join(self.tmpdir, "_bg_job.json")
        self.bglog = os.path.join(self.tmpdir, "seg_speed_render.log")
        with open(self.driver, "w", encoding="utf-8") as fh:
            fh.write(_DRIVER_SRC)
        with open(self.watcher, "w", encoding="utf-8") as fh:
            fh.write(_WATCH_SRC)
        bpy.ops.wm.save_as_mainfile(filepath=self.bgblend, copy=True, relative_remap=True)
        if not os.path.isfile(self.bgblend):
            raise RuntimeError("临时副本没写出来：%s" % self.bgblend)
        self.use_subproc = True
        print("[seg-speed] 独立进程渲染已就绪：%s" % self.bgblend)

    def _tick_subproc(self):
        s = self.s
        if self.child is not None and self.child.poll() is None:
            return self._poll_subproc()
        if self.child is not None:                     # 上一段刚结束，先认领产物
            rc = self.child.poll()
            self.child = None
            self.child_rc = rc
            return self._after_child(rc)

        if self.seg_index >= len(self.seg_list):
            return self._finish(cancelled=False)

        self._launch_segment()
        return 0.2

    def _launch_segment(self):
        start, end, step, idx = self.seg_list[self.seg_index]
        self.cur_frames = max(1, len(range(start, end + 1, step)))
        seg_path = os.path.join(self.rawdir, "seg_%02d" % idx)
        shutter = None
        if self.s.auto_shutter:
            shutter = float(self.saved["eevee_shutter"]) / float(max(1, step))
        job = {
            "scene": self.scene.name,
            "start": int(start),
            "end": int(end),
            "step": int(max(1, step)),
            "shutter": shutter,
            "fps": int(self.s.fps),
            "fps_base": float(self.s.fps_base) or 1.0,
            "filepath": seg_path,
            "parent_pid": os.getpid(),
        }
        with open(self.job_json, "w", encoding="utf-8") as fh:
            json.dump(job, fh, ensure_ascii=False, indent=2)

        cmd = [bpy.app.binary_path, "-b", self.bgblend,
               "--python", self.driver, "--", self.job_json]
        flags = 0x08000000 if os.name == "nt" else 0      # CREATE_NO_WINDOW
        self.child_sink = {"frame": 0, "lines": []}
        self.child_rc = None
        self.raw_stamp = time.time()
        self.rendered_frames = 0
        self.eta_s = None
        self.job_t0 = time.time()
        print("[seg-speed] 第 %d 段启动后台渲染：帧 %d–%d 步长 %d"
              % (self.seg_index + 1, start, end, step))
        self.child = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL, bufsize=1, universal_newlines=True,
            encoding="utf-8", errors="replace", creationflags=flags,
            cwd=os.path.dirname(self.bgblend) or None)
        self.thread = threading.Thread(
            target=_pump_child,
            args=(self.child.stdout, self.child_sink, self.bglog),
            daemon=True)
        self.thread.start()
        self._spawn_watcher()

    def _spawn_watcher(self):
        """起一个独立小进程盯父进程存活：界面被关掉时把渲染子进程一起收走。

        渲染循环握着 GIL，放在子进程里的线程跑不起来，只能靠进程级看门狗。
        看门狗自己会在渲染进程结束后退出，不需要父进程回收。
        """
        if not self.watcher or not os.path.isfile(self.watcher):
            return
        try:
            exe = _python_exe()
            flags = 0x08000000 if os.name == "nt" else 0
            self.watch_proc = subprocess.Popen(
                [exe, self.watcher, str(os.getpid()), str(self.child.pid), self.bglog],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL, creationflags=flags,
                cwd=os.path.dirname(self.watcher) or None)
            print("[seg-speed] 看门狗已就位：pid %d（盯父进程 %d → 渲染 %d）"
                  % (self.watch_proc.pid, os.getpid(), self.child.pid))
        except Exception as exc:
            self.watch_proc = None
            print("[seg-speed] 看门狗没起来（%s），界面被强杀时后台渲染可能残留" % exc)

    def _poll_subproc(self):
        fr = self.child_sink.get("frame") or 0
        if fr:
            start, end, step, idx = self.seg_list[self.seg_index]
            done_seg = len(range(start, min(fr, end) + 1, step))
            self.rendered_frames = max(self.rendered_frames, min(done_seg, self.cur_frames))
        self._publish_subproc()
        return 0.25

    def _after_child(self, rc):
        s = self.s
        if s.cancel_flag:
            return self._finish(cancelled=True,
                                message="第 %d 段渲染已停止（后台进程已结束，半截文件丢弃）"
                                        % (self.seg_index + 1))
        if rc != 0:
            tail = " / ".join(self.child_sink["lines"][-4:]) or "无输出"
            if self.seg_index == 0 and self.subproc_failed == 0:
                self.subproc_failed += 1
                self.use_subproc = False
                print("[seg-speed] 后台渲染失败（退出码 %s：%s），改回本进程渲染" % (rc, tail))
                return 0.01
            return self._finish(
                cancelled=True,
                message="第 %d 段后台渲染失败（退出码 %s）：%s；日志 %s"
                        % (self.seg_index + 1, rc, tail, self.bglog))
        self.rendered_frames = self.cur_frames
        return self._finalize_video_segment()

    def _publish_subproc(self):
        s = self.s
        try:
            start, end, step, idx = self.seg_list[self.seg_index]
            span = max(1, len(range(start, end + 1, step)))
            done_seg = min(span, self.rendered_frames)
            total = max(1, self.total)
            done = self.done_before + done_seg
            elapsed = time.time() - self.t0
            eta = self._eta_seconds(done, total, elapsed)
            s.progress = min(0.99, done / float(total))
            self.done_frames = max(self.done_frames, done)
            note = " ｜ 点停止立即中断" if not s.cancel_flag else " ｜ 正在停止"
            s.progress_text = (
                "第 %d/%d 段 ｜ 后台渲染 帧 %d–%d ｜ 段内 %d/%d ｜ 已用 %.1f 分  剩余约 %.1f 分%s"
                % (self.seg_index + 1, len(self.seg_list), start, end,
                   done_seg, span, elapsed / 60.0, eta / 60.0, note))
            bpy.context.window_manager.progress_update(int(done))
            _tag_redraw()
        except Exception:
            pass

    def _stop_child(self):
        child = self.child
        self.child = None
        if child is None:
            return
        try:
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=6)
                except Exception:
                    child.kill()
        except Exception:
            pass

    def _tick_video(self):
        # 独立进程模式：父进程完全不碰渲染，只发任务、收进度
        if self.use_subproc:
            return self._tick_subproc()
        # 正在渲染：只轮询 job 状态，主循环不阻塞
        if self.job_phase == "render":
            return self._poll_video_job()

        if self.seg_index >= len(self.seg_list):
            return self._finish(cancelled=False)
        if self.s.cancel_flag:
            return self._finish(cancelled=True)

        start, end, step, idx = self.seg_list[self.seg_index]
        self._apply_shutter(step)

        scene = self.scene
        scene.frame_start = start
        scene.frame_end = end
        scene.frame_step = step
        self.cur_frames = max(1, len(range(start, end + 1, step)))
        # 落进本轮专属 rawdir：新文件必然存在，不会被上一轮同名产物顶掉
        seg_path = os.path.join(self.rawdir, "seg_%02d" % idx)
        scene.render.filepath = seg_path

        # 每段渲染前重新确认一次视频输出设置，防止被中途改回图片序列
        try:
            _configure_video(scene, self.s.quality, _real_fps(self.s))
            scene.render.filepath = seg_path
        except Exception as exc:
            print("[seg-speed] 视频设置失败:", exc)

        self.raw_stamp = time.time()
        self.job_seen = False
        self.job_miss = 0
        self.job_t0 = time.time()
        self.rendered_frames = 0
        self.eta_s = None
        self.stats_text = ""
        self.job_phase = "render"
        if not self._dispatch_render():
            # 没有窗口 / INVOKE 不可用：退回阻塞渲染，渲完直接判段
            self.job_phase = "idle"
            return self._finalize_video_segment()
        return 0.1

    def _dispatch_render(self):
        """把整段渲染丢进 Blender 的 Render job，立刻返回。

        INVOKE 模式下 bpy.ops.render.render 只负责「开始渲染」，真正的渲染跑在
        Blender 的 job 里：主循环继续转，界面能点能拖，Windows 也不会把窗口
        标成「未响应」。不支持 INVOKE 的场合退回原来的阻塞渲染。
        """
        wm = bpy.context.window_manager
        win = wm.windows[0] if len(wm.windows) else None
        if win is None:
            bpy.ops.render.render(animation=True)
            return False
        try:
            with bpy.context.temp_override(window=win, screen=win.screen):
                res = bpy.ops.render.render("INVOKE_DEFAULT", animation=True)
            if {"RUNNING_MODAL", "FINISHED"} & set(res):
                return True
            print("[seg-speed] INVOKE 返回 %s，退回阻塞渲染" % (res,))
        except Exception as exc:
            print("[seg-speed] INVOKE 失败，退回阻塞渲染:", exc)
        bpy.ops.render.render(animation=True)
        return False

    def _poll_video_job(self):
        s = self.s
        try:
            running = bpy.app.is_job_running("RENDER")
        except Exception:
            running = False

        if running:
            self.job_seen = True
            self.job_miss = 0
            self._publish_job()
            return 0.2

        if not self.job_seen and time.time() - self.job_t0 < 5.0:
            return 0.1          # job 还没起来，再等等

        # 连续几次确认结束，避免帧间空档被当成渲染完成
        self.job_miss += 1
        if self.job_miss < 3:
            return 0.15

        self.job_phase = "idle"
        if s.cancel_flag:
            return self._finish(
                cancelled=True,
                message="第 %d 段渲染被中断（停止时已渲 %d 帧）" % (
                    self.seg_index + 1, self.rendered_frames))
        return self._finalize_video_segment()

    def _publish_job(self):
        """主线程更新面板：渲染 job 期间每 0.2 秒一次。"""
        s = self.s
        try:
            start, end, step, idx = self.seg_list[self.seg_index]
            span = max(1, len(range(start, end + 1, step)))
            fr = self.scene.frame_current
            done_seg = min(span, max(0, len(range(start, min(fr, end) + 1, step))))
            total = max(1, self.total)
            done = self.done_before + done_seg
            elapsed = time.time() - self.t0
            eta = self._eta_seconds(done, total, elapsed)
            s.progress = min(0.99, done / float(total))
            self.done_frames = max(self.done_frames, done)
            tail = ""
            if self.stats_text.startswith("Time:"):
                tail = " ｜ %s" % self.stats_text.split("(")[0].strip()
            note = " ｜ 点停止会在本段渲完后停下" if s.cancel_flag else ""
            s.progress_text = (
                "第 %d/%d 段 ｜ 渲帧 %d–%d ｜ 段内 %d/%d ｜ 已用 %.1f 分  剩余约 %.1f 分%s%s"
                % (self.seg_index + 1, len(self.seg_list), start, end,
                   done_seg, span, elapsed / 60.0, eta / 60.0, tail, note))
            bpy.context.window_manager.progress_update(int(done))
            _tag_redraw()
        except Exception:
            pass

    def _finalize_video_segment(self):
        scene = self.scene
        start, end, step, idx = self.seg_list[self.seg_index]

        # Blender 5.x 视频输出会把帧范围拼进文件名（seg_000000-0200.mp4），
        # 所以用「本轮专属目录里的文件」定位产物，不猜文件名。
        # 也不写死 .mp4：容器设置不同可能出 .mkv/.mov，写死会把成功误判成失败。
        def _snap(d):
            return set(glob.glob(os.path.join(d, "**", "*"), recursive=True))

        video_ext = (".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v", ".mpg", ".mpeg")
        new_files = sorted(p for p in _snap(self.rawdir) if os.path.isfile(p))
        produced = [p for p in new_files
                    if os.path.splitext(p)[1].lower() in video_ext]
        if not produced:
            # 双保险：rawdir 是本轮新建的，里面任何视频文件都只可能是本轮产物，
            # 按 mtime 再捞一次（防止某些平台快照/缓存行为异常）。
            produced = sorted(
                p for p in _snap(self.rawdir)
                if os.path.isfile(p)
                and os.path.splitext(p)[1].lower() in video_ext
                and os.path.getmtime(p) >= self.raw_stamp - 2.0
            )

        # job 被外部打断（状态栏的 ✕ / 关掉渲染）时会留下半截视频，
        # 直接拿去拼接会得到时长偏短的成片 —— 用「渲到的帧数」识破它。
        if produced and 0 < self.rendered_frames < self.cur_frames:
            self._finish(
                cancelled=True,
                message="第 %d 段渲染被中断（已渲 %d/%d 帧，半截文件已丢弃）"
                        % (self.seg_index + 1, self.rendered_frames, self.cur_frames),
            )
            return None

        if produced:
            raw = produced[-1]
            clean = os.path.join(self.tmpdir, "seg_%02d_x%d%s" % (
                self.seg_index + 1, step, os.path.splitext(raw)[1].lower()))
            if os.path.abspath(raw) != os.path.abspath(clean):
                try:
                    os.replace(raw, clean)
                    raw = clean
                except OSError:
                    pass
            for extra in produced:
                if os.path.abspath(extra) != os.path.abspath(raw):
                    try:
                        os.remove(extra)
                    except OSError:
                        pass
            self.seg_files.append(raw)
            # v1.8.0：段文件当场合上本段音轨，单独拷出去也有声音
            if self.s.audio_mode != "NONE":
                self._segment_audio(self.s, self.seg_index, start, end, step, raw)
            # 本段产物已搬进 tmpdir 的标准命名，rawdir 清空留给下一段
            shutil.rmtree(self.rawdir, ignore_errors=True)
            os.makedirs(self.rawdir, exist_ok=True)
        else:
            try:
                ims = scene.render.image_settings
                fmt = "%s / %s" % (
                    getattr(ims, "media_type", "?"), getattr(ims, "file_format", "?"))
            except Exception:
                fmt = "?"
            seen = "、".join(os.path.basename(p) for p in new_files[:8]) or "一个新文件都没有"
            self._finish(
                cancelled=True,
                message="第 %d 段没有产出视频文件（当前输出格式 %s，渲染路径 %s，本段新增文件：%s）"
                        % (self.seg_index + 1, fmt, scene.render.filepath, seen),
            )
            return None

        self.done_before += self.cur_frames
        self.done_frames = self.done_before
        self.seg_index += 1
        self._publish()
        return 0.01

    def _tick_png(self):
        if self.frame_index >= len(self.frame_jobs):
            return self._finish(cancelled=False)

        frame, step, path = self.frame_jobs[self.frame_index]
        self._apply_shutter(step)
        self.scene.frame_set(frame)
        self.scene.render.filepath = path
        bpy.ops.render.render(write_still=True)

        self.frame_index += 1
        self.done_frames = self.frame_index
        self._publish()
        return 0.01

    # -- 收尾 ---------------------------------------------------------------
    # -- 界面锁定 -----------------------------------------------------------
    def _lock_ui(self):
        """渲染期间关掉 3D 视图的实时显示。

        只动视口的三个开关（shading / overlay / gizmo），不删区域、不改工作区，
        所以渲染一结束就能原样还原，用户布局不会坏。

        为什么有用：视口停在 RENDERED / MATERIAL 档时，主进程每重绘一次就要
        跑一遍 EEVEE 的 GPU 场景；「独立进程」模式下这就变成跟渲染子进程抢显卡。
        切成线框后视口开销几乎为零，显卡全给渲染。
        """
        saved = []
        try:
            windows = list(bpy.context.window_manager.windows)
        except Exception:
            return
        for win in windows:
            screen = getattr(win, "screen", None)
            if screen is None:
                continue
            for area in screen.areas:
                if area.type != "VIEW_3D":
                    continue
                for space in area.spaces:
                    if space.type != "VIEW_3D":
                        continue
                    try:
                        saved.append((space, space.shading.type,
                                      space.overlay.show_overlays,
                                      space.show_gizmo))
                        space.shading.type = "WIREFRAME"
                        space.overlay.show_overlays = False
                        space.show_gizmo = False
                    except Exception:
                        pass
        self.ui_saved = saved
        self.ui_locked = bool(saved)
        if saved:
            print("[seg-speed] 界面已锁定：%d 个 3D 视图切线框、关叠加层，"
                  "面板只重绘侧栏" % len(saved))
        else:
            print("[seg-speed] 没找到可锁定的 3D 视图，界面锁定跳过")

    def _unlock_ui(self):
        if not self.ui_saved:
            self.ui_locked = False
            return
        for space, sh_type, overlays, gizmo in self.ui_saved:
            try:
                space.shading.type = sh_type
                space.overlay.show_overlays = overlays
                space.show_gizmo = gizmo
            except Exception:
                pass
        print("[seg-speed] 界面已还原（%d 个 3D 视图）" % len(self.ui_saved))
        self.ui_saved = []
        self.ui_locked = False

    def _restore(self):
        self._unlock_ui()
        scene = self.scene
        try:
            scene.frame_start = self.saved["frame_start"]
            scene.frame_end = self.saved["frame_end"]
            scene.frame_step = self.saved["frame_step"]
            scene.frame_set(self.saved["frame"])
        except Exception:
            pass
        try:
            scene.render.fps = self.saved["fps"]
            scene.render.fps_base = self.saved["fps_base"]
        except Exception:
            pass
        scene.render.filepath = self.saved["filepath"]
        mt = self.saved.get("media_type")
        if mt:
            try:
                scene.render.image_settings.media_type = mt
            except Exception:
                pass
        try:
            scene.render.image_settings.file_format = self.saved["format"]
        except Exception:
            pass
        try:
            scene.render.motion_blur_shutter = self.saved["eevee_shutter"]
        except Exception:
            pass
        try:
            scene.cycles.motion_blur_shutter = self.saved["cycles_shutter"]
        except Exception:
            pass

    def _finish(self, cancelled, message=""):
        if self.finished:
            return None
        self.finished = True
        _RenderSession._active = None

        try:
            bpy.app.handlers.render_post.remove(_on_render_post)
        except Exception:
            pass
        try:
            bpy.app.handlers.render_stats.remove(_on_render_progress)
        except Exception:
            pass
        self._restore()
        # rawdir 只是本轮的中转目录：成功或中断都清掉，别把半截视频留给下一轮
        self.job_phase = "idle"
        self._stop_child()
        shutil.rmtree(self.rawdir, ignore_errors=True)
        if self.bgblend:
            # 临时副本与驱动脚本用完即删，别在输出目录里留垃圾
            for path in (self.bgblend, self.driver, self.watcher, self.job_json):
                try:
                    if path and os.path.isfile(path):
                        os.remove(path)
                except OSError:
                    pass
        try:
            bpy.context.window_manager.progress_end()
        except Exception:
            pass

        s = self.s
        s.running = False
        s.cancel_flag = False
        elapsed = time.time() - self.t0

        if cancelled:
            s.progress_text = message or ("已停止，完成 %d/%d 帧" % (self.done_frames, self.total))
            _tag_redraw()
            return None

        s.progress = 1.0
        s.progress_text = "渲染完成，用时 %.1f 分钟" % (elapsed / 60.0)
        s.est_seconds = elapsed / max(1, self.done_frames)
        _tag_redraw()

        if not s.auto_compose:
            if self.mode == "VIDEO":
                s.progress_text = "各段已渲染到 %s（未拼接）" % self.tmpdir
            else:
                s.progress_text = "序列已输出，可点「合成视频」出片"
            _tag_redraw()
            return None

        if self.mode == "VIDEO":
            self._compose_video(s, elapsed)
        else:
            try:
                bpy.ops.seg_speed.compose("EXEC_DEFAULT")
            except Exception as exc:
                print("[seg-speed] 合成失败:", exc)
        return None

    # -- 每段音轨（v1.8.0） -------------------------------------------------
    def _resolve_audio_mode(self, s):
        """把 AUTO 定成 SCENE / FILE，结果缓存；定了就复用。"""
        if self.audio_mode_used:
            return self.audio_mode_used
        mode = s.audio_mode
        if mode == "AUTO":
            tsc = target_scene(s)
            se = getattr(tsc, "sequence_editor", None)
            strips = getattr(se, "strips", None) if se is not None else None
            has_vse = strips is not None and len(strips) > 0
            has_file = bool(s.audio_file) and os.path.isfile(
                bpy.path.abspath(s.audio_file))
            mode = "SCENE" if has_vse else ("FILE" if has_file else "")
            self.audio_notes.append("自动判定：VSE %s ｜ 文件 %s → %s" % (
                _vse_report(tsc), bool(has_file), mode or "没找到"))
            if not mode:
                self.audio_fail = "自动模式没找到音频：VSE 里没有条带，也没选音频文件"
                return ""
        self.audio_mode_used = mode
        return mode

    def _audio_window(self, mode, s, idx, start, end):
        """取这一段对应的音频窗口，返回 (路径, 窗口内起点秒数)。

        FILE：直接返回源文件，由 ffmpeg 的 -ss 定位（和成片那条轨完全同一套算法）。
        SCENE：只混这一段帧范围，避免为几秒钟的段混整条 15 小时时间线。
        """
        fps = _real_fps(s)
        f0 = float(self.saved["frame_start"])
        if mode == "FILE":
            src = bpy.path.abspath(s.audio_file or "")
            if not src or not os.path.isfile(src):
                return None, "音频文件不存在或为空：%r" % s.audio_file
            return src, max(0.0, (start - f0) / fps + s.audio_offset)
        if mode == "SCENE":
            win = os.path.join(self.rawdir, "aud_src_%02d.wav" % (idx + 1))
            ok, err = _mixdown_scene_audio(
                win, target_scene(s), self.ffmpeg,
                frame_range=(int(start), int(end)),
                expect_duration=max(0.02, (end + 1 - start) / fps),
                allow_silence=True)
            if not ok:
                return None, "场景混音失败：%s" % err
            return win, max(0.0, s.audio_offset)
        return None, "音频模式无效：%s" % mode

    def _segment_audio(self, s, idx, start, end, step, seg_path):
        """把这一段自己的音轨合进段文件（v1.8.0）。

        失败不影响画面：段文件保持无声，最后成片仍会统一贴一条连续音轨。
        """
        if not self.ffmpeg:
            self.audio_fail = self.audio_fail or "未找到 ffmpeg，段文件没合音轨"
            return False
        mode = self._resolve_audio_mode(s)
        if not mode:
            return False
        fps = _real_fps(s)
        dur = max(0.02, (end + 1 - start) / fps)          # 源时间线长度
        out_dur = dur / float(max(1, step))               # 加速后的长度
        src, t0 = self._audio_window(mode, s, idx, start, end)
        if not src:
            self.audio_fail = t0
            print("[seg-speed] 第 %d 段音轨跳过：%s" % (self.seg_index + 1, t0))
            return False

        piece = os.path.join(self.rawdir, "aud_%02d.wav" % (idx + 1))
        args = ["-y", "-ss", "%.6f" % t0, "-t", "%.6f" % dur, "-i", src]
        af = []
        if step > 1:
            af.append(_atempo_chain(step))
        if abs(s.audio_volume - 1.0) > 1e-3:
            af.append("volume=%.3f" % s.audio_volume)
        if af:
            args += ["-filter:a", ",".join(af)]
        args += ["-vn", "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le", piece]
        ok, log = _ffmpeg_run(self.ffmpeg, args)
        if not ok or not os.path.isfile(piece):
            self.audio_fail = "第 %d 段音轨截取失败：%s" % (self.seg_index + 1, (log or "")[-300:])
            print("[seg-speed]", self.audio_fail)
            return False
        if os.path.getsize(piece) < 2048:
            self.audio_fail = ("第 %d 段音轨是空的（源 %s 的 %.2f~%.2f 秒），"
                              "音频可能没覆盖这个范围" % (self.seg_index + 1, os.path.basename(src),
                                                          t0, t0 + dur))
            print("[seg-speed]", self.audio_fail)
            return False

        muxed = seg_path + ".aud.mp4"
        args = ["-y", "-i", seg_path, "-i", piece,
                "-map", "0:v:0", "-map", "1:a:0",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                "-t", "%.6f" % out_dur, muxed]
        ok, log = _ffmpeg_run(self.ffmpeg, args)
        if ok and os.path.isfile(muxed) and os.path.getsize(muxed) > 1024:
            try:
                os.replace(muxed, seg_path)
            except OSError as exc:
                self.audio_fail = "第 %d 段音轨合并后替换失败：%s" % (self.seg_index + 1, exc)
                print("[seg-speed]", self.audio_fail)
                return False
            self.seg_audio_ok.append(idx)
            self.audio_notes.append("第 %d 段（帧 %d–%d，%d 倍速）音轨 → %.2f 秒，已合进 %s" % (
                self.seg_index + 1, start, end, step, out_dur, os.path.basename(seg_path)))
            print("[seg-speed] 第 %d 段已合上本段音轨：%s（%.2f 秒）"
                  % (self.seg_index + 1, os.path.basename(seg_path), out_dur))
        else:
            self.audio_fail = "第 %d 段音轨合并失败：%s" % (self.seg_index + 1, (log or "")[-300:])
            print("[seg-speed]", self.audio_fail)
            try:
                os.remove(muxed)
            except OSError:
                pass
        # 截取用的 wav 与场景窗口用完即删，段目录里只留段视频
        for p in (piece, src):
            if not p or os.path.dirname(p) != self.rawdir:
                continue          # 只在 rawdir 里删自己生成的临时文件，绝不碰用户源文件
            try:
                os.remove(p)
            except OSError:
                pass
        return True

    def _attach_audio(self, ffmpeg, s, video):
        """给成片加音轨。快放段的音频同步加速，保证音画对位。"""
        tmp = self.tmpdir
        os.makedirs(tmp, exist_ok=True)
        fps = _real_fps(s)
        f0 = float(self.saved["frame_start"])

        # ---- 音频日志：每一步都落盘，出问题可以直接看文件 ----
        log_path = os.path.join(os.path.dirname(video) or ".", "seg_speed_audio.log")
        # 把「每段合音轨」阶段记下的行带到同一份日志里，排障时能看全链路
        logs = list(getattr(self, "audio_notes", []) or [])

        def note(msg):
            logs.append(str(msg))
            try:
                with open(log_path, "w", encoding="utf-8") as fh:
                    fh.write("分段倍速渲染 v%s 音频日志\n\n" % VERSION)
                    fh.write("\n".join(logs))
            except OSError:
                pass

        def fail(msg):
            note("结果：失败 —— %s" % msg)
            return False, msg

        note("成片：%s" % video)
        note("面板 fps=%s base=%s，实际 %.4f" % (s.fps, s.fps_base, fps))
        note("时间线起点帧 %d，声音来源 %s，音频场景 %r" % (int(f0), s.audio_mode, s.audio_scene))
        note("变速跟随 %s，音量 %.3f，偏移 %.3f 秒" % (s.audio_follow_speed, s.audio_volume, s.audio_offset))
        note("ffmpeg：%s" % ffmpeg)

        mode = s.audio_mode
        if mode == "AUTO":
            tsc = target_scene(s)
            se = getattr(tsc, "sequence_editor", None)
            strips = getattr(se, "strips", None) if se is not None else None
            has_vse = strips is not None and len(strips) > 0
            has_file = bool(s.audio_file) and os.path.isfile(
                bpy.path.abspath(s.audio_file))
            note("自动判定：VSE 条带 %s，音频文件 %s" % (
                _vse_report(tsc), repr(s.audio_file)))
            if has_vse:
                mode = "SCENE"
            elif has_file:
                mode = "FILE"
            else:
                return fail("自动模式没找到音频：VSE 里没有条带，也没选音频文件")

        if mode == "SCENE":
            src = os.path.join(tmp, "_scene_mix.wav")
            segs = list(s.segments)
            f_last = max([sg.end for sg in segs] + [int(round(f0))])
            total_dur = sum(max(0.02, (sg.end + 1 - sg.start) / fps) for sg in segs)
            ok, err = _mixdown_scene_audio(
                src, target_scene(s), ffmpeg,
                frame_range=(int(round(f0)), int(f_last)),
                expect_duration=total_dur)
            note("场景混音 → %s" % src)
            if not ok:
                return fail("场景混音失败：%s" % err)
        else:
            src = bpy.path.abspath(s.audio_file or "")
            note("音频文件 → %s" % src)
            if not src or not os.path.isfile(src):
                return fail("音频文件不存在或为空：%r" % s.audio_file)
            sdb, speak = _audio_stats(ffmpeg, src)
            note("源音频体检：mean=%s dB peak=%s dB" % (sdb, speak))
            if sdb is not None and sdb < -60.0:
                return fail("选中的音频文件本身几乎是静音（mean %s dB），换个文件试试" % sdb)

        mux_tmp = video + ".audio.mp4"

        # 不随段变速：整条原样贴上去
        if not s.audio_follow_speed:
            args = ["-y", "-i", video]
            if abs(s.audio_offset) > 1e-4:
                args += ["-itsoffset", "%.4f" % s.audio_offset]
            args += ["-i", src]
            if abs(s.audio_volume - 1.0) > 1e-3:
                args += ["-filter:a", "volume=%.3f" % s.audio_volume]
            args += ["-map", "0:v:0", "-map", "1:a:0",
                     "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                     "-shortest", mux_tmp]
            ok, log = _ffmpeg_run(ffmpeg, args)
            if not ok:
                return False, log[-300:]
            os.replace(mux_tmp, video)
            return True, ""

        pieces = []
        for i, (start, end, step, idx) in enumerate(self.seg_list):
            t0 = max(0.0, (start - f0) / fps + s.audio_offset)
            dur = max(0.02, (end + 1 - start) / fps)
            out = os.path.join(tmp, "aud_%02d.wav" % (i + 1))
            args = ["-y", "-ss", "%.6f" % t0, "-t", "%.6f" % dur, "-i", src]
            af = []
            if step > 1:
                af.append(_atempo_chain(step))
            if abs(s.audio_volume - 1.0) > 1e-3:
                af.append("volume=%.3f" % s.audio_volume)
            if af:
                args += ["-filter:a", ",".join(af)]
            args += ["-vn", "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le", out]
            ok, log = _ffmpeg_run(ffmpeg, args)
            if not ok or not os.path.isfile(out):
                return fail("第 %d 段音频失败：%s" % (i + 1, log[-300:]))
            if os.path.getsize(out) < 2048:
                return fail("第 %d 段音频是空的（从第 %.2f 秒截取 %.2f 秒），"
                            "音频可能没有覆盖这个时间范围" % (i + 1, t0, dur))
            note("  第 %d 段 %s：截取 %.2f~%.2f 秒 %s → %d 字节" % (
                i + 1, os.path.basename(out), t0, t0 + dur,
                ("（atempo %d）" % step) if step > 1 else "", os.path.getsize(out)))
            pieces.append(out)

        if not pieces:
            return fail("没有可用的音频段")

        joined = os.path.join(tmp, "_audio_full.wav")
        if len(pieces) == 1:
            shutil.copy2(pieces[0], joined)
        else:
            list_path = os.path.join(tmp, "_aud_list.txt")
            with open(list_path, "w", encoding="utf-8") as f:
                for p in pieces:
                    f.write("file '%s'\n" % p.replace("\\", "/").replace("'", "'\\''"))
            ok, log = _ffmpeg_run(
                ffmpeg,
                ["-y", "-f", "concat", "-safe", "0", "-i", list_path, "-c", "copy", joined],
            )
            if not ok:
                return fail("音频拼接失败：%s" % log[-300:])

        args = ["-y", "-i", video, "-i", joined,
                "-map", "0:v:0", "-map", "1:a:0",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                "-shortest", mux_tmp]
        ok, log = _ffmpeg_run(ffmpeg, args)
        if not ok:
            return fail("音视频合并失败：%s" % log[-300:])
        try:
            os.replace(mux_tmp, video)
        except OSError as exc:
            return fail("音轨写好了但替换成片失败（文件是不是正在被播放器占用？）：%s" % exc)
        chk = _final_check(ffmpeg, video)
        note("成片复检：%s" % chk)
        if "音轨 ✓" not in chk:
            return fail("音轨已写入但复检不通过 —— %s" % chk)
        note("结果：成功，已把音轨写入成片")
        # 音轨中间文件用完即删；keep_segments 只该留段视频，不该留一堆 wav
        for p in pieces + [joined, os.path.join(tmp, "_aud_list.txt"),
                           os.path.join(tmp, "_scene_mix.wav"), mux_tmp]:
            try:
                if os.path.isfile(p):
                    os.remove(p)
            except OSError:
                pass
        return True, ""

    @classmethod
    def attach_audio_standalone(cls, ffmpeg, video, s, outdir, frame_start):
        """给已存在的成片补音轨（PNG 模式合成后调用）。"""
        obj = cls.__new__(cls)
        obj.tmpdir = os.path.join(outdir, "_audio_tmp")
        obj.saved = {"frame_start": frame_start}
        obj.seg_list = [
            (sg.start, sg.end, sg.step, i) for i, sg in enumerate(s.segments)
        ]
        try:
            return obj._attach_audio(ffmpeg, s, video)
        finally:
            shutil.rmtree(obj.tmpdir, ignore_errors=True)

    def _compose_video(self, s, elapsed):
        ffmpeg = _find_exe("ffmpeg", s.ffmpeg_path)
        video = _abs_file(s.video_path)
        # 成片可能被指到子目录（如 rending/com/seg_speed.mp4），目录不存在时先建
        try:
            vdir = os.path.dirname(video)
            if vdir:
                os.makedirs(vdir, exist_ok=True)
        except OSError as exc:
            s.progress_text = "成片目录无法创建：%s" % exc
            _tag_redraw()
            return
        if len(self.seg_files) == 1:
            try:
                if os.path.abspath(self.seg_files[0]) != os.path.abspath(video):
                    shutil.copy2(self.seg_files[0], video)
                ok, err = True, ""
            except Exception as exc:
                ok, err = False, str(exc)
        elif not ffmpeg:
            s.progress_text = "未找到 ffmpeg，段文件保留在 %s" % self.tmpdir
            _tag_redraw()
            return
        else:
            ok, err = _concat_videos(ffmpeg, self.seg_files, video, self.scene.ssr.quality)

        if ok:
            note = ""
            seg_with_audio = len(self.seg_audio_ok) if self.seg_audio_ok else 0
            if s.audio_mode != "NONE":
                if not ffmpeg:
                    note = " ⚠ 未找到 ffmpeg，音轨没加上"
                else:
                    aok, amsg = self._attach_audio(ffmpeg, s, video)
                    if aok:
                        note = " ＋音轨"
                    elif seg_with_audio >= len(self.seg_files):
                        # 成片音轨这条路失败，但每段自己带着音轨 —— 直接按音频一起拼，
                        # 总比交出一条无声成片强。
                        print("[seg-speed] 连续音轨失败，改用段自带音轨拼接:", amsg)
                        ok2, _err2 = _concat_videos(
                            ffmpeg, self.seg_files, video, s.quality, keep_audio=True)
                        note = " ＋音轨（按段拼接）" if ok2 else " ⚠ 音频没加上：%s" % amsg
                    else:
                        note = " ⚠ 音频没加上：%s" % amsg
                        print("[seg-speed] 音频处理失败:", amsg)
            size_mb = os.path.getsize(video) / (1024.0 * 1024.0)
            check = _final_check(ffmpeg, video) if ffmpeg else ""
            s.progress_text = "完成：%s（%.1f MB）%s%s" % (
                os.path.basename(video), size_mb, note,
                (" ｜ " + check) if check else "",
            )
            if not s.keep_segments:
                shutil.rmtree(self.tmpdir, ignore_errors=True)
        else:
            s.progress_text = "拼接失败，段文件保留在 %s" % self.tmpdir
            print("[seg-speed] 拼接失败:", err)
        _tag_redraw()


# ----------------------------------------------------------------------------
# 渲染操作
# ----------------------------------------------------------------------------


def _reap_child_on_exit():
    """Blender 正常退出（File > Quit / 关窗口）时，别把后台渲染进程留成孤儿。

    非正常退出（任务管理器杀进程、崩溃）这里不会执行，靠驱动脚本里的
    _watch_parent 看门狗兜底：父进程消失 → 子进程 2 秒内自行退出。
    """
    sess = _RenderSession._active
    child = getattr(sess, "child", None) if sess is not None else None
    if child is not None and child.poll() is None:
        try:
            child.terminate()
            child.wait(timeout=5)
        except Exception:
            try:
                child.kill()
            except Exception:
                pass


class SSR_OT_render(bpy.types.Operator):
    bl_idname = "seg_speed.render"
    bl_label = "开始分段渲染"
    bl_description = "按配置的段渲染：视频模式每段直接出 mp4，PNG 模式出连续序列"

    def execute(self, context):
        s = context.scene.ssr
        if s.running or _RenderSession._active is not None:
            self.report({"WARNING"}, "正在渲染中")
            return {"CANCELLED"}
        if not len(s.segments):
            self.report({"ERROR"}, "还没有添加任何段")
            return {"CANCELLED"}

        total = _total_frames(s)
        if not total:
            self.report({"ERROR"}, "段范围内没有可渲染的帧（检查起始/结束帧）")
            return {"CANCELLED"}

        outdir = _abs_dir(s.out_dir)
        os.makedirs(outdir, exist_ok=True)

        s.running = True
        s.cancel_flag = False
        s.progress = 0.0
        s.progress_text = "准备中… 共 %d 帧" % total

        try:
            context.window_manager.progress_begin(0, total)
        except Exception:
            pass

        session = _RenderSession(context.scene, outdir, s.output_mode)
        _RenderSession._active = session
        session.start()

        msg = "开始渲染 %d 帧（%s）→ %s" % (
            total,
            "视频直出" if s.output_mode == "VIDEO" else "PNG 序列",
            outdir,
        )
        if s.output_mode == "VIDEO" and not _find_exe("ffmpeg", s.ffmpeg_path):
            msg += "　⚠ 未找到 ffmpeg，拼接将跳过（段文件会保留）"
        self.report({"INFO"}, msg)
        return {"FINISHED"}


class SSR_OT_audio_diag(bpy.types.Operator):
    bl_idname = "seg_speed.audio_diag"
    bl_label = "诊断音频"
    bl_description = "列出各场景序列编辑器的条带，并试着混一次音频看结果"

    def execute(self, context):
        s = context.scene.ssr
        ffmpeg = _find_exe("ffmpeg", s.ffmpeg_path)
        try:
            use_seq = context.scene.render.use_sequencer
        except Exception:
            use_seq = None
        lines = ["音频来源：%s ｜ Use Sequencer=%s" % (s.audio_mode, use_seq)]
        for sc in bpy.data.scenes:
            lines.append("%s：%s" % (sc.name, _vse_report(sc)))
        if s.audio_mode == "FILE":
            src_f = bpy.path.abspath(s.audio_file or "")
            if not src_f or not os.path.isfile(src_f):
                lines.append("外部文件：不存在 %s" % (src_f or "(空)"))
            else:
                mean_db, peak_db = _audio_stats(ffmpeg, src_f)
                lines.append("外部文件 %s：mean=%s dB peak=%s dB" % (
                    os.path.basename(src_f), mean_db, peak_db))
        if s.audio_mode in ("SCENE", "AUTO"):
            target = target_scene(s)
            tmpdir = _abs_dir(s.out_dir) or bpy.app.tempdir
            src = os.path.join(tmpdir, "_diag_mix.wav")
            ok, msg = _mixdown_scene_audio(src, target, ffmpeg)
            lines.append("试混【%s】：%s%s" % (
                target.name, "成功 " if ok else "失败 ", msg))
            if ok and ffmpeg:
                mean_db, peak_db = _audio_stats(ffmpeg, src)
                lines.append("音量 mean=%s dB peak=%s dB" % (mean_db, peak_db))
            try:
                os.remove(src)
            except Exception:
                pass
        txt = "\n".join(lines)
        s.progress_text = txt
        self.report({"INFO"}, txt.replace("\n", " | "))
        return {"FINISHED"}


class SSR_OT_sync_fps(bpy.types.Operator):
    bl_idname = "seg_speed.sync_fps"
    bl_label = "跟随场景帧率"
    bl_description = "把播放帧率同步为当前场景设置的帧率"

    def execute(self, context):
        r = context.scene.render
        try:
            fps = float(r.fps) / (float(r.fps_base) or 1.0)
        except Exception:
            fps = 24.0
        context.scene.ssr.fps = max(1, int(round(fps)))
        try:
            context.scene.ssr.fps_base = float(r.fps_base) or 1.0
        except Exception:
            context.scene.ssr.fps_base = 1.0
        return {"FINISHED"}


class SSR_OT_cancel(bpy.types.Operator):
    bl_idname = "seg_speed.cancel"
    bl_label = "取消渲染"

    def execute(self, context):
        context.scene.ssr.cancel_flag = True
        return {"FINISHED"}


# ----------------------------------------------------------------------------
# PNG 模式合成
# ----------------------------------------------------------------------------


class SSR_OT_compose(bpy.types.Operator):
    bl_idname = "seg_speed.compose"
    bl_label = "合成视频"
    bl_description = "把已渲染的 PNG 序列按播放帧率合成为 mp4"

    def execute(self, context):
        s = context.scene.ssr
        outdir = _abs_dir(s.out_dir)
        pattern = os.path.join(outdir, "%s_*.png" % s.prefix)
        files = sorted(glob.glob(pattern))
        if not files:
            self.report({"ERROR"}, "没有找到序列图：%s" % pattern)
            return {"CANCELLED"}

        video = _abs_file(s.video_path)
        ffmpeg = _find_exe("ffmpeg", s.ffmpeg_path)

        if ffmpeg:
            cmd = [
                ffmpeg, "-y",
                "-framerate", ("%.6f" % _real_fps(s)),
                "-start_number", "0",
                "-i", os.path.join(outdir, "%s_%%05d.png" % s.prefix),
                "-c:v", "libx264", "-crf", str(_crf_of(s.quality)), "-pix_fmt", "yuv420p",
                video,
            ]
            try:
                res = subprocess.run(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    creationflags=_hide_console_flag(),
                )
                if res.returncode == 0:
                    note = ""
                    if s.audio_mode != "NONE":
                        try:
                            aok, amsg = _RenderSession.attach_audio_standalone(
                                ffmpeg, video, s, outdir, context.scene.frame_start)
                            note = " ＋音轨" if aok else "（音频失败：%s）" % amsg
                        except Exception as exc:
                            note = "（音频失败：%s）" % exc
                    self.report({"INFO"}, "已生成 %s%s" % (video, note))
                    s.progress_text = "成片：%s%s" % (os.path.basename(video), note)
                    return {"FINISHED"}
            except Exception as exc:
                self.report({"WARNING"}, "ffmpeg 合成失败，改用 Blender 合成：%s" % exc)

        try:
            self._compose_vse(context, files, video, _real_fps(s))
            self.report({"INFO"}, "已生成 %s（Blender 内部合成）" % video)
            return {"FINISHED"}
        except Exception as exc:
            self.report({"ERROR"}, "合成失败：%s" % exc)
            return {"CANCELLED"}

    def _compose_vse(self, context, files, video, fps):
        src = context.scene
        name = "SEG_SPEED_COMPOSE"
        old = bpy.data.scenes.get(name)
        if old:
            bpy.data.scenes.remove(old)
        sc = bpy.data.scenes.new(name)
        sc.render.resolution_x = src.render.resolution_x
        sc.render.resolution_y = src.render.resolution_y
        sc.render.resolution_percentage = src.render.resolution_percentage
        sc.render.fps = fps

        se = sc.sequence_editor_create()
        strips = getattr(se, "strips", None)
        if strips is None:
            strips = se.sequences
        strip = strips.new_image(name="seq", filepath=files[0], channel=1, frame_start=1)
        for f in files[1:]:
            strip.elements.append(os.path.basename(f))

        sc.frame_start = 1
        sc.frame_end = len(files)
        sc.render.image_settings.file_format = "FFMPEG"
        sc.render.ffmpeg.format = "MPEG4"
        sc.render.ffmpeg.codec = "H264"
        sc.render.ffmpeg.constant_rate_factor = "HIGH"
        sc.render.filepath = os.path.splitext(video)[0]

        bpy.ops.render.render(animation=True, scene=sc.name)


# ----------------------------------------------------------------------------
# UI
# ----------------------------------------------------------------------------


class SSR_UL_segments(bpy.types.UIList):
    bl_idname = "SSR_UL_segments"

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        if self.layout_type in {"DEFAULT", "COMPACT"}:
            row = layout.row(align=True)
            row.label(text="%d" % (index + 1))
            row.prop(item, "start", text="")
            row.label(text="→")
            row.prop(item, "end", text="")
            row.prop(item, "step", text="×")
            txt = "%d帧" % item.frame_count()
            if item.step > 1:
                txt += " (%.1fx)" % (item.step)
            row.label(text=txt)
        else:
            layout.label(text="", icon="NONE")


class SSR_PT_main(bpy.types.Panel):
    bl_label = "分段倍速渲染 v%s" % VERSION
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "分段倍速"

    def draw(self, context):
        layout = self.layout
        s = context.scene.ssr

        col = layout.column(align=True)
        row = col.row()
        row.template_list("SSR_UL_segments", "", s, "segments", s, "active_index", rows=4)
        side = row.column(align=True)
        side.operator("seg_speed.add_segment", text="", icon="ADD")
        side.operator("seg_speed.remove_segment", text="", icon="REMOVE")
        side.separator()
        side.operator("seg_speed.move_segment", text="", icon="TRIA_UP").direction = "UP"
        side.operator("seg_speed.move_segment", text="", icon="TRIA_DOWN").direction = "DOWN"

        row = col.row(align=True)
        row.operator("seg_speed.add_segment", text="＋正常速 ×1").step = 1
        row.operator("seg_speed.add_segment", text="＋快放 ×4").step = 4
        col.operator("seg_speed.reset_from_scene", icon="FILE_REFRESH")

        total = _total_frames(s)
        orig = sum(max(1, seg.end - seg.start + 1) for seg in s.segments)
        box = layout.box()
        col = box.column(align=True)
        col.label(text="段数 %d   总输出帧数 %d" % (len(s.segments), total))
        col.label(text="成片时长 %.2f 秒（%s fps）" % (total / _real_fps(s), ("%g" % round(_real_fps(s), 3))))
        if total and orig:
            col.label(text="相对原始 %d 帧节省 %.0f%%" % (orig, (1.0 - total / float(orig)) * 100.0))
            if s.est_seconds:
                col.label(text="预计渲染 %.1f 分钟" % (s.est_seconds * total / 60.0))

        box = layout.box()
        col = box.column()
        col.label(text="输出")
        col.row(align=True).prop(s, "output_mode", expand=True)
        if s.output_mode == "VIDEO":
            col.row(align=True).prop(s, "render_process", expand=True)
            if s.render_process == "INPROC":
                col.label(text="本进程会弹出渲染窗口，画面进度直接看得见", icon="RENDER_STILL")
            else:
                col.label(text="独立进程不弹窗口，进度只看此面板（界面零卡顿）", icon="INFO")
        row = col.row(align=True)
        row.prop(s, "lock_ui", toggle=True,
                 icon="LOCKED" if s.lock_ui else "UNLOCKED",
                 text="锁定界面（渲染时关掉 3D 视图显示）")
        if s.lock_ui:
            col.label(text="渲染时视口切线框、只刷新此面板与渲染窗口，结束自动还原", icon="INFO")
        col.prop(s, "out_dir")
        row = col.row(align=True)
        row.prop(s, "fps")
        row.operator("seg_speed.sync_fps", text="", icon="FILE_REFRESH")
        sc = context.scene.render
        try:
            sc_fps = round(float(sc.fps) / (float(sc.fps_base) or 1.0), 2)
        except Exception:
            sc_fps = 24.0
        if abs(s.fps_base - 1.0) > 0.0001:
            col.prop(s, "fps_base")
        if abs(sc_fps - _real_fps(s)) > 0.01:
            col.label(
                text="场景 %s fps，成片按 %s fps 编码" % (sc_fps, "%g" % round(_real_fps(s), 3)),
                icon="INFO")
        col.prop(s, "quality")
        col.prop(s, "auto_shutter")
        if s.output_mode == "PNG":
            col.prop(s, "prefix")
        col.separator()
        col.prop(s, "auto_compose")
        if s.output_mode == "VIDEO":
            col.prop(s, "keep_segments")
        col.prop(s, "video_path")
        if s.output_mode == "VIDEO":
            col.prop(s, "ffmpeg_path")
            ff = _find_exe("ffmpeg", s.ffmpeg_path)
            if ff:
                col.label(text=os.path.basename(ff), icon="CHECKMARK")
            else:
                col.label(text="未找到 ffmpeg，无法拼接成片", icon="ERROR")

        box = layout.box()
        col = box.column()
        col.label(text="音频")
        col.row(align=True).prop(s, "audio_mode", expand=True)
        if s.audio_mode == "FILE":
            col.prop(s, "audio_file")
            if not s.audio_file:
                col.label(text="请选择音频文件", icon="ERROR")
        elif s.audio_mode == "SCENE":
            col.prop(s, "audio_scene")
        if s.audio_mode != "NONE":
            col.prop(s, "audio_offset")
            col.prop(s, "audio_volume")
            col.prop(s, "audio_follow_speed")
            col.label(text="每段渲完就合上本段声音，段文件单独拿出来也有音轨", icon="SOUND")
        else:
            col.label(text="当前不输出音轨（段文件也没有声音）", icon="INFO")
        row = col.row()
        row.scale_y = 1.3
        row.operator("seg_speed.audio_diag", icon="SOUND",
                     text="诊断音频 · 查为什么没声音")

        layout.separator()
        if s.running:
            layout.progress(factor=s.progress, type="BAR", text=s.progress_text)
            layout.operator("seg_speed.cancel", icon="CANCEL")
        else:
            row = layout.row()
            row.scale_y = 1.6
            row.operator("seg_speed.render", icon="RENDER_ANIMATION")
            if s.output_mode == "PNG":
                layout.operator("seg_speed.compose", icon="FILE_MOVIE")
            if s.progress_text:
                layout.label(text=s.progress_text, icon="INFO")


# ----------------------------------------------------------------------------
# 注册
# ----------------------------------------------------------------------------

CLASSES = (
    SSRSegment,
    SSRSettings,
    SSR_OT_add_segment,
    SSR_OT_remove_segment,
    SSR_OT_move_segment,
    SSR_OT_reset_from_scene,
    SSR_OT_render,
    SSR_OT_cancel,
    SSR_OT_sync_fps,
    SSR_OT_audio_diag,
    SSR_OT_compose,
    SSR_UL_segments,
    SSR_PT_main,
)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.ssr = bpy.props.PointerProperty(type=SSRSettings)
    atexit.register(_reap_child_on_exit)


def unregister():
    if hasattr(bpy.types.Scene, "ssr"):
        del bpy.types.Scene.ssr
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
