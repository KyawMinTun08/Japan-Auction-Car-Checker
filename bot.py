import asyncio
import os
import re
import logging
import httpx
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

try:
    import pytesseract
    from PIL import Image
    from io import BytesIO
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

GEMINI_API_KEY        = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL          = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
TOKEN                 = os.environ.get('BOT_TOKEN', '')
SHEET_WEBHOOK         = os.environ.get('SHEET_WEBHOOK', '')
CHANNEL_ID            = os.environ.get('CHANNEL_ID', '-1003749046571')
ADMIN_IDS             = [int(x) for x in os.environ.get('ADMIN_IDS', '').split(',') if x.strip().isdigit()]
ADMIN_USERNAME        = os.environ.get('ADMIN_USERNAME', '')
CLOUDINARY_CLOUD_NAME = os.environ.get('CLOUDINARY_CLOUD_NAME', '')
CLOUDINARY_API_KEY    = os.environ.get('CLOUDINARY_API_KEY', '')
CLOUDINARY_API_SECRET = os.environ.get('CLOUDINARY_API_SECRET', '')

LOC_MAESOT = "MaeSot Freezone"
LOC_KLANG9 = "Klang9 Freezone"

CHASSIS_PREFIX_MAP = {
    "VZNY12":"ADVAN",
    "GRS200":"CROWN","GRS201":"CROWN","GRS202":"CROWN","GRS204":"CROWN","GRS210":"CROWN",
    "GWS204":"CROWN HYBRID",
    "ZGE20":"WISH","ZGE21":"WISH","ZGE22":"WISH","ZGE25":"WISH",
    "GRX133":"MARK X",
    "GGH25":"ALPHARD","GGH20":"ALPHARD","MNH15":"ALPHARD","MNH10":"ALPHARD",
    "ANH15":"ALPHARD","ANH20":"ALPHARD",
    "ZRR75":"VOXY","ZRR70":"VOXY","ZWR80":"VOXY",
    "KDH201":"HIACE VAN","KDH200":"HIACE VAN","KDH205":"HIACE VAN","TRH200":"HIACE VAN",
    "NCP165":"SUCCEED VAN","NCP160":"SUCCEED VAN",
    "NCP59":"SUCCEED WAGON","NCP58":"SUCCEED WAGON",
    "UZJ100":"LAND CRUISER","HDJ101":"LAND CRUISER","HZJ105":"LAND CRUISER",
    "KDN185":"HILUX SURF","KZN185":"HILUX SURF","VZN185":"HILUX SURF",
    "KDJ95":"LAND CRUISER PRADO","KZJ95":"LAND CRUISER PRADO","UZJ101":"LAND CRUISER",
    "USF40":"LEXUS LS","USF41":"LEXUS LS",
    "ACU25":"KLUGER","ACU20":"KLUGER","MCU25":"KLUGER",
    "AZE0":"LEAF",
    "XZC610":"DUTRO","XZU548":"DUTRO TRUCK","XZU300":"DUTRO TRUCK",
    "ACA33":"VANGUARD","ACA38":"VANGUARD","CW4YL":"QUON",
    "NT31":"X-TRAIL","NT32":"X-TRAIL","DNT31":"X-TRAIL","T31":"X-TRAIL",
    "YF15":"JUKE","F15":"JUKE","NF15":"JUKE",
    "SK82TN":"VANETTE TRUCK","SK82VN":"VANETTE TRUCK",
    "GP1":"FIT HYBRID","GP5":"FIT HYBRID","GP6":"FIT HYBRID",
    "GP7":"FIT SHUTTLE HYBRID","GP2":"FIT SHUTTLE HYBRID",
    "GK3":"FIT","GK5":"FIT","GE6":"FIT","GE8":"FIT",
    "GB3":"FREED","GB4":"FREED",
    "RE4":"CRV","RE3":"CRV","RD1":"CRV","RD5":"CRV",
    "ZE2":"INSIGHT","ZE3":"INSIGHT",
    "KE2AW":"CX5","KE2FW":"CX5","KE5FW":"CX5",
    "SKP2T":"BONGO TRUCK","SLP2L":"BONGO TRUCK",
    "S210P":"HIJET TRUCK","S211P":"HIJET TRUCK","S510P":"HIJET TRUCK",
    "S500P":"HIJET TRUCK","S501P":"HIJET TRUCK",
    "S321V":"HIJET VAN","S331V":"HIJET VAN",
    "S200P":"HIJET TRUCK","S201P":"HIJET TRUCK",
    "S211U":"PIXIS TRUCK","S500U":"PIXIS TRUCK",
    "S510J":"SAMBAR TRUCK","S201J":"SAMBAR TRUCK",
    "FE74BV":"CANTER","FE82BS":"CANTER","FBA30":"CANTER",
    "FE82D":"CANTER","FE82EE":"CANTER","FE72EE":"CANTER",
    "FE84DV":"CANTER","FE83D":"CANTER","FE70B":"CANTER",
    "FE73EB":"CANTER","FE70EB":"CANTER","FEA20":"CANTER",
    "FB70BB":"CANTER GUTS",
    "FK61FM":"FUSO FIGHTER","FQ62F":"FUSO FIGHTER","FK71F":"FUSO FIGHTER",
    "FEA50":"FUSO TRUCK","FBA20":"FUSO TRUCK",
    "FY54JTY":"SUPER GREAT","FS54JZ":"SUPER GREAT",
    "FV50JJX":"SUPER GREAT","FV50MJX":"SUPER GREAT",
    "FC6JLW":"RANGER","FC7JKY":"RANGER",
    "FW1EXW":"PROFIA","SH1EDX":"PROFIA",
    "CG5ZA":"UD","CG5ZE":"UD","CG4ZA":"UD","CG4YA":"UD",
    "CD5ZA":"UD","CD4ZA":"UD","CD48R":"BIG THUMB",
    "MK35A":"CONDOR","MK38L":"CONDOR","MK36A":"CONDOR",
    "MK36B":"UD","MK38C":"UD",
    "JNCMM60C6GU":"UD","JNCMM60G6GU":"UD","GK6XA":"QUON","JNCLSC":"CONDOR",
    "V98W":"PAJERO","V97W":"PAJERO","V93W":"PAJERO","V75W":"PAJERO","V78W":"PAJERO",
    "WVWZZZ":"NEW BEETLE",
}

