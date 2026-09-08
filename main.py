from fastapi import FastAPI, Header, HTTPException, Depends
from pydantic import BaseModel
import sqlite3
import secrets
from google import genai

app = FastAPI(title="Custom Trade Compliance API", version="1.0")

# --- Database & Security Setup ---

def get_db():
    conn = sqlite3.connect("trade_pulse_internal.db")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def init_db():
    with sqlite3.connect("trade_pulse_internal.db") as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS api_keys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_name TEXT NOT NULL,
                api_key TEXT UNIQUE NOT NULL,
                is_active BOOLEAN NOT NULL DEFAULT 1
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS compliance_rules (
                country TEXT,
                product_type TEXT,
                status TEXT,
                risk_rating TEXT,
                actionable_notes TEXT,
                PRIMARY KEY (country, product_type)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tariffs (
                country TEXT,
                product_type TEXT,
                duty_rate REAL,
                sales_tax REAL,
                PRIMARY KEY (country, product_type)
            )
        """)
        # Populate initial test data
        conn.execute("""
            INSERT OR REPLACE INTO compliance_rules 
            (country, product_type, status, risk_rating, actionable_notes)
            VALUES (?, ?, ?, ?, ?)
        """, ("Pakistan", "electronics", "Review Required", "Medium", "Verify FBR regulatory requirements and import authorization."))
        
        conn.execute("""
            INSERT OR REPLACE INTO tariffs 
            (country, product_type, duty_rate, sales_tax)
            VALUES (?, ?, ?, ?)
        """, ("Pakistan", "electronics", 20.0, 18.0))

init_db()

# --- Authentication Dependency ---

def verify_api_key(x_api_key: str = Header(...)):
    with sqlite3.connect("trade_pulse_internal.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT is_active FROM api_keys WHERE api_key = ?", (x_api_key,))
        result = cursor.fetchone()
        if not result or result[0] != 1:
            raise HTTPException(status_code=403, detail="Invalid or inactive API key.")
    return x_api_key

# --- Request Models ---

class KeyGenRequest(BaseModel):
    client_name: str

class ShipmentScreenRequest(BaseModel):
    country_of_origin: str
    product_type: str
    declared_value: float

# --- API Endpoints ---

@app.post("/admin/generate-key")
def generate_api_key(body: KeyGenRequest):
    """Generates a new internal API key for a client."""
    new_key = f"trd_live_{secrets.token_hex(16)}"
    with sqlite3.connect("trade_pulse_internal.db") as conn:
        try:
            conn.execute("""
                INSERT INTO api_keys (client_name, api_key, is_active)
                VALUES (?, ?, 1)
            """, (body.client_name, new_key))
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=500, detail="Key collision error. Try again.")
    return {"client_name": body.client_name, "api_key": new_key}

@app.post("/screen-shipment")
def screen_shipment(body: ShipmentScreenRequest, api_key: str = Depends(verify_api_key)):
    """Screens a shipment against local SQLite data and uses Gemini to generate a report."""
    country = body.country_of_origin.strip().capitalize()
    product = body.product_type.strip().lower()

    with sqlite3.connect("trade_pulse_internal.db") as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT c.status, c.risk_rating, c.actionable_notes, t.duty_rate, t.sales_tax
            FROM compliance_rules c
            JOIN tariffs t ON c.country = t.country AND c.product_type = t.product_type
            WHERE c.country = ? AND c.product_type = ?
        """, (country, product))
        data = cursor.fetchone()

    if data:
        status, risk, notes, duty_rate, sales_tax = data
        duty = body.declared_value * (duty_rate / 100.0)
        tax = (body.declared_value + duty) * (sales_tax / 100.0)
        total_cost = round(body.declared_value + duty + tax, 2)
        screening_result = {
            "country_of_origin": country,
            "product_type": product,
            "status": status,
            "risk_rating": risk,
            "estimated_landed_cost_usd": total_cost,
            "actionable_notes": notes
        }
    else:
        default_duty = 0.15
        default_tax = 0.18
        total_cost = round(body.declared_value * (1 + default_duty) * (1 + default_tax), 2)
        screening_result = {
            "country_of_origin": country,
            "product_type": product,
            "status": "Cleared",
            "risk_rating": "Low",
            "estimated_landed_cost_usd": total_cost,
            "actionable_notes": "No specific restrictions found in local registry. Standard rates applied."
        }

    # Generate Gemini report
    client = genai.Client()
    prompt = f"""
    Act as a trade compliance expert. Based on the following trade data screening result, 
    generate a professional summary report for the user. 
    
    Data: {screening_result}
    
    The report should include the status, risk rating, estimated landed cost, and the actionable notes.
    Keep it concise and clear.
    """

    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
        )
        report_text = response.text
    except Exception as e:
        report_text = f"Error generating report with AI: {str(e)}"

    return {
        "screening_data": screening_result,
        "ai_report": report_text
    }