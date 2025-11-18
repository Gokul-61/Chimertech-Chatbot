from flask import Flask, render_template, request, jsonify
from markupsafe import escape
import sqlite3
from fuzzywuzzy import fuzz, process
from functools import lru_cache
import html
import re
from googletrans import Translator
import os

# Import for WhatsApp
try:
    from twilio.twiml.messaging_response import MessagingResponse
    from twilio.rest import Client
    WHATSAPP_ENABLED = True
    
    # Load Twilio credentials from environment
    from dotenv import load_dotenv
    load_dotenv()
    TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
    TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
    TWILIO_WHATSAPP_NUMBER = os.getenv('TWILIO_WHATSAPP_NUMBER', 'whatsapp:+14155238886')
    
    # Initialize Twilio client if credentials exist
    if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN:
        twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        TWILIO_CLIENT_ENABLED = True
    else:
        twilio_client = None
        TWILIO_CLIENT_ENABLED = False
        
except ImportError:
    WHATSAPP_ENABLED = False
    TWILIO_CLIENT_ENABLED = False
    twilio_client = None
    print("⚠️  Twilio not installed. WhatsApp features disabled.")
    print("   Install with: pip install twilio python-dotenv")

app = Flask(__name__)

# Initialize translator
translator = Translator()

# WhatsApp user sessions (stores language preference per phone number)
whatsapp_user_sessions = {}

