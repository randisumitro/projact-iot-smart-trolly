import firebase_admin
from firebase_admin import credentials, db

cred = credentials.Certificate("firebase_key.json")
firebase_admin.initialize_app(cred, {
    'databaseURL': 'https://smartcartesp-default-rtdb.firebaseio.com/'
})

def update_lcd_message(message):
    ref = db.reference('lcd')
    ref.set({'text': message})
