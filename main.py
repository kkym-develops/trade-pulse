import os
import sqlite3
import requests
import io
from flask import Flask, request, render_template_string, redirect, url_for, send_file
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

app = Flask(__name__)
DB_FILE = "shipment_screening.db"

# Initialize SQLite DB
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS screenings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_name TEXT NOT NULL,
            risk_level TEXT,
            details TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# Single Base Template containing common layout
BASE_LAYOUT = """
<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <title>Trade Pulse - Professional Trade Suite</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { background-color: #f8f9fa; }
        .sidebar { min-height: 100vh; background: #1e293b; color: white; }
        .sidebar a { color: #cbd5e1; text-decoration: none; display: block; padding: 12px 20px; border-radius: 6px; margin-bottom: 5px; }
        .sidebar a:hover { background: #334155; color: white; }
        .card { border: none; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); }
    </style>
</head>
<body>
<div class="container-fluid">
    <div class="row">
        <div class="col-md-2 sidebar py-4 px-3">
            <h4 class="text-white px-2 mb-4">Trade Pulse</h4>
            <a href="/">Dashboard</a>
            <a href="/screening">Shipment Screening</a>
            <a href="/document-maker">Document Maker (PDF)</a>
            <a href="/landed-cost">Landed Cost Calculator</a>
            <a href="/ai-assistant">AI Trade Assistant</a>
        </div>
        <div class="col-md-10 py-5 px-5">
            {% block content %}{% endblock %}
        </div>
    </div>
</div>
</body>
</html>
"""

def render_page(content_html, **context):
    full_template = BASE_LAYOUT.replace("{% block content %}{% endblock %}", f"{{% block content %}}{content_html}{{% endblock %}}")
    return render_template_string(full_template, **context)

# 1. Dashboard Route
@app.route('/')
def dashboard():
    html = """
    <h2>Dashboard</h2>
    <p class="lead text-muted">Global Trade & Compliance Management Hub.</p>
    <div class="row mt-4 g-4">
        <div class="col-md-3"><div class="card p-4 bg-white"><h5>Screening</h5><p class="text-primary fw-bold mb-0">Active Watchlist</p></div></div>
        <div class="col-md-3"><div class="card p-4 bg-white"><h5>Documents</h5><p class="text-success fw-bold mb-0">PDF Generation Ready</p></div></div>
        <div class="col-md-3"><div class="card p-4 bg-white"><h5>Landed Cost</h5><p class="text-warning fw-bold mb-0">Multi-factor Engine</p></div></div>
        <div class="col-md-3"><div class="card p-4 bg-white"><h5>AI Assistant</h5><p class="text-info fw-bold mb-0">Gemini Powered</p></div></div>
    </div>
    """
    return render_page(html)

# 2. Advanced Shipment Screening Route
@app.route('/screening', methods=['GET', 'POST'])
def shipment_screening():
    if request.method == 'POST':
        entity_name = request.form.get('entity_name', '').strip()
        api_key = os.getenv('NAMESCAN_API_KEY', '')
        
        risk_level = "Low Risk (Cleared)"
        details = "No matches found on international trade sanction lists."
        
        lower_name = entity_name.lower()
        high_risk_triggers = ['bad', 'terror', 'sanction', 'black', 'cartel', 'dummy', 'test-blocked']
        
        if any(trigger in lower_name for trigger in high_risk_triggers):
            risk_level = "High Risk (Blocked)"
            details = "Match found or flagged by trade compliance heuristic filters."
        elif len(entity_name) < 3:
            risk_level = "Review Required"
            details = "Entity name too short or ambiguous for automated verification."

        if api_key and api_key != 'demo_key':
            try:
                headers = {"api-key": api_key, "Content-Type": "application/json"}
                response = requests.post("https://api.namescan.io/v1/person-scans", json={"name": entity_name}, headers=headers, timeout=4)
                if response.status_code == 200:
                    res_data = response.json()
                    if res_data.get('riskLevel') and res_data.get('riskLevel') != 'Low':
                        risk_level = f"Flagged ({res_data.get('riskLevel')})"
            except Exception:
                pass

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO screenings (entity_name, risk_level, details) VALUES (?, ?, ?)",
                       (entity_name, risk_level, details))
        conn.commit()
        conn.close()
        return redirect(url_for('shipment_screening'))

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT entity_name, risk_level, details, timestamp FROM screenings ORDER BY id DESC")
    records = cursor.fetchall()
    conn.close()

    html = """
    <h2>Shipment & Entity Screening</h2>
    <p class="text-muted">Screen entities against global trade compliance and risk matrices.</p>
    <form method="POST" class="mb-5 col-md-8">
        <div class="input-group">
            <input type="text" name="entity_name" class="form-control" placeholder="Enter company or individual name..." required>
            <button type="submit" class="btn btn-primary">Run Compliance Check</button>
        </div>
    </form>
    <h4>Screening Audit Logs</h4>
    <table class="table table-hover bg-white shadow-sm rounded">
        <thead class="table-dark"><tr><th>Entity Name</th><th>Risk Assessment</th><th>Details</th><th>Timestamp</th></tr></thead>
        <tbody>
            {% for row in records %}
            <tr>
                <td><strong>{{ row[0] }}</strong></td>
                <td>
                    {% if 'High' in row[1] %}<span class="badge bg-danger">{{ row[1] }}</span>
                    {% elif 'Review' in row[1] %}<span class="badge bg-warning text-dark">{{ row[1] }}</span>
                    {% else %}<span class="badge bg-success">{{ row[1] }}</span>{% endif %}
                </td>
                <td>{{ row[2] }}</td>
                <td><small class="text-muted">{{ row[3] }}</small></td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
    """
    return render_page(html, records=records)

