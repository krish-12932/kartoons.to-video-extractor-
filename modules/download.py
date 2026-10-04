#!/usr/bin/env python3
"""Download: valid segments -> parts -> duplicate check -> ffmpeg concat -> single .mp4.

Site kabhi ek hi content do baar alag quality me serve karti hai
(pehla segment 480p, dobara 720p) — dono alag URL hote hain isliye
capture me filter nahi hota. Download ke baad content se check karke
duplicate part hatao, warna video me 7-8s ka repeat aa jayega.
"""
import json
import pathlib
import shutil
import subprocess
import time
import urllib.request

from modules.capture import is_ok_url

_SIG_W = _SIG_H = 32          # duplicate check ke liye chhota frame size
_DUP_MAX_MAD = 3.0            # isse neeche = same content (0 = bilkul same)
_DUP_MIN_FRAMES = 5
_DUP_LEN_RATIO = 0.9          # frame count ka ratio (duration match)


def _gray_sig(path):
    """Part ka 32x32 gray signature: list of frame-byte-strings. Fail -> None."""
    cmd = ["ffmpeg", "-v", "error", "-i", str(path), "-an",
           "-vf", "scale=%d:%d,format=gray" % (_SIG_W, _SIG_H),
           "-f", "rawvideo", "-"]
    try:
        raw = subprocess.run(cmd, capture_output=True).stdout
    except Exception:
        return None
    fsz = _SIG_W * _SIG_H
    n = len(raw) // fsz
    if n < _DUP_MIN_FRAMES:
        return None
    return [raw[i * fsz:(i + 1) * fsz] for i in range(n)]


def _is_dup(sig_a, sig_b):
    """Do signatures same content ke hain? (MAD early-abort ke saath)"""
    if not sig_a or not sig_b:
        return False
    la, lb = len(sig_a), len(sig_b)
    if min(la, lb) / float(max(la, lb)) < _DUP_LEN_RATIO:
        return False
    m = min(la, lb)
    fsz = len(sig_a[0])
    total = 0
    for k in range(m):
        for x, y in zip(sig_a[k], sig_b[k]):
            d = x - y
            total += d if d >= 0 else -d
        if k >= 9 and total / float((k + 1) * fsz) > _DUP_MAX_MAD:
            return False
    return total / float(m * fsz) <= _DUP_MAX_MAD


def _res_of(path):
    """Part ki resolution (width*height) — behtar wala duplicate rakho."""
    try:
        p = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height", "-of", "json", str(path)],
            capture_output=True, text=True, timeout=30).stdout
        s = json.loads(p)["streams"][0]
        return int(s.get("width", 0)) * int(s.get("height", 0))
    except Exception:
        return 0


def dedupe_parts(tmp, count):
    """Adjacent parts me content-duplicate dhundho; behtar resolution wala rakho.
    Returns kept part-index list (order me)."""
    kept = []
    prev_i, prev_sig = None, None
    for i in range(count):
        sig = _gray_sig(tmp / ("part%04d.ts" % i))
        if prev_sig is not None and sig is not None and _is_dup(prev_sig, sig):
            cur_r = _res_of(tmp / ("part%04d.ts" % i))
            if cur_r > _res_of(tmp / ("part%04d.ts" % prev_i)):
                dropped, kept_i = prev_i, i
                kept[-1] = i
                prev_i, prev_sig = i, sig
                print("    [dup] part%04d = part%04d repeat; behtar resolution wala rakha"
                      % (dropped, kept_i))
            else:
                print("    [dup] part%04d = part%04d ka repeat — drop kiya"
                      % (i, prev_i))
        else:
            kept.append(i)
            prev_i, prev_sig = i, sig
        if i and i % 50 == 0:
            print("    ... dup-check %d/%d" % (i, count))
    return kept


def concat_parts(tmp, kept, video):
    """kept parts ko list.txt se join karke final video banao."""
    with open(tmp / "list.txt", "w", encoding="utf-8") as lf:
        for i in kept:
            lf.write("file 'part%04d.ts'\n" % i)
    cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
           "-i", str(tmp / "list.txt"), "-c", "copy", str(video)]
    print("[6] ffmpeg join...")
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(tmp))
    if r.returncode != 0:
        print(r.stderr[-2500:])
        raise RuntimeError("ffmpeg join fail")
    print("[SUCCESS] database me saved: %s" % video)


def download_segments(urls, headers, folder, video):
    clean = [u for u in urls if is_ok_url(u)]
    removed = len(urls) - len(clean)
    print("[5] download: %d valid parts (%d gande hataye)" % (len(clean), removed))
    print("[5] Output: %s" % video)
    if len(clean) < 3:
        raise RuntimeError("Valid segments bahut kam (%d). Video poori chali thi?" % len(clean))
    tmp = pathlib.Path(folder) / "_parts"
    tmp.mkdir(parents=True, exist_ok=True)
    base_h = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
              "Referer": "https://kartoons.to/", "Origin": "https://kartoons.to"}
    base_h.update(headers or {})
    for i, u in enumerate(clean):
        out = tmp / ("part%04d.ts" % i)
        if out.exists() and out.stat().st_size > 0:
            continue
        for _ in range(3):
            try:
                req = urllib.request.Request(u, headers=base_h)
                with urllib.request.urlopen(req, timeout=60) as r, open(out, "wb") as f:
                    while True:
                        chunk = r.read(256 * 1024)
                        if not chunk:
                            break
                        f.write(chunk)
                break
            except Exception as e:
                if i < 3:
                    print("    [fail] part %d: %s" % (i, str(e)[:120]))
                time.sleep(2)
        if i % 25 == 0:
            print("    ... %d/%d" % (i, len(clean)))
    print("[5.1] duplicate content check...")
    kept = dedupe_parts(tmp, len(clean))
    dropped = len(clean) - len(kept)
    if dropped:
        print("[5.1] %d duplicate part(hataye) — video me repeat nahi aayega." % dropped)
    else:
        print("[5.1] koi duplicate nahi mila.")
    concat_parts(tmp, kept, video)
    try:
        shutil.rmtree(tmp, ignore_errors=True)
        print("[6] _parts temp folder saaf (%d files)." % len(clean))
    except Exception as e:
        print("[6] _parts cleanup fail (safe hai): %s" % str(e)[:80])
