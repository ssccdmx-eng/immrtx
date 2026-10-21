import os
import json
import logging
import telebot
from telebot import types
from dotenv import load_dotenv
from bot_store import db
from carriers.att import ATTDriver
# Importar otros carriers cuando estén listos
# from carriers.telcel import TelcelDriver 

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID'))

if not BOT_TOKEN:
    raise ValueError("Falta BOT_TOKEN en .env")

bot = telebot.TeleBot(BOT_TOKEN)
logging.basicConfig(level=logging.INFO)

# Estados del usuario
STATE = {}

def get_state(chat_id):
    return STATE.get(chat_id, None)

def set_state(chat_id, state):
    STATE[chat_id] = state

def clear_state(chat_id):
    STATE.pop(chat_id, None)

# --- INICIALIZACIÓN ---

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user = message.from_user
    db.add_user(user.id, user.username)
    
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn_buy = types.KeyboardButton("/buy_key")
    btn_redeem = types.KeyboardButton("/redeem_key")
    btn_my_profiles = types.KeyboardButton("/my_profiles")
    btn_new_link = types.KeyboardButton("/new_linkage")
    
    markup.add(btn_buy, btn_redeem)
    markup.add(btn_my_profiles, btn_new_link)
    
    bot.reply_to(message, 
                 "Bienvenido al Bot de Automatización de Registro.\n\n"
                 "Selecciona una opción:", reply_markup=markup)

# --- COMANDOS PRINCIPALES ---

@bot.message_handler(commands=['buy_key'])
def buy_key(message):
    admin_msg = f"El usuario {message.from_user.username} (ID: {message.from_user.id}) quiere comprar una Key."
    bot.send_message(ADMIN_ID, admin_msg)
    bot.reply_to(message, f"He notificado al administrador. Espera su respuesta para recibir tu Key.")

@bot.message_handler(commands=['genkey'])
def gen_key_admin(message):
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "Solo el admin puede generar keys.")
        return
    
    parts = message.text.split()
    if len(parts) < 2:
        bot.reply_to(message, "Uso: /genkey [cantidad]")
        return
    
    try:
        count = int(parts[1])
        new_key = db.generate_key(count)
        bot.reply_to(message, f"Key generada: `{new_key}`\nActivaciones: {count}\nFormato: ImMrTx-xxxx-xxxx")
    except ValueError:
        bot.reply_to(message, "Ingresa un número válido.")

@bot.message_handler(commands=['redeem_key'])
def redeem_key(message):
    set_state(message.chat.id, 'WAITING_KEY')
    bot.reply_to(message, "Envía el código de la key (ej: ImMrTx-ABCD1234):")

@bot.message_handler(commands=['my_profiles'])
def my_profiles(message):
    user_profiles = db.get_profiles(message.from_user.id)
    
    if not user_profiles:
        bot.reply_to(message, "No tienes perfiles válidos aún.")
        return

    markup = types.InlineKeyboardMarkup()
    for p in user_profiles:
        name_short = p['full_name'][:20] + ("..." if len(p['full_name']) > 20 else "")
        callback_data = f"profile_{p['id']}"
        markup.add(types.InlineKeyboardButton(name_short, callback_data=callback_data))
    
    markup.add(types.InlineKeyboardButton("➕ Agregar nuevo perfil", callback_data="add_profile"))
    
    bot.send_message(message.chat.id, "Selecciona un perfil o agrega uno nuevo:", reply_markup=markup)

@bot.message_handler(commands=['new_linkage'])
def new_linkage(message):
    markup = types.InlineKeyboardMarkup()
    carriers = ["AT&T", "Telcel", "WeX", "Bait", "Altan", "Movistar"]
    
    for c in carriers:
        markup.add(types.InlineKeyboardButton(c, callback_data=f"carrier_{c.lower()}"))
        
    bot.send_message(message.chat.id, "Selecciona el Carrier para la vinculación:", reply_markup=markup)

# --- MANEJO DE ESTADOS Y MENSAJES ---

@bot.message_handler(func=lambda m: get_state(m.chat.id) == 'WAITING_KEY')
def handle_key_redemption(message):
    key_code = message.text.strip()
    success, msg = db.validate_and_consume_key(key_code)
    
    if success:
        bot.reply_to(message, f"✅ ¡Key canjeada! Ahora tienes acceso completo.")
        clear_state(message.chat.id)
    else:
        bot.reply_to(message, f"❌ Error: {msg}")
        clear_state(message.chat.id)

# --- CALLBACKS (Inline Buttons) ---

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    # 1. Agregar Perfil
    if call.data == "add_profile":
        set_state(call.message.chat.id, {'step': 'PROFILE_NAME'})
        bot.send_message(call.message.chat.id, "Envía tu Nombre Completo (como aparece en el INE):")
        return

    # 2. Seleccionar Perfil existente
    if call.data.startswith("profile_"):
        profile_id = int(call.data.split('_')[1])
        profile = db.get_profile_by_id(profile_id)
        if profile:
            set_state(call.message.chat.id, {'action': 'LINKAGE', 'profile_id': profile_id})
            bot.send_message(call.message.chat.id, f"Perfil seleccionado: {profile['full_name']}. \nAhora selecciona un Carrier abajo para iniciar la automatización.", 
                           reply_markup=get_carrier_markup())
        return

    # 3. Selección de Carrier
    if call.data.startswith("carrier_"):
        carrier_name = call.data.split('_')[1].capitalize()
        state = get_state(call.message.chat.id)
        
        selected_profile = None
        
        # Si estamos vinculando desde Mis Perfiles -> Seleccionar Perfil
        if state and isinstance(state, dict) and state.get('profile_id'):
             selected_profile = db.get_profile_by_id(state['profile_id'])
        else:
            # Si llegamos aquí sin profile_id previo, verificar si hay uno único
            user_profiles = db.get_profiles(call.message.from_user.id)
            if len(user_profiles) == 1:
                selected_profile = user_profiles[0]
                bot.send_message(call.message.chat.id, f"Se usará automáticamente el único perfil: {selected_profile['full_name']}")
            else:
                bot.send_message(call.message.chat.id, "Necesitas tener un perfil válido para continuar.")
                return

        if selected_profile:
            start_selenium_flow(carrier_name, selected_profile, call.message.chat.id)
            return

