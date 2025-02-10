from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from telethon import TelegramClient
from telethon.errors import (
    PhoneNumberInvalidError,
    PhoneNumberBannedError,
    PhoneNumberFloodError,
    SessionPasswordNeededError,
    TimeoutError, TimedoutError, TimedOutError
)
from telethon.tl.functions.contacts import ImportContactsRequest, DeleteContactsRequest
from telethon.tl.types import InputPhoneContact
import os
from dotenv import load_dotenv

from fastapi.middleware.cors import CORSMiddleware

# Load environment variables
load_dotenv()

app = FastAPI(title="Telegram Account Checker")

# After creating the FastAPI app, add:
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with your frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Telegram API credentials
API_ID = os.getenv("TELEGRAM_API_ID")
API_HASH = os.getenv("TELEGRAM_API_HASH")
PHONE_NUMBER = os.getenv("TELEGRAM_PHONE")  # Your phone number for authentication

# Initialize Telegram client
client = TelegramClient('session_name', API_ID, API_HASH)

class PhoneNumber(BaseModel):
    number: str

@app.on_event("startup")
async def startup_event():
    await client.connect()
    if not await client.is_user_authorized():
        # Start the sign in process
        try:
            code = await client.send_code_request(PHONE_NUMBER)
            print(f"Please check your Telegram app and enter the code at startup!")
            # This will prompt in the console - you'll need to enter the code manually
            await client.sign_in(PHONE_NUMBER, input('Enter the code: '))
        except TimeoutError or TimedOutError or TimedoutError:
            print("TimeoutError: Please try again")
        except SessionPasswordNeededError:
            # In case you have two-step verification enabled
            await client.sign_in(password=input('Please enter your password: '))

@app.on_event("shutdown")
async def shutdown_event():
    await client.disconnect()

@app.get("/")
async def read_root():
    return {"message": "Welcome to the Telegram Account Checker API"}


@app.post("/check-account")
async def check_account(phone: PhoneNumber):
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
            
            return {
                "exists": exists,
                "message": "Account exists on Telegram" if exists else "No account found for this number"
            }
                
        except PhoneNumberBannedError:
            raise HTTPException(status_code=403, detail="This phone number is banned from Telegram")
        except PhoneNumberFloodError:
            raise HTTPException(status_code=429, detail="Too many requests. Please try again later")
                
    except PhoneNumberInvalidError:
        raise HTTPException(status_code=400, detail="Invalid phone number format")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# For local development
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)