CARS = [
    # ── MaeSot Freezone ──
    {"chassis":"MNH15-0039667","model":"ALPHARD","color":"WHITE","year":2005,"loc":"MaeSot"},
    {"chassis":"CD48R-30111","model":"BIG THUMB","color":"GREEN","year":2005,"loc":"MaeSot"},
    {"chassis":"FE82EEV500266","model":"CANTER","color":"WHITE","year":2002,"loc":"MaeSot"},
    {"chassis":"FE84DV-550674","model":"CANTER","color":"BLUE","year":2008,"loc":"MaeSot"},
    {"chassis":"FB70BB-512392","model":"CANTER GUTS","color":"WHITE","year":2005,"loc":"MaeSot"},
    {"chassis":"MK35A-10405","model":"CONDOR","color":"PEARL WHITE","year":2006,"loc":"MaeSot"},
    {"chassis":"JNCLSC0A1GU006386","model":"CONDOR","color":"WHITE","year":2016,"loc":"MaeSot"},
    {"chassis":"GRS210-6004548","model":"CROWN","color":"PEARL WHITE","year":2013,"loc":"MaeSot"},
    {"chassis":"GRS200-0001831","model":"CROWN","color":"WHITE","year":2008,"loc":"MaeSot"},
    {"chassis":"GRS200-0020080","model":"CROWN","color":"WHITE","year":2008,"loc":"MaeSot"},
    {"chassis":"GRS202-0002603","model":"CROWN","color":"WHITE","year":2008,"loc":"MaeSot"},
    {"chassis":"XZC610-0001005","model":"DUTRO","color":"WHITE","year":2011,"loc":"MaeSot"},
    {"chassis":"GE6-1539486","model":"FIT","color":"PEARL WHITE","year":2011,"loc":"MaeSot"},
    {"chassis":"GP5-3032237","model":"FIT HYBRID","color":"PEARL WHITE","year":2014,"loc":"MaeSot"},
    {"chassis":"GP1-1131390","model":"FIT HYBRID","color":"WHITE","year":2012,"loc":"MaeSot"},
    {"chassis":"GP1-1049821","model":"FIT HYBRID","color":"PEARL WHITE","year":2011,"loc":"MaeSot"},
    {"chassis":"GP7-1000970","model":"FIT SHUTTLE HYBRID","color":"PEARL WHITE","year":2015,"loc":"MaeSot"},
    {"chassis":"GP2-3106770","model":"FIT SHUTTLE HYBRID","color":"SILVER","year":2013,"loc":"MaeSot"},
    {"chassis":"FK61FM765129","model":"FUSO FIGHTER","color":"WHITE","year":2003,"loc":"MaeSot"},
    {"chassis":"KDH201-0140123","model":"HIACE VAN","color":"WHITE","year":2014,"loc":"MaeSot"},
    {"chassis":"S211P-0217418","model":"HIJET TRUCK","color":"WHITE","year":2013,"loc":"MaeSot"},
    {"chassis":"S210P-2037788","model":"HIJET TRUCK","color":"WHITE","year":2005,"loc":"MaeSot"},
    {"chassis":"S510P-0173458","model":"HIJET TRUCK","color":"WHITE","year":2017,"loc":"MaeSot"},
    {"chassis":"UZJ100-0151432","model":"LAND CRUISER","color":"SILVER","year":2004,"loc":"MaeSot"},
    {"chassis":"USF40-5006069","model":"LEXUS LS","color":"WHITE","year":2006,"loc":"MaeSot"},
    {"chassis":"WVWZZZ16ZDM638030","model":"NEW BEETLE","color":"BLACK","year":2013,"loc":"MaeSot"},
    {"chassis":"ZRR75-0068964","model":"VOXY","color":"PEARL WHITE","year":2010,"loc":"MaeSot"},
    {"chassis":"V98W-0300140","model":"PAJERO","color":"PEARL WHITE","year":2010,"loc":"MaeSot"},
    {"chassis":"S211U-0000227","model":"PIXIS TRUCK","color":"WHITE","year":2011,"loc":"MaeSot"},
    {"chassis":"FC7JKY-14910","model":"RANGER","color":"BLUE","year":2011,"loc":"MaeSot"},
    {"chassis":"NCP165-0001505","model":"SUCCEED VAN","color":"PEARL WHITE","year":2014,"loc":"MaeSot"},
    {"chassis":"NCP59-0012188","model":"SUCCEED WAGON","color":"SILVER","year":2005,"loc":"MaeSot"},
    {"chassis":"FV50JJX-530670","model":"SUPER GREAT","color":"BLACK","year":2004,"loc":"MaeSot"},
    {"chassis":"CG5ZA-30374","model":"UD","color":"PEARL WHITE","year":2014,"loc":"MaeSot"},
    {"chassis":"CD5ZA-30191","model":"UD","color":"SILVER","year":2014,"loc":"MaeSot"},
    {"chassis":"CG4ZA-01338","model":"UD","color":"LIGHT BLUE","year":2006,"loc":"MaeSot"},
    {"chassis":"ZGE22-0005423","model":"WISH","color":"BLACK","year":2011,"loc":"MaeSot"},
    {"chassis":"ZGE20-0010786","model":"WISH","color":"PEARL WHITE","year":2009,"loc":"MaeSot"},
    {"chassis":"ZGE25-0015283","model":"WISH","color":"WHITE","year":2011,"loc":"MaeSot"},
    {"chassis":"NT32-504837","model":"X-TRAIL","color":"BLACK","year":2014,"loc":"MaeSot"},
    {"chassis":"NT32-531693","model":"X-TRAIL","color":"BLACK","year":2015,"loc":"MaeSot"},
    {"chassis":"NT31-316873","model":"X-TRAIL","color":"PEARL WHITE","year":2013,"loc":"MaeSot"},
    {"chassis":"NT32-508661","model":"X-TRAIL","color":"PEARL WHITE","year":2015,"loc":"MaeSot"},
    {"chassis":"SKP2T-108324","model":"BONGO TRUCK","color":"WHITE","year":2013,"loc":"MaeSot"},
    {"chassis":"FE82D-570692","model":"CANTER","color":"WHITE","year":2010,"loc":"MaeSot"},
    {"chassis":"FE82D-530430","model":"CANTER","color":"PEARL WHITE","year":2007,"loc":"MaeSot"},
    {"chassis":"FE72EE-500637","model":"CANTER","color":"WHITE","year":2003,"loc":"MaeSot"},
    {"chassis":"GRS201-0006860","model":"CROWN","color":"SILVER","year":2011,"loc":"MaeSot"},
    {"chassis":"GRS200-0061216","model":"CROWN","color":"PEARL WHITE","year":2011,"loc":"MaeSot"},
    {"chassis":"GRS200-0063933","model":"CROWN","color":"BLACK","year":2011,"loc":"MaeSot"},
    {"chassis":"GWS204-0025870","model":"CROWN HYBRID","color":"SILVER","year":2012,"loc":"MaeSot"},
    {"chassis":"GK3-1029686","model":"FIT","color":"WHITE","year":2014,"loc":"MaeSot"},
    {"chassis":"GP1-1011906","model":"FIT HYBRID","color":"BLUE","year":2010,"loc":"MaeSot"},
    {"chassis":"GP5-3040254","model":"FIT HYBRID","color":"WHITE","year":2014,"loc":"MaeSot"},
    {"chassis":"GP1-1096649","model":"FIT HYBRID","color":"BLACK","year":2011,"loc":"MaeSot"},
    {"chassis":"GP1-1014176","model":"FIT HYBRID","color":"PEARL WHITE","year":2010,"loc":"MaeSot"},
    {"chassis":"GB3-1312198","model":"FREED","color":"PEARL WHITE","year":2010,"loc":"MaeSot"},
    {"chassis":"FQ62F-520185","model":"FUSO FIGHTER","color":"WHITE","year":2008,"loc":"MaeSot"},
    {"chassis":"FEA50-521744","model":"FUSO TRUCK","color":"PEARL WHITE","year":2013,"loc":"MaeSot"},
    {"chassis":"KDH201-0056284","model":"HIACE VAN","color":"WHITE","year":2010,"loc":"MaeSot"},
    {"chassis":"S211P-0276262","model":"HIJET TRUCK","color":"SILVER","year":2014,"loc":"MaeSot"},
    {"chassis":"S510P-0147424","model":"HIJET TRUCK","color":"WHITE","year":2017,"loc":"MaeSot"},
    {"chassis":"S210P-2060815","model":"HIJET TRUCK","color":"WHITE","year":2006,"loc":"MaeSot"},
    {"chassis":"S510P-0149349","model":"HIJET TRUCK","color":"SILVER","year":2017,"loc":"MaeSot"},
    {"chassis":"S210P-2006882","model":"HIJET TRUCK","color":"SILVER","year":2005,"loc":"MaeSot"},
    {"chassis":"ZE2-1130682","model":"INSIGHT","color":"WHITE","year":2009,"loc":"MaeSot"},
    {"chassis":"YF15-033275","model":"JUKE","color":"WHITE","year":2011,"loc":"MaeSot"},
    {"chassis":"HDJ101-0031030","model":"LAND CRUISER","color":"PEARL WHITE","year":2007,"loc":"MaeSot"},
    {"chassis":"AZE0-062459","model":"LEAF","color":"PEARL WHITE","year":2013,"loc":"MaeSot"},
    {"chassis":"GRX133-6003681","model":"MARK X","color":"SILVER","year":2013,"loc":"MaeSot"},
    {"chassis":"WVWZZZ16ZDM685003","model":"NEW BEETLE","color":"BLACK","year":2013,"loc":"MaeSot"},
    {"chassis":"NCP165-0001511","model":"SUCCEED VAN","color":"PEARL WHITE","year":2014,"loc":"MaeSot"},
    {"chassis":"GK6XA-10555","model":"QUON","color":"WHITE","year":2013,"loc":"MaeSot"},
    {"chassis":"FC6JLW-10241","model":"RANGER","color":"PEARL WHITE","year":2006,"loc":"MaeSot"},
    {"chassis":"FY54JTY530030","model":"SUPER GREAT","color":"PEARL WHITE","year":2003,"loc":"MaeSot"},
    {"chassis":"FS54JZ-570431","model":"SUPER GREAT","color":"BLACK","year":2010,"loc":"MaeSot"},
    {"chassis":"FV50MJX520729","model":"SUPER GREAT","color":"BLACK","year":2001,"loc":"MaeSot"},
    {"chassis":"CG5ZA-01150","model":"UD","color":"GREEN","year":2011,"loc":"MaeSot"},
    {"chassis":"CG5ZE-30138","model":"UD","color":"WHITE","year":2015,"loc":"MaeSot"},
    {"chassis":"MK38L-30952","model":"UD","color":"YELLOW","year":2014,"loc":"MaeSot"},
    {"chassis":"MK36A-12656","model":"UD","color":"WHITE","year":2006,"loc":"MaeSot"},
    {"chassis":"ZGE20-0041580","model":"WISH","color":"PEARL WHITE","year":2009,"loc":"MaeSot"},
    {"chassis":"ZGE20-0004342","model":"WISH","color":"WHITE","year":2009,"loc":"MaeSot"},
    {"chassis":"NT32-024640","model":"X-TRAIL","color":"BLACK","year":2014,"loc":"MaeSot"},
    {"chassis":"NT32-037944","model":"X-TRAIL","color":"BLACK","year":2015,"loc":"MaeSot"},
    {"chassis":"NT31-244285","model":"X-TRAIL","color":"PEARL WHITE","year":2012,"loc":"MaeSot"},
    {"chassis":"DNT31-209100","model":"X-TRAIL","color":"WHITE","year":2011,"loc":"MaeSot"},
    # ── Klang9 Freezone ──
    {"chassis":"VZNY12-070391","model":"ADVAN","color":"WHITE","year":2017,"loc":"Klang9"},
    {"chassis":"GGH20-8002412","model":"ALPHARD","color":"PEARL WHITE","year":2008,"loc":"Klang9"},
    {"chassis":"MNH10-0099576","model":"ALPHARD","color":"PEARL WHITE","year":2007,"loc":"Klang9"},
    {"chassis":"SLP2L-102206","model":"BONGO TRUCK","color":"WHITE","year":2017,"loc":"Klang9"},
    {"chassis":"FEA20-520134","model":"CANTER","color":"SILVER","year":2013,"loc":"Klang9"},
    {"chassis":"FE73EB-501814","model":"CANTER","color":"LIGHT GREEN","year":2003,"loc":"Klang9"},
    {"chassis":"FE70EB-506566","model":"CANTER","color":"WHITE","year":2004,"loc":"Klang9"},
    {"chassis":"GRS204-0014299","model":"CROWN","color":"WHITE","year":2010,"loc":"Klang9"},
    {"chassis":"RE4-1006211","model":"CRV","color":"WHITE","year":2006,"loc":"Klang9"},
    {"chassis":"KE2AW-115142","model":"CX5","color":"WHITE","year":2013,"loc":"Klang9"},
    {"chassis":"GP5-3037138","model":"FIT HYBRID","color":"PEARL WHITE","year":2014,"loc":"Klang9"},
    {"chassis":"GP5-3216073","model":"FIT HYBRID","color":"PEARL WHITE","year":2015,"loc":"Klang9"},
    {"chassis":"GB3-1112824","model":"FREED","color":"PEARL WHITE","year":2009,"loc":"Klang9"},
    {"chassis":"FK71F-701985","model":"FUSO FIGHTER","color":"GREEN","year":2007,"loc":"Klang9"},
    {"chassis":"S211P-0042777","model":"HIJET TRUCK","color":"SILVER","year":2009,"loc":"Klang9"},
    {"chassis":"S211P-0138980","model":"HIJET TRUCK","color":"WHITE","year":2011,"loc":"Klang9"},
    {"chassis":"KDN185-0001271","model":"HILUX SURF","color":"SILVER","year":2000,"loc":"Klang9"},
    {"chassis":"ZE2-1128237","model":"INSIGHT","color":"SILVER","year":2009,"loc":"Klang9"},
    {"chassis":"NF15-060818","model":"JUKE","color":"WHITE","year":2012,"loc":"Klang9"},
    {"chassis":"ACU25-0032701","model":"KLUGER","color":"WHITE","year":2004,"loc":"Klang9"},
    {"chassis":"USF40-5079528","model":"LEXUS LS","color":"PEARL WHITE","year":2008,"loc":"Klang9"},
    {"chassis":"WVWZZZ16ZDM635922","model":"NEW BEETLE","color":"RED","year":2013,"loc":"Klang9"},
    {"chassis":"GK6XA-10291","model":"QUON","color":"GREEN","year":2012,"loc":"Klang9"},
    {"chassis":"CW4YL-30468","model":"QUON","color":"SILVER","year":2009,"loc":"Klang9"},
    {"chassis":"NCP165-0056792","model":"SUCCEED VAN","color":"WHITE","year":2018,"loc":"Klang9"},
    {"chassis":"NCP59-0024963","model":"SUCCEED WAGON","color":"DARK BLUE","year":2012,"loc":"Klang9"},
    {"chassis":"CG5ZA-12819","model":"UD","color":"PEARL WHITE","year":2014,"loc":"Klang9"},
    {"chassis":"CG5ZA-11731","model":"UD","color":"WHITE","year":2013,"loc":"Klang9"},
    {"chassis":"CG4YA-00054","model":"UD","color":"WHITE","year":2006,"loc":"Klang9"},
    {"chassis":"CD4ZA-31233","model":"UD","color":"GREEN","year":2009,"loc":"Klang9"},
    {"chassis":"SK82TN-319474","model":"VANETTE TRUCK","color":"WHITE","year":2005,"loc":"Klang9"},
    {"chassis":"ZRR75-0083512","model":"VOXY","color":"PEARL WHITE","year":2011,"loc":"Klang9"},
    {"chassis":"ZGE25-0020690","model":"WISH","color":"PEARL WHITE","year":2012,"loc":"Klang9"},
    {"chassis":"ZGE20-0154748","model":"WISH","color":"PEARL WHITE","year":2013,"loc":"Klang9"},
    {"chassis":"ZGE20-0152288","model":"WISH","color":"BLACK","year":2012,"loc":"Klang9"},
    {"chassis":"NT32-036496","model":"X-TRAIL","color":"BLACK","year":2014,"loc":"Klang9"},
    {"chassis":"NT31-212796","model":"X-TRAIL","color":"PEARL WHITE","year":2011,"loc":"Klang9"},
    {"chassis":"NT31-049247","model":"X-TRAIL","color":"BLACK","year":2009,"loc":"Klang9"},
    {"chassis":"DNT31-205472","model":"X-TRAIL","color":"PEARL WHITE","year":2011,"loc":"Klang9"},
    {"chassis":"NT32-038921","model":"X-TRAIL","color":"PEARL WHITE","year":2015,"loc":"Klang9"},
]

