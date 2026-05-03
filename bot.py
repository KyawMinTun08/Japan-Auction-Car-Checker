import asyncio
import os
import re
import random
import string
import logging
import httpx
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram import BotCommandScopeAllPrivateChats, BotCommandScopeChat
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

# ── Environment Variables ──────────────────────────────
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

# ── Membership Status ──────────────────────────────────
MEMBERSHIP_ENABLED = False  # ⬅️ Coming Soon — True လုပ်ရင် Membership ဖွင့်ပြီ

# ── Membership Plan Pricing (ks) ──────────────────────
PLAN_CH_1M  = int(os.environ.get('PLAN_CH_1M',  '15000'))
PLAN_CH_2M  = int(os.environ.get('PLAN_CH_2M',  '30000'))
PLAN_CH_3M  = int(os.environ.get('PLAN_CH_3M',  '40000'))
PLAN_CH_5M  = int(os.environ.get('PLAN_CH_5M',  '70000'))
PLAN_WEB_1M = int(os.environ.get('PLAN_WEB_1M', '30000'))
PLAN_WEB_2M = int(os.environ.get('PLAN_WEB_2M', '55000'))
PLAN_WEB_3M = int(os.environ.get('PLAN_WEB_3M', '80000'))
PAYMENT_INFO = os.environ.get('PAYMENT_INFO', 'KPay / Wave: ဆက်သွယ်ရန် @' + ADMIN_USERNAME)

# ── Promo Codes: "CODE:days:maxuses,CODE2:days:maxuses" ──
PROMO_CODES_RAW = os.environ.get('PROMO_CODES', '')

LOC_MAESOT   = "MaeSot Freezone"
LOC_KLANG9   = "Klang9 Freezone"
LOC_BORDER44 = "Best Border-44 Gate"

PLAN_PRICES = {
    "CH":  {1: PLAN_CH_1M,  2: PLAN_CH_2M,  3: PLAN_CH_3M,  5: PLAN_CH_5M},
    "WEB": {1: PLAN_WEB_1M, 2: PLAN_WEB_2M, 3: PLAN_WEB_3M},
}
PLAN_NAMES = {
    "CH":  "📱 Standard",
    "WEB": "💎 Web Premium",
}

