import os
import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv

load_dotenv()

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly"
]

def get_sheet_data():
    sheet_id = os.getenv("GOOGLE_SHEET_ID")
    if not sheet_id:
        raise ValueError("Missing GOOGLE_SHEET_ID in environment variables")
        
    creds_path = "credentials.json"
    if not os.path.exists(creds_path):
        raise FileNotFoundError(f"Missing {creds_path}")

    creds = Credentials.from_service_account_file(creds_path, scopes=SCOPES)
    client = gspread.authorize(creds)
    
    # Mở sheet đầu tiên
    sheet = client.open_by_key(sheet_id).sheet1
    
    # get_all_records() sẽ lấy dòng đầu tiên làm header
    # và trả về danh sách các dictionary
    return sheet.get_all_records()
