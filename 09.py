"""
YacineOd — Ooredoo DZ Bot (Final v3)
====================================
إصلاحات:
- إرسال الرقم يبدأ المحادثة مباشرة (لا تكرار، لا صمت)
- زر "إضافة" و /login يعملان بشكل صحيح
- لا تعديل على دوال API
"""

import asyncio
try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

import json
import base64
import time
import uuid
import threading
from datetime import datetime, timezone
from pathlib import Path

import requests
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, ConversationHandler, filters
)

# ═══════════════════════════════════════════════════════════
# CONFIG (كما هو)
# ═══════════════════════════════════════════════════════════
BOT_TOKEN = "8285634872:AAExEfyp1-qvSD7n5ThFT1tC8snYWDaU_KQ" 
BOT_NAME = "yacinedev"
ADMIN_ID = 6936293942
BASE = "https://apis.ooredoo.dz"
CLIENT_ID = "myooredoo-app"
DEVICE_ID = "e47f5390-d08a-11f1-a551-53d2238ad2f61792943038281"
SIG = "5c7641dbb82cf11066df68afc91541c967640106a95192740b43d51a5ce6777a"
PLATFORM_SIG = "eyJwbGF0Zm9ybSI6ImFuZHJvaWQiLCJpcy1waHlzaWNhbC1kZXZpY2UiOnRydWUsImRldmljZS1pZCI6ImU0N2Y1MzkwLWQwOGEtMTFmMS1hNTUxLTUzZDIyMzhhZDJmNjE3OTI5NDMwMzgyODEifQ=="
INTEGRITY = "JWBTpxXcH7KWjFPwOYVi092fDhbWjy2w8dLklCB4zgkItb0fP5g34EeV+zSVHSTeI6bjowWMGizRouGqsu1Y6DVBEvya/TPhvaFNDxI1RMvc+IWPQ2A9MaERhWozCaOe/tDfYdEiD/vtl430OzTflYj9y6NCx4xCjqZ2IRrFZVPr7C1+9lt0cfL+vHuDDT2ytf6EAO9unuC+N7VBBq9aQPg1R11j4EcnNh3ZrieV9k+MuIS5i7hECQCJ2tzHn9PAphg/QxSvH0uxDx42U0VKvt3zA/zD+uUxLKmXpd/5KRgCgKwz2C25uiDBXYKR5G5vPZ5eMWYC4XODz47CpmVBxLH3BDtMSefoIQmZQaRE00Wq6yaPjWfUbg2v/xRFBejMJb4Qr2rw9+oLN5PLsH/kOVFkLIxV9CY2ei+zdLTo6QB6xmCDyV5Lbd8A5ipkbTvHOYB8+49cZvyhB04bESJTkjSyJzXoN39ftqw2AlHEGrUt6lEODkaMH/qQFl/+XNXc/K7Ic3ypFrwJjwZraOOnu9teelSXjIHzDHzwMAjZMklC0mv0oZ3ZqaitT7OxeQyOv1P6Wv+QFRY5I6vnAVloK3jzPg6weCpJuXvG8SvFrcygJM2hQJ+ZlwPGILyO1DfHKD2cbjnglTpjLqshX0GoRqfB++Cum0YmtluOdBEAulMWpFnYuu2aewEgoQq9GmCtwRdXQhWOMVW6zhIOqmBFKqdc5/8gj+kpF9PLI2H6gHaHqP4veLFjmm4KiwhFo6IFjLU2PGs="

TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}"
ACCOUNTS_FILE = Path("accounts.json")
LOGIN_LOG = Path("login_log.json")

ASK_MSISDN, ASK_OTP = 0, 1

_acc_lock = threading.Lock()
_log_lock = threading.Lock()


# ═══════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════
def now_ms(): return int(time.time() * 1000)
def fp(): return uuid.uuid4().hex + uuid.uuid4().hex
def corr(): return f"{uuid.uuid4()}{now_ms()}"
def ts(): return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

def decode(t):
    try:
        p = t.split(".")[1]; p += "=" * (-len(p) % 4)
        return json.loads(base64.urlsafe_b64decode(p))
    except Exception:
        return {}

def parse_exp(s):
    try: return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception: return None


# ═══════════════════════════════════════════════════════════
# STORAGE
# ═══════════════════════════════════════════════════════════
def load_acc():
    if ACCOUNTS_FILE.exists():
        try: return json.loads(ACCOUNTS_FILE.read_text(encoding="utf-8"))
        except Exception: pass
    return {}

def save_acc(d):
    with _acc_lock:
        ACCOUNTS_FILE.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")

def get_user(uid):
    return load_acc().get(str(uid), {})