PRICE_HISTORY = []
pending_photo = {}
warned_3days  = set()

# ── Helpers ───────────────────────────────────────────
def loc_display(loc_key: str) -> str:
    return LOC_KLANG9 if loc_key == "Klang9" else LOC_MAESOT

def guess_model_from_chassis(chassis_input: str) -> str:
    cu = chassis_input.upper().strip()
    for prefix in sorted(CHASSIS_PREFIX_MAP.keys(), key=len, reverse=True):
        if cu.startswith(prefix):
            return CHASSIS_PREFIX_MAP[prefix]
    return "UNKNOWN"

async def guess_model_gemini(chassis_input: str) -> str:
    if not GEMINI_API_KEY:
        return "UNKNOWN"
    try:
        prefix  = chassis_input.split("-")[0] if "-" in chassis_input else chassis_input[:6]
        url     = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
        payload = {"contents":[{"parts":[{"text":f"What Japanese car model has chassis prefix '{prefix}'? Reply ONLY the model name UPPERCASE. If unknown reply UNKNOWN."}]}]}
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=payload, timeout=15)
        data = resp.json()
        if "candidates" in data:
            m = data["candidates"][0]["content"]["parts"][0]["text"].strip().upper().split("\n")[0].strip()
            return m if m and m != "UNKNOWN" else "UNKNOWN"
    except Exception as e:
        logger.error(f"Gemini model: {e}")
    return "UNKNOWN"