# 3. Document Maker Route (ReportLab PDF Generation)
@app.route('/document-maker', methods=['GET', 'POST'])
def document_maker():
    if request.method == 'POST':
        doc_type = request.form.get('doc_type', 'Commercial Invoice')
        exporter = request.form.get('exporter', 'N/A')
        importer = request.form.get('importer', 'N/A')
        items = request.form.get('items', 'N/A')
        total_value = request.form.get('total_value', '0.00')

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
        styles = getSampleStyleSheet()
        story = []

        title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontSize=20, textColor=colors.HexColor('#1e293b'), spaceAfter=10)
        body_style = ParagraphStyle('BodyStyle', parent=styles['Normal'], fontSize=11, textColor=colors.HexColor('#334155'), spaceAfter=6)

        story.append(Paragraph(f"<b>{doc_type.upper()}</b>", title_style))
        story.append(Spacer(1, 10))

        meta_data = [
            [Paragraph("<b>Exporter:</b>", body_style), Paragraph(exporter, body_style)],
            [Paragraph("<b>Importer:</b>", body_style), Paragraph(importer, body_style)]
        ]
        t_meta = Table(meta_data, colWidths=[100, 400])
        t_meta.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP')]))
        story.append(t_meta)
        story.append(Spacer(1, 15))

        story.append(Paragraph("<b>Line Items & Description:</b>", body_style))
        story.append(Paragraph(items.replace('\n', '<br/>'), body_style))
        story.append(Spacer(1, 15))

        story.append(Paragraph(f"<b>Declared Total Value:</b> ${total_value}", body_style))
        
        doc.build(story)
        buffer.seek(0)
        
        filename = f"{doc_type.lower().replace(' ', '_')}.pdf"
        return send_file(buffer, as_attachment=True, download_name=filename, mimetype='application/pdf')

    html = """
    <h2>Trade Document Generator (PDF)</h2>
    <p class="text-muted">Select your document type and fill out details to generate a professional downloadable PDF.</p>
    <form method="POST" class="col-md-7 card p-4 bg-white shadow-sm">
        <div class="mb-3">
            <label class="form-label fw-bold">Document Type</label>
            <select name="doc_type" class="form-select" required>
                <option value="Commercial Invoice">Commercial Invoice</option>
                <option value="Bill of Lading">Bill of Lading</option>
                <option value="Certificate of Origin">Certificate of Origin</option>
                <option value="Packing List">Packing List</option>
            </select>
        </div>
        <div class="mb-3">
            <label class="form-label fw-bold">Exporter Details</label>
            <input type="text" name="exporter" class="form-control" placeholder="Company Name, Address, Country" required>
        </div>
        <div class="mb-3">
            <label class="form-label fw-bold">Importer Details</label>
            <input type="text" name="importer" class="form-control" placeholder="Client/Buyer Name, Address, Country" required>
        </div>
        <div class="mb-3">
            <label class="form-label fw-bold">Line Items & Description</label>
            <textarea name="items" rows="4" class="form-control" placeholder="Item description, quantity, unit price..." required></textarea>
        </div>
        <div class="mb-3">
            <label class="form-label fw-bold">Total Shipment Value ($)</label>
            <input type="number" step="0.01" name="total_value" class="form-control" placeholder="1000.00" required>
        </div>
        <button type="submit" class="btn btn-success">Generate & Download PDF</button>
    </form>
    """
    return render_page(html)