def save_user(uid, msisdn, token, name="", username=""):
    d = load_acc()
    d.setdefault(str(uid), {})
    d[str(uid)]["default"] = msisdn
    d[str(uid)]["name"] = name
    d[str(uid)]["username"] = username
    exp_ts = decode(token).get("exp")
    d[str(uid)].setdefault("accounts", {})[msisdn] = {
        "token": token,
        "expires_at": datetime.fromtimestamp(exp_ts, tz=timezone.utc).isoformat() if exp_ts else None,
        "saved_at": datetime.now(timezone.utc).isoformat(),
    }
    save_acc(d)

def get_token(uid):
    ud = get_user(uid)
    d = ud.get("default")
    if not d: return None
    acc = ud.get("accounts", {}).get(d)
    if not acc: return None
    exp = acc.get("expires_at")
    if exp:
        try:
            exp_dt = datetime.fromisoformat(exp)
            if exp_dt.tzinfo is None:
                exp_dt = exp_dt.replace(tzinfo=timezone.utc)
            if exp_dt < datetime.now(timezone.utc):
                return None
        except Exception:
            pass
    return (d, acc["token"])


def log_login(uid, name, username, msisdn, success=True, reason=""):
    with _log_lock:
        data = {}
        if LOGIN_LOG.exists():
            try: data = json.loads(LOGIN_LOG.read_text(encoding="utf-8"))
            except Exception: pass
        data.setdefault("logins", []).append({
            "uid": uid, "name": name, "username": username, "msisdn": msisdn,
            "success": success, "reason": reason,
            "time": datetime.now(timezone.utc).isoformat(),
        })
        LOGIN_LOG.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


# ═══════════════════════════════════════════════════════════
# SEND
# ═══════════════════════════════════════════════════════════
def send(chat_id, text, buttons, msg_id=None):
    payload = {
        "chat_id": chat_id, "text": text, "parse_mode": "HTML",
        "reply_markup": json.dumps({"inline_keyboard": buttons}, ensure_ascii=False),
    }
    if msg_id:
        payload["message_id"] = msg_id
        try:
            r = requests.post(f"{TG_API}/editMessageText", json=payload, timeout=30)
            if r.status_code == 200:
                return
            if "message is not modified" in r.text.lower():
                return
            payload.pop("message_id", None)
        except Exception:
            payload.pop("message_id", None)
    try:
        requests.post(f"{TG_API}/sendMessage", json=payload, timeout=30)
    except Exception as e:
        print(f"⚠️ send error: {e}")


# ═══════════════════════════════════════════════════════════
# BUTTONS
# ═══════════════════════════════════════════════════════════
def welcome_btn(): return []

def main_btn():
    return [
        [{"text": "💰 الرصيد", "callback_data": "acc", "style": "success"}],
        [{"text": "🎁 هدية يومية", "callback_data": "play", "style": "success"}],
        [{"text": "👤 شخصي", "callback_data": "personal", "style": "primary"}],
        [{"text": "🐍 Power Snake", "callback_data": "ps", "style": "danger"}],
        [{"text": "📦 الباقة", "callback_data": "plan", "style": "primary"}],
        [{"text": "🔧 خدمات أخرى", "callback_data": "more", "style": "primary"}],
    ]

def ps_btn():
    return [
        [{"text": "🎮 العب", "callback_data": "play", "style": "success"}],
        [{"text": "🎁 الجوائز", "callback_data": "prizes", "style": "success"}],
        [{"text": "⚡ استرداد", "callback_data": "redeem", "style": "danger"}],
        [{"text": "🏆 السجل", "callback_data": "hist", "style": "primary"}],
        [{"text": "🔙 رجوع", "callback_data": "menu", "style": "primary"}],
    ]

def more_btn():
    return [
        [{"text": "📜 السجلات", "callback_data": "logs", "style": "primary"}],
        [{"text": "📱 الحسابات", "callback_data": "accounts", "style": "primary"}],
        [{"text": "➕ إضافة", "callback_data": "add", "style": "success"}],
        [{"text": "🚪 خروج", "callback_data": "logout", "style": "danger"}],
        [{"text": "🔙 رجوع", "callback_data": "menu", "style": "primary"}],
    ]

def back_btn():
    return [[{"text": "🔙 رجوع", "callback_data": "menu", "style": "primary"}]]

def cancel_btn():
    return [[{"text": "❌ إلغاء", "callback_data": "cancel", "style": "danger"}]]


# ═══════════════════════════════════════════════════════════
# API (بدون تعديل)
# ═══════════════════════════════════════════════════════════
def h(msisdn, token=None, nonce=None, chronos=None, extra=None):
    hh = {
        "x-msisdn": msisdn, "user-agent": "Dart/3.11 (dart:io)",
        "x-device-fingerprint": fp(), "accept-encoding": "gzip",
        "x-platform-origin": "mobile-android",
        "x-correlation-id": corr(), "platform": "android",
        "x-version": "1.5.17", "x-signature": SIG, "accept": "*/*",
        "x-platform-data-signature": PLATFORM_SIG,
        "x-timestamp": str(now_ms()), "x-instance-id": DEVICE_ID,
    }
    if token: hh["authorization"] = f"Bearer {token}"
    if nonce: hh["x-nonce-id"] = nonce
    if chronos: hh["x-chronos-id"] = chronos
    if extra: hh.update(extra)
    return hh