def find_by_chassis(chassis_input: str):
    c = chassis_input.upper().strip()
    for car in CARS:
        if car["chassis"].upper() == c:
            return car
    return None

def find_by_model(model_input: str):
    m = model_input.upper().strip()
    return [c for c in CARS if m in c["model"].upper()]

def extract_chassis_from_text(text: str):
    text = text.upper().strip()
    for pattern in [
        r'[A-Z]{1,5}\d{1,4}[A-Z]{0,2}\d{0,2}-\d{4,7}',
        r'[A-Z]{2,6}\d{2,4}-\d{4,7}',
        r'[A-Z0-9]{4,20}-\d{4,7}',
    ]:
        matches = re.findall(pattern, text)
        if matches:
            return max(matches, key=len)
    return None

def get_price_history(chassis: str):
    return [p for p in PRICE_HISTORY if p["chassis"] == chassis]

def ys(year) -> str:
    return str(year) if year and year != 0 else "—"

def format_car_info(car, price=None, history=None) -> str:
    txt = (
        f"🚗 *{car['model']}* ({ys(car.get('year',0))})\n"
        f"🔑 `{car['chassis']}`\n"
        f"🎨 {car['color']}\n"
        f"📍 {loc_display(car.get('loc','MaeSot'))}\n"
    )
    if price:
        txt += f"💰 ฿{price:,}\n"
    if history:
        txt += f"\n📈 *မှတ်တမ်း ({len(history)} ကြိမ်):*\n"
        for h in history[-5:]:
            txt += f"  • {h['date']} → ฿{h['price']:,}\n"
    txt += f"\n🌐 [Web မှာကြည့်](https://kyawmintun08.github.io/Japan-Auction-Car-Checker/)"
    return txt

async def upload_to_cloudinary(file_bytes: bytes, chassis: str) -> str:
    if not all([CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET]):
        return ""
    try:
        import base64, hashlib, time
        ts        = str(int(time.time()))
        public_id = f"auction/{chassis.replace('-','_')}_{ts}"
        sig_str   = f"public_id={public_id}&timestamp={ts}{CLOUDINARY_API_SECRET}"
        signature = hashlib.sha1(sig_str.encode()).hexdigest()
        img_b64   = base64.b64encode(file_bytes).decode()
        url       = f"https://api.cloudinary.com/v1_1/{CLOUDINARY_CLOUD_NAME}/image/upload"
        payload   = {"file":f"data:image/jpeg;base64,{img_b64}","public_id":public_id,
                     "timestamp":ts,"api_key":CLOUDINARY_API_KEY,"signature":signature}
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, data=payload, timeout=30)
        return resp.json().get("secure_url","")
    except Exception as e:
        logger.error(f"Cloudinary: {e}")
        return ""

async def save_price(chassis, model, color, year, price, user_name, image_url="", location=LOC_MAESOT):
    now   = datetime.now().strftime("%d/%m/%Y")
    entry = {"chassis":chassis,"model":model,"color":color,"year":year,
             "price":price,"date":now,"location":location,
             "added_by":user_name,"image_url":image_url}
    PRICE_HISTORY.append(entry)
    if SHEET_WEBHOOK:
        try:
            async with httpx.AsyncClient() as client:
                await client.post(SHEET_WEBHOOK, json=entry, timeout=10, follow_redirects=True)
        except Exception as e:
            logger.error(f"save_price: {e}")
    return entry

async def post_to_channel(context, chassis, model, color, year, price, image_url="", location=LOC_MAESOT):
    if not CHANNEL_ID:
        return
    text = (
        f"🚗 *ကားသစ်ဝင်ပြီ!*\n"
        f"━━━━━━━━━━━━━━\n"
        f"🔑 Chassis : `{chassis}`\n"
        f"🚘 Model   : *{model}*\n"
        f"🎨 Color   : {color or '—'}\n"
        f"📅 Year    : {ys(year)}\n"
        f"💰 Price   : *฿{int(price):,}*\n"
        f"📍 {location}\n"
        f"━━━━━━━━━━━━━━\n"
        f"🌐 [Japan Auction Car Checker](https://kyawmintun08.github.io/Japan-Auction-Car-Checker/)"
    )
    try:
        if image_url:
            await context.bot.send_photo(chat_id=CHANNEL_ID, photo=image_url, caption=text, parse_mode='Markdown')
        else:
            await context.bot.send_message(chat_id=CHANNEL_ID, text=text, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Channel post: {e}")

async def notify_admins(context, text: str, reply_markup=None):
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(
                chat_id=admin_id, text=text,
                parse_mode='Markdown', reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Admin notify {admin_id}: {e}")

# ── Confirm helper ────────────────────────────────────
async def send_confirm(update_or_query, data: dict, is_callback=False):
    """
    Save မလုပ်သေး — Confirm / Cancel မေးတဲ့ message ပေးပို့
    """
    txt = (
        f"⚠️ *စစ်ဆေးပါ — မှန်ကန်ပါသလား?*\n\n"
        f"🚗 *{data['model']}* ({ys(data.get('year',0))})\n"
        f"🔑 `{data['chassis']}`\n"
        f"🎨 {data['color']}\n"
        f"📍 {data['loc']}\n"
        f"💰 ฿{data['price']:,}\n\n"
        f"✅ မှန်ရင် *Save* နှိပ်ပါ\n"
        f"❌ မှားရင် *Cancel* နှိပ်ပါ\n"
        f"✏️ Chassis မှားရင် `/price [chassis] [ဈေး]`"
    )
    uid = data['user_id']
    kb  = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ မှန်တယ် Save",    callback_data=f"cs_{uid}"),
        InlineKeyboardButton("❌ မှားတယ် Cancel", callback_data=f"cc_{uid}"),
    ]])
    if is_callback:
        await update_or_query.message.reply_text(txt, parse_mode='Markdown', reply_markup=kb)
    else:
        await update_or_query.message.reply_text(txt, parse_mode='Markdown', reply_markup=kb)

# ── Commands ──────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = []
    if ADMIN_USERNAME:
        kb.append([InlineKeyboardButton("💬 Admin ကို ဆက်သွယ်", url=f"https://t.me/{ADMIN_USERNAME}")])
    kb.append([InlineKeyboardButton("🌐 Web App ကြည့်", url="https://kyawmintun08.github.io/Japan-Auction-Car-Checker/")])
    await update.message.reply_text(
        f"🚗 *JAN JAPAN Auction Bot*\n"
        f"📍 {LOC_MAESOT} & {LOC_KLANG9}\n\n"
        "*Commands:*\n"
        "📸 ကားပုံ တင် → Chassis auto ဖတ်\n"
        "📋 ပုံ + caption `list` → MaeSot List\n"
        "📋 ပုံ + caption `list klang9` → Klang9 List\n"
        "🔍 `/find NT32-504837` → Chassis ရှာ\n"
        "🔎 `/model xtrail` → Model ရှာ\n"
        "💰 `/price NT32-504837 150000` → ဈေးထည့်\n"
        "📋 `/history NT32-504837` → ဈေးမှတ်တမ်း\n"
        "📊 `/list` → ကားအားလုံး\n"
        "🌐 `/web` → Web Link\n"
        "🔄 `/renew` → Membership သက်တမ်းတိုးတောင်းဆို\n",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(kb))

