from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
import sqlite3
import json
import os
from datetime import datetime
from werkzeug.utils import secure_filename
import shutil

# Import je bestaande OCR functies
import pytesseract
from PIL import Image
import google.generativeai as genai
from dotenv import load_dotenv

# Laad environment variabelen
load_dotenv()

app = Flask(__name__)
app.secret_key = 'je-geheime-sleutel-hier'  # Verander dit naar een veilige key

# Configuratie
DATABASE_PATH = 'recepten.db'
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'tiff', 'webp'}
ARCHIVE_FOLDER = os.path.join('uploads', 'archief')

# Maak upload folders aan
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(ARCHIVE_FOLDER, exist_ok=True)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Database helper functies
def get_db_connection():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# OCR functies (van je bestaande code)
def preprocess_image_for_ocr(image_path):
    try:
        img = Image.open(image_path)
        img = img.convert('L')
        return img
    except Exception as e:
        return None

def extract_text_from_image(image_path):
    processed_img = preprocess_image_for_ocr(image_path)
    if processed_img is None:
        return None
    
    try:
        text = pytesseract.image_to_string(processed_img, lang='nld')
        return text
    except Exception as e:
        return None

def refine_text_with_gemini(raw_text):
    # Je bestaande Gemini code hier
    clean_raw_text = raw_text.strip()
    if not clean_raw_text:
        return None

    genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
    model = genai.GenerativeModel("gemini-1.5-flash")
    
    prompt = f"""
    Ik heb tekst geëxtraheerd uit een afbeelding van een recept. Analyseer deze tekst en 
    extraheer de informatie in een gestructureerd JSON formaat.

    Geef het resultaat ALLEEN als JSON in dit exacte formaat:
    {{
        "titel": "Naam van het recept",
        "ingredienten": [
            {{"hoeveelheid": "2", "eenheid": "stuks", "naam": "eieren"}},
            {{"hoeveelheid": "500", "eenheid": "gram", "naam": "bloem"}}
        ],
        "stappen": [
            "Stap 1: beschrijving",
            "Stap 2: beschrijving"
        ],
        "benodigdheden": [
            "Mengkom",
            "Garde"
        ]
    }}

    Hier is de ruwe OCR-tekst:
    ```
    {clean_raw_text}
    ```

    Geef ALLEEN de JSON output, zonder extra tekst of uitleg.
    """
    
    try:
        response = model.generate_content(prompt, request_options={"timeout": 60})
        
        refined_text = ""
        if hasattr(response, 'text'):
            refined_text = response.text
        elif hasattr(response, 'parts') and response.parts:
            refined_text = "".join([part.text for part in response.parts if hasattr(part, 'text')])
        
        if refined_text.strip():
            json_text = refined_text.strip()
            if json_text.startswith("```json"):
                json_text = json_text[7:]
            if json_text.startswith("```"):
                json_text = json_text[3:]
            if json_text.endswith("```"):
                json_text = json_text[:-3]
            
            recipe_data = json.loads(json_text.strip())
            return recipe_data
    except Exception as e:
        return None

# Routes
@app.route('/')
def index():
    conn = get_db_connection()
    recepten = conn.execute('SELECT id, titel, timestamp FROM recepten ORDER BY timestamp DESC').fetchall()
    conn.close()
    return render_template('index.html', recepten=recepten)

@app.route('/recept/<int:id>')
def recept_detail(id):
    conn = get_db_connection()
    recept = conn.execute('SELECT * FROM recepten WHERE id = ?', (id,)).fetchone()
    conn.close()
    
    if recept is None:
        return "Recept niet gevonden", 404
    
    # Parse JSON data
    ingredienten = json.loads(recept['ingredienten']) if recept['ingredienten'] else []
    stappen = json.loads(recept['stappen']) if recept['stappen'] else []
    benodigdheden = json.loads(recept['benodigdheden']) if recept['benodigdheden'] else []
    
    return render_template('recept.html', 
                         recept=recept, 
                         ingredienten=ingredienten,
                         stappen=stappen,
                         benodigdheden=benodigdheden)

@app.route('/zoeken')
def zoeken():
    query = request.args.get('q', '')
    if not query:
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    recepten = conn.execute('''
        SELECT id, titel, timestamp 
        FROM recepten 
        WHERE titel LIKE ? OR ingredienten LIKE ? OR stappen LIKE ?
        ORDER BY timestamp DESC
    ''', (f'%{query}%', f'%{query}%', f'%{query}%')).fetchall()
    conn.close()
    
    return render_template('index.html', recepten=recepten, zoekterm=query)

@app.route('/upload', methods=['GET', 'POST'])
def upload():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('Geen bestand geselecteerd')
            return redirect(request.url)
        
        file = request.files['file']
        
        if file.filename == '':
            flash('Geen bestand geselecteerd')
            return redirect(request.url)
        
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"{timestamp}_{filename}"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            
            file.save(filepath)
            
            # Process met OCR
            raw_text = extract_text_from_image(filepath)
            
            if raw_text:
                recipe_data = refine_text_with_gemini(raw_text)
                
                if recipe_data:
                    # Sla op in database
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    
                    ingredienten_json = json.dumps(recipe_data.get('ingredienten', []), ensure_ascii=False)
                    stappen_json = json.dumps(recipe_data.get('stappen', []), ensure_ascii=False)
                    benodigdheden_json = json.dumps(recipe_data.get('benodigdheden', []), ensure_ascii=False)
                    
                    cursor.execute('''
                        INSERT INTO recepten (titel, ingredienten, stappen, benodigdheden, 
                                            originele_bestandsnaam, ruwe_ocr_tekst)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (recipe_data.get('titel', 'Onbekend Recept'), 
                          ingredienten_json, 
                          stappen_json, 
                          benodigdheden_json,
                          filename, 
                          raw_text))
                    
                    conn.commit()
                    recipe_id = cursor.lastrowid
                    conn.close()
                    
                    # Verplaats naar archief
                    archive_path = os.path.join(ARCHIVE_FOLDER, filename)
                    shutil.move(filepath, archive_path)
                    
                    flash('Recept succesvol toegevoegd!')
                    return redirect(url_for('recept_detail', id=recipe_id))
                else:
                    flash('Kon geen recept informatie vinden in de afbeelding')
                    os.remove(filepath)
            else:
                flash('Kon geen tekst vinden in de afbeelding')
                os.remove(filepath)
    
    return render_template('upload.html')

@app.route('/api/recepten')
def api_recepten():
    conn = get_db_connection()
    recepten = conn.execute('SELECT id, titel, timestamp FROM recepten ORDER BY timestamp DESC').fetchall()
    conn.close()
    
    return jsonify([dict(r) for r in recepten])

if __name__ == '__main__':
    app.run(debug=True, port=5000)