def api_get(url, headers, params=None):
    try:
        r = requests.get(url, headers=headers, params=params, timeout=30)
        return r.json() if r.status_code == 200 else {"_error": r.status_code}
    except Exception as e:
        return {"_error": str(e)}


def request_otp(m):
    try:
        path = "/api/auth/realms/myooredoo/protocol/openid-connect/token"
        r = requests.post(f"{BASE}/api/ooredoo-bff/checkpoint/token", data="{}",
                          headers=h(m, extra={
                              "x-path": path, "x-method": "POST",
                              "content-type": "application/json; charset=utf-8",
                              "x-native-integrity-token": INTEGRITY,
                          }), timeout=30)
        if r.status_code != 202:
            return {"ok": False, "reason": f"checkpoint {r.status_code}"}
        n = r.headers.get("X-Nonce-Id", "")
        c = r.headers.get("X-Chronos-Id", "")
        body = f"client_id={CLIENT_ID}&grant_type=password&username={m}"
        r2 = requests.post(f"{BASE}{path}", data=body, headers=h(m, nonce=n, chronos=c, extra={
            "content-type": "application/x-www-form-urlencoded; charset=utf-8",
            "x-platform-info": PLATFORM_SIG, "x-force-update": "true",
        }), timeout=30)
        if r2.status_code == 403:
            return {"ok": True}
        if r2.status_code == 200:
            try:
                d = r2.json()
                if "access_token" in d:
                    return {"ok": True, "token": d["access_token"]}
            except Exception: pass
        return {"ok": False, "reason": f"HTTP {r2.status_code}"}
    except Exception as e:
        return {"ok": False, "reason": str(e)}


def verify_otp(m, otp):
    try:
        path = "/api/auth/realms/myooredoo/protocol/openid-connect/token"
        r = requests.post(f"{BASE}/api/ooredoo-bff/checkpoint/token", data="{}",
                          headers=h(m, extra={
                              "x-path": path, "x-method": "POST",
                              "content-type": "application/json; charset=utf-8",
                              "x-native-integrity-token": INTEGRITY,
                          }), timeout=30)
        if r.status_code != 202:
            return {"ok": False, "reason": f"checkpoint {r.status_code}"}
        n = r.headers.get("X-Nonce-Id", "")
        c = r.headers.get("X-Chronos-Id", "")
        body = f"client_id={CLIENT_ID}&grant_type=password&username={m}&otp={otp}"
        r2 = requests.post(f"{BASE}{path}", data=body, headers=h(m, nonce=n, chronos=c, extra={
            "content-type": "application/x-www-form-urlencoded; charset=utf-8",
            "x-platform-info": PLATFORM_SIG, "x-force-update": "true",
        }), timeout=30)
        if r2.status_code == 200:
            try: return {"ok": True, "token": r2.json().get("access_token")}
            except Exception: pass
        return {"ok": False, "reason": f"HTTP {r2.status_code}"}
    except Exception as e:
        return {"ok": False, "reason": str(e)}


def get_account(m, t):
    return api_get(f"{BASE}/api/ooredoo-bff/subscriptions/getAccountInfo", h(m, t))


def get_plan(m, t):
    res = {}
    r = api_get(f"{BASE}/api/auth/realms/myooredoo/protocol/openid-connect/userinfo", h(m, t))
    if "_error" not in r: res["ratePlan"] = r.get("ratePlan")
    r = api_get(f"{BASE}/api/ooredoo-bff/bundle/getActivePackages", h(m, t), {"msisdn": m})
    if "_error" not in r:
        res["planName"] = r.get("planName")
        res["planCode"] = r.get("planCode")
    return res


def get_personal(m, t):
    try:
        path = "/api/ooredoo-bff/userInfo/personal"
        r = requests.post(f"{BASE}/api/ooredoo-bff/checkpoint/token", data="{}",
                          headers=h(m, extra={
                              "x-path": path, "x-method": "GET",
                              "content-type": "application/json; charset=utf-8",
                          }), timeout=30)
        if r.status_code != 202: return {"_error": r.status_code}
        n = r.headers.get("X-Nonce-Id", "")
        c = r.headers.get("X-Chronos-Id", "")
        r2 = requests.get(f"{BASE}{path}", headers=h(m, t, n, c), timeout=30)
        return r2.json() if r2.status_code == 200 else {"_error": r2.status_code}
    except Exception as e:
        return {"_error": str(e)}