async def find_car(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Chassis ထည့်ပါ\nဥပမာ: `/find NT32-504837`", parse_mode='Markdown')
        return
    chassis = ' '.join(context.args)
    car     = find_by_chassis(chassis)
    if car:
        history = get_price_history(car['chassis'])
        txt     = format_car_info(car, history[-1]['price'] if history else None, history or None)
        kb      = [[InlineKeyboardButton("💰 ဈေးထည့်", callback_data=f"addprice_{car['chassis']}")]]
        await update.message.reply_text(txt, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(kb))
    else:
        guessed = guess_model_from_chassis(chassis)
        if guessed == "UNKNOWN":
            guessed = await guess_model_gemini(chassis)
        msg = (f"⚠️ `{chassis}` Checklist မှာ မပါဘူး\n🚗 ခန့်မှန်း: *{guessed}*\n\n`/price {chassis} [ဈေး]`"
               if guessed != "UNKNOWN"
               else f"❌ `{chassis}` မတွေ့ပါ\n\n`/price {chassis} [ဈေး]`")
        await update.message.reply_text(msg, parse_mode='Markdown')

async def find_model(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Model ထည့်ပါ\nဥပမာ: `/model xtrail`", parse_mode='Markdown')
        return
    query   = ' '.join(context.args)
    results = find_by_model(query)
    if not results:
        await update.message.reply_text(f"❌ *{query}* မတွေ့ပါ", parse_mode='Markdown')
        return
    txt = f"🔎 *{query.upper()}* ({len(results)} စီး):\n\n"
    for car in results:
        history   = get_price_history(car['chassis'])
        price_str = f"฿{history[-1]['price']:,}" if history else "ဈေးမရသေး"
        txt += f"• `{car['chassis']}` — {car['color']} {ys(car.get('year',0))} [{loc_display(car.get('loc','MaeSot'))}] — *{price_str}*\n"
    txt += f"\n🌐 [Web မှာကြည့်](https://kyawmintun08.github.io/Japan-Auction-Car-Checker/)"
    await update.message.reply_text(txt, parse_mode='Markdown')

async def add_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("❌ Format: `/price NT32-504837 150000`", parse_mode='Markdown')
        return
    chassis = context.args[0].upper()
    try:
        price = int(context.args[1].replace(',',''))
    except:
        await update.message.reply_text("❌ ဈေး ဂဏန်းသာ ထည့်ပါ", parse_mode='Markdown')
        return
    car       = find_by_chassis(chassis) or {"chassis":chassis,"model":guess_model_from_chassis(chassis),"color":"-","year":0,"loc":"MaeSot"}
    user_name = update.effective_user.first_name or "Unknown"
    loc       = loc_display(car.get('loc','MaeSot'))
    entry     = await save_price(car['chassis'], car['model'], car['color'], car['year'], price, user_name, location=loc)
    await update.message.reply_text(
        f"✅ *ဈေးထည့်ပြီး!*\n\n🚗 {car['model']} ({ys(car.get('year',0))}) — `{chassis}`\n"
        f"💰 ฿{price:,}\n📍 {loc}\n📅 {entry['date']}\n👤 {user_name}\n\n"
        f"🌐 [Web မှာကြည့်](https://kyawmintun08.github.io/Japan-Auction-Car-Checker/)",
        parse_mode='Markdown')

async def price_history_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Chassis ထည့်ပါ\nဥပမာ: `/history NT32-504837`", parse_mode='Markdown')
        return
    chassis = ' '.join(context.args).upper()
    history = get_price_history(chassis)
    if not history:
        await update.message.reply_text(f"❌ `{chassis}` ဈေးမှတ်တမ်း မရှိသေးပါ", parse_mode='Markdown')
        return
    car  = find_by_chassis(chassis)
    txt  = f"📈 *{car['model'] if car else chassis}*\n`{chassis}`\n\n"
    prev = None
    for h in history:
        if prev:
            diff  = h['price'] - prev
            arrow = "📈" if diff > 0 else "📉" if diff < 0 else "➡"
            txt += f"• {h['date']} → *฿{h['price']:,}* ({arrow} {diff:+,})\n"
        else:
            txt += f"• {h['date']} → *฿{h['price']:,}*\n"
        prev = h['price']
    if len(history) >= 2:
        change = history[-1]['price'] - history[0]['price']
        pct    = (change / history[0]['price']) * 100
        txt += f"\n📊 ပြောင်းလဲမှု: *{change:+,}* ({pct:+.1f}%)"
    await update.message.reply_text(txt, parse_mode='Markdown')

async def list_cars(update: Update, context: ContextTypes.DEFAULT_TYPE):
    priced = {p['chassis'] for p in PRICE_HISTORY}
    txt    = f"🚗 *ကားစာရင်း ({len(CARS)} စီး)*\n\n"
    for car in CARS[:20]:
        status = "💰" if car['chassis'] in priced else "⏳"
        txt += f"{status} `{car['chassis']}` — {car['model']} {ys(car.get('year',0))} [{loc_display(car.get('loc','MaeSot'))}]\n"
    if len(CARS) > 20:
        txt += f"\n... နှင့် {len(CARS)-20} စီး ထပ်ရှိ"
    txt += f"\n\n🌐 [Web မှာကြည့်](https://kyawmintun08.github.io/Japan-Auction-Car-Checker/)"
    await update.message.reply_text(txt, parse_mode='Markdown')

async def web_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"🌐 *JAN JAPAN Auction Web App*\n\nhttps://kyawmintun08.github.io/Japan-Auction-Car-Checker/\n\n"
        f"• {LOC_MAESOT} + {LOC_KLANG9} 🚗\n• ဈေးကြည့်နိုင် 📈\n• Chart ကြည့်နိုင် 📊",
        parse_mode='Markdown')

async def renew_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user     = update.effective_user
    user_id  = user.id
    name     = user.first_name or "Unknown"
    username = f"@{user.username}" if user.username else str(user_id)

    customer_kb = []
    if ADMIN_USERNAME:
        customer_kb.append([InlineKeyboardButton(
            "💬 Admin ကို တိုက်ရိုက် Message ပို့", url=f"https://t.me/{ADMIN_USERNAME}")])
    await update.message.reply_text(
        "✅ *Membership သက်တမ်းတိုး တောင်းဆိုပြီးပါပြီ!*\n\n"
        "Admin မှ ဆက်သွယ်ပေးမှာပါ — ခဏစောင့်ပါ 🙏\n\n"
        "⚡ အမြန်ဆုံး ဆက်သွယ်ချင်ရင် အောက်က ခလုတ် နှိပ်ပါ 👇",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(customer_kb) if customer_kb else None)

    admin_text = (
        f"🔔 *Membership Renewal Request!*\n\n"
        f"👤 {name} ({username})\n"
        f"🆔 ID: `{user_id}`\n\n"
        f"ထပ်တိုးဖို့ ခလုတ် နှိပ်ပါ 👇"
    )
    admin_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"💬 {name} ကို Message ပို့", url=f"tg://user?id={user_id}")],
        [
            InlineKeyboardButton("✅ 1 လ Approve", callback_data=f"qa_{user_id}_1"),
            InlineKeyboardButton("✅ 3 လ Approve", callback_data=f"qa_{user_id}_3"),
        ],
    ])
    await notify_admins(context, admin_text, reply_markup=admin_kb)

# ── OCR ───────────────────────────────────────────────
def tesseract_ocr_chassis(file_bytes: bytes) -> str:
    if not TESSERACT_AVAILABLE:
        return ""
    try:
        img     = Image.open(BytesIO(file_bytes))
        text    = pytesseract.image_to_string(img)
        chassis = extract_chassis_from_text(text)
        return chassis or ""
    except Exception as e:
        logger.error(f"Tesseract: {e}")
        return ""

async def gemini_ocr_auction_list(file_bytes: bytes) -> list:
    if not GEMINI_API_KEY:
        return []
    try:
        import base64, json
        img_b64 = base64.b64encode(file_bytes).decode()
        url     = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
        payload = {"contents":[{"parts":[
            {"text":"Japan auction car list. Extract ALL cars. Return ONLY JSON array:\n[{\"chassis\":\"NT32-024640\",\"model\":\"X-TRAIL\",\"color\":\"BLACK\",\"year\":2014},...]\nEvery row. No markdown."},
            {"inline_data":{"mime_type":"image/jpeg","data":img_b64}}
        ]}]}
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=payload, timeout=60)
        data = resp.json()
        if "candidates" not in data:
            return []
        text  = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        start = text.find('['); end = text.rfind(']') + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])
    except Exception as e:
        logger.error(f"Gemini list: {e}")
    return []