# -------------------------------
# Multilingual Translations (UI Text)
# -------------------------------
TRANSLATIONS = {
    'en': {
        'greeting': "Hello! I'm your ChimerTech Product Assistant.<br>Type a product name to get started!",
        'greeting_whatsapp': "👋 *Hello! I'm your ChimerTech Product Assistant*\n\n🌾 Type any product name to get started!\n\n📋 *Commands:*\n• Type 'help' for instructions\n• Type 'tamil' or 'hindi' to switch language",
        'help_title': "💡 <strong>How to use:</strong><br>",
        'help_line1': "• Type any product name<br>",
        'help_line2': "• Use partial names (e.g., 'laptop' or 'phone')<br>",
        'help_line3': "• I'll find the best matches!<br>",
        'help_line4': "• Switch language: type 'tamil' or 'hindi'",
        'help_whatsapp': "💡 *How to use:*\n\n✅ Type any product name\n✅ Use partial names (e.g., 'fertilizer')\n✅ I'll find the best matches!\n✅ Switch language: type 'tamil' or 'hindi'\n\n🌐 Available in English, Tamil, Hindi",
        'empty_input': "Please type something 😊",
        'no_match': "Sorry, I couldn't find any product matching '{query}'.",
        'no_match_whatsapp': "❌ Sorry, I couldn't find any product matching *'{query}'*.\n\n💡 Try:\n• Checking your spelling\n• Using a different product name\n• Type 'help' for instructions",
        'suggestion_text': "Try checking your spelling or using a different product name.",
        'multiple_matches': "I found multiple matches for '{query}'. Please select one:",
        'multiple_matches_whatsapp': "I found multiple matches for '{query}'. Please select one by typing the number:\n\n{list}\n\nType the number of the product you want.",
        'no_description': "No description available.",
        'language_switched': "🌐 Language switched to English!",
        'error_message': "Something went wrong. Please try again.",
        'product_info_whatsapp': "✅ *{name}*\n\n📄 *Description:*\n{description}\n\n━━━━━━━━━━━━━━━\n💬 Type another product name to search again"
    },
    'ta': {
        'greeting': "வணக்கம்! நான் உங்கள் ChimerTech தயாரிப்பு உதவியாளர்.<br>தயாரிப்பு பெயரை தட்டச்சு செய்யவும்!",
        'greeting_whatsapp': "👋 *வணக்கம்! நான் உங்கள் ChimerTech தயாரிப்பு உதவியாளர்*\n\n🌾 தயாரிப்பு பெயரை தட்டச்சு செய்யவும்!\n\n📋 *கட்டளைகள்:*\n• 'help' என தட்டச்சு செய்யவும்\n• 'english' அல்லது 'hindi' என மொழி மாற்றவும்",
        'help_title': "💡 <strong>எப்படி பயன்படுத்துவது:</strong><br>",
        'help_line1': "• எந்த தயாரிப்பு பெயரையும் தட்டச்சு செய்யவும்<br>",
        'help_line2': "• பகுதி பெயர்களைப் பயன்படுத்தவும் (எ.கா., 'laptop' அல்லது 'phone')<br>",
        'help_line3': "• நான் சிறந்த பொருத்தங்களைக் கண்டுபிடிப்பேன்!<br>",
        'help_line4': "• மொழி மாற்ற: 'english' அல்லது 'hindi' என தட்டச்சு செய்யவும்",
        'help_whatsapp': "💡 *எப்படி பயன்படுத்துவது:*\n\n✅ எந்த தயாரிப்பு பெயரையும் தட்டச்சு செய்யவும்\n✅ பகுதி பெயர்களைப் பயன்படுத்தவும்\n✅ நான் சிறந்த பொருத்தங்களைக் கண்டுபிடிப்பேன்!\n✅ மொழி மாற்ற: 'english' அல்லது 'hindi'\n\n🌐 தமிழ், ஆங்கிலம், இந்தி மொழிகளில் கிடைக்கும்",
        'empty_input': "தயவுசெய்து ஏதாவது தட்டச்சு செய்யவும் 😊",
        'no_match': "மன்னிக்கவும், '{query}' எனும் தயாரிப்பை என்னால் கண்டுபிடிக்க முடியவில்லை.",
        'no_match_whatsapp': "❌ மன்னிக்கவும், *'{query}'* எனும் தயாரிப்பை கண்டுபிடிக்க முடியவில்லை.\n\n💡 முயற்சிக்கவும்:\n• எழுத்துப்பிழையைச் சரிபார்க்கவும்\n• வேறு தயாரிப்பு பெயரைப் பயன்படுத்தவும்\n• 'help' என தட்டச்சு செய்யவும்",
        'suggestion_text': "உங்கள் எழுத்துப்பிழையைச் சரிபார்க்கவும் அல்லது வேறு தயாரிப்பு பெயரைப் பயன்படுத்தவும்.",
        'multiple_matches': "'{query}' க்கு பல பொருத்தங்களைக் கண்டேன். தயவுசெய்து ஒன்றைத் தேர்ந்தெடுக்கவும்:",
        'multiple_matches_whatsapp': "'{query}' க்கு பல பொருத்தங்களைக் கண்டேன். தயவுசெய்து எண்ணை தட்டச்சு செய்து ஒன்றைத் தேர்ந்தெடுக்கவும்:\n\n{list}\n\nதயாரிப்பின் எண்ணை தட்டச்சு செய்யவும்.",
        'no_description': "விளக்கம் கிடைக்கவில்லை.",
        'language_switched': "🌐 மொழி தமிழுக்கு மாற்றப்பட்டது!",
        'error_message': "ஏதோ தவறு நடந்தது. மீண்டும் முயற்சிக்கவும்.",
        'product_info_whatsapp': "✅ *{name}*\n\n📄 *விளக்கம்:*\n{description}\n\n━━━━━━━━━━━━━━━\n💬 மற்றொரு தயாரிப்பை தேட பெயரை தட்டச்சு செய்யவும்"
    },
    'hi': {
        'greeting': "नमस्ते! मैं आपका ChimerTech उत्पाद सहायक हूं।<br>उत्पाद का नाम टाइप करें!",
        'greeting_whatsapp': "👋 *नमस्ते! मैं आपका ChimerTech उत्पाद सहायक हूं*\n\n🌾 उत्पाद का नाम टाइप करें!\n\n📋 *कमांड:*\n• 'help' टाइप करें निर्देशों के लिए\n• 'english' या 'tamil' भाषा बदलने के लिए",
        'help_title': "💡 <strong>कैसे उपयोग करें:</strong><br>",
        'help_line1': "• कोई भी उत्पाद नाम टाइप करें<br>",
        'help_line2': "• आंशिक नामों का उपयोग करें (जैसे, 'laptop' या 'phone')<br>",
        'help_line3': "• मैं सर्वोत्तम मिलान ढूंढूंगा!<br>",
        'help_line4': "• भाषा बदलें: 'english' या 'tamil' टाइप करें",
        'help_whatsapp': "💡 *कैसे उपयोग करें:*\n\n✅ कोई भी उत्पाद नाम टाइप करें\n✅ आंशिक नामों का उपयोग करें\n✅ मैं सर्वोत्तम मिलान ढूंढूंगा!\n✅ भाषा बदलें: 'english' या 'tamil'\n\n🌐 अंग्रेज़ी, तमिल, हिंदी में उपलब्ध",
        'empty_input': "कृपया कुछ टाइप करें 😊",
        'no_match': "क्षमा करें, मुझे '{query}' से मेल खाने वाला कोई उत्पाद नहीं मिला।",
        'no_match_whatsapp': "❌ क्षमा करें, *'{query}'* से मेल खाने वाला कोई उत्पाद नहीं मिला।\n\n💡 प्रयास करें:\n• अपनी वर्तनी जांचें\n• किसी अन्य उत्पाद नाम का उपयोग करें\n• 'help' टाइप करें",
        'suggestion_text': "अपनी वर्तनी जांचें या किसी अन्य उत्पाद नाम का उपयोग करें।",
        'multiple_matches': "मुझे '{query}' के लिए कई मिलान मिले। कृपया एक चुनें:",
        'multiple_matches_whatsapp': "मुझे '{query}' के लिए कई मिलान मिले। कृपया संख्या टाइप करके एक चुनें:\n\n{list}\n\nउत्पाद की संख्या टाइप करें।",
        'no_description': "कोई विवरण उपलब्ध नहीं है।",
        'language_switched': "🌐 भाषा हिंदी में बदल दी गई!",
        'error_message': "कुछ गलत हो गया। कृपया पुनः प्रयास करें।",
        'product_info_whatsapp': "✅ *{name}*\n\n📄 *विवरण:*\n{description}\n\n━━━━━━━━━━━━━━━\n💬 फिर से खोजने के लिए उत्पाद नाम टाइप करें"
    }
}