def get_prizes(m, t):
    r = api_get(f"{BASE}/api/ooredoo-bff/gamification/power-snake", h(m, t), {"status": "AVAILABLE"})
    return r.get("items", []) if "_error" not in r else []


def get_game_hist(m, t):
    r = api_get(f"{BASE}/api/ooredoo-bff/gamification/history", h(m, t))
    return r.get("gameHistoryData", []) if "_error" not in r else []


def get_history(m, t, ct="topUp"):
    try:
        payload = {"startDate": "2026-10-11T00:00:00.000+01:00",
                   "endDate": datetime.now(timezone.utc).isoformat(),
                   "callTypeList": ct}
        r = requests.post(f"{BASE}/api/ooredoo-bff/history", json=payload, headers=h(m, t), timeout=30)
        return len(r.json().get("subscriberCall", [])) if r.status_code == 200 else -1
    except Exception:
        return -1


def play(m, t):
    try:
        path = "/api/ooredoo-bff/gamification/play"
        r = requests.post(f"{BASE}/api/ooredoo-bff/checkpoint/token", data="{}",
                          headers=h(m, extra={
                              "x-path": path, "x-method": "GET",
                              "content-type": "application/json; charset=utf-8",
                          }), timeout=30)
        if r.status_code != 202: return {"ok": False, "reason": f"checkpoint {r.status_code}"}
        n = r.headers.get("X-Nonce-Id", "")
        c = r.headers.get("X-Chronos-Id", "")
        r2 = requests.get(f"{BASE}{path}", headers=h(m, t, n, c, extra={"x-timestamp": ts()}), timeout=30)
        if r2.status_code == 200: return {"ok": True, "data": r2.json()}
        if r2.status_code == 500:
            try: msg = r2.json().get("message", "")
            except Exception: msg = "خطأ"
            return {"ok": False, "reason": msg}
        return {"ok": False, "reason": f"HTTP {r2.status_code}"}
    except Exception as e:
        return {"ok": False, "reason": str(e)}


def redeem(m, t, uuid_prize):
    try:
        hh = {k: v for k, v in h(m, t).items() if k != "accept-encoding"}
        r = requests.post(f"{BASE}/api/ooredoo-bff/gamification/power-snake/{uuid_prize}/redeem",
                          headers=hh, timeout=30)
        if r.status_code == 200:
            try:
                body = r.json()
                return {"ok": body.get("success", False)}
            except Exception: return {"ok": False}
        if r.status_code == 500:
            try: msg = r.json().get("message", "")
            except Exception: msg = ""
            return {"ok": False, "reason": msg}
        return {"ok": False, "reason": f"HTTP {r.status_code}"}
    except Exception as e:
        return {"ok": False, "reason": str(e)}


# ═══════════════════════════════════════════════════════════
# TEXTS
# ═══════════════════════════════════════════════════════════
WELCOME_TEXT = (
    "          مـــــرحبا بك في <b>yacinedev</b>\n\n"
    "📋 <b>الخـــــــطوات:</b>\n"
    "1️⃣ أرسل رقم أوريدو (05XXXXXXXX)\n"
    "2️⃣ أدخل رمز OTP\n"
    "3️⃣ اختر العرض من القائمة\n\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "📱 <b>أرسل رقم هاتفك للبدء</b>"
)

SEND_MSISDN_TEXT = (
    "📱 <b>أدخل رقم الهاتف</b>\n\n"
    "مثال: <code>05XXXXXXXX</code>\n\n"
    "❌ /cancel للإلغاء"
)

OTP_SENDING_TEXT = "📤 <b>جارٍ إرسال الرمز إلى <code>{m}</code>...</b>"

OTP_SENT_TEXT = (
    "✅ <b>تم إرسال الرمز بنجاح</b>\n\n"
    "💬 يرجى نسخ أو كتابة الرمز المكون من <b>6 أرقام</b>\n"
    "الذي تلقيته في رسالة على هاتفك 📱"
)


def build_menu(msisdn, plan, chip):
    return (
        f"✅ <b>تم التحقق بنجاح</b>\n\n"
        f"📱 <b>الرقم</b> : <code>{msisdn}</code>\n"
        f"📦 <b>العرض</b> : <b>{plan}</b>\n"
        f"💳 <b>الشريحة</b> : <b>{chip}</b>\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"اختر من الأزرار أدناه 🔽"
    )


async def show_menu(chat_id, msisdn, token):
    try:
        p = get_plan(msisdn, token) or {}
        pers = get_personal(msisdn, token) or {}
        if "_error" in p: p = {}
        if "_error" in pers: pers = {}
        plan_name = p.get("planName") or p.get("ratePlan") or "N'YOOZ"
        chip = (pers.get("chipName") or pers.get("simName")
                or pers.get("offerName") or plan_name)
    except Exception:
        plan_name, chip = "N'YOOZ", "N'YOOZ"
    send(chat_id, build_menu(msisdn, plan_name, chip), main_btn())


