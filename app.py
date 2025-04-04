from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
import os
import qrcode
from datetime import datetime
from io import BytesIO
import base64
from pyzbar.pyzbar import decode
import cv2
import numpy as np

app = Flask(__name__)
app.secret_key = 'your_secret_key'
DATABASE = 'database/attendance.db'


def init_hod():
    conn = sqlite3.connect('database/attendance.db')  # Replace with your DB path if needed
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS hod (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL
        )
    ''')
    cur.execute("INSERT OR IGNORE INTO hod (username, password) VALUES (?, ?)", ('admin', 'admin123'))
    conn.commit()
    conn.close()
    print("✅ HOD table created and sample admin inserted.")

def get_db_connection():
    return sqlite3.connect('database/attendance.db')


# ------------------- Database Setup -------------------
def init_db():
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()

    # Create student table
    c.execute('''CREATE TABLE IF NOT EXISTS students (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    mobile TEXT UNIQUE NOT NULL,
                    class TEXT NOT NULL,
                    password TEXT NOT NULL
                )''')

    # Create teacher table
    c.execute('''CREATE TABLE IF NOT EXISTS teachers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL
                )''')

    # Create attendance table
    c.execute('''CREATE TABLE IF NOT EXISTS attendance (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    student_id INTEGER,
                    class TEXT,
                    subject TEXT,
                    date TEXT,
                    time TEXT,
                    FOREIGN KEY(student_id) REFERENCES students(id)
                )''')

    # Insert demo teacher with plain password
    c.execute("SELECT * FROM teachers WHERE email=?", ('admin@gmail.com',))
    if not c.fetchone():
        c.execute("INSERT INTO teachers (email, password) VALUES (?, ?)", ('admin@gmail.com', 'admin'))

    conn.commit()
    conn.close()


# ------------------- Routes -------------------
@app.route('/')
def home():
    return redirect(url_for('login'))


@app.route('/student/mark_attendance', methods=['GET', 'POST'])
def mark_attendance():
    if session.get('role') != 'student':
        return redirect(url_for('login'))

    message = ''
    if request.method == 'POST':
        file = request.files['qr_image']
        if file:
            image = np.frombuffer(file.read(), np.uint8)
            image = cv2.imdecode(image, cv2.IMREAD_COLOR)

            decoded_objs = decode(image)
            if decoded_objs:
                data = decoded_objs[0].data.decode('utf-8')
                parts = dict(item.split(':') for item in data.split('|'))
                class_name = parts['class']
                subject = parts['subject']
                timestamp = parts['timestamp']
                date, time = timestamp.split()

                conn = sqlite3.connect(DATABASE)
                c = conn.cursor()
                c.execute('''
                    INSERT INTO attendance (student_id, class, subject, date, time)
                    VALUES (?, ?, ?, ?, ?)
                ''', (session['user_id'], class_name, subject, date, time))
                conn.commit()
                conn.close()
                message = '✅ Attendance marked successfully!'
            else:
                message = '❌ Could not read QR code. Try again.'

    return render_template('mark_attendance.html', message=message)


@app.route('/student/mark_attendance_live', methods=['GET', 'POST'])
def mark_attendance_live():
    if session.get('role') != 'student':
        return redirect(url_for('login'))

    if request.method == 'GET':
        return render_template('mark_attendance_live.html')

    elif request.method == 'POST':
        data = request.get_json()
        qr_text = data.get('qr_data', '')

        try:
            parts = dict(item.split(':', 1) for item in qr_text.split('|'))
            class_name = parts['class']
            subject = parts['subject']
            timestamp = parts['timestamp']
            date, time = timestamp.split()

            conn = sqlite3.connect(DATABASE)
            c = conn.cursor()
            c.execute('''
                INSERT INTO attendance (student_id, class, subject, date, time)
                VALUES (?, ?, ?, ?, ?)
            ''', (session['user_id'], class_name, subject, date, time))
            conn.commit()
            conn.close()

            return jsonify({'message': '✅ Attendance marked successfully!'})

        except Exception as e:
            return jsonify({'message': f'❌ Failed to mark attendance: {str(e)}'})


# @app.route('/student/mark_attendance_live', methods=['POST'])
# def mark_attendance_live():
#     data = request.get_json()

#     if not data:
#         return jsonify({'message': 'No data provided'}), 400

#     student_id = data.get('student_id')
#     class_name = data.get('class_name')

#     if not student_id or not class_name:
#         return jsonify({'message': 'Missing student_id or class_name'}), 400

#     conn = sqlite3.connect('database/attendance.db')
#     cur = conn.cursor()

#     current_time = datetime.datetime.now()

#     # Check the most recent attendance record for this student/class
#     cur.execute('''
#         SELECT timestamp FROM attendance
#         WHERE student_id = ? AND class_name = ?
#         ORDER BY timestamp DESC LIMIT 1
#     ''', (student_id, class_name))

#     last_record = cur.fetchone()

#     if last_record:
#         last_time = datetime.datetime.fromisoformat(last_record[0])
#         time_diff = current_time - last_time

#         if time_diff.total_seconds() < 60:
#             conn.close()
#             return jsonify({'message': 'Attendance already marked recently. Try again after 1 minute.'}), 200

#     # Insert new attendance record
#     cur.execute('''
#         INSERT INTO attendance (student_id, class_name, timestamp)
#         VALUES (?, ?, ?)
#     ''', (student_id, class_name, current_time.isoformat()))

#     conn.commit()
#     conn.close()

#     return jsonify({'message': 'Attendance marked successfully'}), 200