async def gemini_ocr_chassis(file_bytes: bytes) -> dict:
    if GEMINI_API_KEY:
        try:
            import base64
            img_b64 = base64.b64encode(file_bytes).decode()
            url     = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
            payload = {"contents":[{"parts":[
                {"text":"Japan auction car photo. Find chassis number written on windshield with marker.\nReturn EXACTLY:\nCHASSIS: NT32-024640\nMODEL: X-TRAIL\nCOLOR: BLACK\nYEAR: 2014"},
                {"inline_data":{"mime_type":"image/jpeg","data":img_b64}}
            ]}]}
            async with httpx.AsyncClient() as client:
                resp = await client.post(url, json=payload, timeout=60)
            data = resp.json()
            if "candidates" in data:
                text    = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                chassis = ""; model = ""; color = ""; year = 0
                for line in text.upper().split("\n"):
                    line = line.strip()
                    if line.startswith("CHASSIS:"):
                        raw = line.replace("CHASSIS:","").strip()
                        for pat in [r'[A-Z]{1,5}\d{1,4}[A-Z]{0,2}\d{0,2}-\d{4,7}',
                                    r'[A-Z]{2,6}\d{2,4}-\d{4,7}',
                                    r'[A-Z0-9]{4,20}-\d{4,7}']:
                            m = re.search(pat, raw)
                            if m: chassis = m.group().replace(' ','-'); break
                    elif line.startswith("MODEL:"): model = line.replace("MODEL:","").strip()
                    elif line.startswith("COLOR:"): color = line.replace("COLOR:","").strip()
                    elif line.startswith("YEAR:"):
                        try: year = int(re.search(r'\d{4}', line).group())
                        except: year = 0
                if chassis:
                    return {"chassis":chassis,"model":model,"color":color,"year":year}
        except Exception as e:
            logger.error(f"Gemini OCR: {e}")
    chassis = tesseract_ocr_chassis(file_bytes)
    return {"chassis":chassis,"model":"","color":"","year":0}

# ── Photo Handler ─────────────────────────────────────
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global CARS
    user_id = update.effective_user.id
    photo   = update.message.photo[-1]
    caption = (update.message.caption or "").strip().lower()

    # ── Auction List Mode ──
    if "list" in caption:
        is_klang9  = "klang9" in caption or "klang" in caption
        import_loc = "Klang9" if is_klang9 else "MaeSot"
        loc_name   = LOC_KLANG9 if is_klang9 else LOC_MAESOT
        await update.message.reply_text(f"📋 {loc_name} Auction List ဖတ်နေတယ်... ⏳")
        try:
            file       = await photo.get_file()
            file_bytes = bytes(await file.download_as_bytearray())
            new_cars   = await gemini_ocr_auction_list(file_bytes)
        except Exception as e:
            logger.error(f"Auction list: {e}"); new_cars = []

        if not new_cars:
            await update.message.reply_text("⚠️ List ဖတ်မရပါ\n💡 Gemini API limit ကုန်နိုင်တယ်")
            return

        existing = {c["chassis"].upper() for c in CARS}
        added    = []
        for car in new_cars:
            ch = str(car.get("chassis","")).upper().strip()
            if ch and ch not in existing:
                CARS.append({"chassis":ch,
                             "model":car.get("model","") or guess_model_from_chassis(ch),
                             "color":car.get("color","-"),
                             "year":int(car.get("year",0)),
                             "loc":import_loc})
                existing.add(ch); added.append(ch)

        txt = f"✅ *{loc_name} List Update ပြီး!*\n\n📊 ဖတ်ရ: {len(new_cars)} စီး\n✨ အသစ်: {len(added)} စီး\n"
        if added:
            txt += "\n🆕 " + "".join(f"`{ch}`\n" for ch in added[:10])
            if len(added) > 10: txt += f"... {len(added)-10} စီး ထပ်ရှိ\n"
        txt += f"\n📋 Database: {len(CARS)} စီး"
        await update.message.reply_text(txt, parse_mode='Markdown')
        return

    # ── Car Photo Mode ──
    await update.message.reply_text("🔍 Chassis ရှာနေတယ်... ⏳")

    chassis      = extract_chassis_from_text(caption) if caption else None
    price_match  = re.search(r'(?<![A-Z0-9])(\d{4,6})(?![A-Z0-9])', caption.upper()) if caption else None
    price        = int(price_match.group(1)) if price_match else None
    gemini_model = ""; gemini_color = ""; gemini_year = 0; file_bytes = None

    if not chassis:
        try:
            file       = await photo.get_file()
            file_bytes = bytes(await file.download_as_bytearray())
            result     = await gemini_ocr_chassis(file_bytes)
            chassis      = result.get("chassis","")
            gemini_model = result.get("model","")
            gemini_color = result.get("color","")
            gemini_year  = result.get("year",0)
        except Exception as e:
            logger.error(f"Photo: {e}")

    car       = find_by_chassis(chassis) if chassis else None
    image_url = ""
    if chassis and file_bytes:
        image_url = await upload_to_cloudinary(file_bytes, chassis)

    car_loc = loc_display(car.get('loc','MaeSot')) if car else LOC_MAESOT

    # ── ✅ Chassis + Price တွေ့ → Confirm မေး (Auto Save မလုပ်) ──
    if car and price:
        pending_photo[user_id] = {
            "user_id":   user_id,
            "chassis":   car['chassis'],
            "model":     car['model'],
            "color":     car['color'],
            "year":      car['year'],
            "price":     price,
            "loc":       car_loc,
            "image_url": image_url,
        }
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ မှန်တယ် Save",    callback_data=f"cs_{user_id}"),
            InlineKeyboardButton("❌ မှားတယ် Cancel", callback_data=f"cc_{user_id}"),
        ]])
        await update.message.reply_text(
            f"⚠️ *စစ်ဆေးပါ — မှန်ကန်ပါသလား?*\n\n"
            f"🚗 *{car['model']}* ({ys(car.get('year',0))})\n"
            f"🔑 `{car['chassis']}`\n"
            f"🎨 {car['color']}\n"
            f"📍 {car_loc}\n"
            f"💰 ฿{price:,}\n\n"
            f"✅ မှန်ရင် *Save* နှိပ်ပါ\n"
            f"❌ မှားရင် *Cancel* နှိပ်ပြီး `/price [chassis] [ဈေး]` သုံးပါ",
            parse_mode='Markdown', reply_markup=kb)

    elif car:
        # Price မပါ → price ရိုက်ထည့်ဖို့ မေး
        pending_photo[user_id] = {
            "user_id":   user_id,
            "chassis":   car['chassis'],
            "model":     car['model'],
            "color":     car['color'],
            "year":      car['year'],
            "price":     None,
            "loc":       car_loc,
            "image_url": image_url,
        }
        await update.message.reply_text(
            f"🚗 ကားတွေ့ပြီ!\n\n*{car['model']}* ({ys(car.get('year',0))})\n"
            f"`{car['chassis']}`\n🎨 {car['color']}\n📍 {car_loc}\n\n"
            f"💰 ဈေး ရိုက်ထည့်ပါ:\nဥပမာ: `150000`",
            parse_mode='Markdown')

    elif chassis:
        guessed = gemini_model or guess_model_from_chassis(chassis)
        if not guessed or guessed == "UNKNOWN":
            guessed = guess_model_from_chassis(chassis)
        display_color = gemini_color or "-"
        display_year  = gemini_year or 0

        if price:
            # Checklist မှာ မပါ + price ပါ → Confirm မေး
            pending_photo[user_id] = {
                "user_id":   user_id,
                "chassis":   chassis,
                "model":     guessed,
                "color":     display_color,
                "year":      display_year,
                "price":     price,
                "loc":       LOC_MAESOT,
                "image_url": image_url,
            }
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ မှန်တယ် Save",    callback_data=f"cs_{user_id}"),
                InlineKeyboardButton("❌ မှားတယ် Cancel", callback_data=f"cc_{user_id}"),
            ]])
            await update.message.reply_text(
                f"⚠️ *စစ်ဆေးပါ — Checklist မှာ မပါဘူး*\n\n"
                f"🚗 ခန့်မှန်း: *{guessed}* ({ys(display_year)})\n"
                f"🔑 `{chassis}`\n🎨 {display_color}\n"
                f"💰 ฿{price:,}\n\n"
                f"✅ မှန်ရင် *Save* နှိပ်ပါ\n"
                f"❌ မှားရင် *Cancel* နှိပ်ပြီး `/price [chassis] [ဈေး]` သုံးပါ",
                parse_mode='Markdown', reply_markup=kb)
        else:
            pending_photo[user_id] = {
                "user_id":   user_id,
                "chassis":   chassis,
                "model":     guessed,
                "color":     display_color,
                "year":      display_year,
                "price":     None,
                "loc":       LOC_MAESOT,
                "image_url": image_url,
            }
            msg = (f"⚠️ Checklist မှာ မပါဘူး\n\n🚗 ခန့်မှန်း: *{guessed}* ({ys(display_year)})\n"
                   f"🔑 `{chassis}`\n🎨 {display_color}\n\n💰 ဈေး ရိုက်ထည့်ပါ:\nဥပမာ: `150000`"
                   if guessed and guessed != "UNKNOWN"
                   else f"⚠️ Chassis: `{chassis}`\nChecklist မှာ မပါဘူး — ဈေး ထည့်ပါ:\nဥပမာ: `150000`")
            await update.message.reply_text(msg, parse_mode='Markdown')
    else:
        await update.message.reply_text(
            "⚠️ Chassis ဖတ်မရပါ\nကိုယ်တိုင် ထည့်ပါ:\n`/price [chassis] [ဈေး]`", parse_mode='Markdown')