# Translation cache to avoid repeated API calls
translation_cache = {}

# -------------------------------
# Helper: Clean query input
# -------------------------------
def clean_query(query):
    """Remove trailing punctuation and extra whitespace from query."""
    if not query:
        return query
    query = re.sub(r'[.!?,;:]+\s*$', '', query.strip())
    return query.strip()


# -------------------------------
# Helper: Auto-translate text
# -------------------------------
def auto_translate(text, target_lang='en', source_lang='auto'):
    """Translate text to target language using Google Translate."""
    if not text or target_lang == 'en' and source_lang == 'en':
        return text
    
    cache_key = f"{text[:50]}_{target_lang}"
    if cache_key in translation_cache:
        return translation_cache[cache_key]
    
    try:
        if source_lang == 'auto':
            translated = translator.translate(text, dest=target_lang)
        else:
            translated = translator.translate(text, src=source_lang, dest=target_lang)
        result = translated.text
        
        translation_cache[cache_key] = result
        return result
    except Exception as e:
        app.logger.error(f"Translation error: {e}")
        return text


# -------------------------------
# Helper: Get UI Translation
# -------------------------------
def get_text(key, language='en', whatsapp=False, **kwargs):
    """Get translated text for the given key and language."""
    if whatsapp:
        whatsapp_key = f"{key}_whatsapp"
        text = TRANSLATIONS.get(language, TRANSLATIONS['en']).get(whatsapp_key)
        if text:
            return text.format(**kwargs) if kwargs else text
    
    text = TRANSLATIONS.get(language, TRANSLATIONS['en']).get(key, TRANSLATIONS['en'].get(key, ''))
    return text.format(**kwargs) if kwargs else text


# -------------------------------
# Database Context Manager
# -------------------------------
class DatabaseConnection:
    def __init__(self, db_name='products.db'):
        self.db_name = db_name
        self.conn = None
    
    def __enter__(self):
        self.conn = sqlite3.connect(self.db_name)
        self.conn.row_factory = sqlite3.Row
        return self.conn
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.conn:
            self.conn.close()


# -------------------------------
# Helper: fetch product by exact name
# -------------------------------
def fetch_product(name):
    try:
        with DatabaseConnection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM products WHERE name_en = ?", (name,))
            row = cursor.fetchone()
            return dict(row) if row else None
    except sqlite3.Error as e:
        app.logger.error(f"Database error: {e}")
        return None


# -------------------------------
# Cache product names
# -------------------------------
@lru_cache(maxsize=1)
def get_all_product_names():
    try:
        with DatabaseConnection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name_en FROM products")
            return [row['name_en'] for row in cursor.fetchall()]
    except sqlite3.Error as e:
        app.logger.error(f"Database error: {e}")
        return []


