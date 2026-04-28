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
pending_payment = {}   # user_id -> {package, months, amount, username, name}
pending_updateid = {}  # user_id -> {target_username, old_id, new_id}
pending_edit     = {}  # user_id -> {chassis, field}
pending_broadcast= {}  # user_id -> {pkg_filter, waiting_photo}
pending_request  = {}  # user_id -> {step, data}
proxy_sessions   = {}  # session_id -> {customerId, brokerId, reqId, status}
pending_rating   = {}  # customer_id -> {reqId, brokerId, brokerTgId}
pending_deposit  = {}  # customer_id -> {reqId, brokerTgId, step, slip_info}
active_timers    = {}  # req_id -> asyncio.Task
auction_dep_timers = {}  # req_id -> asyncio.Task (48hr deposit timeout)
fasttrack_paid    = set()   # str_uid — fast track deposit ပေးပြီးသူများ
fasttrack_pending = {}       # str_uid -> {"waiting_slip": True, "slip_info": {}}
warned_3days   = set()
promo_used     = {}
rate_limit     = {}
pending_setqr    = {}  # admin_id -> "kpay" / "wave" / "cb"
payment_qr_cache = {}  # method -> {"file_id": str, "ts": datetime}

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

# ── 10 Day Promo Helpers ──────────────────────────────
async def get_cancel_count(str_uid: str) -> int:
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.post(SHEET_WEBHOOK, json={
                "action": "getCancelCount", "userId": str_uid,
            }, timeout=10)
        return resp.json().get("cancelCount", 0)
    except:
        return 0

async def check_promo10d_eligibility(str_uid: str) -> dict:
    """Returns {eligible, reason, active, carreq_count}"""
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.post(SHEET_WEBHOOK, json={"action":"getMembers"}, timeout=10)
        members = resp.json().get("members", [])
        for m in members:
            if str(m.get("userId","")) == str_uid:
                pkg    = str(m.get("package","")).upper()
                status = str(m.get("status","")).upper()
                if pkg == "PROMO10D":
                    if status == "ACTIVE":
                        return {"eligible": True, "active": True, "reason": ""}
                    if status in ("KICKED", "EXPIRED"):
                        return {"eligible": False, "active": False,
                                "reason": "10 Day Promo သုံးပြီး Order မတင်ခဲ့သောကြောင့် ထပ်မရနိုင်ပါ"}
    except Exception as e:
        logger.error(f"check_promo10d: {e}")

    # Cancel count check
    cancel_count = await get_cancel_count(str_uid)
    if cancel_count >= 2:
        return {"eligible": False, "active": False,
                "reason": "Cancel ၂ ကြိမ်နှင့်အထက် ရှိသောကြောင့် 10 Day Promo မရနိုင်ပါ"}

    return {"eligible": True, "active": False, "reason": ""}

async def activate_promo10d(context, user_id: int, username: str) -> bool:
    """Save PROMO10D member to sheet"""
    now        = datetime.now()
    start_date = now.strftime("%d/%m/%Y")
    expire_date= (now + timedelta(days=10)).strftime("%d/%m/%Y")
    password   = generate_password()
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.post(SHEET_WEBHOOK, json={
                "action":     "saveMember",
                "userId":     str(user_id),
                "username":   username,
                "startDate":  start_date,
                "expireDate": expire_date,
                "status":     "ACTIVE",
                "password":   password,
                "package":    "PROMO10D",
            }, timeout=10)
        return resp.json().get("status") == "ok"
    except Exception as e:
        logger.error(f"activate_promo10d: {e}")
        return False

def generate_password() -> str:
    letters = random.choices(string.ascii_uppercase, k=5)
    digits  = random.choices(string.digits, k=5)
    mixed   = [letters[0], digits[0], letters[1], digits[1], letters[2],
               digits[2], letters[3], digits[3], letters[4], digits[4]]
    return "KMT-" + "".join(mixed[:6]) + "-" + "".join(mixed[6:])

# ── Helpers ───────────────────────────────────────────
# ── Tracking Buttons ──────────────────────────────────
TRACKING_LABELS = {
    "A": [
        ("🔍 ကားကြည့်နေဆဲ",      "searching"),
        ("🔎 ကားစစ်ဆေးနေဆဲ",    "checking"),
        ("🚗 ကားရပြီ",            "found"),
        ("🏷️ Auction တင်ပြီ",    "bidding"),
        ("⏳ ရလဒ်စောင့်စားပါ",   "waiting"),
        ("🏆 Auction Win",        "win"),
        ("❌ Auction Loss",        "loss"),
    ],
    "R": [
        ("🔍 ကားရှာနေဆဲ",        "searching"),
        ("🚗 ကားရပြီ",            "found"),
        ("✅ ကားအဆင်ပြေပြီ",     "ok"),
    ],
}

TRACKING_NOTI = {
    "searching": "🔍 Broker သည် ကားရှာနေဆဲ ဖြစ်ပါသည်",
    "checking":  "🔎 Broker သည် ကားစစ်ဆေးနေဆဲ ဖြစ်ပါသည်",
    "found":     "🚗 ကားတွေ့ပြီ — အသေးစိတ် ဆက်လာမည်",
    "bidding":   "🏷️ Auction တင်ပြီ — ရလဒ် စောင့်ပါ",
    "waiting":   "⏳ Auction ရလဒ် စောင့်နေဆဲ ဖြစ်ပါသည်",
    "win":       "🏆 Auction Win! ကားရပြီ — Broker ဆက်သွယ်ပေးမည်",
    "loss":      "❌ Auction Loss — Broker မှ နောက်ထပ် ဆက်သွယ်ပေးမည်",
    "ok":        "✅ ကားအဆင်ပြေပြီ — Broker ဆက်သွယ်ပေးမည်",
}

def get_tracking_keyboard(svc_type: str, req_id: str) -> InlineKeyboardMarkup:
    t = "A" if svc_type == "auction" else "R"
    buttons = []
    row = []
    for label, key in TRACKING_LABELS[t]:
        row.append(InlineKeyboardButton(label, callback_data=f"track_{t}_{key}_{req_id}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(buttons)

def loc_display(loc_key: str) -> str:
    if loc_key == "Klang9": return LOC_KLANG9
    if loc_key in ("Border44","Best Border","44Gate","44gate"): return LOC_BORDER44
    return LOC_MAESOT

async def get_member_package(user_id: int) -> str | None:
    if user_id in ADMIN_IDS:
        return "WEB"
    try:
        sheet_id = os.environ.get('SHEET_ID', '')
        url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:json&sheet=Members&_={int(datetime.now().timestamp())}"
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, timeout=10)
        text = resp.text
        import json as _json
        raw  = _json.loads(text[text.index('{'):text.rindex('}')+1])
        rows = raw.get('table', {}).get('rows', [])
        now  = datetime.now()
        for row in rows:
            c = row.get('c', [])
            if not c: continue
            uid_cell    = c[0] if len(c) > 0 else None
            expire_cell = c[3] if len(c) > 3 else None
            status_cell = c[4] if len(c) > 4 else None
            pkg_cell    = c[6] if len(c) > 6 else None
            if not uid_cell: continue
            uid_val = uid_cell.get('f') or str(uid_cell.get('v',''))
            uid_val = uid_val.replace('.0','').strip()
            if uid_val != str(user_id): continue
            status = (status_cell.get('v','') if status_cell else '').upper()
            expire_str = (expire_cell.get('f','') if expire_cell else '')
            try:
                ep = expire_str.split('/')
                expire_date = datetime(int(ep[2]), int(ep[1]), int(ep[0]))
            except:
                expire_date = datetime(2000,1,1)
            if status == 'ACTIVE' and expire_date >= now:
                pkg = (pkg_cell.get('v','CH') if pkg_cell else 'CH') or 'CH'
                pkg = str(pkg).upper()
                if pkg == 'CH-PROMO': return 'CH'
                return pkg
            return None
        return None
    except Exception as e:
        logger.error(f"get_member_package: {e}")
        return None

def decode_vin_year(vin: str) -> int:
    VIN_YEAR_MODERN = {
        'A':2010,'B':2011,'C':2012,'D':2013,'E':2014,'F':2015,'G':2016,
        'H':2017,'J':2018,'K':2019,'L':2020,'M':2021,'N':2022,'P':2023,
        'R':2024,'S':2025,'T':2026,
        '1':2001,'2':2002,'3':2003,'4':2004,'5':2005,'6':2006,'7':2007,
        '8':2008,'9':2009,
    }
    try:
        if len(vin) >= 10:
            char = vin[9].upper()
            return VIN_YEAR_MODERN.get(char, 0)
    except:
        pass
    return 0

def is_european_vin(chassis: str) -> bool:
    c = chassis.upper().replace("-","").replace(" ","")
    if len(c) == 17 and c[:1] in ("W","S","V","Z","X","T"):
        return True
    return False

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
        if is_european_vin(chassis_input):
            vin_yr = decode_vin_year(chassis_input)
            yr_hint = f" Year hint from VIN: {vin_yr}." if vin_yr else ""
            prompt = f"This is a European VIN: {chassis_input}.{yr_hint} What car brand and model is this? Reply ONLY the model name UPPERCASE (e.g. NEW BEETLE, AUDI A4, BMW 3 SERIES). If unknown reply UNKNOWN."
        else:
            prefix  = chassis_input.split("-")[0] if "-" in chassis_input else chassis_input[:6]
            prompt  = f"What Japanese car model has chassis prefix '{prefix}'? Reply ONLY the model name UPPERCASE. If unknown reply UNKNOWN."
        url     = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
        payload = {"contents":[{"parts":[{"text":prompt}]}]}
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

async def kick_with_retry(context, user_id: int, max_retries: int = 3) -> bool:
    for attempt in range(max_retries):
        try:
            await context.bot.ban_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
            await context.bot.unban_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
            return True
        except Exception as e:
            logger.error(f"Kick attempt {attempt+1} for {user_id}: {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(5)
    return False

# ── Gemini Slip Reader ────────────────────────────────
async def gemini_read_slip(file_bytes: bytes) -> dict:
    if not GEMINI_API_KEY:
        return {}
    try:
        import base64
        img_b64 = base64.b64encode(file_bytes).decode()
        url     = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
        payload = {"contents":[{"parts":[
            {"text":"""Identify this Myanmar mobile payment slip and extract fields.

HOW TO IDENTIFY:
- Wave Money slip = YELLOW background, "KS" logo with lightning bolt
    * Shows "Transaction ID" + "Date & Time" + "Total" (top amount)
    * "Receive Money" view: has "Sender" field
    * "Send Money" view: has "Receiver" field

- KPay (KBZPay) slip = BLUE background, "KBZ BANK" red logo at top + "KBZPay" blue logo at bottom
    * Shows "Transaction Time" + "Transaction No." + "Transfer To" + "Amount" (top large number)
    * "Transfer To" = the person who RECEIVED the money (e.g. admin name)
    * Sender name NOT shown on this slip type

- CB Bank slip = GREEN background, "CB Bank" or "CB Pay" logo
    * Shows "Transaction Date" + "Transaction No." + "Receiver" + "Amount"

Extract these fields:
TYPE: (Wave or KPay or CB or Other)
TRANSACTION_NO:
  - Wave: number next to "Transaction ID" (e.g. 894983741)
  - KPay: full number next to "Transaction No." (e.g. 01004089020139330692) — ALL digits
  - CB: number next to "Transaction No." or "Reference No."
AMOUNT: (positive number only, no commas, no Ks, no minus/plus — from top large amount, e.g. 1000000)
DATE: (dd/mm/yyyy — from "Date & Time" for Wave, "Transaction Time" for KPay)
TIME: (HH:MM 24hr — convert PM/AM, e.g. 02:55 PM = 14:55)
TRANSFER_TO: (name next to "Transfer To" for KPay, or "Receiver" for Wave Send view — who received the money)
SENDER: (name next to "Sender" for Wave Receive view only — UNKNOWN for KPay and Wave Send view)

TRANSACTION_NO is most critical — read every digit carefully.

Return EXACTLY in this format with no extra text. Write UNKNOWN if not found."""},
            {"inline_data":{"mime_type":"image/jpeg","data":img_b64}}
        ]}]}
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=payload, timeout=60)
        data = resp.json()
        if "candidates" not in data:
            return {}
        text   = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        result = {}
        for line in text.split("\n"):
            line = line.strip()
            if ":" in line:
                key, val = line.split(":", 1)
                result[key.strip().upper()] = val.strip()
        return result
    except Exception as e:
        logger.error(f"Gemini slip: {e}")
        return {}

# ── Payment QR Helpers ────────────────────────────────
PAYMENT_METHOD_INFO = {
    "kpay": {
        "label":  "🔵 KPay",
        "name":   "KPay",
        "number": "09973625985",
        "owner":  "Kyaw Min Tun",
    },
    "wave": {
        "label":  "🟣 Wave",
        "name":   "Wave",
        "number": "09799959537",
        "owner":  "Kyaw Min Tun",
    },
    "cb": {
        "label":  "🟢 CB Bank",
        "name":   "CB Bank MMQR",
        "number": "(QR Scan)",
        "owner":  "Kyaw Min Tun (Merchant)",
    },
}

async def get_payment_qr(method: str) -> str:
    """Sheet ကနေ file_id ဆွဲ (10 min cache)"""
    method = method.lower().strip()
    cached = payment_qr_cache.get(method)
    if cached:
        age = (datetime.now() - cached["ts"]).total_seconds()
        if age < 600:  # 10 min
            return cached["file_id"]
    if not SHEET_WEBHOOK:
        return ""
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.post(SHEET_WEBHOOK, json={
                "action": "getPaymentQR",
                "method": method,
            }, timeout=10)
        data = resp.json()
        if data.get("ok") and data.get("fileId"):
            file_id = data["fileId"]
            payment_qr_cache[method] = {"file_id": file_id, "ts": datetime.now()}
            return file_id
    except Exception as e:
        logger.error(f"get_payment_qr {method}: {e}")
    return ""

async def set_payment_qr(method: str, file_id: str, admin_name: str) -> bool:
    """Sheet မှာ file_id သိမ်း + cache ဖျက်"""
    method = method.lower().strip()
    if not SHEET_WEBHOOK:
        return False
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.post(SHEET_WEBHOOK, json={
                "action":    "setPaymentQR",
                "method":    method,
                "fileId":    file_id,
                "adminName": admin_name,
            }, timeout=10)
        result = resp.json()
        if result.get("ok"):
            payment_qr_cache.pop(method, None)  # cache invalidate
            return True
    except Exception as e:
        logger.error(f"set_payment_qr {method}: {e}")
    return False

# ── Save Member with Password ─────────────────────────
async def save_member_to_sheet(user_id: str, username: str, days: int,
                                password: str = "", package: str = "CH") -> bool:
    if not SHEET_WEBHOOK:
        return False
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(SHEET_WEBHOOK, json={
                "action":   "saveMember",
                "userId":   str(user_id),
                "username": username,
                "days":     days,
                "password": password,
                "package":  package,
            }, timeout=10, follow_redirects=True)
        return resp.json().get("status") == "ok"
    except Exception as e:
        logger.error(f"saveMember: {e}")
        return False

async def create_invite_link(context, days: int) -> str:
    try:
        import time
        invite = await context.bot.create_chat_invite_link(
            chat_id=CHANNEL_ID,
            member_limit=1,
            expire_date=int(time.time() + 1800)
        )
        return invite.invite_link
    except Exception as e:
        logger.error(f"Invite link: {e}")
        return ""

async def send_approval_dm(context, member_id: int, months: int,
                           password: str, invite_url: str, package: str = "CH"):
    is_web      = package == "WEB"
    expire_date = (datetime.now() + timedelta(days=months * 30)).strftime("%d/%m/%Y")
    cust_kb = []
    if invite_url:
        cust_kb.append([InlineKeyboardButton("📢 Channel ဝင်ရန်", url=invite_url)])
    if is_web:
        cust_kb.append([InlineKeyboardButton("🌐 Web App ဖွင့်",
                        url="https://kyawmintun08.github.io/Japan-Auction-Car-Checker/")])

    if is_web:
        text = (
            f"🎉 *Membership Approved!*\n\n"
            f"📦 Package: 💎 Web Premium\n"
            f"📅 သက်တမ်း: *{months} လ*\n"
            f"⏰ ကုန်ဆုံးရက်: `{expire_date}`\n\n"
            f"🔑 *Web Password: `{password}`*\n"
            f"🌐 Web: kyawmintun08.github.io/Japan-Auction-Car-Checker/\n\n"
            f"⚠️ Password ကို မည်သူ့ကိုမျှ မပေးပါနဲ့\n"
            f"   မျှဝေပါက Membership ပိတ်သိမ်းခံရမည်\n\n"
            f"သက်တမ်းတိုးဖို့: /renew\nကျေးဇူးတင်ပါတယ် 🙏"
        )
    else:
        text = (
            f"🎉 *Membership Approved!*\n\n"
            f"📦 Package: 📱 Standard\n"
            f"📅 သက်တမ်း: *{months} လ*\n"
            f"⏰ ကုန်ဆုံးရက်: `{expire_date}`\n\n"
            f"📢 Channel invite link အပေါ်မှ ဝင်ပါ\n\n"
            f"သက်တမ်းတိုးဖို့: /renew\nကျေးဇူးတင်ပါတယ် 🙏"
        )
    try:
        msg = await context.bot.send_message(
            chat_id=member_id, text=text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(cust_kb) if cust_kb else None)
        try:
            await context.bot.pin_chat_message(
                chat_id=member_id,
                message_id=msg.message_id,
                disable_notification=True)
        except Exception as e:
            logger.error(f"Pin message: {e}")
    except Exception as e:
        logger.error(f"Send approval DM: {e}")

# ── Commands ──────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id  = update.effective_user.id
    is_admin = user_id in ADMIN_IDS

    kb = []
    kb.append([InlineKeyboardButton("🆕 Membership ဝယ်ရန်", callback_data="join_start")])
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
            "🌐 `/web` → Web Link\n"
            "🔄 `/renew` → Membership သက်တမ်းတိုး\n"
            "🔑 `/mypassword` → Password ပြန်ယူ\n\n"
            "*Admin Commands:*\n"
            "📸 ကားပုံ တင် → Chassis auto ဖတ်\n"
            "📋 ပုံ + caption `list` → Auction List (Auto detect location)\n"
            "💰 `/price NT32-504837 150000` → ဈေးထည့်\n"
            "✅ `/approve @user 30 WEB` → Member approve\n"
            "👥 `/members` → Member list\n"
            "🔄 `/renew` → Member renew\n"
            "🚫 `/kick @user` → Member kick\n"
            "🔑 `/resetpass @user` → Password reset\n"
            "🆔 `/updateid @user newID` → ID update\n"
            "💳 `/setqr` → Payment QR ထည့်/ပြောင်း\n"
            "💾 `/backup` → CSV backup\n"
        )
    else:
        cmd_text = (
            "*Commands:*\n"
            "🔍 `/find NT32-504837` → Chassis ရှာ\n"
            "🔎 `/model xtrail` → Model ရှာ\n"
            "📋 `/history NT32-504837` → ဈေးမှတ်တမ်း\n"
            "📊 `/list` → ကားအားလုံး\n"
            "🌐 `/web` → Web Link\n"
            "🔄 `/renew` → Membership သက်တမ်းတိုး\n"
            "🔑 `/mypassword` → Password ပြန်ယူ\n"
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
    str_uid  = str(user_id)
    if not await is_active_member(user_id):
        # 10 Day Promo eligibility check
        promo_info = await check_promo10d_eligibility(str_uid)
        if promo_info.get("active"):
            pass  # PROMO10D active — proceed to carrequest
        elif not promo_info.get("eligible"):
            await update.message.reply_text(
                f"❌ *ဝင်ခွင့်မရပါ*\n\n{promo_info['reason']}\n\n"
                f"Membership ရယူရန် /start နှိပ်ပါ",
                parse_mode='Markdown')
            return
        else:
            # Show buying car button
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("🚗 ကားဝယ်ယူဖို့ လာတာလားး?", callback_data=f"buying_car_{user_id}")
            ]])
            await update.message.reply_text(
                "👋 *Japan Auction Car Checker*\n\n"
                "ကားဝယ်ယူလိုပါက *10 Day Free Promo* ရရှိနိုင်ပါသည်\n\n"
                "⚠️ စည်ကမ်းချက်:\n"
                "• Broker နှင့် ဆက်သွယ်ပြီး Order တင်ရမည်\n"
                "• 10 ရက်အတွင်း Order မတင်ပါက Kick ခံရမည်\n"
                "• Cancel ၂ ကြိမ်နှင့်အထက် ဖြစ်ပါက Promo မရနိုင်\n\n"
                "ဆက်လုပ်မည်ဆိုပါက 👇",
                parse_mode='Markdown',
                reply_markup=kb)
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
        if guessed == "UNKNOWN":
            guessed = await guess_model_gemini(chassis)
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
            "`/price CHASSIS PRICE` — အခြေခံ\n"
            "`/price CHASSIS PRICE COLOR` — color ပါ\n"
            "`/price CHASSIS PRICE MODEL COLOR` — model+color ပါ\n\n"
            "ဥပမာ:\n"
            "`/price VZN11-042846 74000 WHITE`\n"
            "`/price VZN11-042846 74000 AD VAN WHITE`",
            parse_mode='Markdown')
        return
    chassis = context.args[0].upper()
    try:
        price = int(context.args[1].replace(',',''))
    except:
        await update.message.reply_text("❌ ဈေး ဂဏန်းသာ ထည့်ပါ", parse_mode='Markdown')
        return

    extra_args = context.args[2:]
    car = find_by_chassis(chassis)

    if extra_args:
        if len(extra_args) == 1:
            override_color = extra_args[0].upper()
            override_model = None
        else:
            override_color = extra_args[-1].upper()
            override_model = " ".join(extra_args[:-1]).upper()

        if car:
            for c in CARS:
                if c.get("chassis","").upper() == chassis.upper():
                    if override_color: c["color"] = override_color
                    if override_model: c["model"] = override_model
                    break
        else:
            base_model = override_model or guess_model_from_chassis(chassis)
            car = {"chassis": chassis, "model": base_model,
                   "color": override_color, "year": 0, "loc": "MaeSot"}

        if override_color and car: car = dict(car); car["color"] = override_color
        if override_model and car: car["model"] = override_model

        if SHEET_WEBHOOK:
            try:
                async with httpx.AsyncClient() as client:
                    if override_color:
                        await client.post(SHEET_WEBHOOK, json={
                            "action": "updateCar", "chassis": chassis,
                            "field": "color", "value": override_color
                        }, timeout=10, follow_redirects=True)
                    if override_model:
                        await client.post(SHEET_WEBHOOK, json={
                            "action": "updateCar", "chassis": chassis,
                            "field": "model", "value": override_model
                        }, timeout=10, follow_redirects=True)
            except Exception as e:
                logger.error(f"updateCar in price cmd: {e}")
    else:
        if not car:
            car = {"chassis": chassis, "model": guess_model_from_chassis(chassis),
                   "color": "-", "year": 0, "loc": "MaeSot"}

    user_name = update.effective_user.first_name or "Unknown"
    loc       = loc_display(car.get('loc','MaeSot'))
    entry     = await save_price(car['chassis'], car['model'], car['color'], car['year'], price, user_name, location=loc)
    await update.message.reply_text(
        f"✅ *ဈေးထည့်ပြီး!*\n\n🚗 {car['model']} ({ys(car.get('year',0))}) — `{chassis}`\n"
        f"🎨 {car['color']}\n💰 ฿{price:,}\n📍 {loc}\n📅 {entry['date']}\n👤 {user_name}\n\n"
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
    user_id = update.effective_user.id
    pkg     = await get_member_package(user_id)
    if pkg == "WEB":
        await update.message.reply_text(
            f"🌐 *Japan Auction Car Checker — Web App*\n\n"
            f"https://kyawmintun08.github.io/Japan-Auction-Car-Checker/\n\n"
            f"• {LOC_MAESOT} + {LOC_KLANG9} 🚗\n• ဈေးကြည့်နိုင် 📈\n• Chart ကြည့်နိုင် 📊",
            parse_mode='Markdown')
    elif pkg == "CH":
        await update.message.reply_text(
            "🚫 *Web App access မရှိသေးပါ*\n\n"
            "လက်ရှိ Package: 📱 Standard\n\n"
            "🌐 Web App ကြည့်ဖို့ *Channel+Web Package* သို့ Upgrade လုပ်ပါ\n"
            "👉 /renew နှိပ်ပြီး 💎 Web Premium package ရွေးပါ",
            parse_mode='Markdown')
    else:
        await update.message.reply_text(
            "🚫 *Member များသာ Web App ကြည့်နိုင်ပါသည်*\n\nMembership ဝယ်ရန် 👉 /renew",
            parse_mode='Markdown')

def build_package_keyboard(user_id: int, action: str = "renew"):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"📱 Standard",      callback_data=f"pkg_CH_{user_id}_{action}"),
         InlineKeyboardButton(f"💎 Web Premium",   callback_data=f"pkg_WEB_{user_id}_{action}")],
        [InlineKeyboardButton("❌ Cancel",          callback_data=f"pkg_cancel_{user_id}")],
    ])

def build_period_keyboard(user_id: int, package: str):
    prices = PLAN_PRICES[package]
    if package == "CH":
        return InlineKeyboardMarkup([
            [InlineKeyboardButton(f"1 လ — {prices[1]:,} ks",  callback_data=f"period_{package}_1_{user_id}"),
             InlineKeyboardButton(f"2 လ — {prices[2]:,} ks",  callback_data=f"period_{package}_2_{user_id}")],
            [InlineKeyboardButton(f"3 လ — {prices[3]:,} ks",  callback_data=f"period_{package}_3_{user_id}"),
             InlineKeyboardButton(f"5 လ — {prices[5]:,} ks",  callback_data=f"period_{package}_5_{user_id}")],
            [InlineKeyboardButton("◀️ နောက်သို့",             callback_data=f"pkg_back_{user_id}")],
        ])
    else:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton(f"1 လ — {prices[1]:,} ks",  callback_data=f"period_{package}_1_{user_id}"),
             InlineKeyboardButton(f"2 လ — {prices[2]:,} ks",  callback_data=f"period_{package}_2_{user_id}"),
             InlineKeyboardButton(f"3 လ — {prices[3]:,} ks",  callback_data=f"period_{package}_3_{user_id}")],
            [InlineKeyboardButton("◀️ နောက်သို့",             callback_data=f"pkg_back_{user_id}")],
        ])

def build_paymethod_keyboard(user_id: int):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔵 KPay",    callback_data=f"paymethod_kpay_{user_id}"),
         InlineKeyboardButton("🟣 Wave",    callback_data=f"paymethod_wave_{user_id}"),
         InlineKeyboardButton("🟢 CB Bank", callback_data=f"paymethod_cb_{user_id}")],
        [InlineKeyboardButton("❌ Cancel",  callback_data=f"pkg_cancel_{user_id}")],
    ])

async def renew_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user    = update.effective_user
    user_id = user.id
    await update.message.reply_text(
        "🔄 *Membership သက်တမ်းတိုး*\n\nPackage ရွေးပါ 👇",
        parse_mode='Markdown',
        reply_markup=build_package_keyboard(user_id, "renew"))