CHASSIS_PREFIX_MAP = {
    "VZNY12":"ADVAN",
    "GRS200":"CROWN","GRS201":"CROWN","GRS202":"CROWN","GRS204":"CROWN","GRS210":"CROWN",
    "GWS204":"CROWN HYBRID",
    "ZGE20":"WISH","ZGE21":"WISH","ZGE22":"WISH","ZGE25":"WISH",
    "GRX133":"MARK X",
    "GGH25":"ALPHARD","GGH20":"ALPHARD","MNH15":"ALPHARD","MNH10":"ALPHARD",
    "ANH15":"ALPHARD","ANH20":"ALPHARD",
    "ZRR75G":"NOAH","ZRR75W":"VOXY",
    "ZRR70G":"NOAH","ZRR70W":"VOXY",
    "ZWR80G":"NOAH HYBRID","ZWR80W":"VOXY HYBRID","ZWR80S":"ESQUIRE",
    "ZRR75":"NOAH","ZRR70":"NOAH","ZWR80":"NOAH HYBRID",
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
    "WWWZZZ":"NEW BEETLE",
    "WVW":"VW",
    "WAU":"AUDI",
    "WBA":"BMW",
    "WBS":"BMW M",
    "WDB":"MERCEDES-BENZ",
    "WDC":"MERCEDES-BENZ",
    "WDD":"MERCEDES-BENZ",
    "SAJ":"JAGUAR",
    "SAL":"LAND ROVER",
    "SAR":"RANGE ROVER",
    "VF1":"RENAULT",
    "ZFA":"FIAT",
    "ZFF":"FERRARI",
    "ZAR":"ALFA ROMEO",
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

PRICE_HISTORY  = []
pending_photo  = {}
pending_payment = {}
pending_updateid = {}
pending_edit     = {}
pending_broadcast= {}
pending_request  = {}
proxy_sessions   = {}
pending_rating   = {}
pending_deposit  = {}
active_timers    = {}
auction_dep_timers = {}
fasttrack_paid    = set()
fasttrack_pending = {}
warned_3days   = set()
promo_used     = {}
rate_limit     = {}
pending_setqr    = {}
payment_qr_cache = {}

# ── Rate Limiting ──────────────────────────────────────
def check_rate_limit(user_id: int, max_req: int = 10, window: int = 60) -> bool:
    now = datetime.now()
    if user_id not in rate_limit:
        rate_limit[user_id] = []
    rate_limit[user_id] = [t for t in rate_limit[user_id]
                           if (now - t).total_seconds() < window]
    if len(rate_limit[user_id]) >= max_req:
        return False
    rate_limit[user_id].append(now)
    return True

# ── Password Generator ─────────────────────────────────
async def is_active_member(user_id: int) -> bool:
    if user_id in ADMIN_IDS:
        return True
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.post(SHEET_WEBHOOK, json={"action":"getMembers"}, timeout=10)
        members = resp.json().get("members", [])
        for m in members:
            if str(m.get("userId","")) == str(user_id):
                return m.get("status","") == "ACTIVE"
    except:
        pass
    return False

def generate_password() -> str:
    letters = random.choices(string.ascii_uppercase, k=5)
    digits  = random.choices(string.digits, k=5)
    mixed   = [letters[0], digits[0], letters[1], digits[1], letters[2],
               digits[2], letters[3], digits[3], letters[4], digits[4]]
    return "KMT-" + "".join(mixed[:6]) + "-" + "".join(mixed[6:])

# ── Helpers ───────────────────────────────────────────
def loc_display(loc_key: str) -> str:
    if loc_key == "Klang9": return LOC_KLANG9
    if loc_key in ("Border44","Best Border","44Gate","44gate"): return LOC_BORDER44
    return LOC_MAESOT

def ys(year) -> str:
    return str(year) if year and year != 0 else "—"

def find_by_chassis(chassis_input: str):
    c = chassis_input.upper().strip()
    for car in CARS:
        if car["chassis"].upper() == c:
            return car
    return None

def find_by_model(model_input: str):
    m = model_input.upper().strip()
    return [c for c in CARS if m in c["model"].upper()]

def get_price_history(chassis: str):
    return [p for p in PRICE_HISTORY if p["chassis"] == chassis]

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

def guess_model_from_chassis(chassis_input: str) -> str:
    cu = chassis_input.upper().strip()
    for prefix in sorted(CHASSIS_PREFIX_MAP.keys(), key=len, reverse=True):
        if cu.startswith(prefix):
            return CHASSIS_PREFIX_MAP[prefix]
    return "UNKNOWN"

def extract_chassis_from_text(text: str):
    text = text.upper().strip()
    vin_matches = re.findall(r'[A-HJ-NPR-Z0-9]{17}', text)
    for v in vin_matches:
        if v[0] in ("W","S","V","Z","X","T"):
            return v
    for pattern in [
        r'[A-Z]{1,5}\d{1,4}[A-Z]{0,2}\d{0,2}-\d{4,7}',
        r'[A-Z]{2,6}\d{2,4}-\d{4,7}',
        r'[A-Z0-9]{4,20}-\d{4,7}',
    ]:
        matches = re.findall(pattern, text)
        if matches:
            return max(matches, key=len)
    return None

# ── Commands ──────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id  = update.effective_user.id
    is_admin = user_id in ADMIN_IDS

    kb = []
    
    # ⬇️ Membership Button — Coming Soon ပိတ်ထားခြင်း
    if MEMBERSHIP_ENABLED:
        kb.append([InlineKeyboardButton("🆕 Membership ဝယ်ရန်", callback_data="join_start")])
    else:
        kb.append([InlineKeyboardButton("🆕 Membership (Coming Soon ⏳)", callback_data="membership_comingsoon")])
    
    if ADMIN_USERNAME:
        kb.append([InlineKeyboardButton("💬 Admin ကို ဆက်သွယ်", url=f"https://t.me/{ADMIN_USERNAME}")])
    kb.append([InlineKeyboardButton("🌐 Web App ကြည့်",
               url="https://kyawmintun08.github.io/Japan-Auction-Car-Checker/")])

    if is_admin:
        cmd_text = (
            "*Member Commands:*\n"
            "🔍 `/find NT32-504837` → Chassis ရှာ\n"
            "🔎 `/model xtrail` → Model ရှာ\n"
            "📋 `/history NT32-504837` → ဈေးမှတ်တမ်း\n"
            "📊 `/list` → ကားအားလုံး\n"
            "🌐 `/web` → Web Link\n\n"
            "*Admin Commands:*\n"
            "📸 ကားပုံ တင် → Chassis auto ဖတ်\n"
            "💰 `/price NT32-504837 150000` → ဈေးထည့်\n"
            "✅ `/approve @user 30` → Member approve\n"
            "👥 `/members` → Member list\n"
            "🚫 `/kick @user` → Member kick\n"
        )
    else:
        cmd_text = (
            "*Commands:*\n"
            "🔍 `/find NT32-504837` → Chassis ရှာ\n"
            "🔎 `/model xtrail` → Model ရှာ\n"
            "📋 `/history NT32-504837` → ဈေးမှတ်တမ်း\n"
            "📊 `/list` → ကားအားလုံး\n"
            "🌐 `/web` → Web Link\n"
        )

    await update.message.reply_text(
        f"🚗 *Japan Auction Car Checker*\n"
        f"📍 {LOC_MAESOT} & {LOC_KLANG9} & {LOC_BORDER44}\n\n"
        + cmd_text,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(kb))

async def find_car(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_rate_limit(update.effective_user.id):
        await update.message.reply_text("⚠️ တစ်မိနစ်အတွင်း Request များသွားတယ် — ခဏစောင့်ပါ")
        return
    user_id  = update.effective_user.id
    if not await is_active_member(user_id):
        await update.message.reply_text(
            "🔒 *Member များသာ သုံးနိုင်ပါသည်*\n\nMembership ရယူရန် /start နှိပ်ပါ",
            parse_mode='Markdown')
        return
    if not context.args:
        await update.message.reply_text("❌ Chassis ထည့်ပါ\nဥပမာ: `/find NT32-504837`", parse_mode='Markdown')
        return
    is_admin = user_id in ADMIN_IDS
    chassis  = ' '.join(context.args)
    car      = find_by_chassis(chassis)
    if car:
        history = get_price_history(car['chassis'])
        txt     = format_car_info(car, history[-1]['price'] if history else None, history or None)
        kb = [[
            InlineKeyboardButton("💰 ဈေးထည့်",  callback_data=f"addprice_{car['chassis']}"),
            InlineKeyboardButton("✏️ ပြင်ရန်",   callback_data=f"editcar_{car['chassis']}"),
        ]] if is_admin else []
        await update.message.reply_text(txt, parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(kb) if kb else None)
    else:
        guessed = guess_model_from_chassis(chassis)
        if is_admin:
            msg = (f"⚠️ `{chassis}` Checklist မှာ မပါဘူး\n🚗 ခန့်မှန်း: *{guessed}*\n\n`/price {chassis} [ဈေး]`"
                   if guessed != "UNKNOWN"
                   else f"❌ `{chassis}` မတွေ့ပါ\n\n`/price {chassis} [ဈေး]`")
        else:
            msg = (f"⚠️ `{chassis}` Checklist မှာ မပါဘူး\n🚗 ခန့်မှန်း: *{guessed}*"
                   if guessed != "UNKNOWN"
                   else f"❌ `{chassis}` မတွေ့ပါ")
        await update.message.reply_text(msg, parse_mode='Markdown')

async def find_model(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_rate_limit(update.effective_user.id):
        await update.message.reply_text("⚠️ တစ်မိနစ်အတွင်း Request များသွားတယ် — ခဏစောင့်ပါ")
        return
    user_id  = update.effective_user.id
    if not await is_active_member(user_id):
        await update.message.reply_text(
            "🔒 *Member များသာ သုံးနိုင်ပါသည်*\n\nMembership ရယူရန် /start နှိပ်ပါ",
            parse_mode='Markdown')
        return
    if not context.args:
        await update.message.reply_text("❌ Model ထည့်ပါ\nဥပမာ: `/model xtrail`", parse_mode='Markdown')
        return
    is_admin = user_id in ADMIN_IDS
    query    = ' '.join(context.args)
    results  = find_by_model(query)
    if not results:
        if is_admin:
            await update.message.reply_text(
                f"❌ *{query}* မတွေ့ပါ\n\n💡 Admin: ပုံ + caption `list` တင်ပြီး checklist ထည့်နိုင်",
                parse_mode='Markdown')
        else:
            await update.message.reply_text(f"❌ *{query}* Checklist မှာ မရှိသေးပါ", parse_mode='Markdown')
        return
    txt = f"🔎 *{query.upper()}* ({len(results)} စီး):\n\n"
    for car in results:
        history   = get_price_history(car['chassis'])
        price_str = f"฿{history[-1]['price']:,}" if history else "ဈေးမရသေး"
        txt += f"• `{car['chassis']}` — {car['color']} {ys(car.get('year',0))} [{loc_display(car.get('loc','MaeSot'))}] — *{price_str}*\n"
    txt += f"\n🌐 [Web မှာကြည့်](https://kyawmintun08.github.io/Japan-Auction-Car-Checker/)"
    await update.message.reply_text(txt, parse_mode='Markdown')

async def add_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("🚫 Admin သာ ဈေးထည့်ခွင့်ရှိတယ်")
        return
    if not check_rate_limit(user_id):
        await update.message.reply_text("⚠️ Request များသွားတယ် — ခဏစောင့်ပါ")
        return
    if len(context.args) < 2:
        await update.message.reply_text(
            "❌ Format:\n"
            "`/price CHASSIS PRICE`\n\n"
            "ဥပမာ: `/price VZN11-042846 74000`",
            parse_mode='Markdown')
        return
    chassis = context.args[0].upper()
    try:
        price = int(context.args[1].replace(',',''))
    except:
        await update.message.reply_text("❌ ဈေး ဂဏန်းသာ ထည့်ပါ", parse_mode='Markdown')
        return

    car = find_by_chassis(chassis)
    if not car:
        car = {"chassis": chassis, "model": guess_model_from_chassis(chassis),
               "color": "-", "year": 0, "loc": "MaeSot"}

    user_name = update.effective_user.first_name or "Unknown"
    loc       = loc_display(car.get('loc','MaeSot'))
    
    now   = datetime.now().strftime("%d/%m/%Y")
    entry = {"chassis":chassis,"model":car['model'],"color":car['color'],"year":car['year'],
             "price":price,"date":now,"location":loc,"added_by":user_name,"image_url":""}
    PRICE_HISTORY.append(entry)
    
    await update.message.reply_text(
        f"✅ *ဈေးထည့်ပြီး!*\n\n🚗 {car['model']} ({ys(car.get('year',0))}) — `{chassis}`\n"
        f"🎨 {car['color']}\n💰 ฿{price:,}\n📍 {loc}\n📅 {entry['date']}\n\n"
        f"🌐 [Web မှာကြည့်](https://kyawmintun08.github.io/Japan-Auction-Car-Checker/)",
        parse_mode='Markdown')

async def price_history_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id  = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("🔒 *Admin သာ သုံးနိုင်ပါသည်*", parse_mode='Markdown')
        return
    if not context.args:
        await update.message.reply_text("❌ Chassis ထည့်ပါ\nဥပမာ: `/history NT32-504837`", parse_mode='Markdown')
        return
    chassis  = ' '.join(context.args).upper()
    history  = get_price_history(chassis)
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
    kb = [[
        InlineKeyboardButton("💰 ဈေးအသစ်ထည့်", callback_data=f"addprice_{chassis}"),
        InlineKeyboardButton("✏️ ပြင်ရန်",      callback_data=f"editcar_{chassis}"),
    ]]
    await update.message.reply_text(txt, parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(kb))

async def list_cars(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await is_active_member(user_id):
        await update.message.reply_text(
            "🔒 *Member များသာ သုံးနိုင်ပါသည်*\n\nMembership ရယူရန် /start နှိပ်ပါ",
            parse_mode='Markdown')
        return
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
        f"🌐 *Japan Auction Car Checker — Web App*\n\n"
        f"https://kyawmintun08.github.io/Japan-Auction-Car-Checker/\n\n"
        f"• {LOC_MAESOT} + {LOC_KLANG9} 🚗\n• ဈေးကြည့်နိုင် 📈\n• Chart ကြည့်နိုင် 📊",
        parse_mode='Markdown')

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data  = query.data

    # ⬇️ Coming Soon Button
    if data == "membership_comingsoon":
        await query.answer("⏳ Membership system မကြီးစုံသေးပါ — မကြာမီ မည်ဖြစ်သည်", show_alert=True)
        return

    # အခြား callback handlers ကို ဒီနေရာမှာ ထည့်နိုင်ပါတယ်

async def editcar_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data  = query.data
    
    if data.startswith("editcar_"):
        if query.from_user.id not in ADMIN_IDS:
            await query.answer("❌ Admin only", show_alert=True)
            return
        chassis = data.replace("editcar_","")
        car = find_by_chassis(chassis)
        if not car:
            await query.answer("❌ Chassis မတွေ့ပါ", show_alert=True)
            return
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"💰 ဈေး",   callback_data=f"editfield_{chassis}_price")],
            [InlineKeyboardButton(f"🎨 Color", callback_data=f"editfield_{chassis}_color")],
            [InlineKeyboardButton(f"🚗 Model", callback_data=f"editfield_{chassis}_model")],
            [InlineKeyboardButton("❌ Cancel", callback_data=f"editfield_{chassis}_cancel")],
        ])
        await query.message.reply_text(
            f"✏️ *{chassis}* — ဘာပြင်မလဲ?",
            parse_mode='Markdown', reply_markup=kb)

    elif data.startswith("editfield_"):
        if query.from_user.id not in ADMIN_IDS:
            await query.answer("❌ Admin only", show_alert=True)
            return
        parts   = data.split("_", 2)
        chassis = parts[1]
        field   = parts[2]
        if field == "cancel":
            pending_edit.pop(query.from_user.id, None)
            await query.message.reply_text("❌ Cancel လုပ်ပြီး")
            return
        pending_edit[query.from_user.id] = {"chassis": chassis, "field": field}
        prompts = {
            "price": f"💰 `{chassis}` ဈေးအသစ် ရိုက်ထည့်ပါ:\nဥပမာ: `150000`",
            "color": f"🎨 `{chassis}` Color အသစ် ရိုက်ထည့်ပါ:\nဥပမာ: `PEARL WHITE`",
            "model": f"🚗 `{chassis}` Model အသစ် ရိုက်ထည့်ပါ:\nဥပမာ: `HONDA FIT`",
        }
        await query.message.reply_text(prompts[field], parse_mode='Markdown')

    elif data.startswith("addprice_"):
        chassis = data.replace("addprice_","")
        car     = find_by_chassis(chassis)
        if car:
            pending_photo[query.from_user.id] = {
                "user_id": query.from_user.id,
                "chassis": car['chassis'], "model": car['model'],
                "color":   car['color'],   "year":  car['year'],
                "price":   None, "loc": loc_display(car.get('loc','MaeSot')), "image_url": ""}
        await query.message.reply_text(
            f"💰 `{chassis}` ဈေး ရိုက်ထည့်ပါ:\nဥပမာ: `150000`", parse_mode='Markdown')

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
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
            msg = (f"⚠️ `{chassis}` Checklist မှာ မပါဘူး\n🚗 ခန့်မှန်း: *{guessed}*"
                   if guessed != "UNKNOWN"
                   else f"❌ `{chassis}` မတွေ့ပါ")
            await update.message.reply_text(msg, parse_mode='Markdown')

