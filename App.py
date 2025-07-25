from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
import sqlite3
import json
import os
from datetime import datetime
from werkzeug.utils import secure_filename
import shutil
import sentry_sdk
from sentry_sdk.integrations.flask import FlaskIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
import logging

# Import je bestaande OCR functies
import pytesseract
from PIL import Image
import google.generativeai as genai
from dotenv import load_dotenv

# Laad environment variabelen
load_dotenv()

# Configureer logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Sentry initialisatie
sentry_logging = LoggingIntegration(
    level=logging.INFO,        # Capture info and above as breadcrumbs
    event_level=logging.ERROR  # Send errors as events
)

def filter_sensitive_data(event, hint):
    """Filter gevoelige data uit Sentry events"""
    # Verwijder API keys uit de event data
    if 'extra' in event:
        if 'GOOGLE_API_KEY' in event['extra']:
            event['extra']['GOOGLE_API_KEY'] = '[FILTERED]'
    
    # Verwijder gevoelige request data
    if 'request' in event and 'data' in event['request']:
        # Filter potentieel gevoelige velden
        sensitive_fields = ['password', 'api_key', 'secret']
        for field in sensitive_fields:
            if field in event['request']['data']:
                event['request']['data'][field] = '[FILTERED]'
    
    return event

sentry_sdk.init(
    dsn=os.getenv("SENTRY_DSN"),  # Voeg SENTRY_DSN toe aan je .env file
    integrations=[
        FlaskIntegration(
            transaction_style='endpoint'
        ),
        sentry_logging,
    ],
    # Performance Monitoring
    traces_sample_rate=1.0,  # Voor productie: verlaag naar 0.1-0.3
    profiles_sample_rate=1.0,  # Voor productie: verlaag naar 0.1-0.3
    
    # Release tracking
    release=os.getenv("SENTRY_RELEASE", "recepten-app@1.0.0"),
    environment=os.getenv("SENTRY_ENVIRONMENT", "development"),
    
    # Session tracking
    send_default_pii=False,  # Bescherm persoonlijke informatie
    
    # Error filtering
    before_send=filter_sensitive_data,
)

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'je-geheime-sleutel-hier')

# Configuratie
DATABASE_PATH = 'recepten.db'
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'tiff', 'webp'}
ARCHIVE_FOLDER = os.path.join('uploads', 'archief')
MAX_FILE_SIZE = 16 * 1024 * 1024  # 16MB max

# Maak upload folders aan
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(ARCHIVE_FOLDER, exist_ok=True)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE

# Database helper functies met error handling
def get_db_connection():
    """Maak een database connectie met error handling"""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        logger.error(f"Database connection error: {str(e)}")
        sentry_sdk.capture_exception(e)
        raise