async def mypassword_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user    = update.effective_user
    user_id = user.id
    if not await is_active_member(user_id):
        await update.message.reply_text(
            "🔒 *Member များသာ သုံးနိုင်ပါသည်*\n\nMembership ရယူရန် /start နှိပ်ပါ",
            parse_mode='Markdown')
        return
    pkg = await get_member_package(user_id)
    if pkg != "WEB":
        await update.message.reply_text(
            "🚫 *Web Password မရှိပါ*\n\n"
            "လက်ရှိ Package: 📱 Standard\n\n"
            "🌐 Web App သုံးဖို့ 💎 *Web Premium* သို့ Upgrade လုပ်ပါ\n"
            "👉 /renew နှိပ်ပြီး Web Premium ရွေးပါ",
            parse_mode='Markdown')
        return
    if not SHEET_WEBHOOK:
        await update.message.reply_text("❌ System error — Admin ကို ဆက်သွယ်ပါ")
        return
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(SHEET_WEBHOOK, json={
                "action": "getPassword",
                "userId": str(user_id),
            }, timeout=10, follow_redirects=True)
        data = resp.json()
        if data.get("status") == "ok" and data.get("password"):
            await update.message.reply_text(
                f"🔑 *သင်၏ Web Password*\n\n"
                f"`{data['password']}`\n\n"
                f"🌐 https://kyawmintun08.github.io/Japan-Auction-Car-Checker/\n\n"
                f"⚠️ Password ကို မည်သူ့ကိုမျှ မပေးပါနဲ့\n"
                f"   မျှဝေပါက Membership ပိတ်သိမ်းခံရမည်",
                parse_mode='Markdown')
        else:
            admin_link = f"\n💬 [Admin ကို ဆက်သွယ်](https://t.me/{ADMIN_USERNAME})" if ADMIN_USERNAME else ""
            await update.message.reply_text(
                f"❌ Password မတွေ့ပါ\n\nAdmin ကို ဆက်သွယ်ပါ{admin_link}",
                parse_mode='Markdown')
    except Exception as e:
        logger.error(f"mypassword: {e}")
        await update.message.reply_text("❌ Error — Admin ကို ဆက်သွယ်ပါ")

async def resetpass_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if ADMIN_IDS and user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Admin သာ သုံးနိုင်တယ်")
        return
    if not context.args:
        await update.message.reply_text("❌ Format: `/resetpass @username` သို့မဟုတ် `/resetpass 123456789`",
                                        parse_mode='Markdown')
        return
    target = context.args[0].replace('@', '')
    new_pw = generate_password()
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(SHEET_WEBHOOK, json={
                "action":   "resetPassword",
                "username": target,
                "password": new_pw,
            }, timeout=10, follow_redirects=True)
        data = resp.json()
        if data.get("status") == "ok":
            member_id = data.get("userId")
            if member_id and str(member_id).isdigit():
                try:
                    await context.bot.send_message(
                        chat_id=int(member_id),
                        text=f"🔑 *Password Reset လုပ်ပြီ*\n\n"
                             f"New Password: `{new_pw}`\n\n"
                             f"🌐 https://kyawmintun08.github.io/Japan-Auction-Car-Checker/\n\n"
                             f"⚠️ မည်သူ့ကိုမျှ မပေးပါနဲ့",
                        parse_mode='Markdown')
                except Exception as e:
                    logger.error(f"resetpass DM: {e}")
            await update.message.reply_text(
                f"✅ Password Reset ပြီ\n👤 @{target}\n🔑 `{new_pw}`",
                parse_mode='Markdown')
        else:
            await update.message.reply_text(f"❌ @{target} မတွေ့ပါ")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

async def updateid_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if ADMIN_IDS and user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Admin သာ သုံးနိုင်တယ်")
        return
    if len(context.args) < 3:
        await update.message.reply_text(
            "❌ Format: `/updateid @username [oldID] [newID]`\n"
            "ဥပမာ: `/updateid @Steve 123456789 987654321`\n\n"
            "⚠️ Old ID မပါရင် update မလုပ်ဘူး — Security အတွက်",
            parse_mode='Markdown')
        return
    target_username = context.args[0].replace('@', '')
    try:
        old_id = int(context.args[1])
        new_id = int(context.args[2])
    except:
        await update.message.reply_text("❌ ID တွေ ဂဏန်းဖြစ်ရမည်")
        return
    if old_id == new_id:
        await update.message.reply_text("❌ Old ID နဲ့ New ID တူနေတယ်")
        return
    if new_id in ADMIN_IDS:
        await update.message.reply_text("❌ Admin ID ကို Member ID အဖြစ် သုံးမရပါ")
        return
    await update.message.reply_text("🔍 Old ID စစ်ဆေးနေတယ်... ⏳")
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(SHEET_WEBHOOK, json={
                "action": "verifyOldId",
                "username": target_username,
                "oldId": str(old_id),
            }, timeout=10, follow_redirects=True)
        data = resp.json()
        if data.get("status") != "ok":
            await update.message.reply_text(
                f"❌ *Old ID မမှန်ဘူး*\n\n"
                f"@{target_username} ရဲ့ Sheet မှာ `{old_id}` မတွေ့ဘူး\n"
                f"Old ID ကို ပြန်စစ်ပြီး ထပ်ကြိုးစားပါ",
                parse_mode='Markdown')
            return
    except Exception as e:
        logger.error(f"verifyOldId: {e}")
        await update.message.reply_text("❌ Sheet စစ်မရ — ထပ်ကြိုးစားပါ")
        return
    pending_updateid[user_id] = {
        "target_username": target_username,
        "old_id": old_id,
        "new_id": new_id,
    }
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ အတည်ပြု",  callback_data=f"uid_ok_{user_id}"),
        InlineKeyboardButton("❌ မလုပ်တော့", callback_data=f"uid_no_{user_id}"),
    ]])
    await update.message.reply_text(
        f"⚠️ *ID Update အတည်ပြုချက်*\n\n"
        f"👤 Member: @{target_username}\n"
        f"🔴 ဟောင်း ID: `{old_id}` ✅ စစ်မှန်ပြီ\n"
        f"🟢 အသစ် ID: `{new_id}`\n\n"
        f"အတည်ပြုရန် 👇",
        parse_mode='Markdown',
        reply_markup=kb)

# ── /setqr — Admin Payment QR Setup ──────────────────
async def setqr_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Admin သာ သုံးနိုင်တယ်")
        return

    # Show current state
    status_lines = []
    for method, info in PAYMENT_METHOD_INFO.items():
        file_id = await get_payment_qr(method)
        mark    = "✅" if file_id else "⚪"
        status_lines.append(f"{mark} {info['label']}")

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔵 KPay",    callback_data=f"setqr_kpay_{user_id}"),
         InlineKeyboardButton("🟣 Wave",    callback_data=f"setqr_wave_{user_id}"),
         InlineKeyboardButton("🟢 CB Bank", callback_data=f"setqr_cb_{user_id}")],
        [InlineKeyboardButton("❌ Cancel",  callback_data=f"setqr_cancel_{user_id}")],
    ])
    await update.message.reply_text(
        f"💳 *Payment QR Setup*\n\n"
        f"လက်ရှိ အခြေအနေ:\n"
        + "\n".join(status_lines)
        + "\n\nဘယ် method အတွက် QR ထည့်/ပြောင်းမလဲ? 👇",
        parse_mode='Markdown',
        reply_markup=kb)

async def broadcast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if ADMIN_IDS and user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Admin သာ သုံးနိုင်တယ်")
        return

    pkg_filter = None
    msg_parts  = context.args if context.args else []
    if msg_parts and msg_parts[0].upper() in ("WEB", "CH"):
        pkg_filter = msg_parts[0].upper()
        msg_parts  = msg_parts[1:]

    message = " ".join(msg_parts)

    if not message:
        pending_broadcast[user_id] = {
            "pkg_filter": pkg_filter,
            "waiting_photo": True
        }
        pkg_label = f" ({pkg_filter} only)" if pkg_filter else " (အားလုံး)"
        await update.message.reply_text(
            f"📢 *Broadcast{pkg_label}*\n\n"
            f"ပုံနဲ့ Caption တွဲပြီး ပို့ပါ\n"
            f"(Caption = Message ဖြစ်မည်)\n\n"
            f"Text သာ ပို့ချင်ရင်:\n"
            f"`/broadcast မက်ဆေ့ပါ`\n\n"
            f"❌ Cancel: /broadcast cancel",
            parse_mode='Markdown')
        return

    if message.lower() == "cancel":
        pending_broadcast.pop(user_id, None)
        await update.message.reply_text("❌ Broadcast ပယ်ဖျက်ပြီ")
        return

    await update.message.reply_text("⏳ Member list ဆွဲနေတယ်...")

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                SHEET_WEBHOOK,
                json={"action": "getMembers"},
                timeout=15,
                follow_redirects=True
            )
        data = resp.json()
        members = data.get("members", [])
    except Exception as e:
        logger.error(f"broadcast getMembers: {e}")
        await update.message.reply_text("❌ Member list ဆွဲမရ")
        return

    targets = []
    for m in members:
        status  = str(m.get("status", "")).upper()
        pkg     = str(m.get("package", "")).upper()
        uid     = m.get("userId") or m.get("userID") or m.get("UserID")
        if status != "ACTIVE":
            continue
        if pkg_filter and pkg != pkg_filter:
            continue
        if uid:
            targets.append(str(uid))

    if not targets:
        await update.message.reply_text("❌ Member မတွေ့ဘူး")
        return

    pkg_label = f" ({pkg_filter} only)" if pkg_filter else ""
    await update.message.reply_text(f"📢 {len(targets)} ယောက်ကို ပို့မည်{pkg_label}...")

    success = 0
    failed  = 0
    for uid in targets:
        try:
            await context.bot.send_message(
                chat_id=int(uid),
                text=f"📢 *Japan Auction Car*\n\n{message}",
                parse_mode='Markdown')
            success += 1
            await asyncio.sleep(0.3)
        except Exception as e:
            logger.error(f"broadcast {uid}: {e}")
            failed += 1

    await update.message.reply_text(
        f"✅ *Broadcast ပြီးပြီ*\n\n"
        f"✅ အောင်မြင်: {success} ယောက်\n"
        f"❌ မရောက်: {failed} ယောက်",
        parse_mode='Markdown')

async def backup_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if ADMIN_IDS and user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Admin သာ သုံးနိုင်တယ်")
        return
    await update.message.reply_text("⏳ Sheet မှ data ဆွဲနေသည်...")
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(SHEET_WEBHOOK, json={
                "action": "getBackupCSV"
            }, timeout=30, follow_redirects=True)
        data = resp.json()
        if data.get("status") == "ok" and data.get("csv"):
            csv_content = data["csv"]
            filename    = f"Members_backup_{datetime.now().strftime('%Y_%m_%d')}.csv"
            csv_bytes   = csv_content.encode('utf-8-sig')
            from io import BytesIO
            bio = BytesIO(csv_bytes)
            bio.name = filename
            await context.bot.send_document(
                chat_id=user_id,
                document=bio,
                filename=filename,
                caption=f"✅ Members Backup\n📅 {datetime.now().strftime('%d/%m/%Y %H:%M')}")
        else:
            await update.message.reply_text("❌ Backup မရနိုင်ပါ — Sheet စစ်ဆေးပါ")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

async def upgrade_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user    = update.effective_user
    user_id = user.id
    await update.message.reply_text(
        "⬆️ *Package Upgrade*\n\n"
        "📱 Standard → 💎 Web Premium\n\n"
        "Web ဝင်ခွင့် ထပ်ထည့်ချင်ရင် Package ရွေးပါ 👇",
        parse_mode='Markdown',
        reply_markup=build_package_keyboard(user_id, "upgrade"))

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

async def gemini_ocr_auction_list(file_bytes: bytes) -> tuple:
    if not GEMINI_API_KEY:
        return [], None
    try:
        import base64, json
        img_b64 = base64.b64encode(file_bytes).decode()
        url     = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
        payload = {"contents":[{"parts":[
            {"text": (
                "This is a JAN JAPAN auction car list image from Thailand.\n\n"
                "STEP 1 — Read the TITLE/HEADER at the very top of the image:\n"
                "   Look for these EXACT words in the blue/colored header band:\n"
                "   → 'KLANG9' or 'KLANG 9' or '9.2 FREEZONE' = location is Klang9\n"
                "   → 'MAESOT' or 'MAE SOT' = location is MaeSot\n"
                "   → 'BEST BORDER' or '44 GATE' or 'BORDER-44' or 'BORDER 44' = location is Border44\n\n"
                "STEP 2 — Extract every car row from the table.\n\n"
                "Return ONLY valid JSON, no markdown, no explanation:\n"
                "{\"location\":\"Klang9\",\"cars\":[{\"chassis\":\"NT32-024640\",\"model\":\"X-TRAIL\",\"color\":\"BLACK\",\"year\":2014}]}\n\n"
                "Rules:\n"
                "- location MUST be exactly 'Klang9' OR 'MaeSot' OR 'Border44'\n"
                "- If header says KLANG9 → location = 'Klang9'\n"
                "- If header says BEST BORDER or 44 GATE → location = 'Border44'\n"
                "- If header says MAESOT → location = 'MaeSot'\n"
                "- year must be a number (e.g. 2014 not '2014')"
            )},
            {"inline_data":{"mime_type":"image/jpeg","data":img_b64}}
        ]}]}
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=payload, timeout=60)
        data = resp.json()
        if "candidates" not in data:
            return [], None
        text  = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        start = text.find('{'); end = text.rfind('}') + 1
        if start >= 0 and end > start:
            parsed = json.loads(text[start:end])
            cars   = parsed.get("cars", [])
            loc    = parsed.get("location", None)
            return cars, loc
        start = text.find('['); end = text.rfind(']') + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end]), None
    except Exception as e:
        logger.error(f"Gemini list: {e}")
    return [], None

