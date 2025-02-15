from contextlib import asynccontextmanager
from fastapi import FastAPI,Request, Form, UploadFile, File, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from telethon import TelegramClient
from telethon.errors import TimeoutError, FloodWaitError, PhoneNumberInvalidError
import asyncio
from telethon.tl.functions.contacts import SearchRequest, ImportContactsRequest, DeleteContactsRequest, GetContactsRequest, GetContactIDsRequest, DeleteByPhonesRequest
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
load_dotenv(override=True)

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
        client = TelegramClient("session_name", API_ID, API_HASH, connection_retries=5, retry_delay=1, timeout=20, system_version="4.16.30-vxCUSTOM")
        if client and client.is_connected():
            logger.info("Client is already connected")
            yield
            return        
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
            logger.info("Disconnected from Telegram")


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
        try:
            await client.send_code_request(PHONE_NUMBER)
            return templates.TemplateResponse("index.html", {"request": request, "message": "Please check your Telegram app and enter the code", "is_authorized": is_authorized})
        except Exception as e:
            logger.error(f"Error sending code: {str(e)}")
            return templates.TemplateResponse("index.html", {"request": request, "error": str(e), "is_authorized": is_authorized})
    return templates.TemplateResponse("index.html", {"request": request, "is_authorized": is_authorized})

@app.post("/verify")
async def verify(request: Request, code: str = Form(...)):
    try:
        await client.sign_in(PHONE_NUMBER, code)
        is_authorized = await client.is_user_authorized()
        return templates.TemplateResponse("index.html", {"request": request, "is_authorized": is_authorized})
    
    except TimeoutError as e:
        logger.error(f"TimeoutError: {str(e)}")
        return templates.TemplateResponse("index.html", {"request": request, "message": "TimeoutError: Please try again", "is_authorized": False})
    
    except Exception as e:
        logger.error(f"Error verifying code: {str(e)}")
        return templates.TemplateResponse("index.html", {"request": request, "error": str(e), "is_authorized": False})

@app.post("/check-account")
async def check_account(request: Request, file: UploadFile = File(None)):
    if not file:
        return templates.TemplateResponse("index.html", {"request": request, "is_authorized": True, "error": "No file uploaded"})
    try:

        contacts = await process_phone_numbers(file)        
        response = []
        logger.info(f"Importing {len(contacts)} contacts...")

        for i in range(0, len(contacts), 9):
            batch =  contacts[i:i+9]
            await asyncio.sleep(1)
            try:
                result = await client(ImportContactsRequest(batch))
                phones = [user.phone for user in result.users]
                imported = [imports.client_id for imports in result.imported]
                popular_invites = [pop.client_id for pop in result.popular_invites if pop.importers > 5]

                for contact in batch:
                    if contact.phone.strip("+") in phones:
                        response.append({
                            "phone": contact.phone,
                            "exists": True,
                            "comment": "Found"
                        })
                    elif contact.client_id not in imported and contact.client_id in popular_invites:

                        response.append({
                            "phone": contact.phone,
                            "exists": False,
                            "comment": "Not found or has privacy ON."
                        })
                    else:
                        response.append({
                            "phone": contact.phone,
                            "exists": False,
                            "comment": "Not found"
                        })
                # await client(DeleteContactsRequest(id=result.users))
                await client(DeleteContactsRequest([user.id for user in result.users]))

            except Exception as e:
                logger.error(f"Error: {str(e)}")
                return templates.TemplateResponse("index.html", {"request": request, "is_authorized": True, "response": response, "error": str(e)})
                
            # Return the existence check result
        return templates.TemplateResponse("index.html", {"request": request, "is_authorized": True, "response": response})
    except Exception as e:
        logger.error(f"Error processing file: {str(e)}")
        return templates.TemplateResponse(
                        "index.html",
                        {"request": request, "is_authorized": True, "error": str(e), "response": response})

async def process_phone_numbers(file: UploadFile):
    numbers = []
    try:
        file_bytes = file.file.read()
        buffer = StringIO(file_bytes.decode('utf-8'))
        reader = csv.reader(buffer)
        next(reader)
        counter = 1
        for row in reader:
            if row and row[0].strip():
                numbers.append(InputPhoneContact(
                    client_id=counter,
                    phone=row[0].strip(),
                    first_name=f"Check{counter}",
                    last_name=f"User{counter}"
                ))
                counter += 1
                if counter > 30:
                    break
                # numbers.append(str(row[0]).strip())
        file.file.close()
        buffer.close()
    except Exception as e:
        logger.error(f"Error reading CSV file: {str(e)}")
    return numbers

if __name__ == "__main__":
    import uvicorn
    PORT = int(os.getenv("PORT", 10000))
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=True)

