import sqlite3
import random
import string
import os
from datetime import datetime

class BotStore:
    def __init__(self, db_path="bot_database.db"):
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self):
        cursor = self.conn.cursor()
        
        # Tabla de Usuarios
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Tabla de Perfiles
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                full_name TEXT,
                ine_front TEXT, -- Ruta relativa o nombre de archivo
                ine_back TEXT,
                selfie_url TEXT,
                status TEXT DEFAULT 'pending', 
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )
        ''')

        # Tabla de Keys
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS keys (
                key_code TEXT PRIMARY KEY,
                activation_count INTEGER,
                used BOOLEAN DEFAULT 0,
                generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        self.conn.commit()

    def get_user(self, user_id):
        return self.conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()

    def add_user(self, user_id, username=None):
        if not self.get_user(user_id):
            self.conn.execute("INSERT INTO users (user_id, username) VALUES (?, ?)", (user_id, username))
            self.conn.commit()
            return True
        return False

    # --- GESTIÓN DE KEYS ---
    
    def generate_key(self, activations=1):
        chars = string.ascii_uppercase + string.digits
        code_part = ''.join(random.choices(chars, k=8))
        key = f"ImMrTx-{code_part}"
        
        existing = self.conn.execute("SELECT * FROM keys WHERE key_code = ?", (key,)).fetchone()
        if existing:
            return self.generate_key(activations)

        self.conn.execute(
            "INSERT INTO keys (key_code, activation_count, used) VALUES (?, ?, 0)",
            (key, activations)
        )
        self.conn.commit()
        return key

    def validate_and_consume_key(self, key_code):
        row = self.conn.execute("SELECT * FROM keys WHERE key_code = ?", (key_code,)).fetchone()
        
        if not row:
            return False, "Key no encontrada."
        
        if row['used']:
            return False, "Esta key ya fue utilizada."
        
        if row['activation_count'] <= 0:
            return False, "No quedan activaciones."
            
        self.conn.execute("UPDATE keys SET used = 1, activation_count = activation_count - 1 WHERE key_code = ?", (key_code,))
        self.conn.commit()
        return True, "Key canjeada exitosamente."

    # --- GESTIÓN DE PERFILES ---

    def add_profile(self, user_id, data_dict):
        try:
            self.conn.execute("""
                INSERT INTO profiles (user_id, full_name, ine_front, ine_back, selfie_url, status)
                VALUES (?, ?, ?, ?, ?, 'valid')
            """, (user_id, data_dict['full_name'], data_dict['ine_front'], data_dict['ine_back'], data_dict['selfie_url']))
            self.conn.commit()
            return True
        except Exception as e:
            print(f"Error adding profile: {e}")
            return False

    def get_profiles(self, user_id):
        return self.conn.execute("SELECT * FROM profiles WHERE user_id = ? AND status = 'valid'", (user_id,)).fetchall()

    def get_profile_by_id(self, profile_id):
        return self.conn.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,)).fetchone()

    def close(self):
        self.conn.close()

# Instancia global
db = BotStore()