# ═══════════════════════════════════════════════════════════
# COMMANDS
# ═══════════════════════════════════════════════════════════
async def cmd_start(update, context):
    d = get_token(update.effective_user.id)
    if d:
        await show_menu(update.effective_chat.id, d[0], d[1])
    else:
        send(update.effective_chat.id, WELCOME_TEXT, welcome_btn())


async def cmd_menu(update, context):
    d = get_token(update.effective_user.id)
    if not d:
        send(update.effective_chat.id, WELCOME_TEXT, welcome_btn())
        return
    await show_menu(update.effective_chat.id, d[0], d[1])


async def cmd_cancel(update, context):
    context.user_data.pop("temp_msisdn", None)
    send(update.effective_chat.id, "❌ تم الإلغاء", welcome_btn())
    return ConversationHandler.END


async def cancel_cb(update, context):
    q = update.callback_query
    await q.answer()
    try: await q.message.delete()
    except Exception: pass
    context.user_data.pop("temp_msisdn", None)
    send(q.message.chat_id, "❌ تم الإلغاء", welcome_btn())
    return ConversationHandler.END


async def cmd_admin(update, context):
    if update.effective_user.id != ADMIN_ID:
        return
    data = load_acc()
    users = list(data.keys())
    total_logins = 0
    if LOGIN_LOG.exists():
        try:
            lj = json.loads(LOGIN_LOG.read_text(encoding="utf-8"))
            total_logins = len(lj.get("logins", []))
        except Exception: pass

    text = (
        f"👑 <b>لوحة الإدارة</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👥 المستخدمون : <b>{len(users)}</b>\n"
        f"🔐 تسجيلات الدخول : <b>{total_logins}</b>\n\n"
        f"اختر:"
    )
    buttons = [
        [{"text": "👥 المستخدمون", "callback_data": "admin_users", "style": "primary"}],
        [{"text": "🔐 سجل الدخول", "callback_data": "admin_logins", "style": "primary"}],
        [{"text": "📊 إحصائيات", "callback_data": "admin_stats", "style": "success"}],
    ]
    send(update.effective_chat.id, text, buttons)


# ═══════════════════════════════════════════════════════════
# LOGIN FLOW (مُعدَّل ليعمل عند إرسال الرقم مباشرة)
# ═══════════════════════════════════════════════════════════
async def handle_initial_number(update, context):
    """
    هذه الدالة تعمل عندما يرسل المستخدم رقماً وهو في الحالة ASK_MSISDN.
    نضع رقمه في user_data ثم نعالجه فوراً في handle_msisdn.
    """
    # تخزين النص في user_data ليتمكن handle_msisdn من قراءته
    # (نحتاج ذلك فقط إذا كنا نأتي من add_start)
    # لكن في هذه الحالة نحن نستدعي handle_msisdn مباشرة.
    return await handle_msisdn(update, context)


async def add_start(update, context):
    """بدء المحادثة عبر /login أو زر إضافة"""
    chat_id = update.effective_chat.id
    if update.callback_query:
        send(chat_id, SEND_MSISDN_TEXT, cancel_btn(),
             msg_id=update.callback_query.message.message_id)
    else:
        send(chat_id, SEND_MSISDN_TEXT, cancel_btn())
    return ASK_MSISDN


async def handle_msisdn(update, context):
    raw = update.message.text.strip().replace(" ", "").replace("+", "").replace("-", "")
    if raw.startswith("0") and len(raw) == 10:
        msisdn = "213" + raw[1:]
    elif raw.startswith("213") and len(raw) == 12:
        msisdn = raw
    else:
        send(update.effective_chat.id, "❌ <b>رقم غير صحيح</b>\n\nمثال: <code>05XXXXXXXX</code>", cancel_btn())
        return ASK_MSISDN

    context.user_data["temp_msisdn"] = msisdn
    chat_id = update.effective_chat.id

    send(chat_id, OTP_SENDING_TEXT.format(m=msisdn), [])

    result = request_otp(msisdn)

    if result.get("token"):
        u = update.effective_user
        save_user(u.id, msisdn, result["token"], name=u.first_name or "", username=u.username or "")
        log_login(u.id, u.first_name or "", u.username or "", msisdn, True, "auto")
        context.user_data.pop("temp_msisdn", None)
        await show_menu(chat_id, msisdn, result["token"])
        return ConversationHandler.END

    if result.get("ok"):
        send(chat_id, OTP_SENT_TEXT, cancel_btn())
        return ASK_OTP

    u = update.effective_user
    log_login(u.id, u.first_name or "", u.username or "", msisdn, False, result.get("reason", "?"))
    context.user_data.pop("temp_msisdn", None)
    send(chat_id, f"❌ <b>فشل</b>\n\n<code>{result.get('reason', '?')}</code>", welcome_btn())
    return ConversationHandler.END


