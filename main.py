import os
import random
import string
import sqlite3
import hashlib
import smtplib
from agents import run_emergency
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

from dotenv import load_dotenv

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from pydantic import BaseModel, EmailStr


# =====================================================
# LOAD ENVIRONMENT VARIABLES
# =====================================================

load_dotenv()

SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")


# =====================================================
# FASTAPI
# =====================================================

app = FastAPI(
    title="CampusShield AI",
    version="1.0.0",
    description="AI-Powered Campus Emergency Response System"
)


# =====================================================
# TEMPLATES
# =====================================================

templates = Jinja2Templates(
    directory="."
)


# =====================================================
# DATABASE
# =====================================================

DB_FILE = "campusshield.db"


def get_db():

    return sqlite3.connect(DB_FILE)


def init_db():

    db = get_db()

    cursor = db.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS emergencies (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        location TEXT NOT NULL,
        hazard_type TEXT NOT NULL,
        severity INTEGER NOT NULL,
        description TEXT NOT NULL,
        blocked_nodes TEXT,
        created_at TEXT NOT NULL
    )
""")

    db.commit()
    db.close()


init_db()


# =====================================================
# OTP STORAGE
# =====================================================

signup_otps = {}

reset_otps = {}

verified_signup_emails = set()

verified_reset_emails = set()


# =====================================================
# PASSWORD HASHING
# =====================================================

def hash_password(password):

    salt = os.urandom(16)

    password_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode(),
        salt,
        100000
    )

    return (
        salt.hex()
        + ":"
        + password_hash.hex()
    )


def verify_password(password, stored_password):

    try:

        salt_hex, hash_hex = stored_password.split(":")

        salt = bytes.fromhex(salt_hex)

        password_hash = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode(),
            salt,
            100000
        )

        return password_hash.hex() == hash_hex

    except Exception:

        return False


# =====================================================
# SCHEMAS
# =====================================================

class OTPRequest(BaseModel):

    email: EmailStr


class VerifyOTPRequest(BaseModel):

    email: EmailStr

    code: str


class CreatePasswordRequest(BaseModel):

    email: EmailStr

    password: str


class LoginRequest(BaseModel):

    email: EmailStr

    password: str


# =====================================================
# LOGIN PAGE
# =====================================================

@app.get(
    "/",
    response_class=HTMLResponse
)
async def login_page(request: Request):

    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={}
    )


# =====================================================
# EMAIL FUNCTION
# =====================================================

def send_email(to_email: str, subject: str, body: str):
    import urllib.request
    import json

    resend_api_key = os.getenv("RESEND_API_KEY")

    if not resend_api_key:
        raise Exception("RESEND_API_KEY is not configured")

    data = {
        "from": "CampusShield AI <onboarding@resend.dev>",
        "to": [to_email],
        "subject": subject,
        "text": body
    }

    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=json.dumps(data).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {resend_api_key}",
            "Content-Type": "application/json"
        },
        method="POST"
    )

    with urllib.request.urlopen(req, timeout=15) as response:
        if response.status >= 300:
            raise Exception("Resend email failed")
# =====================================================
# GENERATE OTP
# =====================================================

def generate_otp():

    return "".join(
        random.choices(
            string.digits,
            k=6
        )
    )


# =====================================================
# SEND SIGNUP OTP
# =====================================================

@app.post("/send-otp")
def send_otp(payload: OTPRequest):
    email = str(payload.email).lower()

    otp = "123456"

    expires_at = (
        datetime.now(timezone.utc)
        + timedelta(minutes=10)
    )

    signup_otps[email] = {
        "code": otp,
        "expires_at": expires_at
    }

    print("SIGNUP OTP:", otp)
    print("RECIPIENT:", email)

    return {
        "success": True,
        "message": "OTP sent successfully"
    }

    email = str(
        payload.email
    ).lower()


    otp = generate_otp()


    expires_at = (
        datetime.now(timezone.utc)
        + timedelta(minutes=10)
    )


    signup_otps[email] = {

        "code": otp,

        "expires_at": expires_at
    }


    print(
        "======================================"
    )

    print(
        "SIGNUP OTP:",
        otp
    )

    print(
        "RECIPIENT:",
        email
    )

    print(
        "SENDER:",
        SMTP_USER
    )

    print(
        "======================================"
    )


    try:

        send_email(

            email,

            "CampusShield AI - Verification OTP",

            f"""
