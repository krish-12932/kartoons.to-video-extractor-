#!/usr/bin/env python3
"""MAIN FILE — app.py: anime naam + episode likho, download database me payo.

Flow:
  [0] login    -> modules/login.py      (.env se auto-login, cookie yaad)
  [1] search   -> modules/search.py     (anime dhoondo, pehla result kholo)
  [2] episode  -> modules/episode.py    (episode kholo + mute/4x play)
  [3] capture  -> modules/capture.py    (segment URLs pakdo, scraper system)
  [4] download -> modules/download.py   (parts -> ffmpeg join -> .mp4)

Output: C:/Users/hp/database/anime/<Title>/Episode_<N>/Episode_<N>.mp4

Usage:
  python app.py
"""
from playwright.sync_api import sync_playwright

from modules.config import (
    KARTOONS_EMAIL, KARTOONS_PASSWORD, mask_email,
    GEMINI_API_KEY, AI_VISION_ON,
    UNATTENDED, HTML_DUMP_ON, AUTO_FIND,
    make_db_paths, save_info_json,
)
from modules.browser import launch_real_chrome, connect_cdp, close_all
from modules.login import logged_in, try_auto_login
from modules.search import search_and_open
from modules.episode import open_episode, start_player
from modules.capture import init_capture, watch_and_collect
from modules.download import download_segments

try:
    from modules.html_dump import save_html as _save_html
except Exception:
    def _save_html(page, name):
        return ""

try:
    from modules.unattended import input_with_timeout
except Exception:
    def input_with_timeout(prompt, timeout=None):
        try:
            return input(prompt)
        except Exception:
            return ""


def _dump(page, name: str):
    if not HTML_DUMP_ON:
        return ""
    try:
        return _save_html(page, name)
    except Exception:
        return ""


def main():
    title = input("Anime name likho (jaise naruto): ").strip() or "naruto"
    season = input("Season likho (jaise 1): ").strip() or "1"
    ep = input("Episode number likho (jaise 1): ").strip() or "1"
    ep_full = "S%sE%s" % (season, ep)
    folder, video = make_db_paths(title, ep_full)
    print("Target: Season %s Episode %s" % (season, ep))
    print("Database folder: %s" % folder)
    print("Output file: %s" % video)
    if KARTOONS_EMAIL and KARTOONS_PASSWORD:
        print("Login: .env me mila (%s) — challenge aaya to auto-login hoga."
              % mask_email(KARTOONS_EMAIL))
    else:
        print("Login: .env me nahi mila — sirf manual tick hoga. (.env.example dekho)")
    if AI_VISION_ON and GEMINI_API_KEY:
        print("AI vision: ON (Gemini fallback — search-result + season/episode select).")
    elif AI_VISION_ON:
        print("AI vision: key nahi mili (.env me GEMINI_API_KEY dalo) — sirf HTML chalega.")
    else:
        print("AI vision: OFF — sirf HTML chalega.")
    if UNATTENDED:
        print("UNATTENDED=1: input() par nahi atkegi. Galat S/E hua to")
        print("  html_dumps/ + screenshot chhod ke clean exit (galat download NAHI).")
    if AUTO_FIND:
        print("AUTO_FIND=1: (Season, Ep) site par na mile to overall EP number maan ke")
        print("  sahi Season/Episode khud dhoondhunga (jaise EP100 = S2 ka episode).")
    if HTML_DUMP_ON:
        print("HTML dump: ON (har page ke baad html_dumps/ me save hoga).")
    if video.exists() and video.stat().st_size > 0:
        again = input_with_timeout("Ye episode pehle se downloaded hai. Dobara karu? (y/N): ").strip().lower()
        if again != "y":
            print("OK, exit.")
            return

    proc = launch_real_chrome()
    if proc is None:
        return
    with sync_playwright() as pw:
        browser, context, page = connect_cdp(pw)
        if page is None:
            close_all(None, proc)
            return
        try:
            # [0] LOGIN — pehle HOME kholo, phir EK BAAR check (double message nahi)
            from modules.config import HOME_URL
            print("[*] home khol raha hun...")
            try:
                page.goto(HOME_URL, wait_until="domcontentloaded", timeout=45000)
            except Exception:
                pass
            page.wait_for_timeout(3000)
            print("[*] login check kar raha hun...")
            ok = logged_in(page)
            if ok:
                print("[*] pehle se logged in ho — login step skip.")
            else:
                print("[*] logged in nahi ho, .env se login kar raha hun (ek baar)...")
                try_auto_login(page)
            # [1] SEARCH
            search_and_open(page, title)
            # [2] EPISODE + PLAYER (False = episode nahi khula -> exit, galat download nahi)
            # Segment listeners episode kholne se PEHLE attach (pehla segment safe)
            segs, hdrs, cstate = init_capture(page, context)
            pg = open_episode(page, ep_full)
            if not pg:
                _dump(page, "episode_abort")
                print("[!] Episode step fail — exit. Galat download NAHI hui.")
                print("    html_dumps/ + debug screenshots dekho, sahi Season/Episode likh ke dobara chalao.")
                return
            page = pg
            _dump(page, "player_page")
            if not start_player(page):
                print("[!] Player khol nahi paya — 4 min tak segment ka wait karunga.")
            _dump(page, "player_started")
            # [3] CAPTURE (scraper system)
            segs, hdrs = watch_and_collect(page, context, segs, hdrs, cstate)
            if len(segs) < 3:
                print("[!] Segments nahi mile. debug screenshots dekho.")
                _dump(page, "no_segments")
                input_with_timeout("    Enter dabao band karne ke liye...")
                return
            # [3.5] Capture ho gayi — ab browser ki zaroorat nahi (download,
            #      dedupe, concat, timeline fix sab offline chalte hain).
            #      Chrome abhi band = ~10 min resources free. finally idempotent hai.
            try:
                close_all(context, proc)
                print("[*] capture complete — Chrome band (background free).")
            except Exception:
                pass
            # [4] DOWNLOAD -> database
            download_segments(segs, hdrs, folder, video)
            save_info_json(folder, video, title, ep_full, len(segs))
            print("Ho gaya! Database file: %s" % video)
        finally:
            close_all(context, proc)


if __name__ == "__main__":
    main()