# ── Text Handler ──────────────────────────────────────
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text    = update.message.text.strip()

    if user_id in pending_photo:
        data = pending_photo[user_id]
        # Price မရှိသေးရင် price ထည့်ဖို့ စောင့်နေ
        if data.get('price') is None and re.match(r'^[\d,]+$', text.replace(' ','')):
            try:
                price            = int(text.replace(',','').replace(' ',''))
                data['price']    = price
                pending_photo[user_id] = data

                # Confirm မေး
                kb = InlineKeyboardMarkup([[
                    InlineKeyboardButton("✅ မှန်တယ် Save",    callback_data=f"cs_{user_id}"),
                    InlineKeyboardButton("❌ မှားတယ် Cancel", callback_data=f"cc_{user_id}"),
                ]])
                await update.message.reply_text(
                    f"⚠️ *စစ်ဆေးပါ — မှန်ကန်ပါသလား?*\n\n"
                    f"🚗 *{data['model']}* ({ys(data.get('year',0))})\n"
                    f"🔑 `{data['chassis']}`\n"
                    f"🎨 {data['color']}\n"
                    f"📍 {data['loc']}\n"
                    f"💰 ฿{price:,}\n\n"
                    f"✅ မှန်ရင် *Save* နှိပ်ပါ\n"
                    f"❌ မှားရင် *Cancel* နှိပ်ပါ",
                    parse_mode='Markdown', reply_markup=kb)
                return
            except: pass

    chassis = extract_chassis_from_text(text)
    if chassis:
        car = find_by_chassis(chassis)
        if car:
            history = get_price_history(car['chassis'])
            txt     = format_car_info(car, history[-1]['price'] if history else None, history or None)
            kb      = [[InlineKeyboardButton("💰 ဈေးထည့်", callback_data=f"addprice_{car['chassis']}")]]
            await update.message.reply_text(txt, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(kb))
        else:
            guessed = guess_model_from_chassis(chassis)
            if guessed == "UNKNOWN": guessed = await guess_model_gemini(chassis)
            msg = (f"⚠️ `{chassis}` Checklist မှာ မပါဘူး\n🚗 ခန့်မှန်း: *{guessed}*\n\n`/price {chassis} [ဈေး]`"
                   if guessed != "UNKNOWN"
                   else f"⚠️ `{chassis}` Checklist မှာ မပါဘူး\n\n`/price {chassis} [ဈေး]`")
            await update.message.reply_text(msg, parse_mode='Markdown')

# ── Callback Handler ──────────────────────────────────
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    # ── ✅ Confirm Save ──
    if query.data.startswith("cs_"):
        uid  = int(query.data.replace("cs_",""))
        data = pending_photo.pop(uid, None)
        if not data or data.get('price') is None:
            await query.message.reply_text("❌ Data မရှိတော့ပါ — ပုံ ပြန်တင်ပါ")
            return
        user_name = query.from_user.first_name or "Unknown"
        await save_price(data['chassis'], data['model'], data['color'], data['year'],
                        data['price'], user_name, data.get('image_url',''), data.get('loc', LOC_MAESOT))
        await query.message.reply_text(
            f"✅ *Save ပြီး!*\n\n"
            f"🚗 {data['model']} ({ys(data.get('year',0))})\n"
            f"🔑 `{data['chassis']}`\n"
            f"📍 {data.get('loc', LOC_MAESOT)}\n"
            f"💰 ฿{data['price']:,}\n\n"
            f"🌐 [Web မှာကြည့်](https://kyawmintun08.github.io/Japan-Auction-Car-Checker/)",
            parse_mode='Markdown')
        await post_to_channel(context, data['chassis'], data['model'], data['color'],
                             data['year'], data['price'], data.get('image_url',''), data.get('loc', LOC_MAESOT))

    # ── ❌ Cancel ──
    elif query.data.startswith("cc_"):
        uid = int(query.data.replace("cc_",""))
        pending_photo.pop(uid, None)
        await query.message.reply_text(
            "❌ *Cancel လုပ်ပြီး*\n\n"
            "Chassis ကိုယ်တိုင် ထည့်ပါ:\n"
            "`/price [chassis] [ဈေး]`\n"
            "ဥပမာ: `/price GP1-1049821 58000`",
            parse_mode='Markdown')

    # ── Add Price button ──
    elif query.data.startswith("addprice_"):
        chassis = query.data.replace("addprice_","")
        car     = find_by_chassis(chassis)
        if car:
            pending_photo[query.from_user.id] = {
                "user_id": query.from_user.id,
                "chassis": car['chassis'], "model": car['model'],
                "color":   car['color'],   "year":  car['year'],
                "price":   None, "loc": loc_display(car.get('loc','MaeSot')), "image_url": ""}
        await query.message.reply_text(
            f"💰 `{chassis}` ဈေး ရိုက်ထည့်ပါ:\nဥပမာ: `150000`", parse_mode='Markdown')

    # ── Quick Approve ──
    elif query.data.startswith("qa_"):
        parts     = query.data.split("_")
        target_id = int(parts[1])
        months    = int(parts[2])
        days      = months * 30
        try:
            chat            = await context.bot.get_chat(target_id)
            member_username = chat.username or chat.first_name or str(target_id)
        except:
            member_username = str(target_id)
        try:
            async with httpx.AsyncClient() as client:
                await client.post(SHEET_WEBHOOK, json={
                    "action":"saveMember","userId":str(target_id),
                    "username":member_username,"days":days
                }, timeout=10, follow_redirects=True)
        except Exception as e:
            logger.error(f"Quick approve: {e}")
        try:
            invite     = await context.bot.create_chat_invite_link(
                chat_id=CHANNEL_ID, member_limit=1,
                expire_date=int((__import__('time').time()) + days * 86400))
            invite_url = invite.invite_link
        except:
            invite_url = None
        expire_date = (datetime.now() + timedelta(days=days)).strftime("%d/%m/%Y")
        try:
            cust_kb = []
            if invite_url:
                cust_kb.append([InlineKeyboardButton("📢 Channel ဝင်ရန်", url=invite_url)])
            await context.bot.send_message(
                chat_id=target_id,
                text=(f"🎉 *Membership ထပ်တိုးပြီးပါပြီ!*\n\n"
                      f"📅 သက်တမ်း: *{months} လ*\n"
                      f"⏰ ကုန်ဆုံးရက်: `{expire_date}`\n\n"
                      f"သက်တမ်းတိုးဖို့: /renew\nကျေးဇူးတင်ပါတယ် 🙏"),
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(cust_kb) if cust_kb else None)
        except Exception as e:
            logger.error(f"Customer notify: {e}")
        await query.message.reply_text(
            f"✅ *Quick Approve ပြီး!*\n\n👤 @{member_username}\n📅 {months} လ\n⏰ ကုန်ဆုံး: `{expire_date}`",
            parse_mode='Markdown')

