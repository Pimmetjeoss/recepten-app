# 🍳 Recepten App

Een slimme Flask-gebaseerde webapplicatie die recepten automatisch kan digitaliseren door afbeeldingen te scannen met OCR (Optical Character Recognition) en AI-verwerking.

![Python](https://img.shields.io/badge/python-v3.8+-blue.svg)
![Flask](https://img.shields.io/badge/flask-v3.0.0-green.svg)
![Sentry](https://img.shields.io/badge/sentry-integrated-purple.svg)
![License](https://img.shields.io/badge/license-MIT-blue.svg)

## ✨ Features

- **📸 Afbeelding naar Recept**: Upload een foto van een recept en de app extraheert automatisch:
  - Titel van het recept
  - Ingrediënten met hoeveelheden
  - Bereidingsstappen
  - Benodigde keukenbenodigdheden
  
- **🔍 Zoeken**: Zoek door je receptenverzameling op titel, ingrediënten of stappen
- **📋 Receptenbeheer**: Bekijk, bewaar en beheer al je gedigitaliseerde recepten
- **🎨 Moderne UI**: Gebruiksvriendelijke interface met custom CSS styling
- **💾 Lokale opslag**: Recepten worden opgeslagen in een SQLite database
- **🛡️ Error Tracking**: Sentry integratie voor professionele error monitoring
- **⚡ Performance Monitoring**: Track de performance van OCR en AI processing

## 🛠️ Technologieën

- **Backend**: Flask (Python web framework)
- **Database**: SQLite voor lokale opslag
- **OCR**: Tesseract OCR voor tekstextractie
- **AI**: Google Gemini API voor intelligente tekstverwerking
- **Frontend**: HTML, CSS, JavaScript
- **Beeldverwerking**: Pillow (PIL) voor afbeeldingsmanipulatie
- **Error Tracking**: Sentry voor monitoring en debugging

## 📋 Vereisten

- Python 3.8+
- Tesseract OCR geïnstalleerd op je systeem
- Google Gemini API key
- Sentry account (optioneel, maar aanbevolen)
- Internetverbinding voor AI-verwerking

## 🚀 Installatie

### 1. **Clone de repository**
```bash
git clone https://github.com/Pimmetjeoss/recepten-app.git
cd recepten-app
```

### 2. **Maak een virtual environment**
```bash
# Windows
python -m venv venv
venv\Scripts\activate

# macOS/Linux
python -m venv venv
source venv/bin/activate
```

### 3. **Installeer Python dependencies**
```bash
pip install -r Requirements.txt
```

### 4. **Installeer Tesseract OCR**

#### Windows
1. Download van [GitHub Tesseract](https://github.com/UB-Mannheim/tesseract/wiki)
2. Installeer het programma
3. Voeg Tesseract toe aan je PATH of specificeer het pad in App.py:
```python
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
```

#### macOS
```bash
brew install tesseract
brew install tesseract-lang  # Voor extra talen
```

#### Linux (Ubuntu/Debian)
```bash
sudo apt update
sudo apt install tesseract-ocr
sudo apt install tesseract-ocr-nld  # Voor Nederlandse taal
```

### 5. **Configureer environment variabelen**

Maak een `.env` bestand in de root directory:
```env
# Google Gemini API
GOOGLE_API_KEY=jouw-google-gemini-api-key-hier

# Sentry configuratie (optioneel)
SENTRY_DSN=https://jouw-sentry-dsn@o0.ingest.sentry.io/0
SENTRY_ENVIRONMENT=development
SENTRY_RELEASE=recepten-app@1.0.0

# Flask configuratie
SECRET_KEY=genereer-een-veilige-secret-key-hier
FLASK_ENV=development
FLASK_DEBUG=True
```

#### API Keys verkrijgen:
- **Google Gemini**: [Google AI Studio](https://makersuite.google.com/app/apikey)
- **Sentry**: [Sentry.io](https://sentry.io) (maak een gratis account)

### 6. **Start de applicatie**
```bash
python App.py
```

De app draait nu op `http://localhost:5000`

## 🎮 Gebruik

### Upload een recept
1. Klik op "Upload Recept" of "📸 Upload je eerste recept"
2. Selecteer een afbeelding met een recept
3. Wacht tot de verwerking is voltooid
4. Bekijk het automatisch geëxtraheerde recept

### Zoek door recepten
1. Gebruik de zoekbalk bovenaan
2. Zoek op titel, ingrediënt of bereidingsstap
3. Resultaten worden direct getoond

### Tips voor beste resultaten
- Gebruik heldere, goed belichte foto's
- Zorg dat de tekst leesbaar is
- Foto's recht van boven werken het beste
- Ondersteunde formaten: PNG, JPG, JPEG, GIF, BMP, TIFF, WEBP

## 📁 Projectstructuur

```
recepten-app/
├── App.py                 # Hoofd Flask applicatie
├── Requirements.txt       # Python dependencies
├── .env                   # Environment variabelen (niet in Git!)
├── .gitignore            # Git ignore file
├── README.md             # Dit bestand
├── templates/            # HTML templates
│   ├── base.html        # Basis template
│   ├── index.html       # Homepage
│   ├── recept.html      # Recept detail pagina
│   ├── upload.html      # Upload pagina
│   ├── 404.html         # 404 error pagina
│   └── 500.html         # 500 error pagina
├── uploads/              # Tijdelijke upload map (niet in Git)
│   └── archief/         # Archief van verwerkte afbeeldingen
├── recepten.db          # SQLite database (niet in Git)
└── venv/                # Virtual environment (niet in Git)
```

## 🔧 Configuratie

### App configuratie
In `App.py` kun je aanpassen:
- `UPLOAD_FOLDER`: Map voor tijdelijke bestandsopslag
- `ALLOWED_EXTENSIONS`: Toegestane bestandsformaten
- `MAX_FILE_SIZE`: Maximum upload grootte (standaard 16MB)

### Sentry configuratie
Voor productie, pas deze waarden aan in `.env`:
```env
SENTRY_ENVIRONMENT=production
SENTRY_RELEASE=recepten-app@2.0.0
```

En in `App.py`:
```python
traces_sample_rate=0.1,  # Sample 10% van transactions
profiles_sample_rate=0.1,  # Sample 10% voor profiling
```

## 📊 Database Schema

```sql
CREATE TABLE recepten (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    titel TEXT NOT NULL,
    ingredienten TEXT,      -- JSON array
    stappen TEXT,           -- JSON array
    benodigdheden TEXT,     -- JSON array
    originele_bestandsnaam TEXT,
    ruwe_ocr_tekst TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

## 🚨 Troubleshooting

### Tesseract niet gevonden
```python
# Windows: voeg dit toe aan App.py
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
```

### Google API errors
- Controleer of je API key correct is in `.env`
- Zorg voor internetverbinding
- Check je [API quota](https://console.cloud.google.com/apis/api/generativelanguage.googleapis.com/quotas)

### Upload problemen
- Check bestandsgrootte (max 16MB)
- Controleer bestandsformaat
- Zorg dat `uploads/` map bestaat en schrijfbaar is

### Database errors
```bash
# Reset database
rm recepten.db
python App.py  # Maakt automatisch nieuwe database
```

## 🧪 Development

### Debug mode
De app draait standaard in debug mode. Voor productie:
```env
FLASK_DEBUG=False
FLASK_ENV=production
```

### Test Sentry integratie
Bezoek `/debug-sentry` om een test error te triggeren (alleen in debug mode)

### Health check
Check app status via `/health` endpoint

## 🤝 Bijdragen

Bijdragen zijn welkom! 

1. Fork het project
2. Maak een feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit je wijzigingen (`git commit -m 'Add some AmazingFeature'`)
4. Push naar de branch (`git push origin feature/AmazingFeature`)
5. Open een Pull Request

## 📝 License

Dit project is gelicenseerd onder de MIT License - zie het [LICENSE](LICENSE) bestand voor details.

## 🙏 Acknowledgments

- [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) voor de geweldige OCR engine
- [Google Gemini](https://deepmind.google/technologies/gemini/) voor AI-powered tekstverwerking
- [Flask](https://flask.palletsprojects.com/) voor het web framework
- [Sentry](https://sentry.io) voor error tracking

## 📧 Contact

Voor vragen of suggesties, maak een issue aan op GitHub of neem contact op via de repository.

---

**Gemaakt met ❤️ door Pimmetjeoss**