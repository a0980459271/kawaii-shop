from pathlib import Path
import io, json, re, sys, time
import requests
from PIL import Image

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

S = requests.Session()
S.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
    'Accept-Language': 'zh-TW,zh;q=0.9,en;q=0.8',
    'Referer': 'https://shopee.tw/',
    'x-api-source': 'pc',
    'x-requested-with': 'XMLHttpRequest',
})

def walk_images(obj):
    found=[]
    if isinstance(obj, dict):
        for k,v in obj.items():
            lk=str(k).lower()
            if lk in ('image','images','image_id','imageid'):
                if isinstance(v,str) and v: found.append(v)
                elif isinstance(v,list): found.extend([x for x in v if isinstance(x,str) and x])
            found.extend(walk_images(v))
    elif isinstance(obj,list):
        for v in obj: found.extend(walk_images(v))
    return found

def get_cover_id(itemid):
    apis=[
        f'https://shopee.tw/api/v4/item/get?itemid={itemid}&shopid={SHOP_ID}',
        f'https://shopee.tw/api/v4/pdp/get_pc?item_id={itemid}&shop_id={SHOP_ID}',
    ]
    for api in apis:
        try:
            r=S.get(api,timeout=30)
            print('API', itemid, r.status_code, api)
            if r.ok:
                data=r.json()
                root=data.get('data') or data
                if isinstance(root,dict):
                    image=root.get('image')
                    images=root.get('images')
                    if isinstance(image,str) and image:
                        return image
                    if isinstance(images,list) and images and isinstance(images[0],str):
                        return images[0]
                for x in walk_images(data):
                    if x and ('http' in x or len(x)>16): return x
        except Exception as e:
            print('api error', itemid, repr(e))
    return None

def get_cover_from_html(itemid):
    urls=[
        f'https://shopee.tw/product/{SHOP_ID}/{itemid}',
        f'https://shopee.tw/-i.{SHOP_ID}.{itemid}',
    ]
    pats=[
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
        r'"image"\s*:\s*"([^"\\]+)"',
    ]
    for url in urls:
        try:
            r=S.get(url,timeout=30,allow_redirects=True)
            print('HTML', itemid, r.status_code, r.url)
            if r.ok:
                for pat in pats:
                    m=re.search(pat,r.text,re.I)
                    if m:
                        return m.group(1).replace('\\u002F','/').replace('\\/','/')
        except Exception as e:
            print('html error', itemid, repr(e))
    return None

def image_candidates(ref):
    if not ref: return []
    ref=ref.replace('\\/','/')
    if ref.startswith('http://') or ref.startswith('https://'):
        return [ref]
    return [
        f'https://down-tw.img.susercontent.com/file/{ref}',
        f'https://cf.shopee.tw/file/{ref}',
        f'https://mms.img.susercontent.com/{ref}',
    ]

def save_image(itemid, ref):
    for url in image_candidates(ref):
        try:
            r=S.get(url,timeout=40)
            ctype=r.headers.get('content-type','')
            print('IMG', itemid, r.status_code, ctype, url)
            if r.ok and len(r.content)>3000:
                im=Image.open(io.BytesIO(r.content)).convert('RGB')
                # Preserve the whole first product image; normalize for fast site loading.
                im.thumbnail((1200,1200), Image.Resampling.LANCZOS)
                im.save(OUT/f'{itemid}.jpg','JPEG',quality=88,optimize=True)
                return url, im.size
        except Exception as e:
            print('image error', itemid, repr(e), url)
    return None, None

status={}
failed=[]
for itemid,name in ITEMS.items():
    ref=get_cover_id(itemid) or get_cover_from_html(itemid)
    url,size=save_image(itemid,ref)
    ok=bool(url)
    status[str(itemid)]={'name':name,'ok':ok,'source':url,'size':size}
    if not ok: failed.append(itemid)
    time.sleep(1)

(OUT/'status.json').write_text(json.dumps(status,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(status,ensure_ascii=False,indent=2))
if failed:
    print('FAILED:', failed, file=sys.stderr)
    sys.exit(2)
