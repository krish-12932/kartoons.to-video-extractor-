#!/usr/bin/env python3
"""Search module: anime search -> pehla result kholo.

Step 2 (login ke baad): /home par search icon dabao,
anime naam likho, results me se pehla result kholo.
"""
import re
import pathlib

from modules.cloudflare import wait_cloudflare, challenge_visible
from modules.config import HOME_URL, GEMINI_API_KEY, AI_VISION_ON, HTML_DUMP_ON
from modules.ai_vision import ai_click

try:
    from modules.html_dump import save_html
except Exception:
    def save_html(page, name):
        return ""


def _dump(page, name: str):
    """HTML_DUMP_ON hai to full page HTML html_dumps/ me save karo."""
    if not HTML_DUMP_ON:
        return ""
    try:
        return save_html(page, name)
    except Exception:
        return ""


def dump_header_buttons(page):
    """HOME ka header HTML dump karo — div/button/a me se jo bhi svg rakhta hai.
    DevTools proof: search icon DIV hai (sc-fZsZjS jhodQc), button NAHI."""
    try:
        page.screenshot(path=str(pathlib.Path(__file__).resolve().parent.parent / "debug_home.png"))
    except Exception:
        pass
    print("    [html] header buttons dump:")
    try:
        btns = page.locator("header div:has(svg), header button, header a, nav button, nav a").all()
        for i, b in enumerate(btns[:10]):
            try:
                if not b.is_visible(timeout=500):
                    continue
                tag = b.evaluate("(e) => e.outerHTML.slice(0,150)") or ""
                box = b.bounding_box() or {}
                print("      [%d] x=%s w=%s :: %s" % (i, box.get("x"), box.get("width"), tag[:120]))
            except Exception:
                continue
    except Exception as e:
        print("    [html] dump fail: %s" % str(e)[:100])


def find_search_icon(page):
    """DevTools proof ke hisab se: search icon ka EXACT signature:
      <div class="sc-fZsZjS jhodQc"><svg data-icon="magnifying-glass" ...>
    Bell icon ka data-icon="bell" hota hai — isliye EXACT match karo,
    position (x) se guess MAT karo. Wahi bell-wala bug tha."""
    dump_header_buttons(page)
    print("    [html] search icon dhoond raha hun (EXACT data-icon=magnifying-glass)...")
    # 1. SABSE SAFE: khud svg dhoondo — ye sirf search ho sakta hai, bell kabhi nahi
    try:
        svg = page.locator("svg[data-icon='magnifying-glass']").first
        if svg.is_visible(timeout=4000):
            print("    [html] svg[data-icon=magnifying-glass] mila — parent div click karunga.")
            try:
                parent = svg.locator("xpath=..")
                return parent, "div>svg[data-icon=magnifying-glass]"
            except Exception:
                return svg, "svg[data-icon=magnifying-glass]"
    except Exception:
        pass
    # 2. Fallback: class se (FontAwesome)
    try:
        svg2 = page.locator("svg.fa-magnifying-glass").first
        if svg2.is_visible(timeout=3000):
            print("    [html] svg.fa-magnifying-glass mila.")
            try:
                return svg2.locator("xpath=.."), "div>svg.fa-magnifying-glass"
            except Exception:
                return svg2, "svg.fa-magnifying-glass"
    except Exception:
        pass
    print("    [html] EXACT icon nahi mila — bell se confuse na ho, isliye generic fallback NAHI.")
    return None, None


