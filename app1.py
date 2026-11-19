import numpy as np
import pandas as pd
import joblib
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import hashlib
from datetime import datetime
import os
import serial

# ---------------------------------------------
# Flask App
# ---------------------------------------------
app = Flask(__name__)
app.secret_key = 'your-secret-key-here'

# ---------------------------------------------
# Arduino Serial Setup
# ---------------------------------------------
try:
    arduino = serial.Serial('COM3', 9600, timeout=1)   # Change COM port as needed
    print("✅ Arduino connected on COM3")
except Exception as e:
    print("❌ Arduino connection failed:", e)
    arduino = None

# ---------------------------------------------
# Database Initialization
# ---------------------------------------------
def init_db():
    conn = sqlite3.connect('agriculture.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sensor_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            ph REAL NOT NULL,
            humidity REAL NOT NULL,
            temperature REAL NOT NULL,
            moisture REAL NOT NULL,
            ldr_status REAL NOT NULL,
            pump_status TEXT NOT NULL
        )
    ''')
    
    conn.commit()
    conn.close()

def get_db_connection():
    conn = sqlite3.connect('agriculture.db')
    conn.row_factory = sqlite3.Row
    return conn

# ---------------------------------------------
# Load ML Model
# ---------------------------------------------
try:
    model = joblib.load("randomforest_model.pkl")
    scaler = joblib.load("scaler.pkl")
    imputer = joblib.load("imputer.pkl")
    label_encoder = joblib.load("label_encoder.pkl")

    if hasattr(model, "feature_names_in_"):
        trained_features = list(model.feature_names_in_)
    else:
        trained_features = ["pH", "humidity", "temperature", "moisture", "ldr_status"]

    print("✅ ML model loaded")

except Exception as e:
    print("❌ Error loading ML model:", e)
    trained_features = ["pH", "humidity", "temperature", "moisture", "ldr_status"]

# ---------------------------------------------
# Helper Functions
# ---------------------------------------------
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def read_sensor_data():
    try:
        with open('sensor_data.txt', 'r') as file:
            lines = file.readlines()
            if lines:
                last_line = lines[-1].strip()
                values = last_line.split('\t')
                if len(values) == 5:
                    return {
                        'pH': float(values[0]),
                        'humidity': float(values[1]),
                        'temperature': float(values[2]),
                        'moisture': float(values[3]),
                        'ldr_status': float(values[4])
                    }
    except Exception as e:
        print(f"Error reading sensor data: {e}")

    return None

def predict_pump_status(sensor_data):
    try:
        df = pd.DataFrame([sensor_data])
        
        for f in trained_features:
            if f not in df.columns:
                df[f] = np.nan

        df = df[trained_features]

        X = imputer.transform(df)
        X_scaled = scaler.transform(X)

        pred_encoded = model.predict(X_scaled)[0]
        pred_label = label_encoder.inverse_transform([pred_encoded])[0]
        return pred_label

    except Exception as e:
        print(f"Prediction error: {e}")
        return "Unknown"

def log_sensor_data(sensor_data, pump_status):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        '''INSERT INTO sensor_logs 
           (ph, humidity, temperature, moisture, ldr_status, pump_status)
           VALUES (?, ?, ?, ?, ?, ?)''',
        (
            sensor_data['pH'], sensor_data['humidity'],
            sensor_data['temperature'], sensor_data['moisture'],
            sensor_data['ldr_status'], pump_status
        )
    )

    conn.commit()
    conn.close()

def send_to_arduino(pump_status):
    if arduino:
        try:
            if pump_status == "1" or pump_status.lower() == "on":
                arduino.write(b'1')
                print("➡️ Sent '1' to Arduino (PUMP ON)")
            else:
                arduino.write(b'0')
                print("➡️ Sent '0' to Arduino (PUMP OFF)")
        except Exception as e:
            print("❌ Serial Write Error:", e)

# ---------------------------------------------
# Routes
# ---------------------------------------------
@app.route('/')
def home():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/home')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        email = request.form['email']

        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            cursor.execute(
                'INSERT INTO users (username, password, email) VALUES (?, ?, ?)',
                (username, hash_password(password), email)
            )
            conn.commit()
            flash("Registration successful!", "success")
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash("Username or Email already exists!", "error")
        finally:
            conn.close()

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            'SELECT * FROM users WHERE username = ? AND password = ?',
            (username, hash_password(password))
        )

        user = cursor.fetchone()
        conn.close()

        if user:
            session['user_id'] = user['id']
            session['username'] = user['username']
            flash("Login successful!", "success")
            return redirect(url_for('dashboard'))
        else:
            flash("Invalid credentials!", "error")

    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    sensor_data = read_sensor_data()
    pump_status = "Unknown"

    if sensor_data:
        pump_status = predict_pump_status(sensor_data)

    return render_template(
        'dashboard.html',
        sensor_data=sensor_data,
        pump_status=pump_status,
        username=session['username']
    )

@app.route('/api/sensor-data')
def api_sensor_data():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    sensor_data = read_sensor_data()
    pump_status = "Unknown"

    if sensor_data:
        pump_status = predict_pump_status(sensor_data)
        log_sensor_data(sensor_data, pump_status)
        send_to_arduino(pump_status)

    return jsonify({
        'sensor_data': sensor_data,
        'pump_status': pump_status,
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    })

@app.route('/logs')
def logs():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    date_filter = request.args.get('date', '')

    conn = get_db_connection()
    cursor = conn.cursor()

    if date_filter:
        cursor.execute(
            'SELECT * FROM sensor_logs WHERE DATE(timestamp) = ? ORDER BY timestamp DESC',
            (date_filter,)
        )
    else:
        cursor.execute('SELECT * FROM sensor_logs ORDER BY timestamp DESC LIMIT 100')

    logs = cursor.fetchall()
    conn.close()

    return render_template('logs.html', logs=logs, date_filter=date_filter)

@app.route('/logout')
def logout():
    session.clear()
    flash("Logged out successfully.", "info")
    return redirect(url_for('index'))

# ---------------------------------------------
# Run Server
# ---------------------------------------------
if __name__ == "__main__":
    init_db()
    app.run(debug=True,host='0.0.0.0')
