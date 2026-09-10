from pathlib import Path
import json, sys, time
from playwright.sync_api import sync_playwright

SHOP_ID = 8673661
ITEMS = {
    54855244568: '白月光凡士林手作球',
    55459814572: '巨無霸黃油棒捏捏',
    46610412369: 'Needoh 冰塊平替',
    56760985158: '麥芽糖包子盲盒',
    29772093199: '磨砂冰晶麥芽糖球',
    27221345281: '麥芽糖冰塊 Needoh平替',
    50006169835: '巨無霸奶酪方塊',
    53300037514: 'Tangle 扭扭樂同款',
}
OUT = Path('assets/products')
OUT.mkdir(parents=True, exist_ok=True)

# This captures what the user asked for: the FIRST/main image visibly shown on
# each individual Shopee product page. We screenshot that rendered element
# instead of reusing shop-homepage thumbnails or unrelated reference images.

def capture_cover(page, itemid, name):
    url = f'https://shopee.tw/-i.{SHOP_ID}.{itemid}'
    print(f'OPEN {itemid} {url}', flush=True)
    page.goto(url, wait_until='domcontentloaded', timeout=60000)
    page.wait_for_timeout(7000)

    # Dismiss common consent/login overlays if present without navigating away.
    for text in ['稍後再說', '取消', '關閉', '我知道了']:
        try:
            loc = page.get_by_text(text, exact=True)
            if loc.count() and loc.first.is_visible():
                loc.first.click(timeout=800)
                page.wait_for_timeout(300)
        except Exception:
            pass

    # Find the large square image shown in the product gallery on the individual
    # item page. Shopee may render it as an <img> or as a background-image div.
    result = page.evaluate("""
    () => {
      const vw = innerWidth;
      const vh = innerHeight;
      const items = [];
      let idx = 0;
      const els = Array.from(document.querySelectorAll('img,div'));
      for (const el of els) {
        const r = el.getBoundingClientRect();
        if (r.width < 260 || r.height < 260 || r.width > 760 || r.height > 760) continue;
        if (r.bottom < 70 || r.top > 900 || r.right < 0 || r.left > vw) continue;
        const ratio = r.width / r.height;
        if (ratio < .72 || ratio > 1.38) continue;
        let src = '';
        let kind = '';
        if (el.tagName === 'IMG') {
          src = el.currentSrc || el.src || '';
          kind = 'img';
        } else {
          const bg = getComputedStyle(el).backgroundImage || '';
          const m = bg.match(/url\([\"']?(.*?)[\"']?\)/);
          if (m) { src = m[1]; kind = 'bg'; }
        }
        if (!src || !/susercontent|shopee|deo\./i.test(src)) continue;
        if (/avatar|logo|icon|banner|voucher|qrcode/i.test(src)) continue;
        const square = 1 - Math.min(1, Math.abs(1-ratio));
        const size = Math.min(r.width, r.height);
        // Main PDP image is normally a large square in the left half near the top.
        let score = size * 10 + square * 800;
        if (r.left < vw * .55) score += 900;
        if (r.top >= 80 && r.top <= 650) score += 700;
        if (r.width >= 380 && r.height >= 380) score += 900;
        if (el.tagName === 'IMG') score += 100;
        el.dataset.oaiCandidateId = String(idx);
        items.push({idx, score, src, kind, x:r.left, y:r.top, w:r.width, h:r.height});
        idx++;
      }
      items.sort((a,b)=>b.score-a.score);
      return items.slice(0,12);
    }
    """)
    print('CANDIDATES', itemid, json.dumps(result, ensure_ascii=False), flush=True)
    if not result:
        page.screenshot(path=str(OUT / f'{itemid}-debug.png'), full_page=False)
        return False, None

    best = result[0]
    loc = page.locator(f'[data-oai-candidate-id="{best["idx"]}"]').first
    try:
        loc.scroll_into_view_if_needed(timeout=3000)
        page.wait_for_timeout(400)
        loc.screenshot(path=str(OUT / f'{itemid}.png'), timeout=10000)
        print('SAVED', itemid, name, best, flush=True)
        return True, best
    except Exception as e:
        print('SCREENSHOT ERROR', itemid, repr(e), flush=True)
        page.screenshot(path=str(OUT / f'{itemid}-debug.png'), full_page=False)
        return False, best

status = {}
failed = []
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=['--disable-blink-features=AutomationControlled'])
    context = browser.new_context(
        viewport={'width': 1440, 'height': 1100},
        locale='zh-TW',
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
    )
    for itemid, name in ITEMS.items():
        page = context.new_page()
        try:
            ok, meta = capture_cover(page, itemid, name)
        except Exception as e:
            print('ERROR', itemid, repr(e), flush=True)
            ok, meta = False, None
        status[str(itemid)] = {'name': name, 'ok': ok, 'candidate': meta}
        if not ok:
            failed.append(itemid)
        page.close()
        time.sleep(.7)
    browser.close()

(OUT / 'status.json').write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(status, ensure_ascii=False, indent=2), flush=True)
if failed:
    print('FAILED:', failed, file=sys.stderr)
    sys.exit(2)