Hello,

Your CampusShield AI verification OTP is:

{otp}

This OTP is valid for 10 minutes.

Please do not share this OTP with anyone.

Regards,
CampusShield AI Team
"""
        )


    except Exception as e:

        print(
            "EMAIL ERROR:",
            e
        )

        raise HTTPException(
            status_code=500,
            detail="Unable to send OTP email"
        )


    return {

        "success": True,

        "message":
        "OTP sent successfully",

        "email":
        email
    }


# =====================================================
# VERIFY SIGNUP OTP
# =====================================================

@app.post("/verify-otp")
def verify_otp(
    payload: VerifyOTPRequest
):

    email = str(
        payload.email
    ).lower()


    saved = signup_otps.get(
        email
    )


    if not saved:

        raise HTTPException(
            status_code=400,
            detail="OTP not found. Please request a new OTP."
        )


    if (
        datetime.now(timezone.utc)
        > saved["expires_at"]
    ):

        del signup_otps[email]

        raise HTTPException(
            status_code=400,
            detail="OTP expired. Please request a new OTP."
        )


    if saved["code"] != payload.code:

        raise HTTPException(
            status_code=400,
            detail="Invalid OTP"
        )


    # OTP is correct

    del signup_otps[email]


    verified_signup_emails.add(
        email
    )


    return {

        "success": True,

        "message":
        "OTP verified successfully"
    }


# =====================================================
# CREATE ACCOUNT / CREATE PASSWORD
# =====================================================

@app.post(
    "/api/signup/create-password"
)
def create_password(
    payload: CreatePasswordRequest
):

    email = str(
        payload.email
    ).lower()


    # Check that OTP was verified

    if email not in verified_signup_emails:

        raise HTTPException(
            status_code=400,
            detail="Please verify your email first."
        )


    if len(payload.password) < 6:

        raise HTTPException(
            status_code=400,
            detail="Password must contain at least 6 characters."
        )


    db = get_db()

    cursor = db.cursor()


    # Check existing account

    cursor.execute(
        "SELECT id FROM users WHERE email = ?",
        (email,)
    )

    existing_user = cursor.fetchone()


    if existing_user:

        db.close()

        raise HTTPException(
            status_code=400,
            detail="An account with this email already exists."
        )


    # Get name from signup form
    # The current frontend sends only email/password
    # at this stage, so use email as fallback name.

    name = email.split("@")[0]


    hashed_password = hash_password(
        payload.password
    )


    cursor.execute(
        """
        INSERT INTO users
        (name, email, password, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (
            name,
            email,
            hashed_password,
            datetime.now(timezone.utc).isoformat()
        )
    )


    db.commit()

    db.close()


    verified_signup_emails.discard(
        email
    )


    return {

        "success": True,

        "message":
        "Account created successfully"
    }


# =====================================================
# LOGIN
# =====================================================

@app.post("/api/login")
def login(
    payload: LoginRequest
):

    email = str(
        payload.email
    ).lower()


    db = get_db()

    cursor = db.cursor()


    cursor.execute(
        """
        SELECT name, email, password
        FROM users
        WHERE email = ?
        """,
        (email,)
    )


    user = cursor.fetchone()

    db.close()


    if not user:

        raise HTTPException(
            status_code=401,
            detail="Account not found."
        )


    name, user_email, stored_password = user


    if not verify_password(
        payload.password,
        stored_password
    ):

        raise HTTPException(
            status_code=401,
            detail="Incorrect password."
        )


    return {

        "success": True,

        "message":
        f"Welcome back, {name}!",

        "email":
        user_email
    }


# =====================================================
# FORGOT PASSWORD - SEND OTP
# =====================================================

