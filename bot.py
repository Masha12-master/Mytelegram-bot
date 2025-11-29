# ================================
# Full Aiogram Bot: OCR + File to Audio + Silero TTS + Referal
# ================================

from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils import executor
import sqlite3
import pytesseract
from PIL import Image
import tempfile
import os
from docx import Document
import pandas as pd
from PyPDF2 import PdfReader
# Silero TTS imports
import torch
import torchaudio

# ==================== CONFIG ====================
TOKEN = "8368526007:AAFKbENCZ05n7AG-ZbcSaeIMTlLxDj7MmkY"
DATABASE = "data/bot.db"
bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

# ==================== DB ====================

def init_db():
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                 user_id INTEGER PRIMARY KEY,
                 username TEXT,
                 lang TEXT DEFAULT 'en',
                 inviter INTEGER DEFAULT NULL)''')
    conn.commit()
    conn.close()

init_db()

# ==================== LANGUAGES ====================
LANG_MAP = {
    "uz": {"name": "Uzbek", "tess": "uzb", "gtts": "uz"},
    "ru": {"name": "Русский", "tess": "rus", "gtts": "ru"},
    "en": {"name": "English", "tess": "eng", "gtts": "en"}
}
DEFAULT_LANG = "en"

# ==================== HELPERS ====================

def get_user_lang(user_id):
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute("SELECT lang FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else DEFAULT_LANG

# ==================== MENYULAR ====================

def main_menu(lang):
    kb = InlineKeyboardMarkup(row_width=2)
    if lang == 'uz':
        kb.add(InlineKeyboardButton('📄 Fayldan ovoz yaratish', callback_data='file_audio'),
               InlineKeyboardButton('🖼 Rasmni o‘qish (OCR)', callback_data='ocr'),
               InlineKeyboardButton('✏️ Matndan ovoz yaratish', callback_data='text_audio'),
               InlineKeyboardButton('🌐 Tilni o‘zgartirish', callback_data='change_lang'),
               InlineKeyboardButton('👤 Mening profilim', callback_data='profile'),
               InlineKeyboardButton('💰 Donat / Yordam', callback_data='donate'))
    elif lang == 'ru':
        kb.add(InlineKeyboardButton('📄 Файл → Голос', callback_data='file_audio'),
               InlineKeyboardButton('🖼 OCR (читать изображение)', callback_data='ocr'),
               InlineKeyboardButton('✏️ Текст → Голос', callback_data='text_audio'),
               InlineKeyboardButton('🌐 Сменить язык', callback_data='change_lang'),
               InlineKeyboardButton('👤 Мой профиль', callback_data='profile'),
               InlineKeyboardButton('💰 Донат / Поддержать', callback_data='donate'))
    else:
        kb.add(InlineKeyboardButton('📄 File → Audio', callback_data='file_audio'),
               InlineKeyboardButton('🖼 OCR (Image Reader)', callback_data='ocr'),
               InlineKeyboardButton('✏️ Text → Voice', callback_data='text_audio'),
               InlineKeyboardButton('🌐 Change Language', callback_data='change_lang'),
               InlineKeyboardButton('👤 My Profile', callback_data='profile'),
               InlineKeyboardButton('💰 Donate / Support', callback_data='donate'))
    return kb

# ==================== START HANDLER ====================
@dp.message_handler(commands=['start'])
async def start_cmd(message: types.Message):
    args = message.get_args()
    inviter = None
    if args.startswith('ref'):
        try:
            inviter = int(args[3:])
        except:
            inviter = None

    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id, username, inviter) VALUES (?, ?, ?)"
              , (message.from_user.id, message.from_user.username, inviter))
    conn.commit()
    conn.close()

    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(InlineKeyboardButton('🇺🇿 Uzbek', callback_data='lang_uz'),
           InlineKeyboardButton('🇷🇺 Русский', callback_data='lang_ru'),
           InlineKeyboardButton('🇬🇧 English', callback_data='lang_en'))
    await message.answer("Tilni tanlang / Choose language / Выберите язык", reply_markup=kb)

# ==================== CALLBACK HANDLER ====================
@dp.callback_query_handler(lambda c: True)
async def callbacks(call: types.CallbackQuery):
    user_id = call.from_user.id
    if call.data.startswith('lang_'):
        lang = call.data.split('_')[1]
        conn = sqlite3.connect(DATABASE)
        c = conn.cursor()
        c.execute("UPDATE users SET lang=? WHERE user_id=?", (lang, user_id))
        conn.commit()
        conn.close()
        await call.message.edit_text(f"Til o'rnatildi: {LANG_MAP[lang]['name']}", reply_markup=main_menu(lang))

    elif call.data == 'ocr':
        await call.message.answer("Rasm yuboring (JPG, PNG)")
    elif call.data == 'text_audio':
        await call.message.answer("Matn yuboring, men uni ovozga aylantiraman")
    elif call.data == 'file_audio':
        await call.message.answer("Fayl yuboring (PDF, DOCX, XLSX, TXT)")
    elif call.data == 'change_lang':
        kb = InlineKeyboardMarkup(row_width=2)
        kb.add(InlineKeyboardButton('🇺🇿 Uzbek', callback_data='lang_uz'),
               InlineKeyboardButton('🇷🇺 Русский', callback_data='lang_ru'),
               InlineKeyboardButton('🇬🇧 English', callback_data='lang_en'))
        await call.message.answer("Tilni tanlang", reply_markup=kb)
    elif call.data == 'profile':
        lang = get_user_lang(user_id)
        ref_link = f"https://t.me/YourBot?start=ref{user_id}"
        await call.message.answer(f"👤 Profil\nID: {user_id}\nReferal link: {ref_link}")
    elif call.data == 'donate':
        await call.message.answer("💰 Donat qilish uchun: [link]")

# ==================== FILE HANDLER ====================
@dp.message_handler(content_types=types.ContentType.DOCUMENT)
async def handle_file(message: types.Message):
    file = message.document
    file_name = file.file_name
    file_ext = file_name.split('.')[-1].lower()

    file_path = f"temp/{file_name}"
    await file.download(destination_file=file_path)
    text = ""

    try:
        if file_ext == 'pdf':
            reader = PdfReader(file_path)
            for page in reader.pages:
                text += page.extract_text() + '\n'
        elif file_ext in ['docx']:
            doc = Document(file_path)
            for p in doc.paragraphs:
                text += p.text + '\n'
        elif file_ext in ['xls','xlsx']:
            df = pd.read_excel(file_path)
            text = df.to_string()
        elif file_ext == 'txt':
            with open(file_path,'r',encoding='utf-8') as f:
                text = f.read()
        else:
            await message.reply("Unsupported file type")
            return
    except Exception as e:
        await message.reply(f"Xatolik: {str(e)}")
        return

    lang = get_user_lang(message.from_user.id)

    # ==================== Silero TTS ====================
    device = 'cpu'
    model, example_text, sample_rate = torch.hub.load(repo_or_dir='snakers4/silero-models',
                                                     model='silero_tts',
                                                     language=lang)
    model.to(device)
    with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as tmp:
        model.save_wav(text, tmp.name, sample_rate=sample_rate)
        tmp_path = tmp.name

    with open(tmp_path,'rb') as audio_file:
        await message.reply_voice(audio_file)
    os.remove(file_path)
    os.remove(tmp_path)

# ==================== OCR PHOTO ====================
@dp.message_handler(content_types=types.ContentType.PHOTO)
async def ocr_photo(message: types.Message):
    user_id = message.from_user.id
    lang = get_user_lang(user_id)
    photo = message.photo[-1]
    file = await bot.get_file(photo.file_id)
    file_bytes = await bot.download_file(file.file_path)
    img = Image.open(file_bytes)
    text = pytesseract.image_to_string(img, lang=LANG_MAP[lang]['tess'])

    # Silero TTS
    device = 'cpu'
    model, example_text, sample_rate = torch.hub.load(repo_or_dir='snakers4/silero-models',
                                                     model='silero_tts',
                                                     language=lang)
    model.to(device)
    with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as tmp:
        model.save_wav(text, tmp.name, sample_rate=sample_rate)
        tmp_path = tmp.name

    with open(tmp_path, 'rb') as audio_file:
        await message.reply_voice(audio_file)
    os.remove(tmp_path)

# ==================== TEXT MESSAGE ====================
@dp.message_handler(content_types=types.ContentType.TEXT)
async def text_to_voice(message: types.Message):
    user_id = message.from_user.id
    lang = get_user_lang(user_id)
    device = 'cpu'
    model, example_text, sample_rate = torch.hub.load(repo_or_dir='snakers4/silero-models',
                                                     model='silero_tts',
                                                     language=lang)
    model.to(device)
    with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as tmp:
        model.save_wav(message.text, tmp.name, sample_rate=sample_rate)
        tmp_path = tmp.name

    with open(tmp_path, 'rb') as audio_file:
        await message.reply_voice(audio_file)
    os.remove(tmp_path)

# ==================== RUN ====================
if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