# ── Membership Commands ────────────────────────────────
async def approve_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if ADMIN_IDS and user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Admin သာ သုံးနိုင်တယ်"); return
    if len(context.args) < 2:
        await update.message.reply_text("❌ Format: `/approve @username 1` သို့မဟုတ် `/approve 123456789 3`", parse_mode='Markdown'); return
    username_or_id = context.args[0].replace('@','')
    try:
        months = int(context.args[1])
    except:
        await update.message.reply_text("❌ လ ဂဏန်းထည့်ပါ", parse_mode='Markdown'); return
    days = months * 30
    try:
        member_id       = int(username_or_id)
        member_username = username_or_id
    except ValueError:
        member_id       = None
        member_username = username_or_id
    if member_id:
        try:
            chat = await context.bot.get_chat(member_id)
            member_username = chat.username or chat.first_name or str(member_id)
        except Exception as e:
            logger.error(f"get_chat: {e}")
    try:
        async with httpx.AsyncClient() as client:
            await client.post(SHEET_WEBHOOK, json={
                "action":"saveMember",
                "userId":str(member_id) if member_id is not None else username_or_id,
                "username":member_username,"days":days
            }, timeout=10, follow_redirects=True)
    except Exception as e:
        logger.error(f"saveMember: {e}")
    try:
        invite     = await context.bot.create_chat_invite_link(
            chat_id=CHANNEL_ID, member_limit=1,
            expire_date=int((__import__('time').time()) + days * 86400))
        invite_url = invite.invite_link
    except Exception as e:
        invite_url = None; logger.error(f"Invite: {e}")
    expire_date = (datetime.now() + timedelta(days=days)).strftime("%d/%m/%Y")
    if member_id:
        try:
            cust_kb = []
            if invite_url:
                cust_kb.append([InlineKeyboardButton("📢 Channel ဝင်ရန်", url=invite_url)])
            await context.bot.send_message(
                chat_id=member_id,
                text=(f"🎉 *Membership Approved!*\n\n📅 သက်တမ်း: *{months} လ*\n"
                      f"⏰ ကုန်ဆုံးရက်: `{expire_date}`\n\nသက်တမ်းတိုးဖို့: /renew\nကျေးဇူးတင်ပါတယ် 🙏"),
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(cust_kb) if cust_kb else None)
        except Exception as e:
            logger.error(f"Customer notify: {e}")
    txt = (f"✅ <b>Membership Approved!</b>\n\n👤 @{member_username}\n"
           f"🆔 <code>{member_id or 'N/A'}</code>\n📅 <b>{months} လ</b>\n"
           f"⏰ ကုန်ဆုံး: <code>{expire_date}</code>\n")
    if invite_url: txt += f"\n🔗 {invite_url}"
    await update.message.reply_text(txt, parse_mode='HTML')

async def members_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if ADMIN_IDS and user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Admin သာ သုံးနိုင်တယ်"); return
    try:
        async with httpx.AsyncClient() as client:
            resp    = await client.post(SHEET_WEBHOOK, json={"action":"getMembers"}, timeout=10, follow_redirects=True)
            members = resp.json().get("members",[])
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}"); return
    if not members:
        await update.message.reply_text("👥 Member မရှိသေးဘူး"); return
    active  = [m for m in members if m.get('status') == 'ACTIVE']
    expired = [m for m in members if m.get('status') == 'EXPIRED']
    txt = f"👥 *Members*\n✅ Active: {len(active)} | ❌ Expired: {len(expired)}\n\n*✅ Active:*\n"
    for m in active:
        txt += f"• @{m['username']} — ကုန်: `{m.get('expireDate','?')}`\n"
    if expired:
        txt += "\n*❌ Expired:*\n"
        for m in expired[:5]:
            txt += f"• @{m['username']} — `{m.get('expireDate','?')}`\n"
    await update.message.reply_text(txt, parse_mode='Markdown')

async def kick_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if ADMIN_IDS and user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Admin သာ သုံးနိုင်တယ်"); return
    if not context.args:
        await update.message.reply_text("❌ Format: `/kick 123456789`", parse_mode='Markdown'); return
    try:
        target_id = int(context.args[0])
        await context.bot.ban_chat_member(chat_id=CHANNEL_ID, user_id=target_id)
        await context.bot.unban_chat_member(chat_id=CHANNEL_ID, user_id=target_id)
        await update.message.reply_text(f"✅ `{target_id}` channel ကထုတ်ပြီ", parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

# ── Auto Expire Check (every 12h) ─────────────────────
async def check_expired_members(context):
    global warned_3days
    try:
        async with httpx.AsyncClient() as client:
            resp    = await client.post(SHEET_WEBHOOK, json={"action":"getMembers"}, timeout=10, follow_redirects=True)
            members = resp.json().get("members",[])
        now = datetime.now(); kicked = []; expiring = []
        for m in members:
            uid = str(m.get('userId',''))
            if not uid: continue
            try:
                expire_date = datetime.strptime(m.get('expireDate','01/01/2000'), "%d/%m/%Y")
            except: continue
            days_left = (expire_date - now).days
            if 0 <= days_left <= 3 and uid not in warned_3days:
                expiring.append(m); warned_3days.add(uid)
                if uid.isdigit():
                    try:
                        kb = []
                        if ADMIN_USERNAME:
                            kb = [[InlineKeyboardButton("💬 Admin ကို ဆက်သွယ်", url=f"https://t.me/{ADMIN_USERNAME}")]]
                        await context.bot.send_message(
                            chat_id=int(uid),
                            text=(f"⚠️ *Membership သတိပေးချက်!*\n\n"
                                  f"သင့် Membership *{days_left} ရက်* အတွင်း ကုန်ဆုံးမည်!\n"
                                  f"⏰ ကုန်ဆုံးရက်: `{m.get('expireDate','?')}`\n\n"
                                  f"သက်တမ်းတိုးဖို့ /renew နှိပ်ပါ 🙏"),
                            parse_mode='Markdown',
                            reply_markup=InlineKeyboardMarkup(kb) if kb else None)
                    except Exception as e:
                        logger.error(f"3day warn: {e}")
            if m.get('status') == 'EXPIRED' and uid.isdigit():
                try:
                    await context.bot.ban_chat_member(chat_id=CHANNEL_ID, user_id=int(uid))
                    await context.bot.unban_chat_member(chat_id=CHANNEL_ID, user_id=int(uid))
                    kicked.append(m)
                except Exception as e:
                    logger.error(f"Auto kick {uid}: {e}")
        if kicked:
            txt = "🚫 *Auto Kick (Membership ကုန်ဆုံး):*\n\n"
            for m in kicked: txt += f"• @{m['username']} — `{m.get('expireDate','?')}`\n"
            await notify_admins(context, txt)
        if expiring:
            txt = "⚠️ *Membership ၃ ရက်အတွင်း ကုန်ဆုံးမည်:*\n\n"
            for m in expiring: txt += f"• @{m['username']} — `{m.get('expireDate','?')}`\n"
            txt += "\nသက်တမ်းတိုး: `/approve [userId] [လ]`"
            await notify_admins(context, txt)
    except Exception as e:
        logger.error(f"check_expired: {e}")

# ── Main ──────────────────────────────────────────────
async def main():
    logger.info("Bot starting...")
    async with httpx.AsyncClient() as client:
        await client.post(f"https://api.telegram.org/bot{TOKEN}/deleteWebhook",
                          params={"drop_pending_updates":True})
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start",   start))
    app.add_handler(CommandHandler("find",    find_car))
    app.add_handler(CommandHandler("model",   find_model))
    app.add_handler(CommandHandler("price",   add_price))
    app.add_handler(CommandHandler("history", price_history_cmd))
    app.add_handler(CommandHandler("list",    list_cars))
    app.add_handler(CommandHandler("web",     web_link))
    app.add_handler(CommandHandler("approve", approve_member))
    app.add_handler(CommandHandler("members", members_list))
    app.add_handler(CommandHandler("kick",    kick_member))
    app.add_handler(CommandHandler("renew",   renew_cmd))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.job_queue.run_repeating(check_expired_members, interval=43200, first=60)
    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)
    logger.info("Bot polling!")
    await asyncio.Event().wait()

if __name__ == '__main__':
    asyncio.run(main())