async def handle_otp(update, context):
    otp = update.message.text.strip()
    if not (otp.isdigit() and len(otp) == 6):
        send(update.effective_chat.id, "❌ <b>الرمز يجب أن يكون 6 أرقام</b>", cancel_btn())
        return ASK_OTP

    msisdn = context.user_data.get("temp_msisdn")
    if not msisdn:
        send(update.effective_chat.id, "❌ جلسة منتهية. /start", welcome_btn())
        return ConversationHandler.END

    chat_id = update.effective_chat.id
    send(chat_id, "🔐 <b>جارٍ التحقق...</b>", [])

    result = verify_otp(msisdn, otp)
    u = update.effective_user
    if result.get("ok") and result.get("token"):
        save_user(u.id, msisdn, result["token"], name=u.first_name or "", username=u.username or "")
        log_login(u.id, u.first_name or "", u.username or "", msisdn, True, "ok")
        context.user_data.pop("temp_msisdn", None)
        await show_menu(chat_id, msisdn, result["token"])
        return ConversationHandler.END

    log_login(u.id, u.first_name or "", u.username or "", msisdn, False, result.get("reason", "?"))
    context.user_data.pop("temp_msisdn", None)
    send(chat_id, f"❌ <b>فشل التحقق</b>\n\n<code>{result.get('reason', '?')}</code>\n\n🔁 /start", welcome_btn())
    return ConversationHandler.END