# -------------------------------
# Smart product lookup
# -------------------------------
def find_products(query):
    """Returns one best match or a list of possible matches."""
    query = clean_query(query)
    if not query:
        return None, []

    names = get_all_product_names()
    if not names:
        return None, []

    # Exact match (case-insensitive)
    for name in names:
        if name.lower() == query.lower():
            return fetch_product(name), []

    # Substring matches
    substring_matches = [n for n in names if query.lower() in n.lower()]
    if len(substring_matches) == 1:
        return fetch_product(substring_matches[0]), []
    elif len(substring_matches) > 1:
        return None, substring_matches[:10]

    # Fuzzy match fallback
    try:
        results = process.extract(query, names, limit=10, scorer=fuzz.token_sort_ratio)
        good = [r[0] for r in results if r[1] >= 70]
        if len(good) == 1:
            return fetch_product(good[0]), []
        elif len(good) > 1:
            return None, good[:10]
    except Exception as e:
        app.logger.error(f"Fuzzy matching error: {e}")

    return None, []


# -------------------------------
# Cleaner Function for Descriptions
# -------------------------------
def clean_description(text: str, language='en') -> str:
    """Removes MS Word artifacts, HTML tags, and encoded junk."""
    if not text:
        return get_text('no_description', language)
    
    text = html.unescape(text)
    text = re.sub(r'<!--.*?-->', '', text, flags=re.DOTALL)
    text = re.sub(r'--[^>]*?--', '', text)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'mso-[a-zA-Z0-9:;.\s]+', '', text)
    text = re.sub(r'&[a-zA-Z]+;', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


# -------------------------------
# WhatsApp Helper Functions
# -------------------------------
def get_whatsapp_user_language(phone_number):
    """Get user's preferred language for WhatsApp."""
    return whatsapp_user_sessions.get(phone_number, {}).get('language', 'en')


def set_whatsapp_user_language(phone_number, language):
    """Set user's preferred language for WhatsApp."""
    if phone_number not in whatsapp_user_sessions:
        whatsapp_user_sessions[phone_number] = {}
    whatsapp_user_sessions[phone_number]['language'] = language


def set_whatsapp_user_context(phone_number, context_type, data):
    """Store user context for follow-up messages."""
    if phone_number not in whatsapp_user_sessions:
        whatsapp_user_sessions[phone_number] = {}
    whatsapp_user_sessions[phone_number]['context'] = {
        'type': context_type,
        'data': data
    }


def get_whatsapp_user_context(phone_number):
    """Get user context."""
    return whatsapp_user_sessions.get(phone_number, {}).get('context', {})


def clear_whatsapp_user_context(phone_number):
    """Clear user context."""
    if phone_number in whatsapp_user_sessions and 'context' in whatsapp_user_sessions[phone_number]:
        del whatsapp_user_sessions[phone_number]['context']


def send_whatsapp_list(to_number, products, query, language='en'):
    """Send WhatsApp list message with product options."""
    if not TWILIO_CLIENT_ENABLED or not twilio_client:
        return False
    
    try:
        # Create list sections
        items = []
        for i, prod_name in enumerate(products[:10]):  # WhatsApp allows max 10 items
            items.append({
                "id": f"product_{i}",
                "title": prod_name[:24],  # WhatsApp title limit
                "description": f"Select to view details"[:72]  # WhatsApp description limit
            })
        
        # Message text based on language
        body_text = {
            'en': f"I found {len(products)} matches for '{query}'.\nPlease select one:",
            'ta': f"'{query}' க்கு {len(products)} பொருத்தங்கள் கிடைத்தன.\nஒன்றைத் தேர்ந்தெடுக்கவும்:",
            'hi': f"'{query}' के लिए {len(products)} मिलान मिले।\nएक चुनें:"
        }.get(language, f"I found {len(products)} matches for '{query}'.\nPlease select one:")
        
        button_text = {
            'en': "View Products",
            'ta': "தயாரிப்புகள் காண்க",
            'hi': "उत्पाद देखें"
        }.get(language, "View Products")
        
        # Send list message
        message = twilio_client.messages.create(
            from_=TWILIO_WHATSAPP_NUMBER,
            to=to_number,
            body=body_text,
            persistent_action=[button_text]  # This creates the list button
        )
        
        # Store products in session for selection
        set_whatsapp_user_context(to_number.replace('whatsapp:', ''), 'product_selection', products)
        
        return True
        
    except Exception as e:
        app.logger.error(f"Error sending WhatsApp list: {e}")
        return False


def send_whatsapp_buttons(to_number, products, query, language='en'):
    """Send WhatsApp message with formatted selection menu."""
    if not TWILIO_CLIENT_ENABLED or not twilio_client:
        return False
    
    try:
        # Create a nicely formatted selection menu
        header = {
            'en': f"🔍 *Found {len(products)} matches for '{query}'*\n",
            'ta': f"🔍 *'{query}' க்கு {len(products)} பொருத்தங்கள்*\n",
            'hi': f"🔍 *'{query}' के लिए {len(products)} मिलान*\n"
        }.get(language, f"🔍 *Found {len(products)} matches for '{query}'*\n")
        
        instruction = {
            'en': "📱 *Tap to select:*\n\n",
            'ta': "📱 *தேர்ந்தெடுக்க தட்டவும்:*\n\n",
            'hi': "📱 *चुनने के लिए टैप करें:*\n\n"
        }.get(language, "📱 *Tap to select:*\n\n")
        
        # Build the product list with emojis
        product_list = []
        emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
        
        for i, prod_name in enumerate(products[:10]):
            emoji = emojis[i] if i < len(emojis) else f"{i+1}."
            product_list.append(f"{emoji} {prod_name}")
        
        footer = {
            'en': "\n\n💬 *Reply with the number* (1-{}) to view details",
            'ta': "\n\n💬 *எண்ணை அனுப்பவும்* (1-{}) விவரங்களைக் காண",
            'hi': "\n\n💬 *नंबर के साथ उत्तर दें* (1-{}) विवरण देखने के लिए"
        }.get(language, "\n\n💬 *Reply with the number* (1-{}) to view details")
        
        body_text = header + instruction + "\n".join(product_list) + footer.format(len(products))
        
        message = twilio_client.messages.create(
            from_=TWILIO_WHATSAPP_NUMBER,
            to=to_number,
            body=body_text
        )
        
        # Store products in session
        phone_only = to_number.replace('whatsapp:', '')
        set_whatsapp_user_context(phone_only, 'product_selection', products)
        
        return True
        
    except Exception as e:
        app.logger.error(f"Error sending WhatsApp buttons: {e}")
        return False


# -------------------------------
# Routes
# -------------------------------
@app.route('/')
def index():
    """Serve the web chat interface."""
    try:
        return render_template('chat.html')
    except Exception as e:
        app.logger.error(f"Error loading template: {e}")
        return """
        <html>
        <head><title>Error</title></head>
        <body style="font-family: Arial; padding: 40px;">
            <h1>⚠️ Template Error</h1>
            <p>Could not find 'chat.html' in templates folder.</p>
            <p><strong>Make sure:</strong></p>
            <ul>
                <li>You have a folder named 'templates' in your project</li>
                <li>The file 'chat.html' is inside the 'templates' folder</li>
            </ul>
            <p><strong>Good news:</strong> WhatsApp is still working! ✅</p>
        </body>
        </html>
        """, 500


@app.route('/chat', methods=['POST'])
def chat():
    """Handle web chat messages."""
    try:
        user_input = request.json.get('message', '').strip()
        language = request.json.get('language', 'en')

        if not user_input:
            return jsonify({"reply": get_text('empty_input', language)})

        user_input = clean_query(user_input)
        safe_input = html.escape(user_input)
        user_lower = user_input.lower()

        # Greeting
        if user_lower in ['hi', 'hello', 'hey', 'start', 'வணக்கம்', 'नमस्ते']:
            return jsonify({
                "reply": get_text('greeting', language)
            })

        # Help command
        if user_lower in ['help', '?', 'உதவி', 'मदद']:
            help_text = (
                get_text('help_title', language) +
                get_text('help_line1', language) +
                get_text('help_line2', language) +
                get_text('help_line3', language) +
                get_text('help_line4', language)
            )
            return jsonify({"reply": help_text})

        # Language switches
        if any(word in user_lower for word in ['tamil', 'தமிழ்']):
            return jsonify({
                "reply": get_text('language_switched', 'ta'),
                "language": "ta"
            })
        if any(word in user_lower for word in ['hindi', 'हिंदी']):
            return jsonify({
                "reply": get_text('language_switched', 'hi'),
                "language": "hi"
            })
        if any(word in user_lower for word in ['english', 'ஆங்கிலம்', 'अंग्रेज़ी']):
            return jsonify({
                "reply": get_text('language_switched', 'en'),
                "language": "en"
            })

        # Translate non-English queries to English for search
        search_query = user_input
        if language != 'en':
            try:
                detected = translator.detect(user_input)
                if detected.lang in ['ta', 'hi']:
                    search_query = auto_translate(user_input, 'en')
                    search_query = clean_query(search_query)
                    app.logger.info(f"Translated '{user_input}' to '{search_query}' for search")
            except Exception as e:
                app.logger.error(f"Language detection error: {e}")
        
        # Find product(s)
        product, multiple = find_products(search_query)

        # Multiple matches
        if multiple:
            translated_suggestions = []
            for prod_name in multiple[:10]:
                if language != 'en':
                    translated_name = auto_translate(prod_name, language)
                    translated_suggestions.append({
                        'original': prod_name,
                        'translated': translated_name
                    })
                else:
                    translated_suggestions.append({
                        'original': prod_name,
                        'translated': prod_name
                    })
            
            return jsonify({
                "type": "suggestions",
                "query": safe_input,
                "suggestions": translated_suggestions,
                "message": get_text('multiple_matches', language, query=safe_input)
            })

        # Single match
        if product:
            name = product.get('name_en', 'Unnamed Product')
            if language != 'en':
                name = auto_translate(name, language)
            
            desc = product.get('desc_en') or product.get('usage_en') or get_text('no_description', language)
            desc = clean_description(desc, language)
            
            if language != 'en' and desc != get_text('no_description', language):
                desc = auto_translate(desc, language)
            
            points = []
            for separator in ['\n', '•', '·', '-', '|', ';']:
                if separator in desc:
                    points = [p.strip() for p in desc.split(separator) if p.strip()]
                    break
            
            if not points:
                points = [s.strip() + '.' for s in re.split(r'\.(?:\s+|$)', desc) if s.strip()]
            
            points = [p for p in points if len(p) > 10]

            image = product.get('image_url')
            if not image and product.get('image_local'):
                image = f"/static/images/{product['image_local']}"

            return jsonify({
                "type": "product",
                "name": name,
                "description": desc,
                "points": points,
                "image": image
            })

        # No match found
        return jsonify({
            "type": "error",
            "message": get_text('no_match', language, query=safe_input),
            "suggestion": get_text('suggestion_text', language)
        })

    except Exception as e:
        app.logger.error(f"Chat error: {e}")
        return jsonify({
            "type": "error",
            "message": get_text('error_message', language)
        }), 500


# -------------------------------
# WhatsApp Webhook Route
# -------------------------------
@app.route('/whatsapp', methods=['POST'])
def whatsapp_webhook():
    """Handle incoming WhatsApp messages."""
    if not WHATSAPP_ENABLED:
        return "WhatsApp not configured", 503
    
    try:
        incoming_msg = request.values.get('Body', '').strip()
        from_number = request.values.get('From', '')
        
        resp = MessagingResponse()
        msg = resp.message()
        
        language = get_whatsapp_user_language(from_number)
        
        if not incoming_msg:
            msg.body(get_text('empty_input', language, whatsapp=True))
            return str(resp)
        
        user_input = clean_query(incoming_msg)
        user_lower = user_input.lower()
        
        # Language switches
        if any(word in user_lower for word in ['tamil', 'தமிழ்']):
            set_whatsapp_user_language(from_number, 'ta')
            msg.body(get_text('language_switched', 'ta', whatsapp=True))
            return str(resp)
        
        if any(word in user_lower for word in ['hindi', 'हिंदी']):
            set_whatsapp_user_language(from_number, 'hi')
            msg.body(get_text('language_switched', 'hi', whatsapp=True))
            return str(resp)
        
        if any(word in user_lower for word in ['english', 'ஆங்கிலம்', 'अंग्रेज़ी']):
            set_whatsapp_user_language(from_number, 'en')
            msg.body(get_text('language_switched', 'en', whatsapp=True))
            return str(resp)
        
        # Greeting
        if user_lower in ['hi', 'hello', 'hey', 'start', 'வணக்கம்', 'नमस्ते']:
            msg.body(get_text('greeting', language, whatsapp=True))
            return str(resp)
        
        # Help
        if user_lower in ['help', '?', 'உதவி', 'मदद']:
            msg.body(get_text('help', language, whatsapp=True))
            return str(resp)
        
        # Check if user is responding to selection
        context = get_whatsapp_user_context(from_number)
        if context.get('type') == 'product_selection' and user_input.isdigit():
            suggestions = context.get('data', [])
            selection_index = int(user_input) - 1
            
            if 0 <= selection_index < len(suggestions):
                selected_product = suggestions[selection_index]
                clear_whatsapp_user_context(from_number)
                
                product = fetch_product(selected_product)
                if product:
                    name = product.get('name_en', 'Unnamed Product')
                    desc = product.get('desc_en') or product.get('usage_en') or get_text('no_description', language, whatsapp=True)
                    desc = clean_description(desc, language)
                    
                    response_text = get_text('product_info', language, whatsapp=True, name=name, description=desc)
                    msg.body(response_text)
                    
                    image_url = product.get('image_url')
                    if image_url:
                        msg.media(image_url)
                    
                    return str(resp)
            
            clear_whatsapp_user_context(from_number)
            msg.body(get_text('error_message', language, whatsapp=True))
            return str(resp)
        
        # Search for products
        product, multiple = find_products(user_input)
        
        # Multiple matches - Try to send interactive message first
        if multiple:
            # Try sending interactive list/buttons if Twilio client is available
            if TWILIO_CLIENT_ENABLED and len(multiple) <= 10:
                # Try to send as buttons/list
                success = send_whatsapp_buttons(from_number, multiple, user_input, language)
                if success:
                    return ''  # Empty response since we sent via Twilio client
            
            # Fallback to numbered list in response
            product_list = "\n".join([f"{i+1}. {name}" for i, name in enumerate(multiple)])
            response_text = get_text('multiple_matches', language, whatsapp=True, query=user_input, list=product_list)
            
            msg.body(response_text)
            set_whatsapp_user_context(from_number, 'product_selection', multiple)
            return str(resp)
        
        # Single match
        if product:
            name = product.get('name_en', 'Unnamed Product')
            desc = product.get('desc_en') or product.get('usage_en') or get_text('no_description', language, whatsapp=True)
            desc = clean_description(desc, language)
            
            response_text = get_text('product_info', language, whatsapp=True, name=name, description=desc)
            msg.body(response_text)
            
            image_url = product.get('image_url')
            if image_url:
                msg.media(image_url)
            
            clear_whatsapp_user_context(from_number)
            return str(resp)
        
        # No match found
        msg.body(get_text('no_match', language, whatsapp=True, query=user_input))
        return str(resp)
        
    except Exception as e:
        app.logger.error(f"WhatsApp webhook error: {e}")
        resp = MessagingResponse()
        msg = resp.message()
        msg.body(get_text('error_message', get_whatsapp_user_language(request.values.get('From', '')), whatsapp=True))
        return str(resp)


# -------------------------------
# Status endpoint
# -------------------------------
@app.route('/status')
def status():
    """Check if both web and WhatsApp are working."""
    return jsonify({
        "web": "✅ Working",
        "whatsapp": "✅ Working" if WHATSAPP_ENABLED else "❌ Not configured (install twilio)",
        "database": "✅ Connected" if os.path.exists('products.db') else "❌ products.db not found"
    })


# -------------------------------
# Clear cache endpoint
# -------------------------------
@app.route('/admin/clear-cache', methods=['POST'])
def clear_cache():
    get_all_product_names.cache_clear()
    translation_cache.clear()
    return jsonify({"status": "Cache cleared"})


# -------------------------------
# Main
# -------------------------------
# -------------------------------
# Main
# -------------------------------
if __name__ == '__main__':
    print("\n" + "="*60)
    print("🚀 ChimerTech Chatbot Starting...")
    print("="*60)
    
    # Check if chat.html exists
    template_path = os.path.join('templates', 'chat.html')
    if os.path.exists(template_path):
        print("✅ Web interface: http://localhost:5000")
    else:
        print("⚠️  Web interface: Template not found")
        print("   Put chat.html in 'templates' folder")
    
    # Check WhatsApp status
    if WHATSAPP_ENABLED:
        print("✅ WhatsApp: Ready (webhook at /whatsapp)")
    else:
        print("⚠️  WhatsApp: Install twilio to enable")
    
    # Check database
    if os.path.exists('products.db'):
        print("✅ Database: Connected")
    else:
        print("❌ Database: products.db not found!")
    
    print("="*60)
    print("\nStarting Flask server...\n")
    
    # REQUIRED FOR RENDER
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