def search_and_open(page, title: str):
    print("[1] Search: %s" % title)
    try:
        page.goto(HOME_URL, wait_until="domcontentloaded", timeout=45000)
    except Exception:
        pass
    page.wait_for_timeout(3000)
    wait_cloudflare(page, timeout=30)
    _dump(page, "home")

    if challenge_visible(page):
        print("[!] Login/verify pending lag raha hai.")
        return False

    # HOME par "Search Everything" hero box pehle se khula hai (screenshot proof).
    # Icon click karne ki zaroorat NAHI — seedha box me type karo.
    # Pehle hero input dhoondo (page body me, header ke bahar wala).
    box = None
    hero_selectors = [
        "input[placeholder*='Search Everything' i]",
        "input[placeholder*='earch Everything' i]",
        "main input", "input[placeholder*='earch' i]",
        "input[type='search']",
    ]
    for sel in hero_selectors:
        try:
            els = page.locator(sel).all()
            for el in els[:5]:
                try:
                    if not el.is_visible(timeout=2000):
                        continue
                    # header ke andar wala nahi, body wala chahiye
                    ph = (el.get_attribute("placeholder") or "")
                    box = el
                    print("    [html] hero search box mila: %s (placeholder='%s')" % (sel, ph[:30]))
                    break
                except Exception:
                    continue
            if box is not None:
                break
        except Exception:
            continue

    # Hero box na mile to icon click karke kholo (fallback)
    if box is None:
        print("    [html] hero box nahi mila, icon click kar raha hun...")
        icon_el, icon_sel = find_search_icon(page)
        if icon_el is not None:
            try:
                icon_el.click(timeout=5000)
                page.wait_for_timeout(2500)
                print("    [html] search icon click OK (%s)" % icon_sel)
            except Exception as e:
                print("    [html] icon click fail: %s" % str(e)[:100])
        for sel in ["input[type='search']", "input[name*='search' i]",
                    "input[placeholder*='earch' i]",
                    "input[placeholder*='itle' i]",
                    "header input", "nav input", "input[type='text']"]:
            try:
                el = page.locator(sel).first
                if el.is_visible(timeout=4000):
                    box = el
                    print("    [html] search box mila: %s" % sel)
                    break
            except Exception:
                continue
    if box is None:
        # Icon click ke baad box render hone me time lag sakta hai — ek baar aur wait karke retry
        print("    [html] box turant nahi mila, 5s wait karke retry...")
        page.wait_for_timeout(5000)
        for sel in ["input[type='search']", "input[name*='search' i]",
                    "input[placeholder*='earch' i]",
                    "input[placeholder*='itle' i]",
                    "header input", "nav input", "input[type='text']"]:
            try:
                el = page.locator(sel).first
                if el.is_visible(timeout=4000):
                    box = el
                    print("    [html] search box mila (retry): %s" % sel)
                    break
            except Exception:
                continue
    if box is None:
        try:
            page.screenshot(path=str(pathlib.Path(__file__).resolve().parent.parent / "debug_search.png"))
        except Exception:
            pass
        raise RuntimeError("Search box nahi mila. debug_search.png dekho.")
    try:
        box.click(timeout=5000)
        box.fill(title, timeout=5000)
        page.wait_for_timeout(1200)
        # LIVE results aate hain (image me "Looking through all titles...")
        # Enter ke baad results ka wait karo, "Searching for <title>" text check karo
        box.press("Enter")
    except Exception as e:
        raise RuntimeError("Search type fail: %s" % str(e)[:120])
    page.wait_for_timeout(6000)
    _dump(page, "search_results")
    try:
        body = (page.content() or "").lower()
        if ('searching for "%s"' % title.lower()) in body or "looking through" in body:
            print("    [html] search page confirm: results load ho rahe hain.")
    except Exception:
        pass

    # Pehla result kholo (screenshot proof: href=/show/naruto-68186, TV Shows grid).
    # NOTE: site /show/ + /movie/ use karti hai.
    # S1E1 manga hai to TV SHOW chahiye, MOVIE nahi -> scoring:
    #   exact title (+100), /show/ (+50), /movie/ (-50 jab episode chahiye).
    # Order: (1) HTML selector exact-title match, (2) AI vision fallback (neeche ho to bhi).
    for _ in range(3):
        try:
            links = page.locator(
                "a[href*='/show/'], a[href*='/movie/'], "
                "a[href*='/watch/'], a[href*='/anime/'], a[href*='/title/']"
            ).all()
            scored = []
            want = title.strip().lower()
            for a in links[:20]:
                try:
                    if not a.is_visible():
                        continue
                    txt = (a.inner_text() or "").strip().lower()
                    href = a.get_attribute("href") or ""
                    if not href:
                        continue
                    score = 0
                    if txt == want:
                        score += 100
                    elif txt.startswith(want + " ") or txt.startswith(want + ":"):
                        score += 60
                    elif want and want.split()[0] in txt:
                        score += 10
                    elif len(txt) > 2:
                        score += 1
                    else:
                        continue
                    if "/show/" in href:
                        score += 50
                    if "/movie/" in href:
                        score -= 50  # episode chahiye to movie galat hai
                    scored.append((score, a, href, txt))
                except Exception:
                    continue
            scored.sort(key=lambda t: t[0], reverse=True)
            if scored:
                score, a, href, txt = scored[0]
                url = href if href.startswith("http") else "https://kartoons.to" + href
                print("[1] Result khol raha hun (score=%d): %s (%s)" % (score, url, txt[:60]))
                page.goto(url, wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(4000)
                _dump(page, "result_page")
                return True
        except Exception:
            pass
        page.wait_for_timeout(3000)
    # HTML se sahi title nahi mila -> AI vision: "naruto kaha par hai" dekh ke click.
    if AI_VISION_ON and GEMINI_API_KEY:
        page.wait_for_timeout(2000)
        ok = ai_click(
            page,
            "the poster/card image or title text for the anime/TV show named '%s' "
            "in the search results grid (prefer the EXACT title match, scroll position "
            "does not matter)" % title,
            label="result '%s'" % title,
        )
        if ok:
            page.wait_for_timeout(4000)
            print("[1] AI se result khola: %s" % title)
            return True
    try:
        page.screenshot(path=str(pathlib.Path(__file__).resolve().parent.parent / "debug_results.png"))
    except Exception:
        pass
    raise RuntimeError("Search result nahi mila. debug_results.png dekho.")