# ═══════════════════════════════════════════════════════════
# CALLBACKS
# ═══════════════════════════════════════════════════════════
async def handle_cb(update, context):
    q = update.callback_query
    await q.answer()
    data = q.data
    uid = update.effective_user.id
    chat_id = q.message.chat_id
    mid = q.message.message_id

    # ===== Admin =====
    if data == "admin_users":
        if uid != ADMIN_ID: return
        acc = load_acc()
        lines = ["👥 <b>المستخدمون</b>", "━━━━━━━━━━━━━━━━━━"]
        for i, (u_id, info) in enumerate(acc.items(), 1):
            name = info.get("name", "?")
            username = info.get("username", "")
            default = info.get("default", "?")
            n_acc = len(info.get("accounts", {}))
            lines.append(f"\n{i}. <b>{name}</b>")
            if username: lines.append(f"   @{username}")
            lines.append(f"   ID: <code>{u_id}</code>")
            lines.append(f"   📱 {default} | حسابات: {n_acc}")
        send(chat_id, "\n".join(lines) if len(acc) > 0 else "لا يوجد مستخدمون",
             [[{"text": "🔙 رجوع", "callback_data": "admin_back", "style": "primary"}]], mid)
        return

    if data == "admin_logins":
        if uid != ADMIN_ID: return
        if not LOGIN_LOG.exists():
            send(chat_id, "لا يوجد سجل", [[{"text": "🔙", "callback_data": "admin_back", "style": "primary"}]], mid)
            return
        try:
            lj = json.loads(LOGIN_LOG.read_text(encoding="utf-8"))
            logins = lj.get("logins", [])[-20:]
        except Exception:
            logins = []
        lines = ["🔐 <b>آخر 20 تسجيل</b>", "━━━━━━━━━━━━━━━━━━"]
        for l in logins:
            st = "✅" if l.get("success") else "❌"
            t = l.get("time", "")[:16]
            lines.append(f"\n{st} {l.get('msisdn')} | {t}")
            if l.get("name"): lines.append(f"   👤 {l.get('name')}")
        send(chat_id, "\n".join(lines), [[{"text": "🔙", "callback_data": "admin_back", "style": "primary"}]], mid)
        return

    if data == "admin_stats":
        if uid != ADMIN_ID: return
        acc = load_acc()
        total_users = len(acc)
        total_accounts = sum(len(v.get("accounts", {})) for v in acc.values())
        total_logins = 0
        if LOGIN_LOG.exists():
            try:
                total_logins = len(json.loads(LOGIN_LOG.read_text(encoding="utf-8")).get("logins", []))
            except Exception: pass
        text = (
            f"📊 <b>إحصائيات</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"👥 المستخدمون: <b>{total_users}</b>\n"
            f"📱 الحسابات: <b>{total_accounts}</b>\n"
            f"🔐 تسجيلات: <b>{total_logins}</b>"
        )
        send(chat_id, text, [[{"text": "🔙", "callback_data": "admin_back", "style": "primary"}]], mid)
        return

    if data == "admin_back":
        if uid != ADMIN_ID: return
        await cmd_admin(update, context)
        return

    # ملاحظة: "add" و "cancel" يتم التعامل معهما في login_conv (entry_points / fallbacks)
    # لا نعالجهما هنا لتجنب التكرار.

    # ===== رجوع =====
    if data == "menu":
        d = get_token(uid)
        if d:
            p = get_plan(d[0], d[1]) or {}
            pers = get_personal(d[0], d[1]) or {}
            if "_error" in p: p = {}
            if "_error" in pers: pers = {}
            plan = p.get("planName") or p.get("ratePlan") or "N'YOOZ"
            chip = (pers.get("chipName") or pers.get("simName")
                    or pers.get("offerName") or plan)
            send(chat_id, build_menu(d[0], plan, chip), main_btn(), mid)
        else:
            send(chat_id, WELCOME_TEXT, welcome_btn(), mid)
        return

    if data == "ps":
        send(chat_id, "🐍 <b>Power Snake</b>\n\n━━━━━━━━━━━━━━━━━━\nاختر:", ps_btn(), mid)
        return

    if data == "more":
        send(chat_id, "🔧 <b>خدمات أخرى</b>\n\n━━━━━━━━━━━━━━━━━━\nاختر:", more_btn(), mid)
        return

    if data == "accounts":
        ud = get_user(uid)
        accs = ud.get("accounts", {})
        if not accs:
            send(chat_id, "📱 <b>لا توجد حسابات</b>", welcome_btn(), mid)
            return
        default = ud.get("default")
        lines = ["📱 <b>حساباتك</b>", "━━━━━━━━━━━━━━━━━━"]
        btns = []
        for m, info in accs.items():
            exp = info.get("expires_at", "?")
            exp_s = exp[:10] if exp else "?"
            star = "⭐" if m == default else "  "
            lines.append(f"{star} <code>{m}</code> — {exp_s}")
            btns.append([{"text": f"{'⭐' if m == default else '📱'} {m}",
                          "callback_data": f"switch_{m}",
                          "style": "success" if m == default else "primary"}])
        btns.append([{"text": "🔙 رجوع", "callback_data": "more", "style": "primary"}])
        send(chat_id, "\n".join(lines), btns, mid)
        return

    if data == "logout":
        send(chat_id, "🚪 <b>حذف كل الحسابات؟</b>", [
            [{"text": "✅ نعم", "callback_data": "logout_ok", "style": "danger"}],
            [{"text": "❌ إلغاء", "callback_data": "more", "style": "primary"}],
        ], mid)
        return

    if data == "logout_ok":
        all_acc = load_acc()
        all_acc.pop(str(uid), None)
        save_acc(all_acc)
        send(chat_id, "✅ تم الحذف\n\n🚪 سجّل من جديد", welcome_btn(), mid)
        return

    # ===== الحساب =====
    d = get_token(uid)
    if not d:
        send(chat_id, WELCOME_TEXT, welcome_btn(), mid)
        return
    msisdn, token = d

    if data == "acc":
        info = get_account(msisdn, token)
        if "_error" in info:
            send(chat_id, f"❌ خطأ ({info['_error']})", back_btn(), mid)
            return
        text = (
            f"💰 <b>الحساب</b>\n━━━━━━━━━━━━━━━━━━\n"
            f"📱 <code>{info.get('msisdn')}</code>\n"
            f"💵 الرصيد: <b>{info.get('accountBalance')} DZD</b>\n"
            f"🏦 قرض: <b>{info.get('sabbaqliLoanBalance')} DZD</b>\n"
            f"📅 <code>{info.get('billCycle')}</code>"
        )
        send(chat_id, text, back_btn(), mid)
        return

    if data == "plan":
        p = get_plan(msisdn, token) or {}
        text = (
            f"📦 <b>الباقة</b>\n━━━━━━━━━━━━━━━━━━\n"
            f"📦 <code>{p.get('ratePlan', '?')}</code>\n"
            f"📱 <b>{p.get('planName', '?')}</b>\n"
            f"🔢 <code>{p.get('planCode', '?')}</code>"
        )
        send(chat_id, text, back_btn(), mid)
        return

    if data == "personal":
        p = get_personal(msisdn, token)
        if "_error" in p:
            send(chat_id, "❌ خطأ", back_btn(), mid)
            return
        text = (
            f"👤 <b>شخصي</b>\n━━━━━━━━━━━━━━━━━━\n"
            f"📱 <code>{p.get('phoneNumber')}</code>\n"
            f"📦 <code>{p.get('ratePlan')}</code>\n"
            f"💳 {p.get('planType')}\n"
            f"👤 {p.get('gender')}"
        )
        send(chat_id, text, back_btn(), mid)
        return

    if data == "prizes":
        items = get_prizes(msisdn, token)
        if not items:
            text = "🎁 <b>الجوائز</b>\n\nℹ️ لا توجد جوائز\n\n💡 العب «هدية يومية»"
        else:
            now = datetime.now(timezone.utc)
            lines = ["🎁 <b>الجوائز</b>", "━━━━━━━━━━━━━━━━━━"]
            for i, p in enumerate(items, 1):
                exp = parse_exp(p.get("expiryDate", ""))
                st = "⏰ منتهية" if (exp and exp <= now) else "✅"
                es = exp.strftime("%m-%d %H:%M") if exp else "?"
                lines.append(f"\n{i}. <code>{p['uuid'][:8]}</code> {st} | {es}")
            text = "\n".join(lines)
        send(chat_id, text, ps_btn(), mid)
        return

    if data == "redeem":
        items = get_prizes(msisdn, token)
        if not items:
            send(chat_id, "🎁 لا توجد جوائز", ps_btn(), mid)
            return
        send(chat_id, "🔄 <b>جارٍ الاسترداد...</b>", [], mid)
        now = datetime.now(timezone.utc)
        ok = exp_c = err = 0
        for p in items:
            exp = parse_exp(p.get("expiryDate", ""))
            if exp and exp <= now:
                exp_c += 1
                continue
            r = redeem(msisdn, token, p["uuid"])
            if r.get("ok"): ok += 1
            elif "expired" in str(r.get("reason", "")).lower(): exp_c += 1
            else: err += 1
        send(chat_id,
             f"🎁 <b>النتيجة</b>\n✅ {ok} | ⏰ {exp_c} | ❌ {err}",
             ps_btn(), mid)
        return

    if data == "play":
        send(chat_id, "🎮 <b>جارٍ اللعب...</b>", [], mid)
        r = play(msisdn, token)
        if r.get("ok"):
            d2 = r["data"]
            send(chat_id,
                 f"🎉 <b>مبروك!</b>\n🎁 <b>{d2.get('giftName')}</b>\n⏰ صالح: {d2.get('validityHour')} ساعة",
                 [[{"text": "⚡ استرداد", "callback_data": "redeem", "style": "danger"}],
                  [{"text": "🔙 رجوع", "callback_data": "menu", "style": "primary"}]], mid)
        else:
            reason = r.get("reason", "?")
            if "already" in reason.lower() or "played" in reason.lower():
                text = "⏭️ لعبت اليوم بالفعل"
            else:
                text = f"❌ فشل\n\n<code>{reason}</code>"
            send(chat_id, text, back_btn(), mid)
        return

    if data == "hist":
        items = get_game_hist(msisdn, token)
        if not items:
            text = "🏆 السجل فارغ"
        else:
            lines = ["🏆 <b>آخر 10</b>", "━━━━━━━━━━━━━━━━━━"]
            for g in items[:10]:
                lines.append(f"• {g.get('giftName')} — {g.get('playedTime', '?')[:16]}")
            text = "\n".join(lines)
        send(chat_id, text, ps_btn(), mid)
        return

    if data == "logs":
        text = "📜 <b>السجلات</b>\n━━━━━━━━━━━━━━━━━━"
        for ct, label in [("topUp", "شحن"), ("purchase", "شراء"),
                          ("data", "بيانات"), ("call", "مكالمات"), ("sms", "رسائل")]:
            n = get_history(msisdn, token, ct)
            text += f"\n📋 {label}: <b>{n if n >= 0 else 'خطأ'}</b>"
        send(chat_id, text, more_btn(), mid)
        return