async def gemini_ocr_chassis(file_bytes: bytes) -> dict:
    if GEMINI_API_KEY:
        try:
            import base64
            img_b64 = base64.b64encode(file_bytes).decode()
            url     = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
            payload = {"contents":[{"parts":[
                {"text":"""Japan auction car photo.
1. Find chassis number written on windshield with marker pen (e.g. NT32-024640, GP1-1049821, S510P-0173458)
2. Identify car body COLOR from the paint (WHITE, BLACK, SILVER, PEARL WHITE, DARK BLUE, RED, BLUE, GREEN, YELLOW, BROWN, ORANGE, GREY)
3. Identify car MODEL from the shape/badge
4. Identify manufacturing YEAR if visible

Return EXACTLY in this format (no extra text):
CHASSIS: S510P-0236416
MODEL: HIJET TRUCK
COLOR: WHITE
YEAR: 2017"""},
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
    user    = update.effective_user
    user_id = user.id
    photo   = update.message.photo[-1]
    caption = (update.message.caption or "").strip().lower()

    if not check_rate_limit(user_id, max_req=5, window=60):
        await update.message.reply_text("⚠️ တစ်မိနစ်အတွင်း ပုံများသွားတယ် — ခဏစောင့်ပါ")
        return

    # ── Admin /setqr Mode ──
    if user_id in ADMIN_IDS and user_id in pending_setqr:
        method     = pending_setqr.pop(user_id)
        file_id    = photo.file_id
        admin_name = update.effective_user.first_name or "admin"
        ok         = await set_payment_qr(method, file_id, admin_name)
        info       = PAYMENT_METHOD_INFO.get(method, {})
        if ok:
            await update.message.reply_text(
                f"✅ *{info.get('label','')} QR Saved!*\n\n"
                f"📋 ID: `{file_id[:20]}...`\n"
                f"👤 By: {admin_name}\n\n"
                f"➡️ နောက် method ထည့်ဖို့ /setqr ထပ်နှိပ်ပါ",
                parse_mode='Markdown')
        else:
            await update.message.reply_text("❌ Save မရဘူး — Sheet စစ်ဆေးပါ")
        return

    # ── Broadcast Photo Mode ──
    if user_id in pending_broadcast and pending_broadcast[user_id].get("waiting_photo"):
        bc      = pending_broadcast.pop(user_id)
        pkg_filter = bc.get("pkg_filter")
        caption_text = update.message.caption or ""

        await update.message.reply_text("⏳ Member list ဆွဲနေတယ်...")
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    SHEET_WEBHOOK,
                    params={"action": "getMembers"},
                    timeout=15, follow_redirects=True)
            data = resp.json()
            members = data.get("members", [])
        except Exception as e:
            logger.error(f"broadcast getMembers: {e}")
            await update.message.reply_text("❌ Member list ဆွဲမရ")
            return

        targets = []
        for m in members:
            status = str(m.get("status","")).upper()
            pkg    = str(m.get("package","")).upper()
            uid    = m.get("userId") or m.get("userID") or m.get("UserID")
            if status != "ACTIVE": continue
            if pkg_filter and pkg != pkg_filter: continue
            if uid: targets.append(str(uid))

        if not targets:
            await update.message.reply_text("❌ Member မတွေ့ဘူး")
            return

        pkg_label = f" ({pkg_filter} only)" if pkg_filter else ""
        await update.message.reply_text(f"📢 {len(targets)} ယောက်ကို ပုံ+စာ ပို့မည်{pkg_label}...")

        file = await photo.get_file()
        file_bytes = bytes(await file.download_as_bytearray())
        from io import BytesIO

        success = 0; failed = 0
        for uid in targets:
            try:
                bio = BytesIO(file_bytes)
                bio.name = "broadcast.jpg"
                cap = f"📢 *Japan Auction Car*\n\n{caption_text}" if caption_text else "📢 *Japan Auction Car*"
                await context.bot.send_photo(
                    chat_id=int(uid),
                    photo=bio,
                    caption=cap,
                    parse_mode="Markdown")
                success += 1
                await asyncio.sleep(0.3)
            except Exception as e:
                logger.error(f"broadcast photo {uid}: {e}")
                failed += 1

        await update.message.reply_text(
            f"✅ *Broadcast ပုံ ပြီးပြီ*\n\n✅ အောင်မြင်: {success} ယောက်\n❌ မရောက်: {failed} ယောက်",
            parse_mode="Markdown")
        return

    # ── Fast Track Deposit Slip ──
    if str(user_id) in fasttrack_pending and fasttrack_pending[str(user_id)].get("waiting_slip"):
        await update.message.reply_text("🔍 Deposit Slip ဖတ်နေတယ်... ⏳")
        try:
            file       = await photo.get_file()
            file_bytes = bytes(await file.download_as_bytearray())
            slip_info  = await gemini_read_slip(file_bytes)
        except Exception as e:
            logger.error(f"fasttrack slip: {e}")
            slip_info = {}
        amount   = slip_info.get("AMOUNT",         "UNKNOWN")
        pay_type = slip_info.get("TYPE",            "UNKNOWN")
        txn_no   = slip_info.get("TRANSACTION_NO", "UNKNOWN")
        date_str = slip_info.get("DATE",            "UNKNOWN")
        amount_ok = ""
        if amount != "UNKNOWN":
            try:
                amt_num = int(re.sub(r'[^\d]', '', amount))
                amount_ok = "✅" if amt_num >= 20000 else "⚠️ မပြည့်မီ (฿20,000 လိုသည်)"
            except:
                amount_ok = "⚠️ စစ်မရ"
        fasttrack_pending[str(user_id)]["slip_info"]    = slip_info
        fasttrack_pending[str(user_id)]["waiting_slip"] = False
        name = update.effective_user.first_name or str(user_id)
        admin_text = (
            f"⚡ *Fast Track Deposit Slip*\n\n"
            f"👤 {name} (`{user_id}`)\n"
            f"🏦 Type: {pay_type}\n"
            f"🔢 Txn: `{txn_no}`\n"
            f"💵 Amount: {amount} ฿ {amount_ok}\n"
            f"📅 Date: {date_str}\n\n"
            f"Confirm → Auction Q&A စတင်မည်"
        )
        admin_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"💬 {name}", url=f"tg://user?id={user_id}")],
            [InlineKeyboardButton("✅ Confirm", callback_data=f"ftdep_ok_{user_id}"),
             InlineKeyboardButton("❌ Reject",  callback_data=f"ftdep_no_{user_id}")],
        ])
        await notify_admins(context, admin_text, reply_markup=admin_kb)
        await update.message.reply_text(
            "✅ *Slip လက်ခံပြီ!*\n\nAdmin စစ်ဆေးနေသည် — ခဏစောင့်ပါ 🙏",
            parse_mode='Markdown')
        return

    if str(user_id) in pending_deposit:
        dep_data = pending_deposit[str(user_id)]
        if dep_data.get("step") == "waiting_slip":
            await update.message.reply_text("🔍 Deposit Slip ဖတ်နေတယ်... ⏳")
            try:
                file       = await photo.get_file()
                file_bytes = bytes(await file.download_as_bytearray())
                slip_info  = await gemini_read_slip(file_bytes)
            except Exception as e:
                logger.error(f"deposit slip read: {e}")
                slip_info = {}

            amount   = slip_info.get("AMOUNT", "UNKNOWN")
            pay_type = slip_info.get("TYPE", "UNKNOWN")
            txn_no   = slip_info.get("TRANSACTION_NO", "UNKNOWN")
            date_str = slip_info.get("DATE", "UNKNOWN")

            amount_ok = ""
            if amount != "UNKNOWN":
                try:
                    amt_num = int(re.sub(r'[^\d]', '', amount))
                    if amt_num >= 20000:
                        amount_ok = "✅"
                    else:
                        amount_ok = "⚠️ မပြည့်မီ (฿20,000 လိုသည်)"
                except:
                    amount_ok = "⚠️ စစ်မရ"

            pending_deposit[str(user_id)]["slip_info"] = slip_info

            req_id       = dep_data.get("reqId", "")
            broker_tg_id = dep_data.get("brokerTgId", "")
            name         = update.effective_user.first_name or str(user_id)

            admin_text = (
                f"💰 *Deposit Slip အသစ်*\n\n"
                f"👤 {name} (`{user_id}`)\n"
                f"🆔 Request: `{req_id}`\n\n"
                f"🏦 Type: {pay_type}\n"
                f"🔢 Txn No: `{txn_no}`\n"
                f"💵 Amount: {amount} ฿ {amount_ok}\n"
                f"📅 Date: {date_str}\n\n"
                f"⚠️ စစ်ဆေးပြီးမှ Confirm လုပ်ပါ"
            )
            admin_kb = InlineKeyboardMarkup([
                [InlineKeyboardButton(f"💬 {name} ကို Message", url=f"tg://user?id={user_id}")],
                [InlineKeyboardButton("✅ Confirm", callback_data=f"dep_ok_{user_id}"),
                 InlineKeyboardButton("❌ Reject",  callback_data=f"dep_no_{user_id}")],
            ])
            await notify_admins(context, admin_text, reply_markup=admin_kb)
            await update.message.reply_text(
                "✅ *Deposit Slip လက်ခံပြီ!*\n\n"
                "Admin စစ်ဆေးနေသည် — ခဏစောင့်ပါ 🙏",
                parse_mode='Markdown')
            return

    # ── Photo Relay Mode (Proxy Chat) ──
    str_uid = str(user_id)
    cust_session_photo = next(
        ((sid, s) for sid, s in proxy_sessions.items()
         if str(s.get("customerId","")) == str_uid and s.get("status") == "ACTIVE"),
        None
    )
    broker_session_photo = next(
        ((sid, s) for sid, s in proxy_sessions.items()
         if str(s.get("brokerId","")) == str_uid and s.get("status") == "ACTIVE"),
        None
    )

    if cust_session_photo or broker_session_photo:
        if cust_session_photo:
            _sid_chk, _sess_chk = cust_session_photo
            _rid_chk = _sess_chk.get("reqId", "")
            if _rid_chk.startswith("A") and not _sess_chk.get("deposit_paid", False):
                return

        if caption:
            blocked, reason = proxy_filter(caption)
            if blocked:
                await update.message.reply_text(
                    f"⚠️ *Photo Block ဖြစ်သွားတယ်*\n\n"
                    f"❌ Caption မှာ {reason}\n"
                    f"Caption ဖြုတ်ပြီး ပြန်ပို့ပါ",
                    parse_mode='Markdown')
                return

        try:
            file       = await photo.get_file()
            file_bytes = bytes(await file.download_as_bytearray())
        except Exception as e:
            logger.error(f"photo relay download: {e}")
            await update.message.reply_text("❌ ပုံ download မရဘူး")
            return

        relay_image_url = ""
        if all([CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET]):
            session_id = cust_session_photo[0] if cust_session_photo else broker_session_photo[0]
            relay_image_url = await upload_to_cloudinary(file_bytes, f"relay_{session_id}_{int(datetime.now().timestamp())}")

        from io import BytesIO

        if cust_session_photo:
            sid, session    = cust_session_photo
            broker_tg_id    = session.get("brokerId")
            req_id          = session.get("reqId", sid)
            cap_text        = f"📷 *Customer #{req_id}:*\n\n{caption}" if caption else f"📷 *Customer #{req_id}*"
            if broker_tg_id:
                try:
                    bio = BytesIO(file_bytes); bio.name = "photo.jpg"
                    await context.bot.send_photo(
                        chat_id=int(broker_tg_id),
                        photo=bio,
                        caption=cap_text,
                        parse_mode='Markdown')
                    await update.message.reply_text("✅ ပုံ ပို့ပြီ")
                except Exception as e:
                    logger.error(f"photo relay C→B: {e}")
                    await update.message.reply_text("❌ Broker ကို မပို့နိုင်ဘူး")
            return

        if broker_session_photo:
            sid, session    = broker_session_photo
            customer_id     = session.get("customerId")
            broker_obj      = session.get("brokerObj", {})
            broker_id       = broker_obj.get("brokerId", "B???")
            req_id          = session.get("reqId", sid)
            cap_text        = f"📷 *Broker #{broker_id}:*\n\n{caption}" if caption else f"📷 *Broker #{broker_id}*"
            if customer_id:
                try:
                    bio = BytesIO(file_bytes); bio.name = "photo.jpg"
                    await context.bot.send_photo(
                        chat_id=int(customer_id),
                        photo=bio,
                        caption=cap_text,
                        parse_mode='Markdown')
                    await update.message.reply_text("✅ ပုံ ပို့ပြီ")
                except Exception as e:
                    logger.error(f"photo relay B→C: {e}")
                    await update.message.reply_text("❌ Customer ကို မပို့နိုင်ဘူး")
            return

    # ── Payment Slip Mode ──
    if user_id in pending_payment:
        pay_data = pending_payment[user_id]
        if pay_data.get("waiting_slip"):
            await update.message.reply_text("🔍 Payment Slip ဖတ်နေတယ်... ⏳")
            try:
                file       = await photo.get_file()
                file_bytes = bytes(await file.download_as_bytearray())
                slip_info  = await gemini_read_slip(file_bytes)
            except Exception as e:
                logger.error(f"Slip read: {e}")
                slip_info = {}

            amount      = slip_info.get("AMOUNT", "UNKNOWN")
            date_str    = slip_info.get("DATE", "UNKNOWN")
            time_str    = slip_info.get("TIME", "UNKNOWN")
            pay_type    = slip_info.get("TYPE", "UNKNOWN")
            reference   = slip_info.get("TRANSACTION_NO", slip_info.get("REFERENCE", "UNKNOWN"))
            sender      = slip_info.get("SENDER", "UNKNOWN")
            transfer_to = slip_info.get("TRANSFER_TO", "UNKNOWN")
            ADMIN_REAL_NAME = os.environ.get("ADMIN_REAL_NAME", "Kyaw Min Tun")
            receiver_ok = ""
            if pay_type == "KPay" and transfer_to != "UNKNOWN":
                if ADMIN_REAL_NAME.lower() in transfer_to.lower():
                    receiver_ok = "✅"
                else:
                    receiver_ok = "⚠️ Admin နာမည် မဟုတ်ဘူး!"

            expected  = pay_data.get("amount", 0)
            amount_ok = ""
            if amount != "UNKNOWN":
                try:
                    amt_num = int(re.sub(r'[^\d]', '', amount))
                    if amt_num >= expected:
                        amount_ok = "✅"
                    else:
                        amount_ok = f"⚠️ မပြည့်မီ (လိုအပ်: {expected:,} ks)"
                except:
                    amount_ok = "⚠️ စစ်မရ"
            else:
                amount_ok = "⚠️ ဖတ်မရ"

            pending_payment[user_id]["slip_info"] = slip_info
            pending_payment[user_id]["file_bytes"] = file_bytes

            pkg_name  = PLAN_NAMES.get(pay_data.get("package","CH"), "Unknown")
            months    = pay_data.get("months", 1)
            name      = pay_data.get("name", "Unknown")
            username  = pay_data.get("username", str(user_id))
            chosen_method = pay_data.get("method", "")
            method_label  = PAYMENT_METHOD_INFO.get(chosen_method, {}).get("label", chosen_method.upper() if chosen_method else "—")

            txn_label = "Transaction ID" if pay_type == "Wave" else "Transaction No"
            admin_text = (
                f"💰 *Payment Slip အသစ်*\n\n"
                f"👤 {name} ({username})\n"
                f"🆔 ID: `{user_id}`\n"
                f"📦 Package: {pkg_name} — {months} လ\n"
                f"🎯 ရွေးခဲ့သော method: {method_label}\n"
                f"💵 Expected: {expected:,} ks\n\n"
                f"📋 *Slip အချက်အလက်:*\n"
                f"🏦 Type: {pay_type}\n"
                f"🔢 {txn_label}: `{reference}`\n"
                f"💵 Amount: {amount} ks {amount_ok}\n"
                f"📅 Date: {date_str} {time_str}\n"
                + (f"📨 Transfer To: {transfer_to} {receiver_ok}\n" if pay_type == "KPay" else f"👤 Sender: {sender}\n")
                + f"\n⚠️ {pay_type} app မှာ `{reference}` စစ်ပြီးမှ Confirm လုပ်ပါ"
            )
            admin_kb = InlineKeyboardMarkup([
                [InlineKeyboardButton(f"💬 {name} ကို Message ပို့", url=f"tg://user?id={user_id}")],
                [InlineKeyboardButton("✅ Confirm", callback_data=f"slip_confirm_{user_id}"),
                 InlineKeyboardButton("❌ Reject",  callback_data=f"slip_no_{user_id}")],
            ])
            await notify_admins(context, admin_text, reply_markup=admin_kb)
            await update.message.reply_text(
                "✅ *Slip လက်ခံရပြီ!*\n\n"
                "Admin မှ စစ်ဆေးနေသည် — ခဏစောင့်ပါ 🙏\n"
                "မကြာမီ Password DM ပို့ပေးမည်",
                parse_mode='Markdown')
            return

    # ── Auction List Mode ──
    if "list" in caption:
        cap_lower = caption.lower()
        caption_klang9 = any(k in cap_lower for k in ["klang9","klang 9","klang","9.2"])
        caption_maesot = any(k in cap_lower for k in ["maesot","mae sot","measot"])
        await update.message.reply_text(f"📋 Auction List ဖတ်နေတယ်... ⏳")
        try:
            file       = await photo.get_file()
            file_bytes = bytes(await file.download_as_bytearray())
            new_cars, detected_loc = await gemini_ocr_auction_list(file_bytes)
        except Exception as e:
            logger.error(f"Auction list: {e}"); new_cars = []; detected_loc = None

        cap_border44 = any(k in cap_lower for k in ["border44","border 44","44gate","44 gate","best border","border-44"])

        if detected_loc in ("Klang9", "MaeSot", "Border44"):
            import_loc = detected_loc
        elif caption_klang9:
            import_loc = "Klang9"
        elif cap_border44:
            import_loc = "Border44"
        elif caption_maesot:
            import_loc = "MaeSot"
        else:
            await update.message.reply_text(
                "⚠️ *Location မသိပါ!*\n\n"
                "Caption မှာ location ထည့်ပြီး ပြန်တင်ပါ:\n"
                "• `klang9 list` → Klang9 Freezone\n"
                "• `maesot list` → MaeSot Freezone\n"
                "• `border44 list` → Best Border-44 Gate\n\n"
                "💡 List ပုံရဲ့ Header ကိုလည်း Gemini ဖတ်ပေးနိုင်တယ်",
                parse_mode='Markdown')
            return

        if import_loc == "Klang9": loc_name = LOC_KLANG9
        elif import_loc == "Border44": loc_name = LOC_BORDER44
        else: loc_name = LOC_MAESOT
        await update.message.reply_text(f"📍 Location: *{loc_name}*", parse_mode='Markdown')

        if not new_cars:
            await update.message.reply_text("⚠️ List ဖတ်မရပါ\n💡 Gemini API limit ကုန်နိုင်တယ်")
            return

        existing = {c["chassis"].upper() for c in CARS}
        added    = []
        unknown  = []

        for car in new_cars:
            ch    = str(car.get("chassis","")).upper().strip()
            model = str(car.get("model","")).strip()
            color = str(car.get("color","")).strip()
            year  = int(car.get("year",0) or 0)
            if not ch:
                continue
            missing_fields = []
            if not model or model.upper() in ("", "UNKNOWN", "N/A"):
                missing_fields.append("Model")
                model = guess_model_from_chassis(ch)
            if not color or color in ("", "-", "N/A"):
                missing_fields.append("Color")
                color = "-"
            if not year:
                missing_fields.append("Year")
            if ch not in existing:
                CARS.append({"chassis":ch,"model":model,"color":color,"year":year,"loc":import_loc})
                existing.add(ch)
                added.append(ch)
            if missing_fields:
                unknown.append({"chassis":ch,"model":model,"missing":missing_fields})

        txt = f"✅ *{loc_name} List Update ပြီး!*\n\n📊 ဖတ်ရ: {len(new_cars)} စီး\n✨ အသစ်: {len(added)} စီး\n"
        if added:
            txt += "\n🆕 " + "".join(f"`{ch}`\n" for ch in added[:10])
            if len(added) > 10:
                txt += f"... {len(added)-10} စီး ထပ်ရှိ\n"
        if unknown:
            txt += f"\n⚠️ *မသေချာ ({len(unknown)} စီး):*\n"
            for u in unknown[:5]:
                txt += f"• `{u['chassis']}` ({u['model']}) — မရ: *{', '.join(u['missing'])}*\n"
            if len(unknown) > 5:
                txt += f"... {len(unknown)-5} စီး ထပ်ရှိ\n"
        txt += f"\n📋 Database: {await get_sheet_car_count()} စီး"
        await update.message.reply_text(txt, parse_mode='Markdown')
        return

    # ── Car Photo Mode ──
    await update.message.reply_text("🔍 Chassis ရှာနေတယ်... ⏳")

    chassis      = extract_chassis_from_text(caption) if caption else None
    price_match  = re.search(r'(?<![A-Z0-9])(\d{4,6})(?![A-Z0-9])', caption.upper()) if caption else None
    price        = int(price_match.group(1)) if price_match else None
    gemini_model = ""; gemini_color = ""; gemini_year = 0; file_bytes = None

    if caption and chassis:
        cap_work = caption.upper()
        cap_work = re.sub(re.escape(chassis.upper()), '', cap_work)
        if price_match:
            cap_work = re.sub(r'(?<![A-Z0-9])' + re.escape(price_match.group(1)) + r'(?![A-Z0-9])', '', cap_work)
        cap_work = cap_work.strip()
        year_m = re.search(r'\b(19|20)\d{2}\b', cap_work)
        if year_m:
            gemini_year = int(year_m.group())
            cap_work = cap_work.replace(year_m.group(), '').strip()
        KNOWN_COLORS = ["PEARL WHITE","DARK BLUE","LIGHT BLUE","LIGHT GREEN",
                        "WHITE","BLACK","SILVER","RED","BLUE","GREEN","YELLOW",
                        "BROWN","ORANGE","GREY","GRAY","GOLD","PURPLE","MAROON"]
        for col in KNOWN_COLORS:
            if col in cap_work:
                gemini_color = col
                cap_work = cap_work.replace(col, '').strip()
                break
        cap_model = re.sub(r'[^A-Z0-9 ]', '', cap_work).strip()
        if cap_model and len(cap_model) >= 2:
            gemini_model = cap_model

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

    if car:
        car_loc = loc_display(car.get('loc', 'MaeSot'))
    else:
        sheet_loc = None
        if chassis and SHEET_WEBHOOK:
            try:
                async with httpx.AsyncClient(follow_redirects=True) as client:
                    resp = await client.get(
                        f"https://docs.google.com/spreadsheets/d/{os.environ.get('SHEET_ID','')}/gviz/tq?tqx=out:json&sheet=Sheet1",
                        timeout=8)
                raw = resp.text
                import json as _json
                data = _json.loads(raw[raw.index('{'):raw.rindex('}')+1])
                rows = data.get('table',{}).get('rows',[])
                for row in rows:
                    c = row.get('c',[])
                    if len(c) > 1:
                        ch_val = (c[1].get('v','') or '') if c[1] else ''
                        if str(ch_val).upper().strip() == chassis.upper().strip():
                            loc_val = (c[6].get('v','') or '') if len(c) > 6 and c[6] else ''
                            if loc_val:
                                sheet_loc = str(loc_val)
                            break
            except Exception as e:
                logger.error(f"sheet loc lookup: {e}")

        if sheet_loc:
            car_loc = loc_display(sheet_loc)
        else:
            cap_l = (caption or "").lower()
            if any(k in cap_l for k in ["klang9","klang 9","klang","9.2"]):
                car_loc = LOC_KLANG9
            elif any(k in cap_l for k in ["border44","border 44","44gate","44 gate","best border","border-44"]):
                car_loc = LOC_BORDER44
            else:
                car_loc = LOC_MAESOT

    final_model = gemini_model if gemini_model and gemini_model not in ("","UNKNOWN") else (car['model'] if car else guess_model_from_chassis(chassis or ""))
    final_color = gemini_color if gemini_color and gemini_color != "-" else (car['color'] if car else "-")
    final_year  = gemini_year  if gemini_year  else (car.get('year', 0) if car else 0)
    final_chassis = chassis or ""

    missing = []
    if not final_chassis:                                          missing.append("Chassis")
    if not final_model or final_model == "UNKNOWN":               missing.append("Model")
    if not final_color or final_color == "-":                     missing.append("Color")
    if not final_year:                                            missing.append("Year")

    if final_chassis and price:
        pending_photo[user_id] = {
            "user_id":   user_id,
            "chassis":   final_chassis,
            "model":     final_model,
            "color":     final_color,
            "year":      final_year,
            "price":     price,
            "loc":       car_loc,
            "image_url": image_url,
        }
        warn = f"\n⚠️ မသေချာ: *{', '.join(missing)}*\n" if missing else ""
        field_labels = {"Model":"🚗 Model","Color":"🎨 Color","Year":"📅 Year"}
        fill_btns = [InlineKeyboardButton(f"✏️ {field_labels.get(f,f)} ဖြည့်",
                     callback_data=f"fill_{user_id}_{f.lower()}") for f in missing if f != "Chassis"]
        loc_row = [
            InlineKeyboardButton(f"{'✅' if car_loc == LOC_MAESOT else '📍'} MaeSot",    callback_data=f"setloc_{user_id}_MaeSot"),
            InlineKeyboardButton(f"{'✅' if car_loc == LOC_KLANG9 else '📍'} Klang9",    callback_data=f"setloc_{user_id}_Klang9"),
            InlineKeyboardButton(f"{'✅' if car_loc == LOC_BORDER44 else '📍'} Border44", callback_data=f"setloc_{user_id}_Border44"),
        ]
        rows = []
        if fill_btns:
            rows.append(fill_btns)
        rows.append(loc_row)
        rows.append([
            InlineKeyboardButton("✅ Save",    callback_data=f"cs_{user_id}"),
            InlineKeyboardButton("❌ Cancel",  callback_data=f"cc_{user_id}"),
        ])
        kb = InlineKeyboardMarkup(rows)
        await update.message.reply_text(
            f"⚠️ *စစ်ဆေးပါ — မှန်ကန်ပါသလား?*\n\n"
            f"🚗 *{final_model}* ({ys(final_year)})\n"
            f"🔑 `{final_chassis}`\n🎨 {final_color}\n📍 {car_loc}\n💰 ฿{price:,}\n"
            f"{warn}",
            parse_mode='Markdown', reply_markup=kb)
    elif final_chassis:
        pending_photo[user_id] = {
            "user_id":user_id,"chassis":final_chassis,"model":final_model,
            "color":final_color,"year":final_year,"price":None,"loc":car_loc,"image_url":image_url,
        }
        warn = f"\n⚠️ မသေချာ: *{', '.join(missing)}*\n" if missing else ""
        loc_row2 = [
            InlineKeyboardButton(f"{'✅' if car_loc == LOC_MAESOT else '📍'} MaeSot",    callback_data=f"setloc_{user_id}_MaeSot"),
            InlineKeyboardButton(f"{'✅' if car_loc == LOC_KLANG9 else '📍'} Klang9",    callback_data=f"setloc_{user_id}_Klang9"),
            InlineKeyboardButton(f"{'✅' if car_loc == LOC_BORDER44 else '📍'} Border44", callback_data=f"setloc_{user_id}_Border44"),
        ]
        await update.message.reply_text(
            f"🚗 *{final_model}* ({ys(final_year)})\n🔑 `{final_chassis}`\n"
            f"🎨 {final_color}\n📍 {car_loc}\n{warn}\n💰 ဈေး ရိုက်ထည့်ပါ:\nဥပမာ: `150000`",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([loc_row2]))
    elif chassis:
        guessed = gemini_model or guess_model_from_chassis(chassis)
        if not guessed or guessed == "UNKNOWN":
            guessed = guess_model_from_chassis(chassis)
        display_color = final_color if final_color and final_color != "-" else (gemini_color or "-")
        display_year  = final_year or gemini_year or 0
        if price:
            pending_photo[user_id] = {
                "user_id":user_id,"chassis":chassis,"model":guessed,
                "color":display_color,"year":display_year,"price":price,"loc":LOC_MAESOT,"image_url":image_url,
            }
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ မှန်တယ် Save",    callback_data=f"cs_{user_id}"),
                InlineKeyboardButton("❌ မှားတယ် Cancel", callback_data=f"cc_{user_id}"),
            ]])
            await update.message.reply_text(
                f"⚠️ *Checklist မှာ မပါဘူး*\n\n🚗 ခန့်မှန်း: *{guessed}* ({ys(display_year)})\n"
                f"🔑 `{chassis}`\n🎨 {display_color}\n💰 ฿{price:,}\n\n"
                f"✅ မှန်ရင် *Save* နှိပ်ပါ",
                parse_mode='Markdown', reply_markup=kb)
        else:
            pending_photo[user_id] = {
                "user_id":user_id,"chassis":chassis,"model":guessed,
                "color":display_color,"year":display_year,"price":None,"loc":LOC_MAESOT,"image_url":image_url,
            }
            msg = (f"⚠️ Checklist မှာ မပါဘူး\n\n🚗 ခန့်မှန်း: *{guessed}* ({ys(display_year)})\n"
                   f"🔑 `{chassis}`\n🎨 {display_color}\n\n💰 ဈေး ရိုက်ထည့်ပါ:\nဥပမာ: `150000`"
                   if guessed and guessed != "UNKNOWN"
                   else f"⚠️ Chassis: `{chassis}`\nChecklist မှာ မပါဘူး — ဈေး ထည့်ပါ:\nဥပမာ: `150000`")
            await update.message.reply_text(msg, parse_mode='Markdown')
    else:
        await update.message.reply_text(
            "⚠️ Chassis ဖတ်မရပါ\nကိုယ်တိုင် ထည့်ပါ:\n`/price [chassis] [ဈေး]`", parse_mode='Markdown')

# ── Proxy Chat Filter ─────────────────────────────────
def proxy_filter(text: str):
    mm_digits = str.maketrans('၀၁၂၃၄၅၆၇၈၉', '0123456789')
    normalized = text.translate(mm_digits)
    digits_only = re.sub(r'[\s\-\.]', '', normalized)
    if re.search(r'\+?0?[6-9]\d{7,11}', digits_only):
        return True, "ဖုန်းနံပါတ် ပေးပို့ခြင်း တားမြစ်ထားသည်"
    if re.search(r'0\s*9[\d\s]{8,}', normalized):
        return True, "ဖုန်းနံပါတ် ပေးပို့ခြင်း တားမြစ်ထားသည်"
    if re.search(r'@[a-zA-Z0-9_]{4,}', text):
        return True, "Telegram Username ပေးပို့ခြင်း တားမြစ်ထားသည်"
    if re.search(r'(https?://|www\.|t\.me/|wa\.me/|line\.me/)', text, re.IGNORECASE):
        return True, "Link ပေးပို့ခြင်း တားမြစ်ထားသည်"
    if re.search(r'facebook\.com|fb\.com|fb\.me|instagram\.com|tiktok\.com', text, re.IGNORECASE):
        return True, "Social Media link ပေးပို့ခြင်း တားမြစ်ထားသည်"
    if re.search(r'\b(line\s?id|viber|whatsapp|zalo)\b', text, re.IGNORECASE):
        return True, "Contact info ပေးပို့ခြင်း တားမြစ်ထားသည်"
    if re.search(r'တိုက်နံပါတ်|အခန်းနံပါတ်|ရပ်ကွက်|မြို့နယ်|တိုင်းဒေသ|ပြည်နယ်|နေရပ်လိပ်စာ|နေထိုင်ရာ', text):
        return True, "လိပ်စာ ပေးပို့ခြင်း တားမြစ်ထားသည်"
    if re.search(r'\b(street|road|lane|avenue|st\.|address|district|township|quarter)\b', text, re.IGNORECASE):
        return True, "လိပ်စာ ပေးပို့ခြင်း တားမြစ်ထားသည်"
    return False, ""

