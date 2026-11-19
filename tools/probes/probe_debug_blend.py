import bpy, json, os, sys

out = {"file": bpy.data.filepath, "blender": bpy.app.version_string, "scenes": []}

for sc in bpy.data.scenes:
    r = sc.render
    d = {
        "name": sc.name,
        "frame_start": sc.frame_start,
        "frame_end": sc.frame_end,
        "frame_step": sc.frame_step,
        "frame_current": sc.frame_current,
        "fps": r.fps,
        "fps_base": r.fps_base,
        "resolution": [r.resolution_x, r.resolution_y, r.resolution_percentage],
        "engine": r.engine,
        "filepath": r.filepath,
        "image_settings": {
            "media_type": getattr(r.image_settings, "media_type", None),
            "file_format": r.image_settings.file_format,
        },
        "ffmpeg": {
            "format": r.ffmpeg.format,
            "codec": r.ffmpeg.codec,
            "constant_rate_factor": r.ffmpeg.constant_rate_factor,
            "audio_codec": r.ffmpeg.audio_codec,
            "gopsize": r.ffmpeg.gopsize,
        },
        "use_sequencer": r.use_sequencer,
        "camera": getattr(sc.camera, "name", None) if sc.camera else None,
        "objects": len(sc.objects),
        "world": getattr(sc.world, "name", None) if sc.world else None,
    }
    se = sc.sequence_editor
    strips = []
    if se:
        raw = getattr(se, "strips", None)
        if raw is None:
            raw = getattr(se, "sequences", [])
        for st in raw:
            item = {
                "name": st.name,
                "type": st.type,
                "channel": getattr(st, "channel", None),
                "frame_start": getattr(st, "frame_start", None),
                "frame_final_start": getattr(st, "frame_final_start", None),
                "frame_final_end": getattr(st, "frame_final_end", None),
            }
            if st.type == "SOUND":
                snd = getattr(st, "sound", None)
                item["sound"] = getattr(snd, "filepath", None)
                item["volume"] = getattr(st, "volume", None)
                item["pan"] = getattr(st, "pan", None)
            strips.append(item)
    d["strips"] = strips
    if hasattr(sc, "ssr"):
        s = sc.ssr
        d["ssr"] = {
            "segments": [{"start": sg.start, "end": sg.end, "step": sg.step} for sg in s.segments],
            "output_mode": s.output_mode,
            "out_dir": s.out_dir,
            "prefix": s.prefix,
            "fps": s.fps,
            "fps_base": s.fps_base,
            "quality": s.quality,
            "audio_mode": s.audio_mode,
            "audio_file": s.audio_file,
            "audio_scene": s.audio_scene,
            "audio_offset": s.audio_offset,
            "audio_volume": s.audio_volume,
            "audio_follow_speed": s.audio_follow_speed,
            "auto_shutter": s.auto_shutter,
            "auto_compose": s.auto_compose,
            "keep_segments": s.keep_segments,
            "ffmpeg_path": s.ffmpeg_path,
        }
    out["scenes"].append(d)

out["sounds"] = [{"name": s.name, "filepath": s.filepath, "packed": bool(s.packed_file)} for s in bpy.data.sounds]
out["objects_total"] = len(bpy.data.objects)
out["has_ssr_types"] = hasattr(bpy.types.Scene, "ssr")

p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "probe_debug_blend.json")
with open(p, "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print("PROBE_WROTE", p)