async def handle_switch(update, context):
    q = update.callback_query
    await q.answer()
    m = q.data.replace("switch_", "")
    uid = update.effective_user.id
    acc = load_acc()
    if str(uid) in acc:
        if m in acc[str(uid)].get("accounts", {}):
            acc[str(uid)]["default"] = m
            save_acc(acc)
            token = acc[str(uid)]["accounts"][m]["token"]
            await show_menu(q.message.chat_id, m, token)
            return
    await q.answer("❌ خطأ", show_alert=True)


# ═══════════════════════════════════════════════════════════
# MAIN (تم تعديله ليعمل عند إرسال الرقم مباشرة)
# ═══════════════════════════════════════════════════════════
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # ★ الحل: نقطة الدخول تشمل إرسال النص العادي (الرقم) مباشرة
    login_conv = ConversationHandler(
        entry_points=[
            CommandHandler("login", add_start),
            CallbackQueryHandler(add_start, pattern="^add$"),
            # ★ السماح لأي رسالة نصية ببدء المحادثة
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_initial_number),
        ],
        states={
            ASK_MSISDN: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_msisdn)],
            ASK_OTP: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_otp)],
        },
        fallbacks=[
            CommandHandler("cancel", cmd_cancel),
            CallbackQueryHandler(cancel_cb, pattern="^cancel$"),
        ],
        per_message=False,
        allow_reentry=True,
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("menu", cmd_menu))
    app.add_handler(CommandHandler("admin", cmd_admin))
    app.add_handler(login_conv)
    app.add_handler(CallbackQueryHandler(handle_switch, pattern="^switch_"))
    app.add_handler(CallbackQueryHandler(handle_cb))

    print(f"🐍 {BOT_NAME} Bot started...")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()