# ── handle_text ──────────────────────────────────────
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text    = update.message.text.strip()

    str_uid = str(user_id)

    if "JAN Broker T&C သဘောတူပါသည်" in text:
        brokers = await get_brokers()
        broker  = next((b for b in brokers if b.get("telegramId") == str_uid), None)
        if broker:
            if broker.get("status") == "KICKED":
                await update.message.reply_text("🚫 Account ပိတ်သိမ်းထားပြီ — Admin ကို ဆက်သွယ်ပါ")
                return
            await update_broker(str_uid, status="FREE")
            await update.message.reply_text(
                f"✅ *T&C လက်ခံပြီ!*\n\n"
                f"🆔 Broker #{broker['brokerId']}\n"
                f"🟢 Status: FREE — Request လက်ခံနိုင်ပြီ\n\n"
                f"Available ဖြစ်ကြောင်း: /available\n"
                f"Busy ဖြစ်ရင်: /busy\n"
                f"Request လက်ခံရန်: `/accept [ReqID]`",
                parse_mode='Markdown')
            await notify_admins(context,
                f"✅ *Broker T&C လက်ခံပြီ*\n\n"
                f"👤 @{update.effective_user.username or str_uid}\n"
                f"🆔 #{broker['brokerId']}\n"
                f"🟢 Status: FREE")
        else:
            await update.message.reply_text("❌ Broker အဖြစ် မှတ်ပုံမတင်ရသေးဘူး — Admin ကို ဆက်သွယ်ပါ")
        return

    cust_session = next(
        ((sid, s) for sid, s in proxy_sessions.items()
         if str(s.get("customerId","")) == str_uid and s.get("status") == "ACTIVE"),
        None
    )
    broker_session = next(
        ((sid, s) for sid, s in proxy_sessions.items()
         if str(s.get("brokerId","")) == str_uid and s.get("status") == "ACTIVE"),
        None
    )

    if cust_session:
        sid, session = cust_session
        broker_tg_id = session.get("brokerId")
        req_id_c = session.get("reqId", "")

        if req_id_c.startswith("A") and not session.get("deposit_paid", False):
            return

        blocked, reason = proxy_filter(text)
        if blocked:
            await update.message.reply_text(
                f"⚠️ *Message Block ဖြစ်သွားတယ်*\n\n❌ {reason}\nBot ထဲမှာပဲ ဆက်သွယ်ရမည်",
                parse_mode='Markdown')
            return
        if broker_tg_id:
            try:
                req_id_c = session.get("reqId", "")
                close_kb = InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔚 Close Chat", callback_data=f"closechat_{req_id_c}_customer")
                ]])
                await context.bot.send_message(
                    chat_id=int(broker_tg_id),
                    text=f"💬 *Customer #{req_id_c}:*\n\n{text}",
                    parse_mode='Markdown')
                await update.message.reply_text(
                    "✅ ပို့ပြီ",
                    reply_markup=close_kb)
            except Exception as e:
                logger.error(f"proxy relay C→B: {e}")
                await update.message.reply_text("❌ Broker ကို မပို့နိုင်ဘူး")
        return

    if broker_session:
        sid, session = broker_session
        customer_id = session.get("customerId")
        blocked, reason = proxy_filter(text)
        if blocked:
            await update.message.reply_text(
                f"⚠️ *Message Block ဖြစ်သွားတယ်*\n\n❌ {reason}\nBot ထဲမှာပဲ ဆက်သွယ်ရမည်",
                parse_mode='Markdown')
            return
        if customer_id:
            try:
                broker_obj  = session.get("brokerObj", {})
                broker_id   = broker_obj.get("brokerId", "B???")
                req_id_b    = session.get("reqId", "")
                close_kb_b  = InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔚 Close Chat", callback_data=f"closechat_{req_id_b}_broker")
                ]])
                await context.bot.send_message(
                    chat_id=int(customer_id),
                    text=f"💬 *Broker #{broker_id}:*\n\n{text}",
                    parse_mode='Markdown')
                await update.message.reply_text(
                    "✅ ပို့ပြီ",
                    reply_markup=close_kb_b)
            except Exception as e:
                logger.error(f"proxy relay B→C: {e}")
                await update.message.reply_text("❌ Customer ကို မပို့နိုင်ဘူး")
        return

    if user_id in pending_request:
        handled = await handle_request_qa(update, context)
        if handled: return

    if user_id in pending_edit:
        edit    = pending_edit.pop(user_id)
        chassis = edit["chassis"]
        field   = edit["field"]

        if chassis == "__photo__":
            photo_uid = edit.get("photo_uid", user_id)
            if photo_uid not in pending_photo:
                await update.message.reply_text("❌ Data ကုန်သွားပြီ — ပုံ ပြန်တင်ပါ")
                return
            pdata = pending_photo[photo_uid]
            val   = text.strip()
            if field == "year":
                try:
                    pdata["year"] = int(re.search(r"\d{4}", val).group())
                except:
                    await update.message.reply_text("❌ ဂဏန်းလေးလုံး ထည့်ပါ (ဥပမာ: `2013`)", parse_mode='Markdown')
                    pending_edit[user_id] = edit; return
            elif field == "color":
                pdata["color"] = val.upper()
            elif field == "model":
                pdata["model"] = val.upper()
            pending_photo[photo_uid] = pdata
            m2 = []
            if not pdata.get("model") or pdata["model"] == "UNKNOWN": m2.append("Model")
            if not pdata.get("color") or pdata["color"] == "-":       m2.append("Color")
            if not pdata.get("year"):                                   m2.append("Year")
            field_labels = {"Model":"🚗 Model","Color":"🎨 Color","Year":"📅 Year"}
            fill_btns = [InlineKeyboardButton(f"✏️ {field_labels.get(f,f)} ဖြည့်",
                         callback_data=f"fill_{photo_uid}_{f.lower()}") for f in m2]
            rows = []
            if fill_btns: rows.append(fill_btns)
            rows.append([
                InlineKeyboardButton("✅ Save",   callback_data=f"cs_{photo_uid}"),
                InlineKeyboardButton("❌ Cancel", callback_data=f"cc_{photo_uid}"),
            ])
            warn = f"\n⚠️ မသေချာ: *{', '.join(m2)}*\n" if m2 else ""
            await update.message.reply_text(
                f"⚠️ *စစ်ဆေးပါ*\n\n"
                f"🚗 *{pdata['model']}* ({ys(pdata.get('year',0))})\n"
                f"🔑 `{pdata['chassis']}`\n🎨 {pdata['color']}\n"
                f"📍 {pdata.get('loc','')}\n💰 ฿{pdata['price']:,}\n{warn}",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(rows))
            return

        car = find_by_chassis(chassis)
        if not car:
            await update.message.reply_text(f"❌ `{chassis}` မတွေ့ပါ", parse_mode='Markdown')
            return

        if field == "price":
            try:
                new_val = int(text.replace(",","").replace(" ",""))
                display = f"฿{new_val:,}"
            except:
                await update.message.reply_text("❌ ဂဏန်းသက်သက်သာ ရိုက်ပါ\nဥပမာ: `150000`", parse_mode='Markdown')
                pending_edit[user_id] = edit
                return
        elif field == "color":
            new_val = text.upper().strip()
            display = new_val
        elif field == "model":
            new_val = text.upper().strip()
            display = new_val
        else:
            return

        for c in CARS:
            if c.get("chassis","").upper() == chassis.upper():
                c[field] = new_val
                break

        if SHEET_WEBHOOK:
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.post(SHEET_WEBHOOK, json={
                        "action": "updateCar",
                        "chassis": chassis,
                        "field": field,
                        "value": str(new_val),
                    }, timeout=10, follow_redirects=True)
            except Exception as e:
                logger.error(f"updateCar webhook: {e}")

        await update.message.reply_text(
            f"✅ *{chassis}* ပြင်ပြီး\n📝 {field.upper()}: *{display}*",
            parse_mode='Markdown')
        return

    if user_id in pending_photo:
        data = pending_photo[user_id]
        if data.get('price') is None and re.match(r'^[\d,]+$', text.replace(' ','')):
            try:
                price            = int(text.replace(',','').replace(' ',''))
                data['price']    = price
                pending_photo[user_id] = data
                kb = InlineKeyboardMarkup([[
                    InlineKeyboardButton("✅ မှန်တယ် Save",    callback_data=f"cs_{user_id}"),
                    InlineKeyboardButton("❌ မှားတယ် Cancel", callback_data=f"cc_{user_id}"),
                ]])
                await update.message.reply_text(
                    f"⚠️ *စစ်ဆေးပါ — မှန်ကန်ပါသလား?*\n\n"
                    f"🚗 *{data['model']}* ({ys(data.get('year',0))})\n"
                    f"🔑 `{data['chassis']}`\n🎨 {data['color']}\n📍 {data['loc']}\n💰 ฿{price:,}\n\n"
                    f"✅ မှန်ရင် *Save* နှိပ်ပါ\n❌ မှားရင် *Cancel* နှိပ်ပါ",
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
    data  = query.data

    # ── 🚗 Buying Car 10 Day Promo ──
    if data.startswith("buying_car_"):
        uid_str  = data.replace("buying_car_", "")
        caller   = str(query.from_user.id)
        if caller != uid_str:
            await query.answer("❌ သင့် button မဟုတ်ဘူး", show_alert=True)
            return
        user_id_int = int(uid_str)
        username    = query.from_user.username or query.from_user.first_name or "Unknown"

        promo_info = await check_promo10d_eligibility(uid_str)
        if not promo_info.get("eligible") or promo_info.get("active"):
            await query.answer("❌ Promo မရနိုင်ပါ", show_alert=True)
            return

        ok = await activate_promo10d(context, user_id_int, username)
        if not ok:
            await query.edit_message_text("❌ Promo activate မဖြစ်ဘူး — Admin ကို ဆက်သွယ်ပါ")
            return

        expire_date = (datetime.now() + timedelta(days=10)).strftime("%d/%m/%Y")

        try:
            invite = await context.bot.create_chat_invite_link(
                chat_id=int(CHANNEL_ID),
                member_limit=1,
                expire_date=int((datetime.now() + timedelta(days=10)).timestamp()))
            invite_url = invite.invite_link
        except Exception as e:
            logger.error(f"promo10d invite: {e}")
            invite_url = ""

        msg = (f"🎉 *10 Day Free Promo ရပြီ!*\n\n"
               f"⏳ ကုန်ဆုံးရက်: `{expire_date}`\n\n"
               f"✅ ခွင့်ပြုချက်:\n"
               f"• ကားဈေးကြည့်ရန်\n"
               f"• Broker နှင့် ဆက်သွယ်ရန်\n"
               f"• /carrequest (၂ ကြိမ်သာ)\n\n"
               f"⚠️ 10 ရက်အတွင်း Order မတင်ပါက Kick ခံရမည်\n\n")
        kb_rows = []
        if invite_url:
            kb_rows.append([InlineKeyboardButton("📢 Channel ဝင်ရန်", url=invite_url)])
        kb_rows.append([InlineKeyboardButton("🚗 ကားတောင်းဆိုရန်", callback_data=f"reqtype_auction_{uid_str}")])

        await query.edit_message_text(msg, parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(kb_rows))

        await notify_admins(context,
            f"🎁 *10 Day Promo အသစ်*\n\n"
            f"👤 @{username} (ID: `{uid_str}`)\n"
            f"⏳ ကုန်ဆုံးရက်: {expire_date}")
        return

    # ── 🔚 Close Chat Button ──
    if data.startswith("closechat_"):
        parts    = data.split("_")
        req_id   = parts[1]
        who      = parts[2] if len(parts) > 2 else "unknown"
        session  = proxy_sessions.get(req_id)
        if not session:
            await query.answer("❌ Session မတွေ့ပါ — ပြီးသွားပြီ ဖြစ်နိုင်တယ်", show_alert=True)
            return

        broker_tg_id  = session.get("brokerId")
        customer_id   = session.get("customerId")
        broker_obj    = session.get("brokerObj", {})
        broker_id_val = broker_obj.get("brokerId", "?")
        closer_id     = str(query.from_user.id)

        proxy_sessions.pop(req_id, None)
        new_broker_status = recalc_broker_status(broker_tg_id)
        await update_broker(broker_tg_id, status=new_broker_status)
        try:
            async with httpx.AsyncClient(follow_redirects=True) as client:
                await client.post(SHEET_WEBHOOK, json={
                    "action": "updateRequest",
                    "reqId":  req_id,
                    "status": "CLOSED",
                }, timeout=10)
        except Exception as e:
            logger.error(f"closechat updateRequest: {e}")

        who_label = "Customer" if who == "customer" else "Broker"
        await query.edit_message_text(
            f"🔚 *Chat ပိတ်ပြီ*\n\n🆔 `{req_id}`\n{who_label} မှ ပိတ်လိုက်သည်",
            parse_mode='Markdown')

        try:
            if who == "customer" and broker_tg_id:
                await context.bot.send_message(
                    chat_id=int(broker_tg_id),
                    text=f"🔚 *Chat ပိတ်ပြီ*\n\n🆔 `{req_id}`\nCustomer မှ Chat ပိတ်လိုက်သည်",
                    parse_mode='Markdown')
            elif who == "broker" and customer_id:
                await context.bot.send_message(
                    chat_id=int(customer_id),
                    text=f"🔚 *Chat ပိတ်ပြီ*\n\n🆔 `{req_id}`\nBroker မှ Chat ပိတ်လိုက်သည်",
                    parse_mode='Markdown')
        except Exception as e:
            logger.error(f"closechat notify: {e}")

        if customer_id:
            try:
                rating_kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton("⭐1", callback_data=f"rate_1_{req_id}"),
                     InlineKeyboardButton("⭐2", callback_data=f"rate_2_{req_id}"),
                     InlineKeyboardButton("⭐3", callback_data=f"rate_3_{req_id}")],
                    [InlineKeyboardButton("⭐4", callback_data=f"rate_4_{req_id}"),
                     InlineKeyboardButton("⭐5", callback_data=f"rate_5_{req_id}")],
                ])
                await context.bot.send_message(
                    chat_id=int(customer_id),
                    text=f"🌟 *Broker ကို Rate လုပ်ပေးပါ*\n\n"
                         f"🆔 Request: `{req_id}`\n\n"
                         f"⭐1 = ညံ့ | ⭐3 = ပုံမှန် | ⭐5 = အကောင်းဆုံး",
                    parse_mode='Markdown',
                    reply_markup=rating_kb)
                pending_rating[str(customer_id)] = {
                    "reqId":      req_id,
                    "brokerId":   broker_id_val,
                    "brokerTgId": broker_tg_id,
                }
            except Exception as e:
                logger.error(f"closechat rating: {e}")
        return

    # ── 📋 Report Form ──
    if data.startswith("report_"):
        parts      = data.split("_")
        report_type = parts[1]
        req_id     = "_".join(parts[2:])
        rater_id   = str(query.from_user.id)

        rate_info = pending_rating.get(rater_id, {})
        broker_tg_id  = rate_info.get("brokerTgId", "")
        broker_id_val = rate_info.get("brokerId", "?")

        if report_type == "ok":
            await query.edit_message_text(
                f"✅ *ကျေးဇူးတင်ပါသည်!*\n\n"
                f"🆔 `{req_id}`\n\n"
                f"Feedback ပေးသည့်အတွက် ကျေးဇူးတင်ပါသည် 🙏",
                parse_mode='Markdown')
            return

        report_labels = {
            "incomplete": "⚠️ လုပ်ငန်းမပြီးစုံ",
            "wrongcar":   "🚗 ကားမမှန်ကန်",
            "nosearch":   "❌ ကားမရှာပေ",
        }
        report_label = report_labels.get(report_type, report_type)

        await query.edit_message_text(
            f"📋 *Report တင်ပြီ*\n\n"
            f"🆔 `{req_id}`\n"
            f"အကြောင်းရင်း: {report_label}\n\n"
            f"Broker ကို 1 Month Temporary Ban ချမှတ်ပြီ",
            parse_mode='Markdown')

        if broker_tg_id:
            ban_until = (datetime.now() + timedelta(days=30)).strftime("%d/%m/%Y")
            await update_broker(broker_tg_id, status="BANNED")
            try:
                async with httpx.AsyncClient(follow_redirects=True) as client:
                    await client.post(SHEET_WEBHOOK, json={
                        "action":    "updateBroker",
                        "telegramId": broker_tg_id,
                        "status":    "TEMP_BAN",
                        "banUntil":  ban_until,
                    }, timeout=10)
            except Exception as e:
                logger.error(f"report temp ban: {e}")

            try:
                await context.bot.send_message(
                    chat_id=int(broker_tg_id),
                    text=f"🚨 *Report တင်ခံရပြီ*\n\n"
                         f"🆔 Request: `{req_id}`\n"
                         f"အကြောင်းရင်း: {report_label}\n\n"
                         f"⏳ 1 Month Temporary Ban ချမှတ်ခြင်းခံရပြီ\n"
                         f"(ကုန်ဆုံးရက်: {ban_until})\n\n"
                         f"မကျေနပ်ပါက သက်သေများ စုဆောင်းပြီး\n"
                         f"Admin ထံ Appeal တင်နိုင်ပါသည် 👇",
                    parse_mode='Markdown',
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("📩 Admin ကို Appeal တင်ရန်",
                                            url=f"https://t.me/{ADMIN_USERNAME}")
                    ]]))
            except Exception as e:
                logger.error(f"report broker notify: {e}")

        await notify_admins(context,
            f"🚨 *Broker Report တင်ခံရပြီ*\n\n"
            f"🆔 Request: `{req_id}`\n"
            f"👷 Broker: #{broker_id_val}\n"
            f"အကြောင်းရင်း: {report_label}\n"
            f"⏳ 1 Month Temp Ban ချမှတ်ပြီ")
        return

    # ── ✅ Customer T&C Agree / Disagree ──
    if data.startswith("cust_tc_agree_"):
        user_id_str = data.replace("cust_tc_agree_", "")
        if str(query.from_user.id) != user_id_str:
            await query.answer("❌ သင့် button မဟုတ်ဘူး", show_alert=True)
            return
        user_id_int = int(user_id_str)
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("🏆 လေလံဆွဲရန်", callback_data=f"reqtype_auction_{user_id_int}"),
            InlineKeyboardButton("🔍 ကားရှာရန်",   callback_data=f"reqtype_search_{user_id_int}"),
        ]])
        await query.edit_message_text(
            "✅ *သဘောတူပြီ!*\n\n"
            "🚗 *ကားဝန်ဆောင်မှု*\n\n"
            "🏆 *လေလံဆွဲရန်* — Auction ကားဝယ်ယူရန် (Deposit ฿20,000 လိုအပ်)\n"
            "🔍 *ကားရှာရန်* — ကားရှာဖွေပေးမည်\n\n"
            "ဝန်ဆောင်မှု ရွေးချယ်ပါ 👇",
            parse_mode='Markdown',
            reply_markup=kb)
        return

    if data.startswith("cust_tc_disagree_"):
        user_id_str = data.replace("cust_tc_disagree_", "")
        if str(query.from_user.id) != user_id_str:
            await query.answer("❌ သင့် button မဟုတ်ဘူး", show_alert=True)
            return
        await query.edit_message_text(
            "❌ *သဘောမတူဘူး*\n\n"
            "Customer T&C သဘောမတူသောကြောင့် ကားရှာ Service ဆက်လုပ်၍ မရပါ\n\n"
            "သဘောပြောင်းပါက /carrequest ထပ်နှိပ်ပါ",
            parse_mode='Markdown')
        return

    # ── ✅ T&C Agree / Disagree ──
    if data.startswith("tc_agree_"):
        user_id = data.replace("tc_agree_", "")
        if str(query.from_user.id) != user_id:
            await query.answer("❌ သင့် button မဟုတ်ဘူး", show_alert=True)
            return
        brokers = await get_brokers()
        broker  = next((b for b in brokers if b.get("telegramId") == user_id), None)
        broker_id_val = broker["brokerId"] if broker else "?"
        await query.edit_message_text(
            f"✅ *သဘောတူပြီ!*\n\n"
            f"🆔 Broker ID: `{broker_id_val}`\n\n"
            f"Japan Auction Car Checker T&C ကို သဘောတူပြီး Broker အဖြစ် စတင်ပြီ 🎉\n\n"
            f"Request လက်ခံဖို့ /available နှိပ်ပါ",
            parse_mode='Markdown')
        return

    if data.startswith("tc_disagree_"):
        user_id = data.replace("tc_disagree_", "")
        if str(query.from_user.id) != user_id:
            await query.answer("❌ သင့် button မဟုတ်ဘူး", show_alert=True)
            return
        await query.edit_message_text(
            f"❌ *သဘောမတူဘူး*\n\n"
            f"T&C သဘောမတူသောကြောင့် Broker အဖြစ် ဆက်လုပ်၍ မရပါ\n\n"
            f"သဘောပြောင်းပါက Admin ကို ဆက်သွယ်ပါ",
            parse_mode='Markdown')
        return

    # ── 👷 Broker Start Button ──
    if data.startswith("brokerstart_"):
        tg_id   = data.replace("brokerstart_", "")
        user_id = str(query.from_user.id)
        if user_id != tg_id:
            await query.answer("❌ သင့် button မဟုတ်ဘူး", show_alert=True)
            return
        brokers = await get_brokers()
        broker  = next((b for b in brokers if b.get("telegramId") == user_id), None)
        if not broker:
            await query.answer("❌ Broker အဖြစ် မှတ်ပုံမတင်ရသေးဘူး", show_alert=True)
            return
        broker_id_val = broker['brokerId']
        tc_text = (
            f"🤝 *Japan Auction Car Checker T&C*\n\n"
            f"🆔 Broker ID: `{broker_id_val}`\n\n"
            f"အောက်ပါ စည်ကမ်းများကို သဘောတူကြောင်း confirm လုပ်ပါ:\n\n"
            f"① တစ်ချိန်တည်း Customer ၁ ယောက်သာ\n"
            f"② Bot ထဲမှာပဲ ဆက်သွယ်ရမည်\n"
            f"③ Condition Report မှန်ကန်စွာ ပေးရမည်\n"
            f"④ Photo အနည်းဆုံး ၁၀ ပုံ ပေးရမည်\n"
            f"⑤ ကားနဲ့ ပတ်သက်ပြီး အမှားအယွင်း မဖြစ်အောင် လုပ်ဆောင်ပေးရမည်\n"
            f"⑥ အမှားအယွင်း ဖြစ်ပေါ်ပါက Admin စိစစ်၍ Admin ၏ အဆုံးအဖြတ်ကို လိုက်နာရမည်\n"
            f"⑦ Platform ပြင်ပ Deal = Lifetime Ban\n"
            f"⑧ Rating 1 × 3 = Permanent Ban\n\n"
            f"သဘောတူမတူ အောက်က Button နှိပ်ပါ 👇"
        )
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ သဘောတူပါတယ်", callback_data=f"tc_agree_{user_id}"),
            InlineKeyboardButton("❌ သဘောမတူပါ",    callback_data=f"tc_disagree_{user_id}"),
        ]])
        await query.message.reply_text(tc_text, parse_mode='Markdown', reply_markup=kb)
        await query.edit_message_reply_markup(reply_markup=None)
        return

    # ── 📦 Tracking Status Update ──
    if data.startswith("track_"):
        parts    = data.split("_")
        svc_t    = parts[1]
        status   = parts[2]
        req_id   = "_".join(parts[3:])
        session  = proxy_sessions.get(req_id)
        if not session:
            await query.answer("❌ Session မတွေ့ပါ — ပြီးသွားပြီ ဖြစ်နိုင်တယ်", show_alert=True)
            return
        broker_id  = session.get("brokerId")
        customer_id = session.get("customerId")
        if str(query.from_user.id) != str(broker_id):
            await query.answer("❌ သင့် Session မဟုတ်ဘူး", show_alert=True)
            return
        noti_text = TRACKING_NOTI.get(status, status)
        if customer_id:
            try:
                await context.bot.send_message(
                    chat_id=int(customer_id),
                    text=(f"📦 *Status Update*\n\n"
                          f"🆔 `{req_id}`\n"
                          f"{noti_text}\n\n"
                          f"Status စစ်ရန်: /mystatus"),
                    parse_mode='Markdown')
            except Exception as e:
                logger.error(f"tracking noti: {e}")
        svc_type_full = "auction" if svc_t == "A" else "search"
        svc_label     = "🏆 Auction" if svc_t == "A" else "🔍 ကားရှာ"
        await query.edit_message_text(
            f"📦 *Status Tracking — {svc_label}*\n\n"
            f"🆔 `{req_id}`\n"
            f"✅ ပို့ပြီး: {noti_text}\n\n"
            f"နောက်တဆင့် Button နှိပ်ပါ 👇",
            parse_mode='Markdown',
            reply_markup=get_tracking_keyboard(svc_type_full, req_id))
        return

    # ── ✅ Confirm Save ──
    if data.startswith("cs_"):
        uid  = int(data.replace("cs_",""))
        info = pending_photo.pop(uid, None)
        if not info or info.get('price') is None:
            await query.message.reply_text("❌ Data မရှိတော့ပါ — ပုံ ပြန်တင်ပါ")
            return
        user_name = query.from_user.first_name or "Unknown"
        await save_price(info['chassis'], info['model'], info['color'], info['year'],
                        info['price'], user_name, info.get('image_url',''), info.get('loc', LOC_MAESOT))
        await query.message.reply_text(
            f"✅ *Save ပြီး!*\n\n🚗 {info['model']} ({ys(info.get('year',0))})\n"
            f"🔑 `{info['chassis']}`\n🎨 {info.get('color','')}\n📍 {info.get('loc', LOC_MAESOT)}\n💰 ฿{info['price']:,}\n\n"
            f"🌐 [Web မှာကြည့်](https://kyawmintun08.github.io/Japan-Auction-Car-Checker/)",
            parse_mode='Markdown')
        await post_to_channel(context, info['chassis'], info['model'], info['color'],
                             info['year'], info['price'], info.get('image_url',''), info.get('loc', LOC_MAESOT))

    elif data.startswith("cc_"):
        uid = int(data.replace("cc_",""))
        pending_photo.pop(uid, None)
        await query.message.reply_text(
            "❌ *Cancel လုပ်ပြီး*\n\nChassis ကိုယ်တိုင် ထည့်ပါ:\n"
            "`/price [chassis] [ဈေး]`\nဥပမာ: `/price GP1-1049821 58000`",
            parse_mode='Markdown')

    elif data.startswith("setloc_"):
        parts      = data.split("_")
        target_uid = int(parts[1])
        loc_key    = parts[2]
        loc_map    = {"MaeSot": LOC_MAESOT, "Klang9": LOC_KLANG9, "Border44": LOC_BORDER44}
        new_loc    = loc_map.get(loc_key, LOC_MAESOT)
        if target_uid not in pending_photo:
            await query.answer("❌ Data ကုန်သွားပြီ — ပုံ ပြန်တင်ပါ", show_alert=True)
            return
        pending_photo[target_uid]["loc"] = new_loc
        pdata = pending_photo[target_uid]
        loc_row = [
            InlineKeyboardButton(f"{'✅' if new_loc == LOC_MAESOT else '📍'} MaeSot",    callback_data=f"setloc_{target_uid}_MaeSot"),
            InlineKeyboardButton(f"{'✅' if new_loc == LOC_KLANG9 else '📍'} Klang9",    callback_data=f"setloc_{target_uid}_Klang9"),
            InlineKeyboardButton(f"{'✅' if new_loc == LOC_BORDER44 else '📍'} Border44", callback_data=f"setloc_{target_uid}_Border44"),
        ]
        if pdata.get('price') is not None:
            await query.edit_message_text(
                f"⚠️ *စစ်ဆေးပါ — မှန်ကန်ပါသလား?*\n\n"
                f"🚗 *{pdata['model']}* ({ys(pdata.get('year',0))})\n"
                f"🔑 `{pdata['chassis']}`\n🎨 {pdata['color']}\n📍 {new_loc}\n💰 ฿{pdata['price']:,}",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([
                    loc_row,
                    [InlineKeyboardButton("✅ Save",   callback_data=f"cs_{target_uid}"),
                     InlineKeyboardButton("❌ Cancel", callback_data=f"cc_{target_uid}")],
                ]))
        else:
            await query.edit_message_text(
                f"🚗 *{pdata['model']}* ({ys(pdata.get('year',0))})\n"
                f"🔑 `{pdata['chassis']}`\n🎨 {pdata['color']}\n📍 {new_loc}\n\n"
                f"💰 ဈေး ရိုက်ထည့်ပါ:\nဥပမာ: `150000`",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([loc_row]))

    elif data.startswith("editcar_"):
        if query.from_user.id not in ADMIN_IDS:
            await query.answer("❌ Admin only", show_alert=True)
            return
        chassis = data.replace("editcar_","")
        car = find_by_chassis(chassis)
        if not car:
            await query.answer("❌ Chassis မတွေ့ပါ", show_alert=True)
            return
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"💰 ဈေး ({car.get('price','?')})",   callback_data=f"editfield_{chassis}_price")],
            [InlineKeyboardButton(f"🎨 Color ({car.get('color','-')})",  callback_data=f"editfield_{chassis}_color")],
            [InlineKeyboardButton(f"🚗 Model ({car.get('model','-')})",  callback_data=f"editfield_{chassis}_model")],
            [InlineKeyboardButton("❌ Cancel",                           callback_data=f"editfield_{chassis}_cancel")],
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

    elif data.startswith("fill_"):
        parts  = data.split("_", 2)
        uid    = int(parts[1])
        field  = parts[2]
        if uid not in pending_photo:
            await query.answer("❌ Data ကုန်သွားပြီ", show_alert=True)
            return
        pending_edit[query.from_user.id] = {"chassis": "__photo__", "field": field, "photo_uid": uid}
        prompts = {
            "model": "🚗 Model ထည့်ပါ:\nဥပမာ: `CROWN`, `AD VAN`",
            "color": "🎨 Color ထည့်ပါ:\nဥပမာ: `WHITE`, `PEARL WHITE`",
            "year":  "📅 Year ထည့်ပါ:\nဥပမာ: `2013`",
        }
        await query.message.reply_text(prompts.get(field,"ထည့်ပါ:"), parse_mode='Markdown')
        await query.answer()

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

    elif data.startswith("join_start"):
        user_id = query.from_user.id
        await query.message.reply_text(
            "🆕 *Membership ဝယ်ရန်*\n\nPackage ရွေးပါ 👇",
            parse_mode='Markdown',
            reply_markup=build_package_keyboard(user_id, "join"))

    elif data.startswith("pkg_cancel_"):
        pending_payment.pop(query.from_user.id, None)
        await query.message.reply_text("❌ Cancel လုပ်ပြီး")

    elif data.startswith("pkg_back_"):
        user_id = query.from_user.id
        await query.message.reply_text(
            "Package ပြန်ရွေးပါ 👇",
            reply_markup=build_package_keyboard(user_id, "renew"))

    elif data.startswith("pkg_"):
        parts   = data.split("_")
        package = parts[1]
        user_id = int(parts[2])
        action  = parts[3] if len(parts) > 3 else "renew"
        prices  = PLAN_PRICES.get(package, PLAN_PRICES["CH"])
        pending_payment[user_id] = {
            "package": package, "action": action,
            "name":    query.from_user.first_name or "Unknown",
            "username": f"@{query.from_user.username}" if query.from_user.username else str(user_id),
        }
        pkg_name = PLAN_NAMES.get(package,"")
        await query.message.reply_text(
            f"✅ Package: *{pkg_name}*\n\nPeriod ရွေးပါ 👇",
            parse_mode='Markdown',
            reply_markup=build_period_keyboard(user_id, package))

    # ── 🆕 Period → Method ရွေးခိုင်း ──
    elif data.startswith("period_"):
        parts   = data.split("_")
        package = parts[1]
        months  = int(parts[2])
        user_id = int(parts[3])
        amount  = PLAN_PRICES.get(package, {}).get(months, 0)
        pkg_name = PLAN_NAMES.get(package,"")

        if user_id not in pending_payment:
            pending_payment[user_id] = {}
        pending_payment[user_id].update({
            "package": package,
            "months":  months,
            "amount":  amount,
        })

        await query.message.reply_text(
            f"✅ Package: *{pkg_name}*\n"
            f"📅 Period: *{months} လ*\n"
            f"💵 ပေးရမည်: *{amount:,} ks*\n\n"
            f"💳 *Payment Method ရွေးပါ* 👇",
            parse_mode='Markdown',
            reply_markup=build_paymethod_keyboard(user_id))

    # ── 🆕 Method ရွေးပြီး QR ပြ ──
    elif data.startswith("paymethod_"):
        parts   = data.split("_")
        method  = parts[1]
        user_id = int(parts[2])
        if query.from_user.id != user_id:
            await query.answer("❌ သင့် button မဟုတ်ဘူး", show_alert=True); return
        if user_id not in pending_payment:
            await query.answer("❌ Session ကုန်ပြီ — /renew ပြန်စပါ", show_alert=True); return

        info     = PAYMENT_METHOD_INFO.get(method, {})
        amount   = pending_payment[user_id].get("amount", 0)
        package  = pending_payment[user_id].get("package", "CH")
        months   = pending_payment[user_id].get("months", 1)
        pkg_name = PLAN_NAMES.get(package, "")
        file_id  = await get_payment_qr(method)

        pending_payment[user_id]["method"]       = method
        pending_payment[user_id]["waiting_slip"] = True

        caption = (
            f"{info.get('label','')} *Payment*\n\n"
            f"💵 *Amount:* {amount:,} ks\n"
            f"📦 {pkg_name} — {months} လ\n"
            f"📱 *Number:* {info.get('number','')}\n"
            f"👤 *Name:* {info.get('owner','')}\n\n"
            f"⬇️ QR ကို *long-press* → Save Photo\n"
            f"📲 ဒါမှမဟုတ် App နဲ့ Scan\n\n"
            f"💸 ပြီးရင် *Payment Slip* ဒီနေရာမှာ ပို့ပါ"
        )

        if file_id:
            try:
                await context.bot.send_photo(
                    chat_id=user_id, photo=file_id,
                    caption=caption, parse_mode='Markdown')
            except Exception as e:
                logger.error(f"send QR photo: {e}")
                await query.message.reply_text(
                    f"⚠️ QR ပုံ ပြလို့မရဘူး — Admin ကို ဆက်သွယ်ပါ\n\n{caption}",
                    parse_mode='Markdown')
        else:
            await query.message.reply_text(
                f"⚠️ {info.get('label','')} QR မထည့်ရသေးပါ — Admin ကို ဆက်သွယ်ပါ\n\n{caption}",
                parse_mode='Markdown')

    # ── 🆕 Admin /setqr Method ရွေး ──
    elif data.startswith("setqr_"):
        parts = data.split("_", 2)
        if len(parts) < 3:
            return
        action  = parts[1]
        user_id = int(parts[2])
        if query.from_user.id != user_id or user_id not in ADMIN_IDS:
            await query.answer("❌ Admin only", show_alert=True); return
        if action == "cancel":
            pending_setqr.pop(user_id, None)
            await query.edit_message_text("❌ Cancel လုပ်ပြီး")
            return
        if action not in ("kpay","wave","cb"):
            return
        pending_setqr[user_id] = action
        info = PAYMENT_METHOD_INFO.get(action, {})
        await query.edit_message_text(
            f"✅ *{info.get('label','')}* ရွေးပြီ\n\n"
            f"📤 {info.get('label','')} QR ပုံကို ဒီနေရာမှာ ပို့ပါ\n\n"
            f"(file ID auto-save ဖြစ်မယ်)",
            parse_mode='Markdown')

    # ── Slip Confirm (Admin) ──
    elif data.startswith("slip_confirm_"):
        if query.from_user.id not in ADMIN_IDS:
            await query.answer("❌ Admin သာ လုပ်နိုင်တယ်", show_alert=True)
            return
        member_id = int(data.replace("slip_confirm_",""))
        pay_data  = pending_payment.get(member_id, {})
        if not pay_data:
            await query.answer("❌ Data ကုန်သွားပြီ", show_alert=True)
            return
        name   = pay_data.get("name", "Unknown")
        pkg    = PLAN_NAMES.get(pay_data.get("package","CH"), "Unknown")
        months = pay_data.get("months", 1)
        amount = pay_data.get("amount", 0)
        confirm_kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Yes — Approve", callback_data=f"slip_ok_{member_id}"),
            InlineKeyboardButton("❌ Cancel",        callback_data=f"slip_okcancel_{member_id}"),
        ]])
        await query.message.reply_text(
            f"⚠️ *Approve အတည်ပြုချက်*\n\n"
            f"👤 {name}\n"
            f"📦 {pkg} — {months} လ\n"
            f"💵 {amount:,} ks\n\n"
            f"Channel link + Password ပေးမည် — သေချာပါသလား?",
            parse_mode='Markdown',
            reply_markup=confirm_kb)

    elif data.startswith("slip_okcancel_"):
        if query.from_user.id not in ADMIN_IDS:
            await query.answer("❌ Admin သာ လုပ်နိုင်တယ်", show_alert=True)
            return
        await query.message.reply_text("❌ Approve Cancel လုပ်ပြီး")

    elif data.startswith("slip_ok_"):
        if query.from_user.id not in ADMIN_IDS:
            await query.answer("❌ Admin သာ လုပ်နိုင်တယ်", show_alert=True)
            return
        member_id  = int(data.replace("slip_ok_",""))
        pay_data   = pending_payment.pop(member_id, {})
        if not pay_data:
            await query.message.reply_text("❌ Data ကုန်သွားပြီ")
            return
        package  = pay_data.get("package", "CH")
        months   = pay_data.get("months", 1)
        name     = pay_data.get("name", "Unknown")
        username = pay_data.get("username", str(member_id))
        password = generate_password() if package == "WEB" else ""

        await save_member_to_sheet(str(member_id), username.replace("@",""), months * 30, password, package)

        slip_info = pay_data.get("slip_info", {})
        chosen_method = pay_data.get("method", "")
        try:
            async with httpx.AsyncClient() as client:
                await client.post(SHEET_WEBHOOK, json={
                    "action": "logPayment",
                    "payment": {
                        "date":          slip_info.get("DATE", datetime.now().strftime("%d/%m/%Y")),
                        "time":          slip_info.get("TIME", datetime.now().strftime("%H:%M")),
                        "userId":        str(member_id),
                        "username":      username,
                        "package":       PLAN_NAMES.get(package, package),
                        "months":        months,
                        "amount":        slip_info.get("AMOUNT", pay_data.get("amount","")),
                        "payType":       slip_info.get("TYPE", ""),
                        "method":        chosen_method.upper() if chosen_method else "",
                        "transactionNo": slip_info.get("TRANSACTION_NO", slip_info.get("REFERENCE","")),
                        "receiver":      slip_info.get("RECEIVER", ""),
                        "sender":        slip_info.get("SENDER", ""),
                        "status":        "APPROVED",
                    }
                }, timeout=10, follow_redirects=True)
        except Exception as e:
            logger.error(f"logPayment: {e}")

        invite_url = await create_invite_link(context, months * 30)
        await send_approval_dm(context, member_id, months, password, invite_url)

        expire_date = (datetime.now() + timedelta(days=months*30)).strftime("%d/%m/%Y")
        await query.message.reply_text(
            f"✅ *Payment Confirmed + Approved!*\n\n"
            f"👤 {name} ({username})\n"
            f"📦 {PLAN_NAMES.get(package,'')} — {months} လ\n"
            f"⏰ ကုန်ဆုံး: `{expire_date}`\n"
            f"🔑 Password: `{password}`\n\n"
            f"Member ကို DM ပို့ပြီးပြီ ✅",
            parse_mode='Markdown')

    elif data.startswith("slip_no_"):
        if query.from_user.id not in ADMIN_IDS:
            await query.answer("❌ Admin သာ လုပ်နိုင်တယ်", show_alert=True)
            return
        member_id = int(data.replace("slip_no_",""))
        pending_payment.pop(member_id, None)
        try:
            admin_link = f"\n💬 [Admin ကို ဆက်သွယ်](https://t.me/{ADMIN_USERNAME})" if ADMIN_USERNAME else ""
            await context.bot.send_message(
                chat_id=member_id,
                text=f"❌ *Payment မအတည်မပြုနိုင်ပါ*\n\n"
                     f"Slip မှားနိုင်သည် သို့မဟုတ် ငွေပမာဏ မပြည့်မှီပါ\n\n"
                     f"ပြန်လည် ကြိုးစားရန် /renew{admin_link}",
                parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Reject DM: {e}")
        await query.message.reply_text(f"❌ Rejected — Member ကို notify ပြီးပြီ")

    elif data.startswith("uid_ok_"):
        admin_id  = int(data.replace("uid_ok_",""))
        info      = pending_updateid.pop(admin_id, None)
        if not info:
            await query.message.reply_text("❌ Data ကုန်သွားပြီ")
            return
        target_username = info["target_username"]
        new_id          = info["new_id"]
        new_pw          = generate_password()
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(SHEET_WEBHOOK, json={
                    "action":   "updateMemberId",
                    "username": target_username,
                    "newId":    str(new_id),
                    "password": new_pw,
                }, timeout=10, follow_redirects=True)
            result = resp.json()
            old_id = result.get("oldId", "?")
            if result.get("status") == "ok":
                try:
                    await context.bot.send_message(
                        chat_id=new_id,
                        text=f"✅ *Account Update ပြီ*\n\n"
                             f"Telegram ID အသစ်နဲ့ ချိတ်ဆက်ပြီ\n"
                             f"🔑 New Password: `{new_pw}`\n\n"
                             f"🌐 https://kyawmintun08.github.io/Japan-Auction-Car-Checker/",
                        parse_mode='Markdown')
                except Exception as e:
                    logger.error(f"UpdateID notify: {e}")
                await query.message.reply_text(
                    f"✅ *ID Update ပြီ*\n\n"
                    f"👤 @{target_username}\n"
                    f"🗑 ဟောင်း: `{old_id}`\n"
                    f"✅ အသစ်: `{new_id}`\n"
                    f"🔑 Password: `{new_pw}`",
                    parse_mode='Markdown')
            else:
                await query.message.reply_text(f"❌ @{target_username} မတွေ့ပါ")
        except Exception as e:
            await query.message.reply_text(f"❌ Error: {e}")

    elif data.startswith("uid_no_"):
        admin_id = int(data.replace("uid_no_",""))
        pending_updateid.pop(admin_id, None)
        await query.message.reply_text("❌ Cancel လုပ်ပြီး")

    elif data.startswith("qa_"):
        parts     = data.split("_")
        target_id = int(parts[1])
        months    = int(parts[2])
        days      = months * 30
        try:
            chat            = await context.bot.get_chat(target_id)
            member_username = chat.username or chat.first_name or str(target_id)
        except:
            member_username = str(target_id)

        password   = generate_password()
        await save_member_to_sheet(str(target_id), member_username, days, password, "CH")
        invite_url = await create_invite_link(context, days)
        await send_approval_dm(context, target_id, months, password, invite_url)
        expire_date = (datetime.now() + timedelta(days=days)).strftime("%d/%m/%Y")
        await query.message.reply_text(
            f"✅ *Quick Approve ပြီး!*\n\n👤 @{member_username}\n📅 {months} လ\n"
            f"⏰ ကုန်ဆုံး: `{expire_date}`\n🔑 Password: `{password}`",
            parse_mode='Markdown')

    elif data.startswith("req_budget_"):
        user_id = query.from_user.id
        if user_id not in pending_request: return
        amount = data.replace("req_budget_","")
        pending_request[user_id]["data"]["budget"] = f"฿{int(amount):,}"
        pending_request[user_id]["step"] = 4
        kb = [
            [InlineKeyboardButton("⭐",     callback_data="req_cond_1"),
             InlineKeyboardButton("⭐⭐",    callback_data="req_cond_2"),
             InlineKeyboardButton("⭐⭐⭐",   callback_data="req_cond_3")],
            [InlineKeyboardButton("⭐⭐⭐⭐",  callback_data="req_cond_4"),
             InlineKeyboardButton("⭐⭐⭐⭐⭐", callback_data="req_cond_5")],
        ]
        await query.edit_message_text(
            "⭐ *Condition ရွေးပါ*\n\n⭐ = ဈေးသက်သာ\n⭐⭐⭐ = ပုံမှန်\n⭐⭐⭐⭐⭐ = အကောင်းဆုံး",
            parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(kb))

    elif data.startswith("req_cond_"):
        user_id = query.from_user.id
        if user_id not in pending_request: return
        stars = int(data.replace("req_cond_",""))
        pending_request[user_id]["data"]["condition"] = "⭐" * stars
        pending_request[user_id]["step"] = 5
        kb = [
            [InlineKeyboardButton("🔥 ၃ ရက်",     callback_data="req_time_3days"),
             InlineKeyboardButton("📅 ၁ ပတ်",    callback_data="req_time_1week")],
            [InlineKeyboardButton("🗓 ၁ လ",      callback_data="req_time_1month"),
             InlineKeyboardButton("⏳ ရမှပြောမည်", callback_data="req_time_open")],
        ]
        await query.edit_message_text(
            "⏳ *Timeline ရွေးပါ*",
            parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(kb))

    elif data.startswith("req_time_"):
        user_id = query.from_user.id
        if user_id not in pending_request: return
        tmap = {
            "req_time_3days":  "🔥 ၃ ရက်",
            "req_time_1week":  "📅 ၁ ပတ်",
            "req_time_1month": "🗓 ၁ လ",
            "req_time_open":   "⏳ ရမှပြောမည်",
        }
        pending_request[user_id]["data"]["timeline"] = tmap.get(data, data)
        pending_request[user_id]["step"] = 6
        await finish_request(query, context, user_id)

    elif data == "req_confirm":
        user_id  = query.from_user.id
        username = query.from_user.username or query.from_user.first_name or str(user_id)
        await query.edit_message_text("⏳ Request တင်နေတယ်...")
        await submit_request(context, user_id, username)

    elif data == "req_cancel":
        user_id = query.from_user.id
        pending_request.pop(user_id, None)
        await query.edit_message_text("❌ Request ပယ်ဖျက်ပြီ\nပြန်တင်ရန်: /carrequest")

    elif data.startswith("dep_start_"):
        parts        = data.split("_", 3)
        req_id       = parts[2]
        broker_tg_id = parts[3]
        customer_id  = str(query.from_user.id)

        PAYMENT_INFO_DEP = os.environ.get('PAYMENT_INFO', 'KPay / Wave: Admin ကို ဆက်သွယ်ပါ')

        pending_deposit[customer_id] = {
            "reqId":      req_id,
            "brokerTgId": broker_tg_id,
            "step":       "waiting_slip",
        }
        await query.edit_message_text(
            f"💰 *Deposit ฿20,000*\n\n"
            f"🆔 Request: `{req_id}`\n\n"
            f"💳 *Payment Info:*\n{PAYMENT_INFO_DEP}\n\n"
            f"⬇️ Slip ကို ဒီ bot ထဲမှာ တိုက်ရိုက် ပို့ပါ",
            parse_mode='Markdown')

    elif data.startswith("dep_ok_"):
        if query.from_user.id not in ADMIN_IDS:
            await query.answer("❌ Admin only", show_alert=True); return
        customer_id  = data.replace("dep_ok_", "")
        dep_data     = pending_deposit.pop(customer_id, {})
        req_id       = dep_data.get("reqId", "")
        broker_tg_id = dep_data.get("brokerTgId", "")
        slip_info    = dep_data.get("slip_info", {})

        mmk_rate   = int(os.environ.get("MMK_RATE", "3800"))
        thb_amount = 20000
        mmk_amount = thb_amount * mmk_rate
        now_str    = datetime.now().strftime("%d/%m/%Y")

        try:
            async with httpx.AsyncClient(follow_redirects=True) as client:
                await client.post(SHEET_WEBHOOK, json={
                    "action":     "saveDeposit",
                    "reqId":      req_id,
                    "customerId": customer_id,
                    "brokerTgId": broker_tg_id,
                    "thbAmount":  thb_amount,
                    "mmkAmount":  mmk_amount,
                    "mmkRate":    mmk_rate,
                    "date":       now_str,
                    "txnNo":      slip_info.get("TRANSACTION_NO", ""),
                    "payType":    slip_info.get("TYPE", ""),
                    "status":     "HOLD",
                }, timeout=10)
        except Exception as e:
            logger.error(f"saveDeposit: {e}")

        try:
            await context.bot.send_message(
                chat_id=int(customer_id),
                text=(f"✅ *Deposit လက်ခံပြီ!*\n\n"
                      f"🆔 `{req_id}`\n"
                      f"💰 ฿{thb_amount:,} ({mmk_amount:,} ks)\n"
                      f"📅 {now_str}\n\n"
                      f"Broker က ကားရှာပေးနေပြီ ⏳"),
                parse_mode='Markdown')
        except Exception as e:
            logger.error(f"dep_ok customer: {e}")

        if broker_tg_id:
            try:
                await context.bot.send_message(
                    chat_id=int(broker_tg_id),
                    text=(f"✅ *Customer Deposit ရပြီ*\n\n"
                          f"🆔 `{req_id}`\n"
                          f"💰 ฿{thb_amount:,} — HOLD ✅\n\n"
                          f"ကားရှာပေးနိုင်ပြီ"),
                    parse_mode='Markdown')
            except Exception as e:
                logger.error(f"dep_ok broker: {e}")

        await query.message.reply_text(
            f"✅ *Deposit Confirmed!*\n\n"
            f"🆔 `{req_id}`\n"
            f"👤 Customer: `{customer_id}`\n"
            f"💰 ฿{thb_amount:,} = {mmk_amount:,} ks\n"
            f"📅 Rate: {mmk_rate} ks/฿",
            parse_mode='Markdown')

        if req_id in proxy_sessions:
            proxy_sessions[req_id]["deposit_paid"] = True

        cancel_auction_dep_timer(req_id)

    elif data.startswith("dep_no_"):
        if query.from_user.id not in ADMIN_IDS:
            await query.answer("❌ Admin only", show_alert=True); return
        customer_id = data.replace("dep_no_", "")
        pending_deposit.pop(customer_id, None)
        try:
            await context.bot.send_message(
                chat_id=int(customer_id),
                text="❌ *Deposit Slip မအတည်မပြုနိုင်*\n\nSlip မှားနိုင်သည် — ပြန်ပို့ပါ",
                parse_mode='Markdown')
        except: pass
        await query.message.reply_text("❌ Deposit ပယ်ချပြီ")

    elif data.startswith("auction_fasttrack_"):
        target_uid = int(data.replace("auction_fasttrack_", ""))
        if query.from_user.id != target_uid:
            await query.answer("❌ သင်၏ request မဟုတ်ဘူး", show_alert=True); return
        fasttrack_pending[str(target_uid)] = {"waiting_slip": True}
        await query.edit_message_text(
            "💰 *Deposit Fast Track — ฿20,000*\n\n"
            f"{PAYMENT_INFO}\n\n"
            "Slip screenshot ပို့ပါ 👇\n\n"
            "⏰ 15 မိနစ်အတွင်း မပို့ရင် cancel ဖြစ်မည်",
            parse_mode='Markdown')

    elif data.startswith("ftdep_ok_"):
        if query.from_user.id not in ADMIN_IDS:
            await query.answer("❌ Admin only", show_alert=True); return
        customer_id = int(data.replace("ftdep_ok_", ""))
        str_cid     = str(customer_id)
        ft_data     = fasttrack_pending.pop(str_cid, {})
        slip_info   = ft_data.get("slip_info", {})
        fasttrack_paid.add(str_cid)

        mmk_rate   = int(os.environ.get("MMK_RATE", "3800"))
        thb_amount = 20000
        mmk_amount = thb_amount * mmk_rate
        now_str    = datetime.now().strftime("%d/%m/%Y")

        try:
            async with httpx.AsyncClient(follow_redirects=True) as client:
                await client.post(SHEET_WEBHOOK, json={
                    "action":     "saveDeposit",
                    "reqId":      "FASTTRACK",
                    "customerId": str_cid,
                    "brokerTgId": "",
                    "thbAmount":  thb_amount,
                    "mmkAmount":  mmk_amount,
                    "mmkRate":    mmk_rate,
                    "date":       now_str,
                    "txnNo":      slip_info.get("TRANSACTION_NO", ""),
                    "payType":    slip_info.get("TYPE", ""),
                    "status":     "FASTTRACK_HOLD",
                }, timeout=10)
        except Exception as e:
            logger.error(f"ftdep_ok saveDeposit: {e}")

        await query.edit_message_text(f"✅ Fast Track Confirm — `{customer_id}`", parse_mode='Markdown')
        pending_request[customer_id] = {"step": 0, "data": {"service_type": "auction"}}
        try:
            await context.bot.send_message(
                chat_id=customer_id,
                text="✅ *Admin confirm ပြီးပါပြီ — Deposit ฿20,000 ✅*\n\n"
                     "🏆 *လေလံဆွဲရန် Request*\n\n"
                     "မေးချင်တဲ့ ကားအမည် ရိုက်ထည့်ပါ:\n"
                     "ဥပမာ: `ALPHARD`, `X-TRAIL`, `HIACE VAN`\n\n"
                     "Cancel လုပ်ရန်: /cancelrequest",
                parse_mode='Markdown')
        except Exception as e:
            logger.error(f"ftdep_ok notify: {e}")

    elif data.startswith("ftdep_no_"):
        if query.from_user.id not in ADMIN_IDS:
            await query.answer("❌ Admin only", show_alert=True); return
        customer_id = int(data.replace("ftdep_no_", ""))
        str_cid     = str(customer_id)
        fasttrack_pending.pop(str_cid, None)
        await query.edit_message_text(f"❌ Fast Track Reject — `{customer_id}`", parse_mode='Markdown')
        try:
            await context.bot.send_message(
                chat_id=customer_id,
                text="❌ *Deposit Slip မအတည်မပြုနိုင်*\n\nSlip မမှန်ကန်ပါ — ပြန်ကြိုးစားရန်: /carrequest",
                parse_mode='Markdown')
        except Exception as e:
            logger.error(f"ftdep_no notify: {e}")

    elif data.startswith("reqtype_"):
        parts       = data.split("_")
        svc_type    = parts[1]
        target_uid  = int(parts[2])

        if query.from_user.id != target_uid:
            await query.answer("❌ သင်၏ request မဟုတ်ဘူး", show_alert=True); return

        user_id = target_uid
        str_uid = str(user_id)

        existing_session = next(
            ((sid, s) for sid, s in proxy_sessions.items()
             if str(s.get("customerId","")) == str_uid and s.get("status") == "ACTIVE"),
            None
        )
        if existing_session:
            await query.answer("⚠️ Request တင်ပြီးသားရှိနေတယ်", show_alert=True); return
        if user_id in pending_request:
            await query.answer("⚠️ Request ဖြည်နေဆဲ", show_alert=True); return

        pending_request[user_id] = {"step": 0, "data": {"service_type": svc_type}}

        if svc_type == "auction":
            ban_count  = 0
            ban_status = ""
            ban_expire = ""
            try:
                async with httpx.AsyncClient(follow_redirects=True) as client:
                    resp_ban = await client.post(SHEET_WEBHOOK, json={
                        "action":     "getAuctionCancelCount",
                        "customerId": str_uid,
                    }, timeout=10)
                ban_data   = resp_ban.json()
                ban_count  = ban_data.get("banCount", 0)
                ban_status = ban_data.get("banStatus", "")
                ban_expire = ban_data.get("banExpire", "")
            except Exception as e:
                logger.error(f"auction ban check: {e}")

            if ban_count > 0 and ban_status:
                if ban_status == "LIFETIME_BAN":
                    await query.edit_message_text(
                        "🚫 *Auction Car — Lifetime Ban*\n\n"
                        "Deposit မပေဘဲ Cancel ၃ ကြိမ်ကျော်သောကြောင့်\n"
                        "Auction Car access ထာဝရပိတ်ပြီ",
                        parse_mode='Markdown')
                    return
                elif ban_expire and ban_expire != "LIFETIME":
                    try:
                        ep = ban_expire.split('/')
                        expire_dt = datetime(int(ep[2]), int(ep[1]), int(ep[0]))
                        if datetime.now() < expire_dt:
                            days_left = (expire_dt - datetime.now()).days + 1
                            await query.edit_message_text(
                                f"⏳ *Auction Car — Temporary Ban*\n\n"
                                f"Deposit မပေဘဲ Cancel လုပ်ခဲ့သောကြောင့် Ban ဖြစ်နေသည်\n\n"
                                f"🗓 Ban ကုန်ဆုံးရက်: `{ban_expire}`\n"
                                f"⏰ ကျန်ရှိသည်: {days_left} ရက်",
                                parse_mode='Markdown')
                            return
                    except Exception as e:
                        logger.error(f"ban expire parse: {e}")

            completed_outside = 0
            try:
                async with httpx.AsyncClient(follow_redirects=True) as client:
                    resp_oc = await client.post(SHEET_WEBHOOK, json={
                        "action":     "getCompletedOutsideCount",
                        "customerId": str_uid,
                    }, timeout=10)
                completed_outside = resp_oc.json().get("count", 0)
            except Exception as e:
                logger.error(f"getCompletedOutsideCount: {e}")

            if completed_outside < 2:
                pending_request.pop(user_id, None)
                kb_ft = InlineKeyboardMarkup([[
                    InlineKeyboardButton("⚡ ฿20,000 Deposit ပေးမည်",       callback_data=f"auction_fasttrack_{user_id}"),
                    InlineKeyboardButton("🔍 အပြင်ကားရှာပေး ဆက်လုပ်မည်", callback_data=f"reqtype_search_{user_id}"),
                ]])
                await query.edit_message_text(
                    "⚠️ *Auction Car — Access မရသေးပါ*\n\n"
                    "အပြင်ကားရှာပေး × 2 ပြည့်ဖို့ လိုပါတယ်\n\n"
                    f"သင့် record: {completed_outside}/2 ✅\n\n"
                    "💡 OR — ฿20,000 Deposit ကြိုပေးပြီး တန်းဝင်နိုင်ပါတယ်",
                    parse_mode='Markdown',
                    reply_markup=kb_ft)
                return

            await query.edit_message_text(
                "🏆 *လေလံဆွဲရန် Request*\n\n"
                "⚠️ ဒီဝန်ဆောင်မှုမှာ Deposit *฿20,000* လိုအပ်ပါသည်\n\n"
                "မေးချင်တဲ့ ကားအမည် ရိုက်ထည့်ပါ:\n"
                "ဥပမာ: `ALPHARD`, `X-TRAIL`, `HIACE VAN`\n\n"
                "Cancel လုပ်ရန်: /cancelrequest",
                parse_mode='Markdown')
        else:
            await query.edit_message_text(
                "🔍 *ကားရှာရန် Request*\n\n"
                "မေးချင်တဲ့ ကားအမည် ရိုက်ထည့်ပါ:\n"
                "ဥပမာ: `X-TRAIL`, `ALPHARD`, `HIACE VAN`\n\n"
                "Cancel လုပ်ရန်: /cancelrequest",
                parse_mode='Markdown')

    elif data.startswith("endchat_yes_"):
        req_id  = data.replace("endchat_yes_", "")
        user_id = str(query.from_user.id)
        brokers = await get_brokers()
        broker  = next((b for b in brokers if b.get("telegramId") == user_id), None)
        if not broker:
            await query.answer("❌ Broker မဟုတ်ဘူး", show_alert=True); return

        session = proxy_sessions.pop(req_id, None)
        cancel_request_timer(req_id)
        cancel_auction_dep_timer(req_id)
        new_broker_status = recalc_broker_status(user_id)
        await update_broker(user_id, status=new_broker_status)

        if session:
            try:
                async with httpx.AsyncClient(follow_redirects=True) as client:
                    await client.post(SHEET_WEBHOOK, json={
                        "action": "updateRequest",
                        "reqId":  req_id,
                        "status": "CLOSED",
                    }, timeout=10)
            except Exception as e:
                logger.error(f"endchat confirm: {e}")

            status_msg = {
                "FREE":        "🟢 FREE — Request အသစ် ၂ ခုထိ လက်ခံနိုင်ပြီ",
                "HAS_AUCTION": "🟡 Auction ၁ ခု ကျန်နေဆဲ — ကားရှာ request လက်ခံနိုင်ပြီ",
                "HAS_SEARCH":  "🟡 ကားရှာ ၁ ခု ကျန်နေဆဲ — Auction request လက်ခံနိုင်ပြီ",
            }.get(new_broker_status, "🟢 FREE")
            await query.edit_message_text(
                f"✅ *Session ပိတ်ပြီ*\n\n"
                f"🆔 `{req_id}`\n"
                f"{status_msg}",
                parse_mode='Markdown')

            customer_id = session.get("customerId")
            if customer_id:
                try:
                    rating_kb = InlineKeyboardMarkup([
                        [InlineKeyboardButton("⭐1", callback_data=f"rate_1_{req_id}"),
                         InlineKeyboardButton("⭐2", callback_data=f"rate_2_{req_id}"),
                         InlineKeyboardButton("⭐3", callback_data=f"rate_3_{req_id}")],
                        [InlineKeyboardButton("⭐4", callback_data=f"rate_4_{req_id}"),
                         InlineKeyboardButton("⭐5", callback_data=f"rate_5_{req_id}")],
                    ])
                    await context.bot.send_message(
                        chat_id=int(customer_id),
                        text=f"🌟 *Broker ကို Rate လုပ်ပေးပါ*\n\n"
                             f"🆔 Request: `{req_id}`\n\n"
                             f"⭐1 = ညံ့ | ⭐3 = ပုံမှန် | ⭐5 = အကောင်းဆုံး",
                        parse_mode='Markdown',
                        reply_markup=rating_kb)
                    pending_rating[str(customer_id)] = {
                        "reqId":      req_id,
                        "brokerId":   broker["brokerId"],
                        "brokerTgId": user_id,
                    }
                except Exception as e:
                    logger.error(f"endchat rating prompt: {e}")
        else:
            await query.edit_message_text("✅ FREE ဖြစ်ပြီ")

    elif data.startswith("endchat_no_"):
        req_id = data.replace("endchat_no_", "")
        await query.edit_message_text(
            f"↩️ *Cancel — Session ဆက်ဖွင့်နေဆဲ*\n\n"
            f"🆔 `{req_id}`\n"
            f"💬 Chat ဆက်လုပ်နိုင်ပါသည်",
            parse_mode='Markdown')

    elif data.startswith("breq_accept_"):
        req_id  = data.replace("breq_accept_", "")
        user_id = str(query.from_user.id)
        brokers = await get_brokers()
        broker  = next((b for b in brokers if b.get("telegramId") == user_id), None)
        if not broker:
            await query.answer("❌ Broker မဟုတ်ဘူး", show_alert=True); return
        if broker.get("status") == "BUSY":
            await query.answer("❌ BUSY ဖြစ်နေတယ် — /available နှိပ်ပြီးမှ လက်ခံပါ", show_alert=True); return

        customer_id = None; customer_username = ""; req_data = {}
        try:
            async with httpx.AsyncClient(follow_redirects=True) as client:
                resp = await client.post(SHEET_WEBHOOK, json={
                    "action": "getRequest", "reqId": req_id,
                }, timeout=10)
            rdata = resp.json()
            if rdata.get("status") == "ok":
                customer_id       = rdata.get("customerId")
                customer_username = rdata.get("username", "")
                req_data          = rdata
            else:
                await query.answer(f"❌ Request {req_id} မတွေ့ဘူး", show_alert=True); return
        except Exception as e:
            logger.error(f"breq_accept getRequest: {e}")
            await query.answer("❌ Sheet error", show_alert=True); return

        await update_broker(user_id, status="BUSY")
        try:
            async with httpx.AsyncClient(follow_redirects=True) as client:
                await client.post(SHEET_WEBHOOK, json={
                    "action": "updateRequest", "reqId": req_id,
                    "status": "MATCHED", "brokerId": broker["brokerId"],
                }, timeout=10)
        except Exception as e:
            logger.error(f"breq_accept updateRequest: {e}")

        proxy_sessions[req_id] = {
            "customerId":       customer_id,
            "customerUsername": customer_username,
            "brokerId":         user_id,
            "brokerObj":        broker,
            "reqId":            req_id,
            "status":           "ACTIVE",
            "startTime":        datetime.now().isoformat(),
        }

        await query.edit_message_text(
            f"✅ *Request လက်ခံပြီ!*\n\n"
            f"🆔 `{req_id}`\n"
            f"🚗 {req_data.get('carType','')}\n"
            f"💰 {req_data.get('budget','')}\n\n"
            f"💬 Customer ကို message ပို့နိုင်ပြီ\n"
            f"ပြီးရင်: `/endchat {req_id}`",
            parse_mode='Markdown')

        if customer_id:
            try:
                await context.bot.send_message(
                    chat_id=int(customer_id),
                    text=(f"🎉 *Broker ရှာပေးနေပြီ!*\n\n"
                          f"🆔 Request: `{req_id}`\n"
                          f"👷 Broker #{broker['brokerId']} က သင့် Request လက်ခံပြီ\n\n"
                          f"ကားရှာပေးနေတယ် ⏳\n"
                          f"Status စစ်ရန်: /mystatus"),
                    parse_mode='Markdown')
            except Exception as e:
                logger.error(f"breq_accept customer notify: {e}")

        await notify_admins(context,
            f"🤝 *Broker Accept ပြီ (Button)*\n\n"
            f"🆔 `{req_id}`\n"
            f"👷 #{broker['brokerId']} @{broker['username']}\n"
            f"👤 Customer: @{customer_username}")

        start_request_timer(context, req_id=req_id,
            broker_tg_id=user_id, broker_id=broker["brokerId"],
            customer_id=str(customer_id) if customer_id else "")

        if req_id.startswith("A"):
            start_auction_dep_timer(
                context,
                req_id       = req_id,
                customer_id  = str(customer_id) if customer_id else "",
                broker_tg_id = user_id,
                broker_id    = broker["brokerId"],
                username     = customer_username,
            )

    elif data.startswith("breq_decline_"):
        req_id = data.replace("breq_decline_", "")
        await query.edit_message_text(
            f"❌ *Request ငြင်းပယ်ပြီ*\n\n🆔 `{req_id}`\n\nRequest အသစ် ထပ်လာရင် notify ပေးမည် 🔔",
            parse_mode='Markdown')

    elif data.startswith("rate_"):
        parts      = data.split("_")
        stars      = int(parts[1])
        req_id     = parts[2]
        rater_id   = str(query.from_user.id)

        rate_info  = pending_rating.pop(rater_id, None)
        if not rate_info or rate_info["reqId"] != req_id:
            await query.answer("⚠️ Rating ကုန်သွားပြီ", show_alert=True)
            return

        broker_id    = rate_info["brokerId"]
        broker_tg_id = rate_info["brokerTgId"]
        ban = False; new_rating = 0; one_star_count = 0

        try:
            async with httpx.AsyncClient(follow_redirects=True) as client:
                resp = await client.post(SHEET_WEBHOOK, json={
                    "action":     "saveRating",
                    "reqId":      req_id,
                    "brokerId":   broker_id,
                    "stars":      stars,
                    "customerId": rater_id,
                }, timeout=10)
            result         = resp.json()
            ban            = result.get("ban", False)
            new_rating     = result.get("newRating", 0)
            one_star_count = result.get("oneStarCount", 0)
        except Exception as e:
            logger.error(f"saveRating: {e}")

        star_display = "⭐" * stars
        report_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ လုပ်ငန်းပြီဆုံး၊ အဆင်ပြေပါတယ်", callback_data=f"report_ok_{req_id}")],
            [InlineKeyboardButton("⚠️ လုပ်ငန်းမပြီးစုံ",               callback_data=f"report_incomplete_{req_id}")],
            [InlineKeyboardButton("🚗 ကားမမှန်ကန်",                     callback_data=f"report_wrongcar_{req_id}")],
            [InlineKeyboardButton("❌ ကားမရှာပေ",                       callback_data=f"report_nosearch_{req_id}")],
        ])
        await query.edit_message_text(
            f"✅ *Rating ပေးပြီ — {star_display} ({stars}/5)*\n\n"
            f"🆔 `{req_id}`\n\n"
            f"လုပ်ငန်းဆောင်တာ မည်သို့ဖြစ်ပါသလဲ? 👇",
            parse_mode='Markdown',
            reply_markup=report_kb)

        try:
            await context.bot.send_message(
                chat_id=int(broker_tg_id),
                text=f"⭐ *Rating ရပြီ*\n\n🆔 `{req_id}`\n{star_display} ({stars}/5)",
                parse_mode='Markdown')
        except Exception as e:
            logger.error(f"rating notify broker: {e}")

        if ban:
            await update_broker(broker_tg_id, status="BANNED")
            await notify_admins(context,
                f"🚨 *Broker BAN!*\n\n🆔 #{broker_id}\n"
                f"⭐1 × 3 ကြိမ် ရောက်ပြီ → BANNED")
            try:
                await context.bot.send_message(
                    chat_id=int(broker_tg_id),
                    text="🚨 *Broker Account ပိတ်ခံရပြီ*\n\n"
                         "⭐1 Rating ၃ ကြိမ် ရောက်သောကြောင့်\nAdmin ကို ဆက်သွယ်ပါ",
                    parse_mode='Markdown')
            except Exception as e:
                logger.error(f"ban notify: {e}")

        await notify_admins(context,
            f"⭐ *Rating တင်ပြီ*\n\n🆔 `{req_id}`\n"
            f"👷 Broker: #{broker_id}\n{star_display} ({stars}/5)\n"
            + (f"📊 Average: {float(new_rating):.1f}" if new_rating else ""))
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ ဟုတ်ကဲ့ — ပိတ်မည်",  callback_data=f"endchat_yes_{req_id}"),
        InlineKeyboardButton("❌ မပိတ်သေးဘူး",         callback_data=f"endchat_no_{req_id}"),
    ]])
    await update.message.reply_text(
        f"⚠️ *Session ပိတ်တော့မည်!*\n\n"
        f"🆔 `{req_id}`\n\n"
        f"Session ပိတ်လိုက်ရင်:\n"
        f"• Chat history အကုန် ဆုံးသွားမည်\n"
        f"• Customer ကို Rating prompt သွားမည်\n"
        f"• Timer ပိတ်သွားမည်\n"
        f"• သင် FREE ဖြစ်သွားမည်\n\n"
        f"သေချာပြီလား?",
        parse_mode='Markdown',
        reply_markup=kb)

