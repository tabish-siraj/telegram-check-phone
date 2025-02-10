from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, Form
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from telethon import TelegramClient
from telethon.errors import (
    PhoneNumberInvalidError,
    PhoneNumberBannedError,
    PhoneNumberFloodError,
    SessionPasswordNeededError,
    TimeoutError
)
from telethon.tl.functions.contacts import ImportContactsRequest, DeleteContactsRequest
from telethon.tl.types import InputPhoneContact
import os
from dotenv import load_dotenv
import asyncio
from fastapi.middleware.cors import CORSMiddleware

# Load environment variables
load_dotenv()

# Telegram API credentials
API_ID = os.getenv("TELEGRAM_API_ID")
API_HASH = os.getenv("TELEGRAM_API_HASH")
PHONE_NUMBER = os.getenv("TELEGRAM_PHONE")

client = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    
    global client
    try:
        client = TelegramClient('session_name', API_ID, API_HASH)
        await client.connect()
        print("Connected to Telegram")
        yield
    finally:
        # Shutdown
        if client:
            await client.disconnect()
            print("Disconnected from Telegram")


app = FastAPI(title="Telegram Account Checker", lifespan=lifespan)
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class PhoneNumber(BaseModel):
    number: str

async def get_client():
    global client
    if client is None or not client.is_connected():
        client = TelegramClient('session_name', API_ID, API_HASH)
        await client.connect()
    return client

@app.get("/")
async def read_root(request: Request):
    is_authorized = await client.is_user_authorized()
    if not is_authorized:
        await client.send_code_request(PHONE_NUMBER)
        return templates.TemplateResponse("index.html", {"request": request, "message": "Please check your Telegram app and enter the code", "is_authorized": is_authorized})
    return templates.TemplateResponse("index.html", {"request": request, "is_authorized": is_authorized})

@app.post("/verify")
async def verify(request: Request, code: str = Form(...)):
    try:
        await client.sign_in(PHONE_NUMBER, code)
        is_authorized = await client.is_user_authorized()
        return templates.TemplateResponse("index.html", {"request": request, "is_authorized": is_authorized})
    except TimeoutError:
        return templates.TemplateResponse("index.html", {"request": request, "message": "TimeoutError: Please try again", "is_authorized": False})

@app.post("/check-account")
async def check_account(request: Request, phone: PhoneNumber):
    try:
        # Clean the phone number (remove spaces, dashes, etc.)
        cleaned_number = ''.join(filter(str.isdigit, phone.number))
        
        # Add '+' prefix if not present
        if not cleaned_number.startswith('+'):
            cleaned_number = '+' + cleaned_number

        # Create an InputPhoneContact object
        contact = InputPhoneContact(
            client_id=0,
            phone=cleaned_number,
            first_name="Check",
            last_name="User"
        )
        
        try:
            # Import the contact and check the result
            result = await client(ImportContactsRequest([contact]))
            
            # Store the existence check result
            exists = bool(result.users)
            
            # If we found a user, we need to clean up the contact
            if exists:
                # Delete the contact we just added
                await client(DeleteContactsRequest(id=result.users))
            
            # Return the existence check result
            return templates.TemplateResponse("index.html", {"request": request, "is_authorized": True,"exists": exists, "phone": cleaned_number})
        except Exception as e:
            return templates.TemplateResponse(
                        "index.html",
                        {"request": request, "error": str(e)}
                    )
    except Exception as e:
        return templates.TemplateResponse(
                        "index.html",
                        {"request": request, "error": str(e)}
                    )