async def approve_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if ADMIN_IDS and user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Admin သာ သုံးနိုင်တယ်")
        return
    if len(context.args) < 2:
        await update.message.reply_text("❌ Format: `/approve @username 1`",
                                        parse_mode='Markdown')
        return
    username_or_id = context.args[0].replace('@','')
    try:
        months = int(context.args[1])
    except:
        await update.message.reply_text("❌ လ ဂဏန်းထည့်ပါ", parse_mode='Markdown')
        return
    
    await update.message.reply_text(
        f"✅ *Member Approve ပြီ!*\n\n"
        f"👤 @{username_or_id}\n"
        f"📅 {months} လ",
        parse_mode='Markdown')

async def members_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if ADMIN_IDS and user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Admin သာ သုံးနိုင်တယ်")
        return
    await update.message.reply_text("👥 Member စာရင်း (အလုပ်လုပ်ပြီ ✅)", parse_mode='Markdown')

async def kick_member_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if ADMIN_IDS and user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Admin သာ သုံးနိုင်တယ်")
        return
    if not context.args:
        await update.message.reply_text("❌ Format: `/kick 123456789`", parse_mode='Markdown')
        return
    await update.message.reply_text("🚫 Kick လုပ်ပြီ", parse_mode='Markdown')

async def main():
    logger.info("Bot starting...")
    async with httpx.AsyncClient() as client:
        await client.post(f"https://api.telegram.org/bot{TOKEN}/deleteWebhook",
                          params={"drop_pending_updates":True})
    
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start",      start))
    app.add_handler(CommandHandler("find",       find_car))
    app.add_handler(CommandHandler("model",      find_model))
    app.add_handler(CommandHandler("price",      add_price))
    app.add_handler(CommandHandler("history",    price_history_cmd))
    app.add_handler(CommandHandler("list",       list_cars))
    app.add_handler(CommandHandler("web",        web_link))
    app.add_handler(CommandHandler("approve",    approve_member))
    app.add_handler(CommandHandler("members",    members_list))
    app.add_handler(CommandHandler("kick",       kick_member_cmd))
    
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(CallbackQueryHandler(editcar_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    await app.initialize()
    await app.start()

    member_commands = [
        BotCommand("start",    "🚗 Bot စတင်ရန်"),
        BotCommand("find",     "🔍 Chassis ဖြင့်ရှာရန်"),
        BotCommand("model",    "🔎 Model အမည်ဖြင့်ရှာရန်"),
        BotCommand("history",  "📈 ဈေးနှုန်း မှတ်တမ်းကြည့်ရန်"),
        BotCommand("list",     "📊 ကားစာရင်း အားလုံးကြည့်ရန်"),
        BotCommand("web",      "🌐 Web App link ကြည့်ရန်"),
    ]
    
    admin_commands = member_commands + [
        BotCommand("price",    "💰 ကားဈေးထည့်ရန် (Admin)"),
        BotCommand("approve",  "✅ Member approve (Admin)"),
        BotCommand("members",  "👥 Member စာရင်း (Admin)"),
        BotCommand("kick",     "🚫 Member ထုတ်ရန် (Admin)"),
    ]
    
    try:
        await app.bot.set_my_commands(member_commands, scope=BotCommandScopeAllPrivateChats())
        for admin_id in ADMIN_IDS:
            try:
                await app.bot.set_my_commands(admin_commands, scope=BotCommandScopeChat(chat_id=admin_id))
            except Exception as e:
                logger.warning(f"Admin scope set failed: {e}")
        logger.info("Command scopes set successfully")
    except Exception as e:
        logger.error(f"set_my_commands error: {e}")

    startup_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    startup_msg = (
        f"🟢 *Bot ပြန်စတင်ပြီ*\n\n"
        f"⏰ {startup_time}\n"
        f"🤖 Model: `{GEMINI_MODEL}`\n"
        f"📦 Cars: {len(CARS)}\n"
        f"🔐 Membership: {'✅ ENABLED' if MEMBERSHIP_ENABLED else '❌ COMING SOON'}"
    )
    for admin_id in ADMIN_IDS:
        try:
            await app.bot.send_message(chat_id=admin_id, text=startup_msg, parse_mode='Markdown')
        except Exception as e:
            logger.warning(f"Startup notify failed: {e}")

    await app.updater.start_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)
    logger.info("Bot polling!")
    await asyncio.Event().wait()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"FATAL: {e}")
        raise