# ── Membership Commands ────────────────────────────────
async def approve_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if ADMIN_IDS and user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Admin သာ သုံးနိုင်တယ်"); return
    if len(context.args) < 2:
        await update.message.reply_text("❌ Format: `/approve @username 1` သို့မဟုတ် `/approve 123456789 3`",
                                        parse_mode='Markdown'); return
    username_or_id = context.args[0].replace('@','')
    try:
        months = int(context.args[1])
    except:
        await update.message.reply_text("❌ လ ဂဏန်းထည့်ပါ", parse_mode='Markdown'); return
    package = "WEB" if len(context.args) > 2 and context.args[2].upper() == "WEB" else "CH"
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

    password   = generate_password()
    await save_member_to_sheet(
        str(member_id) if member_id else username_or_id,
        member_username, days, password, package)
    invite_url = await create_invite_link(context, days)
    if member_id:
        await send_approval_dm(context, member_id, months, password, invite_url)

    expire_date = (datetime.now() + timedelta(days=days)).strftime("%d/%m/%Y")
    txt = (f"✅ <b>Membership Approved!</b>\n\n"
           f"👤 @{member_username}\n"
           f"🆔 <code>{member_id or 'N/A'}</code>\n"
           f"📦 Package: {PLAN_NAMES.get(package,'')}\n"
           f"📅 <b>{months} လ</b>\n"
           f"⏰ ကုန်ဆုံး: <code>{expire_date}</code>\n"
           f"🔑 Password: <code>{password}</code>\n")
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
    kicked  = [m for m in members if m.get('status') == 'KICKED']

    def pkg_label(pkg):
        if pkg == 'WEB':      return '💎 WEB'
        if pkg == 'CH-PROMO': return '🎁 PROMO'
        return '📱 CH'

    txt = f"👥 *Members*\n✅ Active: {len(active)} | ❌ Expired: {len(expired)} | 🚫 Kicked: {len(kicked)}\n\n"
    txt += "⚠️ _Member ဖယ်ရှားရန် `/kick ID` သာ သုံးပါ — Sheet တိုက်ရိုက် မဖျက်ရ_\n\n"
    txt += "*✅ Active:*\n"
    for m in active:
        label = pkg_label(m.get('package','CH'))
        txt += f"• @{m['username']} {label} — ကုန်: `{m.get('expireDate','?')}`\n"
    if expired:
        txt += "\n*❌ Expired:*\n"
        for m in expired[:5]:
            label = pkg_label(m.get('package','CH'))
            txt += f"• @{m['username']} {label} — `{m.get('expireDate','?')}`\n"
    if kicked:
        txt += "\n*🚫 Kicked:*\n"
        for m in kicked[:3]:
            txt += f"• @{m['username']} — `{m.get('expireDate','?')}`\n"
    await update.message.reply_text(txt, parse_mode='Markdown')

