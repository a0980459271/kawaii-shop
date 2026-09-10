from pathlib import Path
import json, re, sys, time
import requests
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
UA='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36'

# Shopee's individual -i product URL returns HTML even when its JSON APIs reject
# datacenter requests. First inspect that HTML for embedded image data.
def raw_product_html(itemid):
    u=f'https://shopee.tw/-i.{SHOP_ID}.{itemid}'
    r=requests.get(u,headers={'User-Agent':UA,'Accept-Language':'zh-TW,zh;q=0.9','Referer':'https://shopee.tw/'},timeout=30)
    print('RAW',itemid,r.status_code,len(r.text),r.url,flush=True)
    return r.text if r.ok else ''

def extract_from_raw(html):
    if not html: return []
    h=html.replace('\\u002F','/').replace('\\/','/')
    candidates=[]
    pats=[
      r'https://[^"\'<> ]*(?:img\.susercontent\.com|shopee\.tw/file)[^"\'<> ]*',
      r'(?:(?:tw|sg)-\d{6,}-[A-Za-z0-9_-]{8,})',
      r'"(?:image|image_id|imageId)"\s*:\s*"([^"\\]{12,})"',
      r'"images"\s*:\s*\[\s*"([^"\\]{12,})"',
    ]
    for pat in pats:
        for m in re.finditer(pat,h,re.I):
            v=m.group(1) if m.groups() else m.group(0)
            if v not in candidates: candidates.append(v)
    return candidates

def capture_rendered(page,itemid):
    url=f'https://shopee.tw/-i.{SHOP_ID}.{itemid}'
    page.goto(url,wait_until='domcontentloaded',timeout=60000)
    page.wait_for_timeout(5000)
    vals=page.evaluate("""() => Array.from(document.images).map(i=>({src:i.currentSrc||i.src,w:i.getBoundingClientRect().width,h:i.getBoundingClientRect().height,x:i.getBoundingClientRect().x,y:i.getBoundingClientRect().y})).filter(x=>x.src).slice(0,200)""")
    return vals

status={}
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,args=['--disable-blink-features=AutomationControlled'])
    context=browser.new_context(viewport={'width':1440,'height':1100},locale='zh-TW',user_agent=UA)
    for n,(itemid,name) in enumerate(ITEMS.items()):
        html=raw_product_html(itemid)
        raw=extract_from_raw(html)
        print('RAW_CANDIDATES',itemid,json.dumps(raw[:60],ensure_ascii=False),flush=True)
        if n==0:
            (OUT/f'{itemid}-raw.html').write_text(html,encoding='utf-8')
        page=context.new_page()
        try:
            rendered=capture_rendered(page,itemid)
        except Exception as e:
            rendered=[]
            print('BROWSER_ERR',itemid,repr(e),flush=True)
        finally:
            page.close()
        print('RENDERED',itemid,json.dumps(rendered[:40],ensure_ascii=False),flush=True)
        status[str(itemid)]={'name':name,'raw_candidates':raw[:60],'rendered':rendered[:40]}
        time.sleep(.4)
    browser.close()
(OUT/'status.json').write_text(json.dumps(status,ensure_ascii=False,indent=2),encoding='utf-8')
# Diagnostic pass intentionally exits non-zero until exact first-image extraction is verified.
sys.exit(2)
