import os
from dotenv import load_dotenv
from cryptography.fernet import Fernet

# load_dotenv here too, so FERNET_KEY is available no matter the import order.
load_dotenv()

# The secret key that both encrypts AND decrypts (symmetric). Lives in .env.
# Guarded so importing this module doesn't crash when the key is missing
# (e.g. on Vercel, not configured yet) — the functions just fail at call time.
FERNET_KEY = os.getenv("FERNET_KEY")
fernet = Fernet(FERNET_KEY) if FERNET_KEY else None


def encrypt_token(plain_text):
    # plain string -> encrypted string (safe to store in the DB)
    return fernet.encrypt(plain_text.encode()).decode()


def decrypt_token(cipher_text):
    # encrypted string -> original plain string
    return fernet.decrypt(cipher_text.encode()).decode()