# --- FLUJO DE SUBIDA DE DOCUMENTOS ---

@bot.message_handler(func=lambda m: get_state(m.chat.id) and get_state(m.chat.id).get('step') == 'PROFILE_NAME')
def handle_profile_name(message):
    full_name = message.text
    set_state(message.chat.id, {'step': 'INE_FRONT', 'data': {'full_name': full_name}})
    bot.send_message(message.chat.id, "Ahora envía la foto de la parte FRONTAL de tu INE:")

@bot.message_handler(content_types=['photo', 'document'])
def handle_document_upload(message):
    chat_id = message.chat.id
    state = get_state(chat_id)
    
    if not state or 'step' not in state: 
        return

    # Descargar archivo
    if message.content_type == 'photo':
        file_info = bot.get_file(message.photo[-1].file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        filename = f"data/profiles/{chat_id}_front.jpg" # Guardar en carpeta data
    else:
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        filename = f"data/profiles/{chat_id}_front.jpg"

    # Crear carpeta si no existe
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    
    with open(filename, 'wb') as new_file:
        new_file.write(downloaded_file)
    
    current_data = state.get('data', {})
    current_data[state['step']] = filename
    
    step = state['step']
    
    if step == 'INE_FRONT':
        current_data['ine_front'] = filename
        set_state(chat_id, {'step': 'INE_BACK', 'data': current_data})
        bot.reply_to(message, "Perfecto. Ahora envía la parte TRASERA del INE:")
        
    elif step == 'INE_BACK':
        current_data['ine_back'] = filename
        set_state(chat_id, {'step': 'SELFIE', 'data': current_data})
        bot.reply_to(message, "Genial. Por último, envíate una SELFIE sosteniendo el INE o mirando a cámara:")
        
    elif step == 'SELFIE':
        current_data['selfie_url'] = filename
        
        # Guardar en DB
        success = db.add_profile(message.from_user.id, current_data)
        if success:
            bot.reply_to(message, f"✅ Perfil '{current_data['full_name']}' guardado y validado correctamente.")
        else:
            bot.reply_to(message, "⚠️ Perfil guardado pero requiere revisión manual.")
            
        clear_state(chat_id)

# Helper para generar markup de carriers inline
def get_carrier_markup():
    markup = types.InlineKeyboardMarkup()
    carriers = ["AT&T", "Telcel", "WeX", "Bait", "Altan", "Movistar"]
    for c in carriers:
        markup.add(types.InlineKeyboardButton(c, callback_data=f"carrier_{c.lower()}"))
    return markup

# --- AUTOMATIZACIÓN CON SELENIUM/PLAYWRIGHT ---

def start_selenium_flow(carrier_name, profile, chat_id):
    """
    Inicia el proceso de Selenium/Playwright en un hilo separado para no bloquear el bot.
    """
    bot.send_message(chat_id, f"🔄 Iniciando automatización para {carrier_name}...")
    
    import threading
    t = threading.Thread(target=run_carrier_script, args=(carrier_name, profile, chat_id))
    t.start()

def run_carrier_script(carrier_name, profile, chat_id):
    """
    Ejecuta el driver específico del carrier.
    """
    try:
        if carrier_name == "Att":
            run_att_flow(profile, chat_id)
        else:
            bot.send_message(chat_id, f"🚧 Carrier {carrier_name} en desarrollo.")
    except Exception as e:
        bot.send_message(chat_id, f"❌ Error en {carrier_name}: {str(e)}")
        logging.exception(f"Error en {carrier_name}")

async def run_att_flow(profile, chat_id):
    """
    Flujo específico para AT&T usando el driver adaptado.
    """
    driver = ATTDriver()
    try:
        await driver.start()
        bot.send_message(chat_id, "🚗 Navegador abierto en AT&T.")
        
        # Rellenar datos básicos
        await driver.fill_profile(profile)
        bot.send_message(chat_id, "📄 Campos de texto rellenados.")
        
        # Subir imágenes
        await driver.upload_images(profile)
        bot.send_message(chat_id, "🔙 Documentos subidos.")
        
        # Resolver Slider
        await driver.solve_slider()
        bot.send_message(chat_id, "🎯 Slider resuelto.")
        
        # Finalizar
        await driver.complete()
        bot.send_message(chat_id, "✅ Vinculación completada para AT&T.")
        
    except Exception as e:
        raise e
    finally:
        await driver.close()

# Iniciar bot
if __name__ == "__main__":
    print("Bot iniciado...")
    bot.infinity_polling()