async def kick_member_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if ADMIN_IDS and user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Admin သာ သုံးနိုင်တယ်"); return
    if not context.args:
        await update.message.reply_text("❌ Format: `/kick 123456789`", parse_mode='Markdown'); return
    try:
        target_id = int(context.args[0])
        sheet_ok = False
        if SHEET_WEBHOOK:
            try:
                async with httpx.AsyncClient(follow_redirects=True) as client:
                    resp = await client.post(SHEET_WEBHOOK, json={
                        "action": "updateStatus",
                        "userId": str(target_id),
                        "status": "KICKED"
                    }, timeout=10)
                sheet_ok = resp.json().get("status") == "ok"
            except Exception as e:
                logger.error(f"kick sheet: {e}")

        ch_ok = await kick_with_retry(context, target_id)

        if ch_ok and sheet_ok:
            await update.message.reply_text(
                f"✅ *Kick အောင်မြင်ပြီ*\n\n🆔 `{target_id}`\n📋 Sheet ထဲကပါ ဖျက်ပြီ ✅\n📢 Channel ကပါ ထုတ်ပြီ ✅",
                parse_mode='Markdown')
        elif ch_ok and not sheet_ok:
            await update.message.reply_text(
                f"⚠️ Channel ကထုတ်ပြီ ✅\n❌ Sheet ထဲကပါ ဖျက်မရ — ကိုယ်တိုင် ဖျက်ပါ",
                parse_mode='Markdown')
        elif sheet_ok and not ch_ok:
            await update.message.reply_text(
                f"⚠️ Sheet ထဲကဖျက်ပြီ ✅\n❌ Channel ကထုတ်မရ — Member ကိုယ်တိုင် ထွက်ပြီးသားဖြစ်နိုင်",
                parse_mode='Markdown')
        else:
            await update.message.reply_text(f"❌ Kick မအောင်မြင်ပါ — စစ်ဆေးပါ")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

# ── Broker Helper ─────────────────────────────────────
def gen_broker_id() -> str:
    chars = string.ascii_uppercase + string.digits
    return 'B' + ''.join(random.choices(chars, k=4))

async def get_sheet_car_count() -> int:
    if not SHEET_WEBHOOK: return len(CARS)
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.post(SHEET_WEBHOOK,
                json={"action": "getCarsCount"}, timeout=8)
        return resp.json().get("count", len(CARS))
    except Exception:
        return len(CARS)

async def get_brokers() -> list:
    if not SHEET_WEBHOOK: return []
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.post(SHEET_WEBHOOK, json={"action":"getBrokers"}, timeout=10)
        return resp.json().get("brokers", [])
    except Exception as e:
        logger.error(f"getBrokers: {e}")
        return []

def get_broker_session_types(broker_tg_id: str) -> set:
    types = set()
    for sid, s in proxy_sessions.items():
        if str(s.get("brokerId","")) == broker_tg_id and s.get("status") == "ACTIVE":
            svc = s.get("serviceType", "search")
            types.add(svc)
    return types

def recalc_broker_status(broker_tg_id: str) -> str:
    types = get_broker_session_types(broker_tg_id)
    if not types:
        return "FREE"
    if "auction" in types and "search" in types:
        return "FULL"
    if "auction" in types:
        return "HAS_AUCTION"
    if "search" in types:
        return "HAS_SEARCH"
    return "FREE"

async def update_broker(telegram_id: str, **kwargs) -> bool:
    if not SHEET_WEBHOOK: return False
    try:
        payload = {"action": "updateBroker", "telegramId": telegram_id}
        payload.update(kwargs)
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.post(SHEET_WEBHOOK, json=payload, timeout=10)
        return resp.json().get("status") == "ok"
    except Exception as e:
        logger.error(f"updateBroker: {e}")
        return False

async def addbroker_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if ADMIN_IDS and user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Admin သာ သုံးနိုင်တယ်"); return
    if not context.args:
        await update.message.reply_text(
            "❌ Format: `/addbroker @username 123456789`\n"
            "ဥပမာ: `/addbroker @Ko_Aung 987654321`",
            parse_mode='Markdown'); return
    try:
        username  = context.args[0].replace("@","").strip()
        tg_id     = context.args[1].strip() if len(context.args) > 1 else ""
        if not tg_id.isdigit():
            await update.message.reply_text("❌ Telegram ID ဂဏန်းဖြစ်ရမည်"); return

        broker_id = gen_broker_id()
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.post(SHEET_WEBHOOK, json={
                "action":     "addBroker",
                "brokerId":   broker_id,
                "telegramId": tg_id,
                "username":   username,
            }, timeout=10)
        if resp.json().get("status") == "ok":
            try:
                await context.bot.send_message(
                    chat_id=int(tg_id),
                    text=(f"🎉 *Japan Auction Car Checker*\n\n"
                          f"✅ Broker အဖြစ် ထည့်သွင်းပြီ!\n\n"
                          f"🆔 Broker ID: `{broker_id}`\n\n"
                          f"အောက်က Button နှိပ်ပြီး စတင်ပါ 👇"),
                    parse_mode='Markdown',
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("👷 Broker စတင်ရန်", callback_data=f"brokerstart_{tg_id}")
                    ]]))
            except Exception as e:
                logger.error(f"addbroker DM: {e}")

            # ── Broker command scope ချက်ချင်း set ──
            try:
                _broker_cmds = [
                    BotCommand("start",          "🚗 Bot စတင်ရန်"),
                    BotCommand("carrequest",     "🚙 ကားလိုအပ်ပါက ဒီနေရာနှိပ်ပါ"),
                    BotCommand("mystatus",       "📋 Request Status စစ်ရန်"),
                    BotCommand("find",           "🔍 Chassis ဖြင့်ရှာရန်"),
                    BotCommand("model",          "🔎 Model အမည်ဖြင့်ရှာရန်"),
                    BotCommand("history",        "📈 ဈေးနှုန်း မှတ်တမ်းကြည့်ရန်"),
                    BotCommand("list",           "📊 ကားစာရင်း အားလုံးကြည့်ရန်"),
                    BotCommand("web",            "🌐 Web App link ကြည့်ရန်"),
                    BotCommand("renew",          "🔄 Membership သက်တမ်းတိုး"),
                    BotCommand("mypassword",     "🔑 Password ပြန်ယူရန်"),
                    BotCommand("redeem",         "🎁 Promo Code သုံးရန်"),
                    BotCommand("brokerstart",    "👷 Broker စတင်ရန်"),
                    BotCommand("available",      "🟢 Available ဖြစ်ကြောင်း"),
                    BotCommand("busy",           "🔴 Busy ဖြစ်ကြောင်း"),
                    BotCommand("accept",         "✅ Request လက်ခံရန်"),
                    BotCommand("endchat",        "🔚 Session ပိတ်ရန်"),
                    BotCommand("depositrequest", "💰 Customer ကို Deposit တောင်းရန်"),
                ]
                await context.bot.set_my_commands(
                    _broker_cmds,
                    scope=BotCommandScopeChat(chat_id=int(tg_id)))
            except Exception as e:
                logger.warning(f"addbroker set_commands: {e}")

            await update.message.reply_text(
                f"✅ *Broker ထည့်ပြီ*\n\n"
                f"👤 @{username}\n"
                f"🆔 ID: `{broker_id}`\n"
                f"📨 DM ပို့ပြီ — `/brokerstart` နှိပ်ဖို့ ပြောပြီ",
                parse_mode='Markdown')
        else:
            await update.message.reply_text("❌ Sheet error — ထပ်ကြိုးစားပါ")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

async def kickbroker_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if ADMIN_IDS and user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Admin သာ သုံးနိုင်တယ်"); return
    if not context.args:
        await update.message.reply_text(
            "❌ Format: `/kickbroker 123456789`",
            parse_mode='Markdown'); return
    try:
        tg_id = context.args[0].strip()
        if not tg_id.isdigit():
            await update.message.reply_text("❌ Telegram ID ဂဏန်းဖြစ်ရမည်"); return

        brokers = await get_brokers()
        broker = next((b for b in brokers if str(b.get("telegramId","")) == tg_id), None)
        if not broker:
            await update.message.reply_text(f"❌ Broker ID `{tg_id}` မရှိဘူး", parse_mode='Markdown'); return

        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.post(SHEET_WEBHOOK, json={
                "action":     "removeBroker",
                "telegramId": tg_id,
            }, timeout=10)

        if resp.json().get("status") == "ok":
            try:
                await context.bot.send_message(
                    chat_id=int(tg_id),
                    text="🚫 *Japan Auction Car Checker*\n\nသင်၏ Broker အကောင့် ပိတ်သိမ်းလိုက်ပါပြီ။\nAdmin ကို ဆက်သွယ်ပါ။",
                    parse_mode='Markdown')
            except Exception as e:
                logger.error(f"kickbroker DM: {e}")

            await update.message.reply_text(
                f"✅ *Broker ဖြတ်ပြီ*\n\n"
                f"👤 @{broker.get('username','?')}\n"
                f"🆔 TG ID: `{tg_id}`",
                parse_mode='Markdown')
        else:
            await update.message.reply_text("❌ Sheet error — ထပ်ကြိုးစားပါ")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

async def brokers_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if ADMIN_IDS and user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Admin သာ သုံးနိုင်တယ်"); return

    brokers = await get_brokers()
    if not brokers:
        await update.message.reply_text("👷 Broker မရှိသေးဘူး — `/addbroker` နဲ့ ထည့်ပါ", parse_mode='Markdown'); return

    free      = [b for b in brokers if b.get("status") == "FREE"]
    has_auc   = [b for b in brokers if b.get("status") == "HAS_AUCTION"]
    has_srch  = [b for b in brokers if b.get("status") == "HAS_SEARCH"]
    full      = [b for b in brokers if b.get("status") == "FULL"]
    other     = [b for b in brokers if b.get("status") not in ("FREE","HAS_AUCTION","HAS_SEARCH","FULL")]

    def badge(b):
        deals  = b.get("deals", 0)
        rating = b.get("rating", 0)
        if deals >= 20 and rating >= 4.5: return "🥇"
        if deals >= 10 and rating >= 3.5: return "🥈"
        return "🥉"

    def rating_stars(r):
        r = float(r) if r else 0
        return f"⭐{r:.1f}" if r > 0 else "🆕 New"

    txt = f"👷 *Broker List ({len(brokers)} ယောက်)*\n\n"
    if free:
        txt += "🟢 *FREE (ရနိုင်):*\n"
        for b in free:
            txt += f"  {badge(b)} #{b['brokerId']} @{b['username']} {rating_stars(b['rating'])} | Deals: {b.get('deals',0)}\n"
    if has_auc:
        txt += "\n🏆 *HAS AUCTION:*\n"
        for b in has_auc:
            txt += f"  {badge(b)} #{b['brokerId']} @{b['username']} {rating_stars(b['rating'])}\n"
    if has_srch:
        txt += "\n🔍 *HAS SEARCH:*\n"
        for b in has_srch:
            txt += f"  {badge(b)} #{b['brokerId']} @{b['username']} {rating_stars(b['rating'])}\n"
    if full:
        txt += "\n🔴 *FULL:*\n"
        for b in full:
            txt += f"  {badge(b)} #{b['brokerId']} @{b['username']} {rating_stars(b['rating'])}\n"
    if other:
        txt += "\n⚫ *Others:*\n"
        for b in other:
            txt += f"  #{b['brokerId']} @{b['username']} — {b.get('status','?')}\n"

    await update.message.reply_text(txt, parse_mode='Markdown')

async def brokerstart_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user    = update.effective_user
    user_id = str(user.id)

    brokers = await get_brokers()
    broker  = next((b for b in brokers if b.get("telegramId") == user_id), None)
    if not broker:
        await update.message.reply_text(
            "❌ Broker အဖြစ် မှတ်ပုံမတင်ရသေးဘူး\nAdmin ကို ဆက်သွယ်ပါ"); return

    broker_id = broker['brokerId']
    tc_text = (
        f"🤝 *Japan Auction Car Checker T&C*\n\n"
        f"🆔 Broker ID: `{broker_id}`\n\n"
        f"အောက်ပါ စည်ကမ်းများကို သဘောတူကြောင်း confirm လုပ်ပါ:\n\n"
        f"① တစ်ချိန်တည်း Customer ၁ ယောက်သာ\n"
        f"② Bot ထဲမှာပဲ ဆက်သွယ်ရမည်\n"
        f"③ Condition Report မှန်ကန်စွာ ပေးရမည်\n"
        f"④ Photo အနည်းဆုံး ၁၀ ပုံ ပေးရမည်\n"
        f"⑤ ကားနဲ့ ပတ်သက်ပြီး အမှားအယွင်း မဖြစ်အောင် လုပ်ဆောင်ပေးရမည်\n"
        f"⑥ အမှားအယွင်း ဖြစ်ပေါ်ပါက Admin စိစစ်၍ Admin ၏ အဆုံးအဖြတ်ကို လိုက်နာရမည်\n"
        f"⑦ Platform ပြင်ပ Deal = Lifetime Ban\n"
        f"⑧ Rating 1 × 3 = Permanent Ban\n\n"
        f"သဘောတူမတူ အောက်က Button နှိပ်ပါ 👇"
    )
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ သဘောတူပါတယ်",  callback_data=f"tc_agree_{user_id}"),
        InlineKeyboardButton("❌ သဘောမတူပါ",     callback_data=f"tc_disagree_{user_id}"),
    ]])
    await update.message.reply_text(tc_text, parse_mode='Markdown', reply_markup=kb)

async def available_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    brokers = await get_brokers()
    broker  = next((b for b in brokers if b.get("telegramId") == user_id), None)
    if not broker:
        await update.message.reply_text("❌ Broker မဟုတ်ဘူး"); return

    ok = await update_broker(user_id, status="FREE")
    if ok:
        await update.message.reply_text(
            f"🟢 *Available ဖြစ်ပြီ*\n\n🆔 #{broker['brokerId']}\nRequest လက်ခံနိုင်ပြီ ✅",
            parse_mode='Markdown')
    else:
        await update.message.reply_text("❌ Update မအောင်မြင်ပါ")

async def busy_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    brokers = await get_brokers()
    broker  = next((b for b in brokers if b.get("telegramId") == user_id), None)
    if not broker:
        await update.message.reply_text("❌ Broker မဟုတ်ဘူး"); return

    ok = await update_broker(user_id, status="BUSY")
    if ok:
        await update.message.reply_text(
            f"🔴 *Busy ဖြစ်ပြီ*\n\n🆔 #{broker['brokerId']}\nRequest အသစ် လက်မခံနိုင်တော့ဘူး",
            parse_mode='Markdown')
    else:
        await update.message.reply_text("❌ Update မအောင်မြင်ပါ")

# ── /carrequest ─────────────────────────────────────
REQ_STEPS = ["car_name","year","grade","budget","condition","timeline"]
REQ_LABELS = {
    "car_name":  "🚗 ကားအမည်",
    "year":      "📅 ထုတ်လုပ်သည့် နှစ်",
    "grade":     "🔧 Grade / Features",
    "budget":    "💰 Budget",
    "condition": "⭐ Condition",
    "timeline":  "⏳ Timeline",
}