@app.route('/student/view_attendance')
def student_view_attendance():
    if session.get('role') != 'student':
        return redirect(url_for('login'))

    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute('''
        SELECT class, subject, date, time FROM attendance
        WHERE student_id = ?
        ORDER BY date DESC, time DESC
    ''', (session['user_id'],))
    attendance_data = c.fetchall()
    conn.close()

    return render_template('student_view_attendance.html', records=attendance_data)


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        mobile = request.form['mobile']
        student_class = request.form['class_']
        password = generate_password_hash(request.form['password'])

        try:
            conn = sqlite3.connect(DATABASE)
            c = conn.cursor()
            c.execute("INSERT INTO students (name, mobile, class, password) VALUES (?, ?, ?, ?)",
                      (name, mobile, student_class, password))
            conn.commit()
            flash('Registration successful. Please login.', 'success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Mobile number already registered.', 'danger')
        finally:
            conn.close()

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        role = request.form.get('role')
        password = request.form.get('password')

        conn = sqlite3.connect(DATABASE)
        c = conn.cursor()

        if role == 'student':
            mobile = request.form.get('mobile')
            c.execute('SELECT id, name, password FROM students WHERE mobile=?', (mobile,))
            student = c.fetchone()
            if student and check_password_hash(student[2], password):
                session['user_id'] = student[0]
                session['username'] = student[1]
                session['role'] = 'student'
                conn.close()
                return redirect(url_for('student_dashboard'))
            else:
                flash('Invalid student credentials.', 'danger')

        elif role == 'teacher':
            email = request.form.get('email')
            c.execute('SELECT id, password FROM teachers WHERE email=?', (email,))
            teacher = c.fetchone()
            if teacher and teacher[1] == password:  # No hashing for teacher
                session['user_id'] = teacher[0]
                session['username'] = 'Admin'
                session['role'] = 'teacher'
                conn.close()
                return redirect(url_for('teacher_dashboard'))
            else:
                flash('Invalid teacher credentials.', 'danger')

        conn.close()

    return render_template('login.html')

@app.route('/student/dashboard')
def student_dashboard():

    if session.get('role') != 'student':
        return redirect(url_for('login'))

    # Fetch student attendance records
    student_id = session.get('user_id')
    student_name = session.get('user_name')

    conn = sqlite3.connect('database/attendance.db')
    cursor = conn.cursor()
    cursor.execute("SELECT subject, date, time FROM attendance WHERE student_id = ?", (student_id,))
    attendance_records = cursor.fetchall()
    conn.close()

    return render_template('student_dashboard.html', student_name=student_name, attendance_records=attendance_records)



@app.route('/teacher/dashboard')
def teacher_dashboard():
    if session.get('role') != 'teacher':
        return redirect(url_for('login'))
    return render_template('teacher_dashboard.html', message="Welcome Admin!")


@app.route('/teacher/generate_qr', methods=['GET', 'POST'])
def generate_qr():
    if session.get('role') != 'teacher':
        return redirect(url_for('login'))

    qr_data = None
    if request.method == 'POST':
        class_name = request.form['class']
        subject = request.form['subject']
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        qr_text = f"class:{class_name}|subject:{subject}|timestamp:{timestamp}"

        img = qrcode.make(qr_text)
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        qr_data = base64.b64encode(buffer.getvalue()).decode('utf-8')

    return render_template('generate_qr.html', qr_data=qr_data)

@app.route('/teacher/view_attendance', methods=['GET', 'POST'])
def teacher_view_attendance():
    if session.get('role') != 'teacher':
        return redirect(url_for('login'))

    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()

    # Get all unique classes and subjects
    c.execute("SELECT DISTINCT class FROM students")
    classes = [row[0] for row in c.fetchall()]

    c.execute("SELECT DISTINCT subject FROM attendance")
    subjects = [row[0] for row in c.fetchall()]

    records = []
    class_filter = subject_filter = date_filter = ""

    if request.method == 'POST':
        class_filter = request.form.get('class', '')
        subject_filter = request.form.get('subject', '')
        date_filter = request.form.get('date', '')

        query = '''
            SELECT students.name, students.class, attendance.subject, attendance.date, attendance.time
            FROM attendance
            JOIN students ON attendance.student_id = students.id
            WHERE 1=1
        '''
        params = []

        if class_filter:
            query += ' AND students.class = ?'
            params.append(class_filter)
        if subject_filter:
            query += ' AND attendance.subject = ?'
            params.append(subject_filter)
        if date_filter:
            query += ' AND attendance.date = ?'
            params.append(date_filter)

        query += ' ORDER BY attendance.date DESC, attendance.time DESC'

        c.execute(query, params)
        records = c.fetchall()

    conn.close()

    return render_template('teacher_view_attendance.html',
                           records=records,
                           classes=classes,
                           subjects=subjects,
                           class_filter=class_filter,
                           subject_filter=subject_filter,
                           date_filter=date_filter)



@app.route('/hod-login', methods=['GET', 'POST'])
def hod_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM hod WHERE username=? AND password=?", (username, password))
        hod = cur.fetchone()
        conn.close()

        print(username)
        print(password)

        if username == 'rohan' and password == 'rohan123':
            return render_template('hod_dashboard.html')


        # if hod:
        #     session['username'] = username
        #     # session['role'] = 'hod'
        #     session['password'] = password
        #     return redirect(url_for('hod_dashboard'))
        else:
            flash("Invalid credentials", "error")
    
    return render_template('hod_login.html')

@app.route('/hod-dashboard')
def hod_dashboard():
    if 'username' not in session or session.get('role') != 'hod':
        return redirect(url_for('hod_login'))
    return render_template('hod_dashboard.html')



if __name__ == '__main__':
    # Ensure the database directory exists
    os.makedirs(os.path.dirname(DATABASE), exist_ok=True)

    # Initialize the database tables
    init_db()
    init_hod()

    # Start the Flask app
  
    app.run(host='0.0.0.0', port=5000, debug=True)

