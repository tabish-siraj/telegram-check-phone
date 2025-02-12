from contextlib import asynccontextmanager
from fastapi import FastAPI,Request, Form, UploadFile, File
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from telethon import TelegramClient
from telethon.errors import (
    TimeoutError
)
from telethon.tl.functions.contacts import ImportContactsRequest, DeleteContactsRequest
from telethon.tl.types import InputPhoneContact
import os
from dotenv import load_dotenv
import csv
from fastapi.middleware.cors import CORSMiddleware
import logging
from io import StringIO

# Configure logging to be less verbose
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Disable debug logs for specific modules
logging.getLogger('telethon.network.mtprotosender').setLevel(logging.WARNING)
logging.getLogger('telethon.extensions.messagepacker').setLevel(logging.WARNING)
logging.getLogger('telethon.network.connection.connection').setLevel(logging.WARNING)
logging.getLogger('telethon.client.telegrambaseclient').setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Telegram API credentials
API_ID = os.getenv("TELEGRAM_API_ID")
API_HASH = os.getenv("TELEGRAM_API_HASH")
PHONE_NUMBER = os.getenv("TELEGRAM_PHONE")

# Verify credentials are loaded
if not all([API_ID, API_HASH, PHONE_NUMBER]):
    raise ValueError("Missing required environment variables. Please check your .env file.")


client: TelegramClient = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    
    global client
    try:
        if client and client.is_connected():
            logger.info("Client is already connected")
            yield
            return
        client = TelegramClient('session_name', API_ID, API_HASH, connection_retries=5, retry_delay=1, timeout=20, system_version="4.16.30-vxCUSTOM")
        
        logger.info("Attempting to connect to Telegram...")
        
        await client.connect()

        logger.info("Connected to Telegram successfully")

        # Test the connection
        if await client.is_user_authorized():
            logger.info("Client is already authorized")
        else:
            logger.info("Client needs authorization")

        yield

    except Exception as e:
        logger.error(f"Error during startup: {str(e)}", exc_info=True)
        raise
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
async def check_account(request: Request, file: UploadFile = File(None)):
    response = []
    try:
        if not file:
            return templates.TemplateResponse("index.html", {"request": request, "is_authorized": True, "error": "No file uploaded"})

        contacts = await process_phone_numbers(file)        
        try:
            # Import the contact and check the result
            logger.info(f"Importing {len(contacts)} contacts...")
            result = await client(ImportContactsRequest(contacts))
            phones = [user.phone for user in result.users]
            for contact in contacts:
                if contact.phone.strip("+") in phones:
                    response.append({
                        "phone": contact.phone,
                        "exists": True
                    })
                else:
                    response.append({
                        "phone": contact.phone,
                        "exists": False
                    })

            # Delete the contact we just added
            await client(DeleteContactsRequest(id=result.users))
            
            # Return the existence check result
            return templates.TemplateResponse("index.html", {"request": request, "is_authorized": True, "response": response})
        except Exception as e:
            return templates.TemplateResponse(
                        "index.html",
                        { "request": request, "is_authorized": True, "error": str(e)})
    except Exception as e:
        return templates.TemplateResponse(
                        "index.html",
                        {"request": request, "is_authorized": True, "error": str(e)})
    

async def process_phone_numbers(file: UploadFile):
    numbers = []
    try:
        file_bytes = file.file.read()
        buffer = StringIO(file_bytes.decode('utf-8'))
        reader = csv.reader(buffer)
        counter = 0
        next(reader)
        for row in reader:
            if not row: continue
            numbers.append(InputPhoneContact(
                client_id=counter,
                phone=row[0],
                first_name="Check",
                last_name="User"
            ))
            counter += 1
        
        file.file.close()
        buffer.close()
    except Exception as e:
        logger.error(f"Error reading CSV file: {str(e)}")
    return numbers

if __name__ == "__main__":
    import uvicorn
    PORT = int(os.getenv("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=PORT)