def init_db():
    """Initialiseer de database met de juiste tabel structuur"""
    try:
        conn = get_db_connection()
        conn.execute('''
            CREATE TABLE IF NOT EXISTS recepten (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                titel TEXT NOT NULL,
                ingredienten TEXT,
                stappen TEXT,
                benodigdheden TEXT,
                originele_bestandsnaam TEXT,
                ruwe_ocr_tekst TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        conn.close()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Database initialization error: {str(e)}")
        sentry_sdk.capture_exception(e)
        raise

# Initialiseer database bij opstarten
with app.app_context():
    init_db()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# OCR functies met error handling en monitoring
@sentry_sdk.trace
def preprocess_image_for_ocr(image_path):
    """Preprocess image voor betere OCR resultaten"""
    try:
        with sentry_sdk.start_span(op="image.process", description="Preprocess image for OCR"):
            img = Image.open(image_path)
            
            # Log image info
            sentry_sdk.set_context("image_info", {
                "format": img.format,
                "size": img.size,
                "mode": img.mode
            })
            
            img = img.convert('L')  # Convert to grayscale
            
            # Optioneel: verbeter contrast
            # from PIL import ImageEnhance
            # enhancer = ImageEnhance.Contrast(img)
            # img = enhancer.enhance(1.5)
            
            return img
    except Exception as e:
        logger.error(f"Image preprocessing error: {str(e)}")
        sentry_sdk.capture_exception(e)
        return None

@sentry_sdk.trace
def extract_text_from_image(image_path):
    """Extract text uit afbeelding met Tesseract OCR"""
    try:
        with sentry_sdk.start_span(op="ocr.extract", description="Extract text with Tesseract"):
            processed_img = preprocess_image_for_ocr(image_path)
            if processed_img is None:
                return None
            
            # Configureer Tesseract pad voor Windows indien nodig
            # pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
            
            # Probeer verschillende talen
            languages = ['nld', 'eng']  # Nederlands en Engels
            best_text = ""
            best_confidence = 0
            
            for lang in languages:
                try:
                    # Get text with confidence scores
                    data = pytesseract.image_to_data(processed_img, lang=lang, output_type=pytesseract.Output.DICT)
                    
                    # Calculate average confidence
                    confidences = [int(conf) for conf in data['conf'] if int(conf) > 0]
                    avg_confidence = sum(confidences) / len(confidences) if confidences else 0
                    
                    # Get text
                    text = pytesseract.image_to_string(processed_img, lang=lang)
                    
                    if avg_confidence > best_confidence:
                        best_text = text
                        best_confidence = avg_confidence
                    
                    logger.info(f"OCR with {lang}: confidence={avg_confidence:.2f}")
                    
                except Exception as lang_error:
                    logger.warning(f"OCR failed for language {lang}: {str(lang_error)}")
            
            sentry_sdk.set_context("ocr_result", {
                "text_length": len(best_text),
                "confidence": best_confidence,
                "language": "multi"
            })
            
            if not best_text.strip():
                raise ValueError("No text extracted from image")
            
            return best_text
            
    except Exception as e:
        logger.error(f"OCR extraction error: {str(e)}")
        sentry_sdk.capture_exception(e)
        return None

@sentry_sdk.trace
def refine_text_with_gemini(raw_text):
    """Verfijn ruwe OCR tekst met Google Gemini AI"""
    clean_raw_text = raw_text.strip()
    if not clean_raw_text:
        return None

    try:
        with sentry_sdk.start_span(op="ai.process", description="Process with Gemini AI"):
            # Check API key
            api_key = os.getenv("GOOGLE_API_KEY")
            if not api_key:
                raise ValueError("Google API key not configured")
            
            genai.configure(api_key=api_key)
            
            # Gebruik een veiligere model configuratie
            generation_config = {
                "temperature": 0.2,  # Lagere temperatuur voor consistentere output
                "top_p": 0.8,
                "top_k": 40,
                "max_output_tokens": 2048,
            }
            
            safety_settings = [
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
            ]
            
            model = genai.GenerativeModel(
                "gemini-1.5-flash",
                generation_config=generation_config,
                safety_settings=safety_settings
            )
            
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

            Als je bepaalde informatie niet kunt vinden, gebruik dan lege arrays.
            Zorg ervoor dat de JSON valide is.

            Hier is de ruwe OCR-tekst:
            ```
            {clean_raw_text}
            ```

            Geef ALLEEN de JSON output, zonder extra tekst of uitleg.
            """
            
            # Maak de API call met retry logic
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    response = model.generate_content(prompt)
                    
                    if hasattr(response, 'text'):
                        refined_text = response.text
                    elif hasattr(response, 'parts') and response.parts:
                        refined_text = "".join([part.text for part in response.parts if hasattr(part, 'text')])
                    else:
                        raise ValueError("No text in Gemini response")
                    
                    # Clean up de response
                    json_text = refined_text.strip()
                    if json_text.startswith("```json"):
                        json_text = json_text[7:]
                    if json_text.startswith("```"):
                        json_text = json_text[3:]
                    if json_text.endswith("```"):
                        json_text = json_text[:-3]
                    
                    # Parse en valideer JSON
                    recipe_data = json.loads(json_text.strip())
                    
                    # Valideer de structuur
                    required_fields = ['titel', 'ingredienten', 'stappen', 'benodigdheden']
                    for field in required_fields:
                        if field not in recipe_data:
                            recipe_data[field] = [] if field != 'titel' else 'Onbekend Recept'
                    
                    # Log success
                    sentry_sdk.set_context("gemini_result", {
                        "success": True,
                        "attempt": attempt + 1,
                        "recipe_title": recipe_data.get('titel', 'Unknown')
                    })
                    
                    return recipe_data
                    
                except json.JSONDecodeError as json_error:
                    logger.warning(f"JSON parsing error on attempt {attempt + 1}: {str(json_error)}")
                    if attempt == max_retries - 1:
                        sentry_sdk.capture_exception(json_error)
                except Exception as api_error:
                    logger.warning(f"Gemini API error on attempt {attempt + 1}: {str(api_error)}")
                    if attempt == max_retries - 1:
                        sentry_sdk.capture_exception(api_error)
                    
    except Exception as e:
        logger.error(f"Gemini refinement error: {str(e)}")
        sentry_sdk.capture_exception(e)
        return None

# Routes met error handling
@app.route('/')
def index():
    try:
        conn = get_db_connection()
        cursor = conn.execute('SELECT id, titel, timestamp FROM recepten ORDER BY timestamp DESC')
        recepten_raw = cursor.fetchall()
        conn.close()
        
        # Converteer timestamps naar datetime objecten
        recepten = []
        for recept in recepten_raw:
            recept_dict = dict(recept)
            # Parse timestamp string naar datetime object
            if recept_dict['timestamp']:
                try:
                    recept_dict['timestamp'] = datetime.strptime(
                        recept_dict['timestamp'], 
                        '%Y-%m-%d %H:%M:%S'
                    )
                except ValueError:
                    # Als parsing faalt, gebruik de string as-is
                    pass
            recepten.append(recept_dict)
        
        return render_template('index.html', recepten=recepten)
    except Exception as e:
        logger.error(f"Error loading index: {str(e)}")
        sentry_sdk.capture_exception(e)
        flash('Er is een fout opgetreden bij het laden van de recepten.')
        return render_template('index.html', recepten=[])

@app.route('/recept/<int:id>')
def recept_detail(id):
    try:
        conn = get_db_connection()
        recept = conn.execute('SELECT * FROM recepten WHERE id = ?', (id,)).fetchone()
        conn.close()
        
        if recept is None:
            sentry_sdk.capture_message(f"Recipe not found: {id}", level="warning")
            return render_template('404.html'), 404
        
        # Parse JSON data met error handling
        try:
            ingredienten = json.loads(recept['ingredienten']) if recept['ingredienten'] else []
            stappen = json.loads(recept['stappen']) if recept['stappen'] else []
            benodigdheden = json.loads(recept['benodigdheden']) if recept['benodigdheden'] else []
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error for recipe {id}: {str(e)}")
            sentry_sdk.capture_exception(e)
            ingredienten = []
            stappen = []
            benodigdheden = []
        
        return render_template('recept.html', 
                             recept=recept, 
                             ingredienten=ingredienten,
                             stappen=stappen,
                             benodigdheden=benodigdheden)
    except Exception as e:
        logger.error(f"Error loading recipe {id}: {str(e)}")
        sentry_sdk.capture_exception(e)
        flash('Er is een fout opgetreden bij het laden van het recept.')
        return redirect(url_for('index'))

@app.route('/zoeken')
def zoeken():
    query = request.args.get('q', '')
    search_type = request.args.get('type', 'all')  # 'all', 'titel', 'ingredienten'
    
    if not query:
        return redirect(url_for('index'))
    
    try:
        with sentry_sdk.start_span(op="search", description=f"Search recipes: {query} (type: {search_type})"):
            conn = get_db_connection()
            
            # Bouw query op basis van zoektype
            if search_type == 'titel':
                cursor = conn.execute('''
                    SELECT DISTINCT id, titel, timestamp, ingredienten 
                    FROM recepten 
                    WHERE titel LIKE ?
                    ORDER BY timestamp DESC
                ''', (f'%{query}%',))
            elif search_type == 'ingredienten':
                cursor = conn.execute('''
                    SELECT DISTINCT id, titel, timestamp, ingredienten 
                    FROM recepten 
                    WHERE ingredienten LIKE ?
                    ORDER BY timestamp DESC
                ''', (f'%{query}%',))
            else:  # 'all'
                cursor = conn.execute('''
                    SELECT DISTINCT id, titel, timestamp, ingredienten 
                    FROM recepten 
                    WHERE titel LIKE ? OR ingredienten LIKE ? OR stappen LIKE ?
                    ORDER BY timestamp DESC
                ''', (f'%{query}%', f'%{query}%', f'%{query}%'))
            
            recepten_raw = cursor.fetchall()
            conn.close()
            
            # Converteer timestamps en markeer gevonden ingrediënten
            recepten = []
            for recept in recepten_raw:
                recept_dict = dict(recept)
                
                # Parse timestamp
                if recept_dict['timestamp']:
                    try:
                        recept_dict['timestamp'] = datetime.strptime(
                            recept_dict['timestamp'], 
                            '%Y-%m-%d %H:%M:%S'
                        )
                    except ValueError:
                        pass
                
                # Als we op ingrediënten zoeken, markeer welke ingrediënten matchen
                if search_type == 'ingredienten' and recept_dict.get('ingredienten'):
                    try:
                        ingredienten_lijst = json.loads(recept_dict['ingredienten'])
                        matching_ingredients = []
                        
                        for ingredient in ingredienten_lijst:
                            ingredient_name = ingredient.get('naam', '').lower()
                            if query.lower() in ingredient_name:
                                matching_ingredients.append(ingredient.get('naam', ''))
                        
                        recept_dict['matching_ingredients'] = matching_ingredients
                    except json.JSONDecodeError:
                        recept_dict['matching_ingredients'] = []
                
                recepten.append(recept_dict)
            
            sentry_sdk.set_tag("search.query", query)
            sentry_sdk.set_tag("search.type", search_type)
            sentry_sdk.set_tag("search.results_count", len(recepten))
            
            return render_template('index.html', 
                                 recepten=recepten, 
                                 zoekterm=query,
                                 search_type=search_type)
    except Exception as e:
        logger.error(f"Search error for query '{query}': {str(e)}")
        sentry_sdk.capture_exception(e)
        flash('Er is een fout opgetreden bij het zoeken.')
        return redirect(url_for('index'))

@app.route('/upload', methods=['GET', 'POST'])
def upload():
    if request.method == 'POST':
        transaction = sentry_sdk.start_transaction(op="upload", name="Upload Recipe")
        
        try:
            with transaction:
                # Validatie
                if 'file' not in request.files:
                    flash('Geen bestand geselecteerd')
                    return redirect(request.url)
                
                file = request.files['file']
                
                if file.filename == '':
                    flash('Geen bestand geselecteerd')
                    return redirect(request.url)
                
                if file and allowed_file(file.filename):
                    # Beveilig bestandsnaam
                    filename = secure_filename(file.filename)
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    filename = f"{timestamp}_{filename}"
                    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    
                    # Sla bestand op
                    with sentry_sdk.start_span(op="file.save", description="Save uploaded file"):
                        file.save(filepath)
                        
                        # Log file info
                        file_size = os.path.getsize(filepath)
                        sentry_sdk.set_context("upload_info", {
                            "filename": filename,
                            "size": file_size,
                            "type": file.content_type
                        })
                    
                    # Process met OCR
                    raw_text = extract_text_from_image(filepath)
                    
                    if raw_text:
                        # Verfijn met AI
                        recipe_data = refine_text_with_gemini(raw_text)
                        
                        if recipe_data:
                            # Sla op in database
                            with sentry_sdk.start_span(op="db.save", description="Save recipe to database"):
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
                            
                            # Log success
                            logger.info(f"Recipe successfully added: {recipe_data.get('titel')} (ID: {recipe_id})")
                            sentry_sdk.capture_message(
                                f"Recipe uploaded successfully: {recipe_data.get('titel')}",
                                level="info"
                            )
                            
                            flash('Recept succesvol toegevoegd!')
                            return redirect(url_for('recept_detail', id=recipe_id))
                        else:
                            flash('Kon geen recept informatie vinden in de afbeelding')
                            os.remove(filepath)
                    else:
                        flash('Kon geen tekst vinden in de afbeelding')
                        os.remove(filepath)
                else:
                    flash('Ongeldig bestandstype. Alleen afbeeldingen zijn toegestaan.')
                    
        except Exception as e:
            logger.error(f"Upload error: {str(e)}")
            sentry_sdk.capture_exception(e)
            flash('Er is een fout opgetreden bij het verwerken van het bestand.')
            
            # Cleanup bij error
            try:
                if 'filepath' in locals() and os.path.exists(filepath):
                    os.remove(filepath)
            except:
                pass
        
        finally:
            transaction.finish()
    
    return render_template('upload.html')

@app.route('/api/recepten')
def api_recepten():
    try:
        conn = get_db_connection()
        recepten = conn.execute('SELECT id, titel, timestamp FROM recepten ORDER BY timestamp DESC').fetchall()
        conn.close()
        
        return jsonify([dict(r) for r in recepten])
    except Exception as e:
        logger.error(f"API error: {str(e)}")
        sentry_sdk.capture_exception(e)
        return jsonify({"error": "Internal server error"}), 500

@app.route('/api/ingredienten')
def api_ingredienten():
    """API endpoint om alle unieke ingrediënten op te halen voor autocomplete"""
    try:
        conn = get_db_connection()
        recepten = conn.execute('SELECT ingredienten FROM recepten').fetchall()
        conn.close()
        
        # Verzamel alle unieke ingrediënten
        alle_ingredienten = set()
        for recept in recepten:
            if recept['ingredienten']:
                try:
                    ingredienten_lijst = json.loads(recept['ingredienten'])
                    for ingredient in ingredienten_lijst:
                        if 'naam' in ingredient:
                            alle_ingredienten.add(ingredient['naam'].lower())
                except json.JSONDecodeError:
                    continue
        
        # Sorteer alfabetisch
        ingredienten_sorted = sorted(list(alle_ingredienten))
        
        return jsonify({
            "ingredienten": ingredienten_sorted,
            "count": len(ingredienten_sorted)
        })
        
    except Exception as e:
        logger.error(f"API ingredienten error: {str(e)}")
        sentry_sdk.capture_exception(e)
        return jsonify({"error": "Internal server error"}), 500

@app.route('/geavanceerd-zoeken')
def geavanceerd_zoeken():
    """Geavanceerde zoekpagina met meerdere filters"""
    try:
        # Haal alle unieke ingrediënten op voor checkboxes
        conn = get_db_connection()
        recepten = conn.execute('SELECT ingredienten FROM recepten').fetchall()
        conn.close()
        
        alle_ingredienten = set()
        for recept in recepten:
            if recept['ingredienten']:
                try:
                    ingredienten_lijst = json.loads(recept['ingredienten'])
                    for ingredient in ingredienten_lijst:
                        if 'naam' in ingredient:
                            alle_ingredienten.add(ingredient['naam'])
                except json.JSONDecodeError:
                    continue
        
        return render_template('geavanceerd_zoeken.html', 
                             ingredienten=sorted(list(alle_ingredienten)))
    except Exception as e:
        logger.error(f"Advanced search error: {str(e)}")
        sentry_sdk.capture_exception(e)
        flash('Er is een fout opgetreden.')
        return redirect(url_for('index'))

@app.route('/health')
def health_check():
    """Health check endpoint voor monitoring"""
    try:
        # Check database connection
        conn = get_db_connection()
        conn.execute('SELECT 1')
        conn.close()
        
        # Check Tesseract
        pytesseract.get_tesseract_version()
        
        return jsonify({
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "version": os.getenv("SENTRY_RELEASE", "1.0.0")
        })
    except Exception as e:
        sentry_sdk.capture_exception(e)
        return jsonify({
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }), 500

# Error handlers
@app.errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Internal server error: {str(error)}")
    return render_template('500.html'), 500

@app.errorhandler(413)
def request_entity_too_large(error):
    flash('Bestand is te groot. Maximum grootte is 16MB.')
    return redirect(request.url)

# Test route voor Sentry (alleen in development)
if app.debug:
    @app.route('/debug-sentry')
    def trigger_error():
        """Test route om Sentry integratie te testen"""
        division_by_zero = 1 / 0

if __name__ == '__main__':
    app.run(debug=True, port=5000)