async def carrequest_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user    = update.effective_user
    user_id = user.id
    str_uid = str(user_id)

    if not await is_active_member(user_id):
        await update.message.reply_text(
            "🔒 *Member များသာ သုံးနိုင်ပါသည်*\n\nMembership ရယူရန် /start နှိပ်ပါ",
            parse_mode='Markdown')
        return

    pkg = await get_member_package(user_id)
    if pkg == "PROMO10D" or (await check_promo10d_eligibility(str_uid)).get("active"):
        cancel_count = await get_cancel_count(str_uid)
        if cancel_count >= 2:
            await update.message.reply_text(
                "❌ *10 Day Promo — Request ကုန်သွားပြီ*\n\n"
                "Cancel ၂ ကြိမ် ပြည့်သောကြောင့် ထပ်မတင်နိုင်ပါ\n"
                "Membership ဝယ်ရန်: /start",
                parse_mode='Markdown')
            return

    existing_session = next(
        ((sid, s) for sid, s in proxy_sessions.items()
         if str(s.get("customerId","")) == str_uid and s.get("status") == "ACTIVE"),
        None
    )
    if existing_session:
        _, sess = existing_session
        await update.message.reply_text(
            f"⚠️ *Request တင်ပြီးသားရှိနေတယ်*\n\n"
            f"🆔 `{sess.get('reqId','')}`\n\n"
            f"Status စစ်ရန်: /mystatus\n"
            f"Cancel လုပ်ရန်: /cancelrequest",
            parse_mode='Markdown')
        return

    if user_id in pending_request:
        await update.message.reply_text(
            "⚠️ Request ဖြည်နေဆဲရှိတယ် — ဆက်ဖြည့်ပါ\nCancel လုပ်ရန်: /cancelrequest")
        return

    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ သဘောတူပါတယ်", callback_data=f"cust_tc_agree_{user_id}"),
        InlineKeyboardButton("❌ သဘောမတူပါ",    callback_data=f"cust_tc_disagree_{user_id}"),
    ]])
    await update.message.reply_text(
        "📜 *Japan Auction Car Checker*\n"
        "*— Customer စည်းကမ်းချက်များ —*\n\n"
        "① Customer အနေဖြင့် ကားဝယ်ယူရန် သေချာမှသာ "
        "*ကားရှာမည်* ကို နှိပ်ပေးပါ\n\n"
        "② Customer အနေဖြင့် မိမိ၏ လိုအပ်ချက်များကို "
        "Broker အား အသေးစိတ် ပြောပြပေးပါ\n\n"
        "③ ကားယူပြီး *Cancel မလုပ်ဖို့* မေတ္တာရပ်ခံပါသည်\n\n"
        "④ ဆက်သွယ်ရာတွင် *စာသား* ဖြင့် အဓိက ဆက်သွယ်ပေးစေချင်ပါသည် — "
        "အမှားအယွင်း ဖြစ်ပါက သက်သေအဖြစ် ပြသနိုင်ရန်\n\n"
        "⑤ ကားဝယ်ယူရာတွင် အမှားအယွင်း ဖြစ်ပေါ်လာပါက "
        "Admin ၏ စိစစ်ချက်ကို လက်ခံပေးရမည် ဖြစ်ပါသည်\n\n"
        "သဘောတူမတူ အောက်က Button နှိပ်ပါ 👇",
        parse_mode='Markdown',
        reply_markup=kb)

async def cancelrequest_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user    = update.effective_user
    user_id = update.effective_user.id
    str_uid = str(user_id)

    if user_id in pending_request:
        pending_request.pop(user_id)
        await update.message.reply_text("❌ Request ပယ်ဖျက်ပြီ")
        return

    session_data = next(
        ((sid, s) for sid, s in proxy_sessions.items()
         if str(s.get("customerId","")) == str_uid and s.get("status") == "ACTIVE"),
        None
    )

    if not session_data:
        await update.message.reply_text(
            "❌ Active request မရှိဘူး\n\n"
            "ကားတောင်းဆိုရန်: /carrequest")
        return

    sid, session = session_data
    req_id       = session.get("reqId", sid)

    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            dep_resp = await client.post(SHEET_WEBHOOK, json={
                "action": "getDeposit",
                "reqId":  req_id,
            }, timeout=10)
        dep = dep_resp.json()
        if dep.get("status") == "ok" and dep.get("depositStatus") in ("HOLD","WON"):
            await update.message.reply_text(
                f"🚫 *Cancel မလုပ်နိုင်ပါ*\n\n"
                f"🆔 `{req_id}`\n\n"
                f"Deposit ฿20,000 ပေးပြီးသောကြောင့်\n"
                f"Cancel လုပ်ခွင့် မရှိတော့ပါ",
                parse_mode='Markdown')
            return
    except Exception as e:
        logger.error(f"cancelrequest deposit check: {e}")

    cancel_count = 0
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            count_resp = await client.post(SHEET_WEBHOOK, json={
                "action": "getCancelCount",
                "userId": str_uid,
            }, timeout=10)
        cancel_count = count_resp.json().get("cancelCount", 0)
    except Exception as e:
        logger.error(f"getCancelCount: {e}")

    new_count = cancel_count + 1

    proxy_sessions.pop(sid, None)
    cancel_request_timer(req_id)
    cancel_auction_dep_timer(req_id)
    broker_tg_id = session.get("brokerId","")
    broker_obj   = session.get("brokerObj", {})
    broker_id    = broker_obj.get("brokerId","B???")

    if broker_tg_id:
        await update_broker(broker_tg_id, status="FREE")

    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            await client.post(SHEET_WEBHOOK, json={
                "action":      "saveCancelCount",
                "userId":      str_uid,
                "cancelCount": new_count,
                "reqId":       req_id,
            }, timeout=10)
            await client.post(SHEET_WEBHOOK, json={
                "action": "updateRequest",
                "reqId":  req_id,
                "status": "CANCELLED_BY_CUSTOMER",
            }, timeout=10)
    except Exception as e:
        logger.error(f"saveCancelCount: {e}")

    if new_count >= 3:
        ban_expire = (datetime.now() + timedelta(days=30)).strftime("%d/%m/%Y")
        try:
            async with httpx.AsyncClient(follow_redirects=True) as client:
                await client.post(SHEET_WEBHOOK, json={
                    "action":    "banCustomer",
                    "userId":    str_uid,
                    "banExpire": ban_expire,
                }, timeout=10)
        except Exception as e:
            logger.error(f"banCustomer: {e}")

        await update.message.reply_text(
            f"🚨 *Account ယာယီ Ban ဖြစ်ပြီ*\n\n"
            f"Cancel {new_count} ကြိမ် ရောက်သောကြောင့်\n"
            f"🗓 Ban ကုန်ဆုံးရက်: `{ban_expire}`",
            parse_mode='Markdown')

        await notify_admins(context,
            f"🚨 *Customer Temp Ban*\n\n"
            f"👤 {user.first_name} (`{user_id}`)\n"
            f"🆔 `{req_id}`\n"
            f"📊 Cancel: {new_count}")

    elif new_count == 2:
        await update.message.reply_text(
            f"⚠️ *Cancel ၂ ကြိမ် ပြည့်ပြီ*\n\n"
            f"🆔 `{req_id}`\n\n"
            f"⚠️ ထပ် cancel ရင် 30 ရက် Ban\n\n"
            f"/carrequest ပြန်တင်နိုင်",
            parse_mode='Markdown')

    else:
        await update.message.reply_text(
            f"❌ *Request Cancel ပြီ*\n\n"
            f"🆔 `{req_id}`\n\n"
            f"📊 Cancel: {new_count}/3\n\n"
            f"ပြန်တင်ရန်: /carrequest",
            parse_mode='Markdown')

    if broker_tg_id:
        try:
            await context.bot.send_message(
                chat_id=int(broker_tg_id),
                text=(f"❌ *Customer Cancel*\n\n🆔 `{req_id}`\n🟢 FREE ဖြစ်ပြီ"),
                parse_mode='Markdown')
        except Exception as e:
            logger.error(f"cancel broker notify: {e}")


async def handle_request_qa(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user    = update.effective_user
    user_id = user.id
    if user_id not in pending_request: return False

    text = update.message.text.strip()
    req  = pending_request[user_id]
    step = req["step"]

    if step == 3 and not req["data"].get("budget"):
        return False

    req["data"][REQ_STEPS[step]] = text
    step += 1
    req["step"] = step

    if step == 1:
        await update.message.reply_text(
            "📅 *ထုတ်လုပ်သည့် နှစ်*\n\nFormat: `2014` သို့ `2018-2022`\nမသိရင်: `any`",
            parse_mode='Markdown')
    elif step == 2:
        await update.message.reply_text(
            "🔧 *Grade / Features*\n\nဥပမာ: `20X, Alloy, DVD`\nမသတ်မှတ်ရင်: `any`",
            parse_mode='Markdown')
    elif step == 3:
        kb = [
            [InlineKeyboardButton("฿50,000",  callback_data="req_budget_50000"),
             InlineKeyboardButton("฿100,000", callback_data="req_budget_100000")],
            [InlineKeyboardButton("฿150,000", callback_data="req_budget_150000"),
             InlineKeyboardButton("฿200,000", callback_data="req_budget_200000")],
            [InlineKeyboardButton("฿250,000", callback_data="req_budget_250000"),
             InlineKeyboardButton("฿300,000", callback_data="req_budget_300000")],
        ]
        await update.message.reply_text(
            "💰 *Budget ရွေးပါ*", parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(kb))
    elif step == 4:
        kb = [
            [InlineKeyboardButton("⭐",        callback_data="req_cond_1"),
             InlineKeyboardButton("⭐⭐",       callback_data="req_cond_2"),
             InlineKeyboardButton("⭐⭐⭐",      callback_data="req_cond_3")],
            [InlineKeyboardButton("⭐⭐⭐⭐",     callback_data="req_cond_4"),
             InlineKeyboardButton("⭐⭐⭐⭐⭐",    callback_data="req_cond_5")],
        ]
        await update.message.reply_text(
            "⭐ *Condition ရွေးပါ*",
            parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(kb))
    elif step == 5:
        kb = [
            [InlineKeyboardButton("🔥 ၃ ရက်",    callback_data="req_time_3days"),
             InlineKeyboardButton("📅 ၁ ပတ်",   callback_data="req_time_1week")],
            [InlineKeyboardButton("🗓 ၁ လ",     callback_data="req_time_1month"),
             InlineKeyboardButton("⏳ ရမှပြောမည်", callback_data="req_time_open")],
        ]
        await update.message.reply_text(
            "⏳ *Timeline ရွေးပါ*", parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(kb))

    return True

async def finish_request(update_or_query, context, user_id: int):
    req  = pending_request.get(user_id)
    if not req: return
    d    = req["data"]
    txt  = (
        f"📋 *Request Summary*\n"
        f"{'─'*24}\n"
        f"🚗 ကား: *{d.get('car_name','—')}*\n"
        f"📅 နှစ်: {d.get('year','—')}\n"
        f"🔧 Grade: {d.get('grade','—')}\n"
        f"💰 Budget: {d.get('budget','—')}\n"
        f"⭐ Condition: {d.get('condition','—')}\n"
        f"⏳ Timeline: {d.get('timeline','—')}\n"
        f"{'─'*24}\n\n"
        f"အတည်ပြုမည်လား?"
    )
    kb = [[
        InlineKeyboardButton("✅ အတည်ပြု", callback_data="req_confirm"),
        InlineKeyboardButton("✏️ ပြင်မည်",  callback_data="req_cancel"),
    ]]
    if hasattr(update_or_query, 'message'):
        await update_or_query.message.reply_text(txt, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(kb))
    else:
        await update_or_query.edit_message_text(txt, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(kb))

async def submit_request(context, user_id: int, username: str):
    req = pending_request.pop(user_id, None)
    if not req: return

    d      = req["data"]
    svc_prefix = 'A' if d.get("service_type") == "auction" else 'R'
    req_id = svc_prefix + ''.join(random.choices(string.digits, k=6))

    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            await client.post(SHEET_WEBHOOK, json={
                "action":     "addRequest",
                "reqId":      req_id,
                "customerId": str(user_id),
                "username":   username,
                "carType":    "Auction" if d.get("service_type") == "auction" else "Search",
                "budget":     d.get("budget",""),
                "year":       d.get("year",""),
                "grade":      d.get("grade",""),
                "condition":  d.get("condition",""),
                "timeline":   d.get("timeline",""),
            }, timeout=10)
    except Exception as e:
        logger.error(f"submit_request: {e}")

    await context.bot.send_message(
        chat_id=user_id,
        text=(f"✅ *Request တင်ပြီ!*\n\n"
              f"🆔 Request ID: `{req_id}`\n"
              f"🚗 {d.get('car_name','')}\n"
              f"💰 {d.get('budget','')}\n\n"
              f"Broker က ရှာပေးမည် ⏳"),
        parse_mode='Markdown')

    brokers    = await get_brokers()
    svc_type   = d.get("service_type", "search")

    eligible_brokers = []
    for b in brokers:
        if b.get("status") in ("BANNED", "KICKED"): continue
        tg_id       = str(b.get("telegramId",""))
        active_types = get_broker_session_types(tg_id)
        if svc_type in active_types: continue
        if len(active_types) >= 2:   continue
        eligible_brokers.append(b)

    for b in eligible_brokers:
        try:
            btn_label = "🏆 Auction Order လက်ခံမည်" if svc_type == "auction" else "🔍 ကားရှာ Order လက်ခံမည်"
            req_kb = InlineKeyboardMarkup([[
                InlineKeyboardButton(btn_label,    callback_data=f"breq_accept_{req_id}"),
                InlineKeyboardButton("❌ ငြင်းမည်", callback_data=f"breq_decline_{req_id}"),
            ]])
            svc_header = (
                "🏆 *AUCTION CAR ORDER*\n━━━━━━━━━━━━━━\nDeposit ฿20,000 လိုအပ်မည်"
                if svc_type == "auction" else
                "🔍 *ကားရှာ ORDER*\n━━━━━━━━━━━━━━\nအပြင်ကား ရှာပေးရန်"
            )
            await context.bot.send_message(
                chat_id=int(b["telegramId"]),
                text=(f"🔔 *Order အသစ်တက်လာပြီ!*\n\n"
                      f"{svc_header}\n\n"
                      f"🆔 `{req_id}`\n"
                      f"🚘 *{d.get('car_name','')}*\n"
                      f"📅 နှစ်: {d.get('year','')}\n"
                      f"🔧 Grade: {d.get('grade','')}\n"
                      f"💰 Budget: {d.get('budget','')}\n"
                      f"⭐ Condition: {d.get('condition','')}\n"
                      f"⏳ Timeline: {d.get('timeline','')}"),
                parse_mode='Markdown',
                reply_markup=req_kb)
        except Exception as e:
            logger.error(f"notify broker {b['brokerId']}: {e}")

    await notify_admins(context,
        f"📥 *Request အသစ်*\n\n"
        f"🆔 `{req_id}`\n"
        f"📌 {'🏆 လေလံ' if d.get('service_type') == 'auction' else '🔍 ကားရှာ'}\n"
        f"👤 @{username}\n"
        f"🚘 {d.get('car_name','')}\n"
        f"💰 {d.get('budget','')}")

async def mystatus_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    str_uid = str(user_id)

    if not await is_active_member(user_id):
        await update.message.reply_text(
            "🔒 Member များသာ သုံးနိုင်ပါသည်",
            parse_mode='Markdown')
        return

    session_data = next(
        ((sid, s) for sid, s in proxy_sessions.items()
         if str(s.get("customerId","")) == str_uid and s.get("status") == "ACTIVE"),
        None
    )

    if session_data:
        sid, sess    = session_data
        req_id       = sess.get("reqId", sid)
        broker_obj   = sess.get("brokerObj", {})
        broker_id    = broker_obj.get("brokerId", "?")
        await update.message.reply_text(
            f"📋 *Request Status*\n\n"
            f"🆔 `{req_id}`\n"
            f"🤝 *MATCHED*\n"
            f"👷 Broker: #{broker_id}",
            parse_mode='Markdown')
        return

    if user_id in pending_request:
        step = pending_request[user_id].get("step", 0)
        await update.message.reply_text(
            f"📋 Request ဖြည်နေဆဲ ({step}/{len(REQ_STEPS)})")
        return

    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.post(SHEET_WEBHOOK, json={
                "action":     "getMyRequests",
                "customerId": str_uid,
            }, timeout=10)
        data     = resp.json()
        requests = data.get("requests", [])
        if requests:
            latest = requests[0]
            req_id = latest.get("reqId", "?")
            status = latest.get("status", "?")
            await update.message.reply_text(
                f"📋 *Request မှတ်တမ်း*\n\n"
                f"🆔 `{req_id}`\n"
                f"🚗 {latest.get('carType','')}\n"
                f"📊 {status}",
                parse_mode='Markdown')
            return
    except Exception as e:
        logger.error(f"mystatus: {e}")

    await update.message.reply_text("📋 Request မရှိ — /carrequest")

async def accept_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user    = update.effective_user
    user_id = str(user.id)

    brokers = await get_brokers()
    broker  = next((b for b in brokers if b.get("telegramId") == user_id), None)
    if not broker:
        await update.message.reply_text("❌ Broker မဟုတ်ဘူး"); return

    if broker.get("status") == "BANNED":
        await update.message.reply_text("🚫 Account ပိတ်သိမ်းထားပြီ"); return

    if not context.args:
        await update.message.reply_text("❌ Format: `/accept R123456`", parse_mode='Markdown'); return

    req_id = context.args[0].strip().upper()

    customer_id = None
    customer_username = ""
    req_data = {}
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.post(SHEET_WEBHOOK, json={
                "action": "getRequest",
                "reqId":  req_id,
            }, timeout=10)
        rdata = resp.json()
        if rdata.get("status") == "ok":
            customer_id       = rdata.get("customerId")
            customer_username = rdata.get("username","")
            req_data          = rdata
        else:
            await update.message.reply_text(f"❌ Request `{req_id}` မတွေ့ဘူး", parse_mode='Markdown')
            return
    except Exception as e:
        logger.error(f"accept getRequest: {e}")
        await update.message.reply_text("❌ Sheet error"); return

    svc_type     = "auction" if req_data.get("carType","").lower() == "auction" else "search"
    active_types = get_broker_session_types(user_id)
    if svc_type in active_types:
        await update.message.reply_text("❌ Session တူ ရှိပြီးသား")
        return
    if len(active_types) >= 2:
        await update.message.reply_text("❌ Order ၂ ခု ပြည့်နေပြီ")
        return

    new_status = "FULL" if (svc_type == "auction" and "search" in active_types) or (svc_type == "search" and "auction" in active_types) else ("HAS_AUCTION" if svc_type == "auction" else "HAS_SEARCH")
    await update_broker(user_id, status=new_status)

    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            await client.post(SHEET_WEBHOOK, json={
                "action":   "updateRequest",
                "reqId":    req_id,
                "status":   "MATCHED",
                "brokerId": broker["brokerId"],
            }, timeout=10)
    except Exception as e:
        logger.error(f"accept updateRequest: {e}")

    proxy_sessions[req_id] = {
        "customerId":       customer_id,
        "customerUsername": customer_username,
        "brokerId":         user_id,
        "brokerObj":        broker,
        "reqId":            req_id,
        "status":           "ACTIVE",
        "serviceType":      svc_type,
        "startTime":        datetime.now().isoformat(),
    }

    svc_label_accept = "🏆 လေလံ" if svc_type == "auction" else "🔍 ကားရှာ"
    await update.message.reply_text(
        f"✅ *Accept ပြီ!*\n\n🆔 `{req_id}`\n📌 {svc_label_accept}",
        parse_mode='Markdown')

    if customer_id:
        try:
            await context.bot.send_message(
                chat_id=int(customer_id),
                text=(f"🎉 *Broker ရှာပေးနေပြီ!*\n\n🆔 `{req_id}`\n👷 Broker #{broker['brokerId']}"),
                parse_mode='Markdown')
        except Exception as e:
            logger.error(f"accept customer notify: {e}")

    await notify_admins(context,
        f"🤝 *Broker Accept*\n\n🆔 `{req_id}`\n👷 #{broker['brokerId']}")

    start_request_timer(
        context, req_id=req_id, broker_tg_id=user_id,
        broker_id=broker["brokerId"],
        customer_id=str(customer_id) if customer_id else "")

    if svc_type == "auction":
        start_auction_dep_timer(
            context, req_id=req_id,
            customer_id=str(customer_id) if customer_id else "",
            broker_tg_id=user_id, broker_id=broker["brokerId"],
            username=customer_username)

    svc_label_track = "🏆 Auction" if svc_type == "auction" else "🔍 ကားရှာ"
    await update.message.reply_text(
        f"📦 *Status Tracking — {svc_label_track}*\n\n🆔 `{req_id}`",
        parse_mode='Markdown',
        reply_markup=get_tracking_keyboard(svc_type, req_id))

async def endchat_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    brokers = await get_brokers()
    broker  = next((b for b in brokers if b.get("telegramId") == user_id), None)
    if not broker:
        await update.message.reply_text("❌ Broker မဟုတ်ဘူး"); return

    req_id = context.args[0].strip().upper() if context.args else ""
    if not req_id:
        await update.message.reply_text(
            "❌ Format: `/endchat R123456`", parse_mode='Markdown'); return

    if req_id not in proxy_sessions:
        await update.message.reply_text(
            f"❌ `{req_id}` Session မတွေ့ပါ",
            parse_mode='Markdown'); return

    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ ဟုတ်ကဲ့ — ပိတ်မည်",  callback_data=f"endchat_yes_{req_id}"),
        InlineKeyboardButton("❌ မပိတ်သေးဘူး",         callback_data=f"endchat_no_{req_id}"),
    ]])
    await update.message.reply_text(
        f"⚠️ *Session ပိတ်တော့မည်*\n\n🆔 `{req_id}`\n\nသေချာပြီလား?",
        parse_mode='Markdown', reply_markup=kb)


# ── Promo Code ────────────────────────────────────────
def parse_promo_codes() -> dict:
    codes = {}
    if not PROMO_CODES_RAW:
        return codes
    for entry in PROMO_CODES_RAW.split(','):
        parts = entry.strip().split(':')
        if len(parts) >= 2:
            code     = parts[0].strip().upper()
            days     = int(parts[1]) if parts[1].isdigit() else 30
            max_uses = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 40
            codes[code] = {"days": days, "max_uses": max_uses}
    return codes