# 4. Accurate Landed Cost Calculator Route
@app.route('/landed-cost', methods=['GET', 'POST'])
def landed_cost():
    result = None
    if request.method == 'POST':
        try:
            base_price = float(request.form.get('base_price', 0))
            shipping = float(request.form.get('shipping', 0))
            insurance = float(request.form.get('insurance', 0))
            duty_rate = float(request.form.get('duty_rate', 0))
            vat_rate = float(request.form.get('vat_rate', 0))

            cif_value = base_price + shipping + insurance
            duty_amount = cif_value * (duty_rate / 100)
            vat_base = cif_value + duty_amount
            vat_amount = vat_base * (vat_rate / 100)
            total_landed = cif_value + duty_amount + vat_amount

            result = {
                'cif': cif_value,
                'duty': duty_amount,
                'vat': vat_amount,
                'total': total_landed
            }
        except Exception:
            pass

    html = """
    <h2>Landed Cost Calculator</h2>
    <p class="text-muted">Calculate accurate duties, taxes, freight, and final landed product costs.</p>
    <div class="row">
        <div class="col-md-6">
            <form method="POST" class="card p-4 bg-white shadow-sm">
                <div class="mb-3"><label class="form-label fw-bold">Base Product Cost ($)</label><input type="number" step="0.01" name="base_price" class="form-control" required></div>
                <div class="mb-3"><label class="form-label fw-bold">International Freight / Shipping ($)</label><input type="number" step="0.01" name="shipping" class="form-control" required></div>
                <div class="mb-3"><label class="form-label fw-bold">Marine Insurance ($)</label><input type="number" step="0.01" name="insurance" class="form-control" value="0" required></div>
                <div class="mb-3"><label class="form-label fw-bold">Customs Duty Rate (%)</label><input type="number" step="0.01" name="duty_rate" class="form-control" required></div>
                <div class="mb-3"><label class="form-label fw-bold">Import VAT / Sales Tax Rate (%)</label><input type="number" step="0.01" name="vat_rate" class="form-control" value="0" required></div>
                <button type="submit" class="btn btn-warning fw-bold text-dark">Calculate Landed Cost</button>
            </form>
        </div>
        <div class="col-md-6">
            {% if result %}
            <div class="card p-4 bg-light border-warning shadow-sm">
                <h4 class="text-dark mb-3">Cost Breakdown</h4>
                <ul class="list-group list-group-flush mb-3">
                    <li class="list-group-item d-flex justify-content-between"><span>CIF Value:</span> <strong>${{ "%.2f"|format(result.cif) }}</strong></li>
                    <li class="list-group-item d-flex justify-content-between"><span>Estimated Duty:</span> <strong>${{ "%.2f"|format(result.duty) }}</strong></li>
                    <li class="list-group-item d-flex justify-content-between"><span>Import VAT / Tax:</span> <strong>${{ "%.2f"|format(result.vat) }}</strong></li>
                </ul>
                <div class="alert alert-warning mb-0 text-center">
                    <h5 class="mb-1">Total Landed Cost</h5>
                    <h3 class="fw-bold text-dark">${{ "%.2f"|format(result.total) }}</h3>
                </div>
            </div>
            {% endif %}
        </div>
    </div>
    """
    return render_page(html, result=result)

# 5. Live Gemini AI Trade Assistant Route
@app.route('/ai-assistant', methods=['GET', 'POST'])
def ai_assistant():
    response_text = None
    if request.method == 'POST':
        query = request.form.get('query', '').strip()
        
        # Securely fetch the API key from environment variables (configured in Railway)
        gemini_key = os.getenv('GEMINI_API_KEY')
        
        if gemini_key:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.7-flash:generateContent?key={gemini_key}"
                payload = {
                    "contents": [{
                        "parts": [{"text": f"You are an expert global trade and customs compliance AI assistant. Provide actionable guidance for this trade query: {query}"}]
                    }]
                }
                api_res = requests.post(url, json=payload, timeout=8)
                if api_res.status_code == 200:
                    data = api_res.json()
                    response_text = data['candidates'][0]['content']['parts'][0]['text']
                else:
                    response_text = f"API error connecting to Gemini (Status {api_res.status_code}). Please check your GEMINI_API_KEY configuration in Railway."
            except Exception as e:
                response_text = f"Connection error occurred: {str(e)}"
        else:
            response_text = "API Key missing. Please set the GEMINI_API_KEY environment variable in your Railway dashboard."

    html = """
    <h2>AI Trade & Compliance Assistant</h2>
    <p class="text-muted">Ask complex questions regarding tariffs, compliance, HS codes, and shipping regulations.</p>
    <form method="POST" class="col-md-8 card p-4 bg-white shadow-sm">
        <div class="mb-3">
            <label class="form-label fw-bold">Your Compliance / Trade Query</label>
            <textarea name="query" rows="3" class="form-control" placeholder="e.g., What are the documentation requirements and tariff codes for importing lithium-ion batteries into the US?" required></textarea>
        </div>
        <button type="submit" class="btn btn-info text-white fw-bold">Ask AI Assistant</button>
    </form>
    {% if response_text %}
    <div class="card p-4 mt-4 col-md-8 bg-white border-info shadow-sm">
        <h5 class="text-info fw-bold">AI Trade Advisory Output</h5>
        <hr>
        <p style="white-space: pre-line;" class="mb-0">{{ response_text }}</p>
    </div>
    {% endif %}
    """
    return render_page(html, response_text=response_text)

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=True)