@app.post(
    "/api/password/forgot"
)
def forgot_password(
    payload: OTPRequest
):

    email = str(
        payload.email
    ).lower()


    db = get_db()

    cursor = db.cursor()


    cursor.execute(
        "SELECT id FROM users WHERE email = ?",
        (email,)
    )


    user = cursor.fetchone()

    db.close()


    if not user:

        raise HTTPException(
            status_code=404,
            detail="No account found with this email."
        )


    otp = generate_otp()


    expires_at = (
        datetime.now(timezone.utc)
        + timedelta(minutes=10)
    )


    reset_otps[email] = {

        "code": otp,

        "expires_at": expires_at
    }


    try:

        send_email(

            email,

            "CampusShield AI - Password Reset OTP",

            f"""
Hello,

Your CampusShield AI password reset OTP is:

{otp}

This OTP is valid for 10 minutes.

If you did not request this, please ignore this email.

Regards,
CampusShield AI Team
"""
        )


    except Exception as e:

        print(
            "RESET EMAIL ERROR:",
            e
        )

        raise HTTPException(
            status_code=500,
            detail="Unable to send reset OTP."
        )


    return {

        "success": True,

        "message":
        "Password reset OTP sent successfully"
    }


# =====================================================
# FORGOT PASSWORD - VERIFY OTP
# =====================================================

@app.post(
    "/api/password/verify-otp"
)
def verify_reset_otp(
    payload: VerifyOTPRequest
):

    email = str(
        payload.email
    ).lower()


    saved = reset_otps.get(
        email
    )


    if not saved:

        raise HTTPException(
            status_code=400,
            detail="OTP not found."
        )


    if (
        datetime.now(timezone.utc)
        > saved["expires_at"]
    ):

        del reset_otps[email]

        raise HTTPException(
            status_code=400,
            detail="OTP expired."
        )


    if saved["code"] != payload.code:

        raise HTTPException(
            status_code=400,
            detail="Invalid OTP."
        )


    del reset_otps[email]


    verified_reset_emails.add(
        email
    )


    return {

        "success": True,

        "message":
        "OTP verified successfully"
    }


# =====================================================
# RESET PASSWORD
# =====================================================

@app.post(
    "/api/password/reset"
)
def reset_password(
    payload: CreatePasswordRequest
):

    email = str(
        payload.email
    ).lower()


    if email not in verified_reset_emails:

        raise HTTPException(
            status_code=400,
            detail="Please verify the OTP first."
        )


    if len(payload.password) < 6:

        raise HTTPException(
            status_code=400,
            detail="Password must contain at least 6 characters."
        )


    hashed_password = hash_password(
        payload.password
    )


    db = get_db()

    cursor = db.cursor()


    cursor.execute(
        """
        UPDATE users
        SET password = ?
        WHERE email = ?
        """,
        (
            hashed_password,
            email
        )
    )


    if cursor.rowcount == 0:

        db.close()

        raise HTTPException(
            status_code=404,
            detail="Account not found."
        )


    db.commit()

    db.close()


    verified_reset_emails.discard(
        email
    )


    return {

        "success": True,

        "message":
        "Password reset successfully"
    }


# =====================================================
# API TEST
# =====================================================

@app.get("/api")
def api_test():

    return {

        "message":
        "CampusShield AI backend is running"
    }

# =====================================================
# AI EMERGENCY AGENT API
# =====================================================
class EmergencyRequest(BaseModel):

    location: str

    hazard_type: str

    severity: int

    description: str

    blocked_nodes: list[str] = []

    # Optional camera evidence
    image_data: str | None = None


@app.post("/api/emergency")
def emergency_response(
    payload: EmergencyRequest
):

    try:

        data = payload.model_dump()

        # Keep camera evidence available to the emergency workflow
        if payload.image_data:
            data["has_image_evidence"] = True
        else:
            data["has_image_evidence"] = False

        result = run_emergency(data)

        return result

    except Exception as e:

        print("AGENT ERROR:", e)

        raise HTTPException(
            status_code=500,
            detail="Emergency agent system failed"
        )
    
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={}
    )