async def redeem_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user    = update.effective_user
    user_id = user.id

    if not context.args:
        await update.message.reply_text(
            "🎁 *Promo Code သုံးရန်*\n\n`/redeem CODE`\nဥပမာ: `/redeem TIKTOK30`",
            parse_mode='Markdown')
        return

    code     = context.args[0].strip().upper()
    username = user.username or user.first_name or str(user_id)

    await update.message.reply_text("🔍 Code စစ်ဆေးနေတယ်... ⏳")

    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp   = await client.post(SHEET_WEBHOOK, json={
                "action": "redeemPromo",
                "code":   code,
                "userId": str(user_id),
            }, timeout=15)
        result = resp.json()
    except Exception as e:
        logger.error(f"redeemPromo: {e}")
        await update.message.reply_text("❌ Server error — ခဏကြိုးစားပါ")
        return

    status = result.get("status")

    if status == "error":
        msg_map = {
            "invalid_code":  "❌ *Code မမှန်ကန်ပါ*\n\nAdmin ထံမှ မှန်ကန်သော Code ယူပါ",
            "already_used":  "❌ *Code ကို တစ်ကြိမ်သာ သုံးနိုင်ပါသည်*\n\nဤ Code ကို သင် ရှိပြီးသား သုံးထားပါသည်",
            "max_reached":   f"❌ *Code ကုန်ဆုံးပြီ*\n\n{result.get('used',0)}/{result.get('max',0)} ဦး သုံးပြီးပါပြီ",
            "no_sheet":      "❌ System error — Admin ကို ဆက်သွယ်ပါ",
        }
        msg = msg_map.get(result.get("msg",""), "❌ Code မမှန်ကန်ပါ")
        await update.message.reply_text(msg, parse_mode='Markdown')
        return

    days       = result.get("days", 30)
    used       = result.get("used", 0)
    max_uses   = result.get("max", 40)
    remaining  = max_uses - used
    pkg        = result.get("package", "WEB").upper()

    if pkg == "WEB":
        member_pkg = "WEB-PROMO"
        pkg_label  = "🌐 Web + Channel"
    else:
        member_pkg = "CH-PROMO"
        pkg_label  = "📱 Channel Only"

    password   = generate_password()
    await save_member_to_sheet(str(user_id), username, days, password, member_pkg)
    invite_url = await create_invite_link(context, days)
    await send_approval_dm(context, user_id, days // 30, password, invite_url, package=pkg)

    await update.message.reply_text(
        f"🎉 *Promo Code အောင်မြင်!*\n\n"
        f"{pkg_label} Membership *{days} ရက်* ရပါပြီ\n"
        f"🔑 Password DM ပို့ပြီ\n\n"
        f"🙏 ကျေးဇူးတင်ပါသည်",
        parse_mode='Markdown')

    await notify_admins(context,
        f"🎁 *Promo Redeemed!*\n\n"
        f"👤 @{username} (ID: `{user_id}`)\n"
        f"🏷 Code: `{code}`\n"
        f"📅 {days} ရက်\n"
        f"📊 သုံးပြီး: {used}/{max_uses}\n"
        f"🔢 ကျန်: {remaining}")

# ── Auto Timer ───────────────────────────────────────
async def request_timer_task(context, req_id: str, broker_tg_id: str,
                              broker_id: str, customer_id: str):
    try:
        await asyncio.sleep(4 * 3600)

        if req_id not in proxy_sessions:
            return

        broker_msg = (
            f"⏰ *4 နာရီ Reminder*\n\n"
            f"🆔 Request: `{req_id}`\n\n"
            f"Customer ကို ကားရှာပေးနေပြီ ၄ နာရီကျော်ပြီ\n"
            f"Update တစ်ခုခု ပေးဖို့ မမေ့ပါနဲ့ 📞\n\n"
            f"ပြီးရင်: `/endchat {req_id}`"
        )
        try:
            await context.bot.send_message(
                chat_id=int(broker_tg_id),
                text=broker_msg,
                parse_mode='Markdown')
        except Exception as e:
            logger.error(f"timer 4hr broker: {e}")

        await notify_admins(context,
            f"⏰ *4hr Reminder*\n\n"
            f"🆔 `{req_id}`\n"
            f"👷 Broker #{broker_id} — 4 နာရီကျော်ပြီ\n"
            f"Session ဆက်ဖွင့်နေဆဲ")

        await asyncio.sleep(20 * 3600)

        if req_id not in proxy_sessions:
            return

        proxy_sessions.pop(req_id, None)
        active_timers.pop(req_id, None)

        await update_broker(broker_tg_id, status="FREE")

        try:
            async with httpx.AsyncClient(follow_redirects=True) as client:
                await client.post(SHEET_WEBHOOK, json={
                    "action": "updateRequest",
                    "reqId":  req_id,
                    "status": "CANCELLED_TIMEOUT",
                }, timeout=10)
        except Exception as e:
            logger.error(f"timer cancel sheet: {e}")

        try:
            await context.bot.send_message(
                chat_id=int(broker_tg_id),
                text=(f"⚠️ *Request Auto Cancel ဖြစ်ပြီ*\n\n"
                      f"🆔 `{req_id}`\n"
                      f"24 နာရီ အတွင်း မပြီးဆုံးတဲ့အတွက် ပိတ်လိုက်ပြီ\n\n"
                      f"🟢 Status: FREE ဖြစ်ပြီ"),
                parse_mode='Markdown')
        except Exception as e:
            logger.error(f"timer 24hr broker: {e}")

        if customer_id:
            try:
                await context.bot.send_message(
                    chat_id=int(customer_id),
                    text=(f"⚠️ *Request ပိတ်သွားပြီ*\n\n"
                          f"🆔 `{req_id}`\n"
                          f"24 နာရီ အတွင်း ကားမရသောကြောင့် Request ပိတ်ပြီ\n\n"
                          f"ပြန်တင်ရန်: /carrequest 🙏"),
                    parse_mode='Markdown')
            except Exception as e:
                logger.error(f"timer 24hr customer: {e}")

        await notify_admins(context,
            f"🚨 *Request Auto Cancel (24hr timeout)*\n\n"
            f"🆔 `{req_id}`\n"
            f"👷 Broker #{broker_id} → FREE\n"
            f"👤 Customer: `{customer_id}`")

    except asyncio.CancelledError:
        logger.info(f"Timer cancelled for {req_id}")
    except Exception as e:
        logger.error(f"request_timer_task: {e}")


def start_request_timer(context, req_id: str, broker_tg_id: str,
                         broker_id: str, customer_id: str):
    if req_id in active_timers:
        active_timers[req_id].cancel()

    task = asyncio.create_task(
        request_timer_task(context, req_id, broker_tg_id, broker_id, customer_id)
    )
    active_timers[req_id] = task


def cancel_request_timer(req_id: str):
    task = active_timers.pop(req_id, None)
    if task:
        task.cancel()


# ── Auction Deposit 48hr Timer ────────────────────────
async def _auction_dep_timer_task(context, req_id: str, customer_id: str,
                                   broker_tg_id: str, broker_id: str, username: str):
    await asyncio.sleep(48 * 3600)

    session = proxy_sessions.get(req_id)
    if session and session.get("deposit_paid", False):
        auction_dep_timers.pop(req_id, None)
        return

    ban_count = 0
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.post(SHEET_WEBHOOK, json={
                "action":     "getAuctionCancelCount",
                "customerId": customer_id,
            }, timeout=10)
        ban_count = resp.json().get("banCount", 0)
    except Exception as e:
        logger.error(f"getAuctionCancelCount timer: {e}")

    new_ban_count = ban_count + 1
    if new_ban_count == 1:
        ban_expire = (datetime.now() + timedelta(days=7)).strftime("%d/%m/%Y")
        ban_status = "BAN_7D"
        ban_label  = f"⏳ 7 Day Auction Ban\n(ကုန်ဆုံးရက်: {ban_expire})"
    elif new_ban_count == 2:
        ban_expire = (datetime.now() + timedelta(days=30)).strftime("%d/%m/%Y")
        ban_status = "BAN_1M"
        ban_label  = f"⏳ 1 Month Auction Ban\n(ကုန်ဆုံးရက်: {ban_expire})"
    else:
        ban_expire = "LIFETIME"
        ban_status = "LIFETIME_BAN"
        ban_label  = "🚫 Lifetime Ban — Auction Car access ထာဝရပိတ်ပြီ"

    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            await client.post(SHEET_WEBHOOK, json={
                "action":     "saveAuctionCancel",
                "customerId": customer_id,
                "username":   username,
                "reqId":      req_id,
                "banCount":   new_ban_count,
                "banStatus":  ban_status,
                "banExpire":  ban_expire,
            }, timeout=10)
    except Exception as e:
        logger.error(f"saveAuctionCancel: {e}")

    proxy_sessions.pop(req_id, None)
    if broker_tg_id:
        await update_broker(broker_tg_id, status="FREE")

    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            await client.post(SHEET_WEBHOOK, json={
                "action": "updateRequest",
                "reqId":  req_id,
                "status": "CANCELLED_NO_DEPOSIT",
            }, timeout=10)
    except Exception as e:
        logger.error(f"auc_dep_timer updateRequest: {e}")

    try:
        await context.bot.send_message(
            chat_id=int(customer_id),
            text=(f"⏰ *Auction Deposit Timeout*\n\n"
                  f"🆔 `{req_id}`\n\n"
                  f"Deposit ฿20,000 ၂ ရက်အတွင်း မပေသောကြောင့်\n"
                  f"Request အလိုအလျောက် Cancel ဖြစ်သွားပြီ\n\n"
                  f"{ban_label}"),
            parse_mode='Markdown')
    except Exception as e:
        logger.error(f"auc_dep_timer customer notify: {e}")

    if broker_tg_id:
        try:
            await context.bot.send_message(
                chat_id=int(broker_tg_id),
                text=(f"⏰ *Auction Deposit Timeout*\n\n"
                      f"🆔 `{req_id}`\n"
                      f"Customer Deposit မပေဘဲ ၂ ရက် ကြာသောကြောင့် Auto Cancel ဖြစ်ပြီ\n\n"
                      f"🟢 FREE ဖြစ်ပြီ — Request အသစ် လက်ခံနိုင်ပြီ"),
                parse_mode='Markdown')
        except Exception as e:
            logger.error(f"auc_dep_timer broker notify: {e}")

    await notify_admins(context,
        f"⏰ *Auction Deposit Timeout Auto Cancel*\n\n"
        f"🆔 `{req_id}`\n"
        f"👤 Customer: `{customer_id}`\n"
        f"📊 Ban Count: {new_ban_count} → {ban_status}\n"
        f"🗓 {ban_expire}")

    auction_dep_timers.pop(req_id, None)


def start_auction_dep_timer(context, req_id: str, customer_id: str,
                             broker_tg_id: str, broker_id: str, username: str = ""):
    if req_id in auction_dep_timers:
        auction_dep_timers[req_id].cancel()
    task = asyncio.create_task(
        _auction_dep_timer_task(context, req_id, customer_id, broker_tg_id, broker_id, username)
    )
    auction_dep_timers[req_id] = task


def cancel_auction_dep_timer(req_id: str):
    task = auction_dep_timers.pop(req_id, None)
    if task:
        task.cancel()


# ── /depositrequest (Broker only) ────────────────────
async def depositrequest_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    brokers = await get_brokers()
    broker  = next((b for b in brokers if b.get("telegramId") == user_id), None)
    if not broker:
        await update.message.reply_text("❌ Broker မဟုတ်ဘူး")
        return

    session = next(
        ((sid, s) for sid, s in proxy_sessions.items()
         if str(s.get("brokerId","")) == user_id and s.get("status") == "ACTIVE"),
        None
    )
    if not session:
        await update.message.reply_text(
            "❌ Active session မရှိဘူး\nCustomer နဲ့ chat ဖွင့်ပြီးမှ တောင်းပါ")
        return

    sid, sess   = session
    customer_id = sess.get("customerId")
    req_id      = sess.get("reqId", sid)

    if not customer_id:
        await update.message.reply_text("❌ Customer ID မတွေ့ပါ")
        return

    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "💰 ကားဝယ်ယူရန် (Deposit ฿20,000)",
            callback_data=f"dep_start_{req_id}_{user_id}")
    ]])
    try:
        await context.bot.send_message(
            chat_id=int(customer_id),
            text=(f"🚗 *ကားဝယ်ယူရန် Deposit*\n\n"
                  f"🆔 Request: `{req_id}`\n\n"
                  f"Broker က Deposit ฿20,000 တောင်းနေပြီ\n"
                  f"ဆက်လုပ်ရန် အောက်ပါ button နှိပ်ပါ 👇"),
            parse_mode='Markdown',
            reply_markup=kb)
        await update.message.reply_text("✅ Customer ဆီ Deposit request ပို့ပြီ")
    except Exception as e:
        logger.error(f"depositrequest: {e}")
        await update.message.reply_text("❌ Customer ကို မပို့နိုင်ဘူး")


# ── /auctionwon (Admin only) ──────────────────────────
async def auctionwon_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Admin သာ သုံးနိုင်တယ်")
        return
    if not context.args:
        await update.message.reply_text(
            "❌ Format: `/auctionwon R123456 [ကားဖိုး]`\n"
            "ဥပမာ: `/auctionwon R001234 150000`",
            parse_mode='Markdown')
        return

    req_id = context.args[0].strip().upper()

    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.post(SHEET_WEBHOOK, json={
                "action": "getDeposit",
                "reqId":  req_id,
            }, timeout=10)
        dep = resp.json()
    except Exception as e:
        logger.error(f"auctionwon getDeposit: {e}")
        await update.message.reply_text("❌ Sheet error")
        return

    if dep.get("status") != "ok":
        await update.message.reply_text(f"❌ `{req_id}` Deposit မတွေ့ပါ", parse_mode='Markdown')
        return

    customer_id  = dep.get("customerId")
    broker_tg_id = dep.get("brokerTgId")
    thb_amount   = dep.get("thbAmount", 20000)
    car_price    = int(context.args[1]) if len(context.args) > 1 else 0
    remaining    = car_price - thb_amount if car_price else 0

    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            await client.post(SHEET_WEBHOOK, json={
                "action":        "updateDeposit",
                "reqId":         req_id,
                "auctionResult": "WON",
                "carPrice":      car_price,
            }, timeout=10)
    except Exception as e:
        logger.error(f"auctionwon updateDeposit: {e}")

    if customer_id:
        try:
            msg = (f"🏆 *ကားရပြီ!*\n\n"
                   f"🆔 Request: `{req_id}`\n\n"
                   f"💰 Deposit: ฿{thb_amount:,} (ကားဖိုးထဲ ထည့်တွက်ပြီ)\n")
            if car_price:
                msg += (f"🚗 ကားဖိုး: ฿{car_price:,}\n"
                        f"💵 ကျန်ပေးရမည်: ฿{remaining:,} + Commission\n\n")
            msg += "Admin မှ ကျန်ငွေ + Commission တောင်းပါမည် 📞"
            await context.bot.send_message(
                chat_id=int(customer_id), text=msg, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"auctionwon customer: {e}")

    if broker_tg_id:
        try:
            await context.bot.send_message(
                chat_id=int(broker_tg_id),
                text=(f"🏆 *Auction Won!*\n\n"
                      f"🆔 `{req_id}`\n"
                      f"Customer ကို ကျန်ငွေ တောင်းဆိုပြီ ✅"),
                parse_mode='Markdown')
        except Exception as e:
            logger.error(f"auctionwon broker: {e}")

    await update.message.reply_text(
        f"✅ *Auction Won မှတ်တမ်းတင်ပြီ*\n\n"
        f"🆔 `{req_id}`\n"
        f"💰 Deposit ฿{thb_amount:,} ကားဖိုးထဲ ထည့်တွက်ပြီ\n"
        + (f"💵 ကျန်ငွေ: ฿{remaining:,} + Commission" if car_price else ""),
        parse_mode='Markdown')


async def auctionlost_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Admin သာ သုံးနိုင်တယ်")
        return
    if not context.args:
        await update.message.reply_text(
            "❌ Format: `/auctionlost R123456`",
            parse_mode='Markdown')
        return

    req_id = context.args[0].strip().upper()

    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.post(SHEET_WEBHOOK, json={
                "action": "getDeposit",
                "reqId":  req_id,
            }, timeout=10)
        dep = resp.json()
    except Exception as e:
        logger.error(f"auctionlost getDeposit: {e}")
        await update.message.reply_text("❌ Sheet error")
        return

    if dep.get("status") != "ok":
        await update.message.reply_text(f"❌ `{req_id}` Deposit မတွေ့ပါ", parse_mode='Markdown')
        return

    customer_id  = dep.get("customerId")
    broker_tg_id = dep.get("brokerTgId")
    mmk_amount   = dep.get("mmkAmount", 0)
    thb_amount   = dep.get("thbAmount", 20000)

    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            await client.post(SHEET_WEBHOOK, json={
                "action":        "updateDeposit",
                "reqId":         req_id,
                "auctionResult": "LOST",
            }, timeout=10)
    except Exception as e:
        logger.error(f"auctionlost updateDeposit: {e}")

    if customer_id:
        try:
            await context.bot.send_message(
                chat_id=int(customer_id),
                text=(f"😔 *ကားမရဘူး*\n\n"
                      f"🆔 Request: `{req_id}`\n\n"
                      f"💰 Deposit ฿{thb_amount:,}\n"
                      f"💵 ပြန်ပေးမည်: *{mmk_amount:,} ks*\n\n"
                      f"(ပေးသည့်နေ့ rate အတိုင်း MMK ပြန်ပေးမည်)\n\n"
                      f"Admin မှ ၂-၃ ရက်အတွင်း ပြန်လွှဲပေးပါမည် 🙏"),
                parse_mode='Markdown')
        except Exception as e:
            logger.error(f"auctionlost customer: {e}")

    await notify_admins(context,
        f"💸 *Refund လုပ်ပေးရမည်!*\n\n"
        f"🆔 `{req_id}`\n"
        f"👤 Customer ID: `{customer_id}`\n"
        f"💵 ပြန်ပေးရမည်: *{mmk_amount:,} ks*\n\n"
        f"ပြန်လွှဲပြီးရင် `/refunddone {req_id}` နှိပ်ပါ",)

    if broker_tg_id:
        try:
            await context.bot.send_message(
                chat_id=int(broker_tg_id),
                text=(f"😔 *Auction Lost*\n\n"
                      f"🆔 `{req_id}`\n"
                      f"Customer ကို Deposit ပြန်ပေးမည် — Admin handle လုပ်မည်"),
                parse_mode='Markdown')
        except Exception as e:
            logger.error(f"auctionlost broker: {e}")

    await update.message.reply_text(
        f"✅ *Auction Lost မှတ်တမ်းတင်ပြီ*\n\n"
        f"🆔 `{req_id}`\n"
        f"💵 Refund: *{mmk_amount:,} ks*\n\n"
        f"⚠️ Customer ကို ပြန်လွှဲပေးဖို့ မမေ့ပါနဲ့!",
        parse_mode='Markdown')


async def refunddone_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Admin သာ သုံးနိုင်တယ်")
        return
    if not context.args:
        await update.message.reply_text("❌ Format: `/refunddone R123456`", parse_mode='Markdown')
        return

    req_id = context.args[0].strip().upper()

    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            await client.post(SHEET_WEBHOOK, json={
                "action":        "updateDeposit",
                "reqId":         req_id,
                "auctionResult": "REFUNDED",
            }, timeout=10)
            dep_resp = await client.post(SHEET_WEBHOOK, json={
                "action": "getDeposit",
                "reqId":  req_id,
            }, timeout=10)
        dep = dep_resp.json()
    except Exception as e:
        logger.error(f"refunddone: {e}")
        await update.message.reply_text("❌ Sheet error")
        return

    customer_id = dep.get("customerId")
    mmk_amount  = dep.get("mmkAmount", 0)

    if customer_id:
        try:
            await context.bot.send_message(
                chat_id=int(customer_id),
                text=(f"✅ *Deposit ပြန်ပေးပြီ!*\n\n"
                      f"🆔 `{req_id}`\n"
                      f"💵 *{mmk_amount:,} ks* လွှဲပေးပြီ\n\n"
                      f"ဆက်လုပ်ချင်ရင် /carrequest နှိပ်ပါ 🙏"),
                parse_mode='Markdown')
        except Exception as e:
            logger.error(f"refunddone notify: {e}")

    await update.message.reply_text(
        f"✅ Refund ပြီးကြောင်း မှတ်တမ်းတင်ပြီ\n🆔 `{req_id}`",
        parse_mode='Markdown')


# ── Auto Expire Check ─────────────────────────────────
async def check_expired_members(context):
    global warned_3days
    try:
        async with httpx.AsyncClient() as client:
            resp    = await client.post(SHEET_WEBHOOK, json={"action":"getMembers"}, timeout=10, follow_redirects=True)
            members = resp.json().get("members",[])
        now = datetime.now(); kicked = []; kick_failed = []; expiring = []
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
                        pw_resp = await (httpx.AsyncClient()).post(SHEET_WEBHOOK, json={
                            "action": "getPassword", "userId": uid}, timeout=10, follow_redirects=True)
                        pw_data  = pw_resp.json()
                        password = pw_data.get("password","")
                        pw_line  = f"\n🔑 Web Password: `{password}`\n" if password else ""
                        kb = []
                        if ADMIN_USERNAME:
                            kb = [[InlineKeyboardButton("💬 Admin ကို ဆက်သွယ်", url=f"https://t.me/{ADMIN_USERNAME}")]]
                        await context.bot.send_message(
                            chat_id=int(uid),
                            text=(f"⚠️ *Membership သတိပေးချက်!*\n\n"
                                  f"သင့် Membership *{days_left} ရက်* အတွင်း ကုန်ဆုံးမည်!\n"
                                  f"⏰ ကုန်ဆုံးရက်: `{m.get('expireDate','?')}`\n"
                                  f"{pw_line}\n"
                                  f"သက်တမ်းတိုးဖို့ /renew နှိပ်ပါ 🙏"),
                            parse_mode='Markdown',
                            reply_markup=InlineKeyboardMarkup(kb) if kb else None)
                    except Exception as e:
                        logger.error(f"3day warn: {e}")

            if m.get('status') == 'EXPIRED' and uid.isdigit():
                if int(uid) in ADMIN_IDS:
                    logger.warning(f"Skipping kick for admin ID {uid}")
                    continue

                pkg = str(m.get('package','')).upper()

                if pkg == 'PROMO10D':
                    cancel_c = await get_cancel_count(uid)
                    has_order = cancel_c > 0
                    kick_status = "KICKED"
                    try:
                        await context.bot.send_message(
                            chat_id=int(uid),
                            text=("⏰ *10 Day Promo ကုန်ဆုံးပြီ*\n\n"
                                  + ("Order တင်ခဲ့သောကြောင့် ကျေးဇူးတင်ပါသည် 🙏\n"
                                     "Membership ဝယ်ရန် /start" if has_order else
                                     "❌ Order မတင်ဘဲ ကုန်ဆုံးသောကြောင့် Kick ခံရပြီ\n"
                                     "နောက်ထပ် Promo မရနိုင်ပါ")),
                            parse_mode='Markdown')
                    except Exception as e:
                        logger.error(f"promo10d expire notify: {e}")

                success = await kick_with_retry(context, int(uid))
                if success:
                    kicked.append(m)
                    if SHEET_WEBHOOK:
                        try:
                            async with httpx.AsyncClient() as client:
                                await client.post(SHEET_WEBHOOK, json={
                                    "action": "updateStatus",
                                    "userId": uid,
                                    "status": "KICKED"
                                }, timeout=10, follow_redirects=True)
                        except Exception as e:
                            logger.error(f"updateStatus kicked: {e}")
                else:
                    kick_failed.append(m)

        if kicked:
            txt = "🚫 *Auto Kick (Membership ကုန်ဆုံး):*\n\n"
            for m in kicked: txt += f"• @{m['username']} — `{m.get('expireDate','?')}`\n"
            await notify_admins(context, txt)

        if kick_failed:
            txt = "⚠️ *Kick မအောင်မြင် — ကိုယ်တိုင် ဆောင်ရွက်ပါ:*\n\n"
            for m in kick_failed: txt += f"• @{m['username']} — ID: `{m.get('userId','?')}`\n"
            txt += "\n`/kick [userId]` သုံးပါ"
            await notify_admins(context, txt)

        if expiring:
            txt = "⚠️ *Membership ၃ ရက်အတွင်း ကုန်ဆုံးမည်:*\n\n"
            for m in expiring: txt += f"• @{m['username']} — `{m.get('expireDate','?')}`\n"
            txt += "\nသက်တမ်းတိုး: `/approve [userId] [လ]`"
            await notify_admins(context, txt)
    except Exception as e:
        logger.error(f"check_expired: {e}")

# ── Ban Auto-Lift Scheduler ───────────────────────────
async def check_expired_bans(context):
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.post(SHEET_WEBHOOK, json={
                "action": "liftExpiredBans",
            }, timeout=15)
        result = resp.json()
        lifted = result.get("lifted", [])
        if lifted:
            txt = "🔓 *Ban Auto-Lift*\n\n"
            for row in lifted:
                txt += f"• `{row.get('customerId')}` (@{row.get('username','?')}) — {row.get('banStatus')} ကုန်ဆုံးပြီ\n"
            await notify_admins(context, txt)
    except Exception as e:
        logger.error(f"check_expired_bans: {e}")

# ── Main ──────────────────────────────────────────────
async def main():
    logger.info("Bot starting...")
    async with httpx.AsyncClient() as client:
        await client.post(f"https://api.telegram.org/bot{TOKEN}/deleteWebhook",
                          params={"drop_pending_updates":True})
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start",       start))
    app.add_handler(CommandHandler("find",        find_car))
    app.add_handler(CommandHandler("model",       find_model))
    app.add_handler(CommandHandler("price",       add_price))
    app.add_handler(CommandHandler("history",     price_history_cmd))
    app.add_handler(CommandHandler("list",        list_cars))
    app.add_handler(CommandHandler("web",         web_link))
    app.add_handler(CommandHandler("approve",     approve_member))
    app.add_handler(CommandHandler("members",     members_list))
    app.add_handler(CommandHandler("kick",        kick_member_cmd))
    app.add_handler(CommandHandler("renew",       renew_cmd))
    app.add_handler(CommandHandler("mypassword",  mypassword_cmd))
    app.add_handler(CommandHandler("resetpass",   resetpass_cmd))
    app.add_handler(CommandHandler("updateid",    updateid_cmd))
    app.add_handler(CommandHandler("backup",      backup_cmd))
    app.add_handler(CommandHandler("setqr",       setqr_cmd))
    app.add_handler(CommandHandler("broadcast",   broadcast_cmd))
    app.add_handler(CommandHandler("upgrade",     upgrade_cmd))
    app.add_handler(CommandHandler("redeem",        redeem_cmd))
    app.add_handler(CommandHandler("addbroker",     addbroker_cmd))
    app.add_handler(CommandHandler("kickbroker",    kickbroker_cmd))
    app.add_handler(CommandHandler("brokers",       brokers_cmd))
    app.add_handler(CommandHandler("brokerstart",   brokerstart_cmd))
    app.add_handler(CommandHandler("available",     available_cmd))
    app.add_handler(CommandHandler("busy",          busy_cmd))
    app.add_handler(CommandHandler("carrequest",    carrequest_cmd))
    app.add_handler(CommandHandler("cancelrequest", cancelrequest_cmd))
    app.add_handler(CommandHandler("mystatus",      mystatus_cmd))
    app.add_handler(CommandHandler("accept",        accept_cmd))
    app.add_handler(CommandHandler("endchat",       endchat_cmd))
    app.add_handler(CommandHandler("depositrequest", depositrequest_cmd))
    app.add_handler(CommandHandler("auctionwon",     auctionwon_cmd))
    app.add_handler(CommandHandler("auctionlost",    auctionlost_cmd))
    app.add_handler(CommandHandler("refunddone",     refunddone_cmd))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.job_queue.run_repeating(check_expired_members, interval=43200, first=60)
    app.job_queue.run_repeating(check_expired_bans,    interval=43200, first=120)
    await app.initialize()
    await app.start()

    member_commands = [
        BotCommand("start",         "🚗 Bot စတင်ရန်"),
        BotCommand("carrequest",    "🚙 ကားလိုအပ်ပါက ဒီနေရာနှိပ်ပါ"),
        BotCommand("mystatus",      "📋 Request Status စစ်ရန်"),
        BotCommand("find",          "🔍 Chassis ဖြင့်ရှာရန်"),
        BotCommand("model",         "🔎 Model အမည်ဖြင့်ရှာရန်"),
        BotCommand("history",       "📈 ဈေးနှုန်း မှတ်တမ်းကြည့်ရန်"),
        BotCommand("list",          "📊 ကားစာရင်း အားလုံးကြည့်ရန်"),
        BotCommand("web",           "🌐 Web App link ကြည့်ရန်"),
        BotCommand("renew",         "🔄 Membership သက်တမ်းတိုး"),
        BotCommand("mypassword",    "🔑 Password ပြန်ယူရန်"),
        BotCommand("redeem",        "🎁 Promo Code သုံးရန်"),
    ]
    broker_commands = member_commands + [
        BotCommand("brokerstart",   "👷 Broker စတင်ရန်"),
        BotCommand("available",     "🟢 Available ဖြစ်ကြောင်း"),
        BotCommand("busy",          "🔴 Busy ဖြစ်ကြောင်း"),
        BotCommand("accept",        "✅ Request လက်ခံရန်"),
        BotCommand("endchat",       "🔚 Session ပိတ်ရန်"),
        BotCommand("depositrequest","💰 Customer ကို Deposit တောင်းရန်"),
    ]
    admin_commands = member_commands + [
        BotCommand("price",         "💰 ကားဈေးထည့်ရန် (Admin)"),
        BotCommand("approve",       "✅ Member approve လုပ်ရန် (Admin)"),
        BotCommand("members",       "👥 Member စာရင်းကြည့်ရန် (Admin)"),
        BotCommand("kick",          "🚫 Member ထုတ်ရန် (Admin)"),
        BotCommand("resetpass",     "🔑 Password reset (Admin)"),
        BotCommand("updateid",      "🆔 Member ID update (Admin)"),
        BotCommand("setqr",         "💳 Payment QR setup (Admin)"),
        BotCommand("backup",        "💾 CSV Backup (Admin)"),
        BotCommand("broadcast",     "📢 Broadcast ပို့ရန် (Admin)"),
        BotCommand("addbroker",     "👷 Broker ထည့်ရန် (Admin)"),
        BotCommand("kickbroker",    "🚫 Broker ဖြတ်ရန် (Admin)"),
        BotCommand("brokers",       "📋 Broker list (Admin)"),
        BotCommand("auctionwon",    "🏆 ကားရပြီ (Admin)"),
        BotCommand("auctionlost",   "❌ ကားမရဘူး (Admin)"),
        BotCommand("refunddone",    "💸 Refund ပြီး (Admin)"),
    ]
    try:
        await app.bot.set_my_commands(member_commands, scope=BotCommandScopeAllPrivateChats())
        for admin_id in ADMIN_IDS:
            try:
                await app.bot.set_my_commands(admin_commands, scope=BotCommandScopeChat(chat_id=admin_id))
            except Exception as e:
                logger.warning(f"Admin scope set failed for {admin_id}: {e}")
        brokers = await get_brokers()
        for b in brokers:
            try:
                tg_id = int(b.get("telegramId", 0))
                if tg_id:
                    await app.bot.set_my_commands(broker_commands, scope=BotCommandScopeChat(chat_id=tg_id))
            except Exception as e:
                logger.warning(f"Broker scope set failed: {e}")
        logger.info("Command scopes set successfully")
    except Exception as e:
        logger.error(f"set_my_commands error: {e}")

    startup_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    startup_msg = (
        f"🟢 *Bot ပြန်စတင်ပြီ*\n\n"
        f"⏰ {startup_time}\n"
        f"🤖 Model: `{GEMINI_MODEL}`\n"
        f"📦 Cars in memory: {len(CARS)}\n"
        f"👑 Admin IDs: {len(ADMIN_IDS)}"
    )
    for admin_id in ADMIN_IDS:
        try:
            await app.bot.send_message(
                chat_id=admin_id,
                text=startup_msg,
                parse_mode='Markdown')
        except Exception as e:
            logger.warning(f"Startup notify {admin_id} failed: {e}")

    await app.updater.start_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)
    logger.info("Bot polling!")
    await asyncio.Event().wait()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user (Ctrl+C)")
    except Exception as e:
        import traceback
        logger.error(f"FATAL CRASH: {e}")
        logger.error(traceback.format_exc())
        raise
