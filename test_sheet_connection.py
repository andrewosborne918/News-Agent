import os, sys, traceback
from dotenv import load_dotenv

print("🔧 Loading .env from:", os.path.abspath(".env"))
load_dotenv(".env")

SHEET_KEY = os.getenv("GOOGLE_SHEETS_KEY")
CREDS_PATH = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON_PATH")

print("ENV:")
print("  GOOGLE_SHEETS_KEY =", SHEET_KEY)
print("  GOOGLE_SERVICE_ACCOUNT_JSON_PATH =", CREDS_PATH)
print("  CWD =", os.getcwd())
print("  Python =", sys.executable)

def die(msg):
    print("❌", msg)
    sys.exit(1)

if not SHEET_KEY:
    die("GOOGLE_SHEETS_KEY missing in .env (put the spreadsheet ID between /d/ and /edit).")

if not CREDS_PATH:
    die("GOOGLE_SERVICE_ACCOUNT_JSON_PATH missing in .env")

if not os.path.exists(CREDS_PATH):
    die(f"Service account key not found at {CREDS_PATH} (place your JSON key there).")

try:
    import gspread
    print("✅ gspread imported")
except Exception as e:
    print("❌ Could not import gspread")
    traceback.print_exc()
    sys.exit(1)

try:
    print("🔗 Authorizing with service account…")
    gc = gspread.service_account(filename=CREDS_PATH)
    print("🔗 Opening spreadsheet by key:", SHEET_KEY)
    sh = gc.open_by_key(SHEET_KEY)
    titles = [ws.title for ws in sh.worksheets()]
    print("📄 Worksheets found:", titles)

    # Ensure required tabs exist
    required = {"Questions", "Runs", "AnswerSegments"}
    missing = required - set(titles)
    if missing:
        die(f"Missing required tab(s): {', '.join(sorted(missing))}")

    # Read Questions
    ws_q = sh.worksheet("Questions")
    rows = ws_q.get_all_records()
    active = [(r["question_id"], r["question_text"]) for r in rows if str(r.get("enabled","TRUE")).upper() == "TRUE"]
    print("✅ Active questions:")
    for qid, qtext in active:
        print(f"   - {qid}: {qtext}")

    # Optional write test (commented out)
    """
    ws_seg = sh.worksheet("AnswerSegments")
    ws_seg.append_rows([[
        "diagnostic-run", "what_happened", 0,
        "Test sentence from diagnostic script.", "", 3.5
    ]], value_input_option="RAW")
    print("✍️  Appended one test row to AnswerSegments.")
    """

    print("🎉 All good.")
except Exception as e:
    print("💥 Exception during Sheets access:")
    traceback.print_exc()
    sys.exit(1)