import uuid
import sqlite3
import os
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, g

app = Flask(__name__)
app.secret_key = 'super_secret_key_for_flash_messages'

DATABASE = 'database.db'

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    with app.app_context():
        db = get_db()
        db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                email TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                password TEXT NOT NULL
            )
        ''')
        db.execute('''
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                user_email TEXT NOT NULL,
                day TEXT NOT NULL,
                name TEXT NOT NULL,
                done BOOLEAN NOT NULL CHECK (done IN (0, 1)),
                FOREIGN KEY(user_email) REFERENCES users(email)
            )
        ''')
        db.commit()

with app.app_context():
    init_db()

def get_default_tasks():
    return {
        'Monday': [],
        'Tuesday': [],
        'Wednesday': [],
        'Thursday': [],
        'Friday': [],
        'Saturday': [],
        'Sunday': []
    }

def get_user_tasks(email):
    db = get_db()
    rows = db.execute('SELECT * FROM tasks WHERE user_email = ?', (email,)).fetchall()
    tasks = get_default_tasks()
    for row in rows:
        if row['day'] in tasks:
            tasks[row['day']].append({
                'id': row['id'],
                'name': row['name'],
                'done': bool(row['done'])
            })
    return tasks

@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        db = get_db()
        user = db.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
        
        if user and user['password'] == password:
            session['user'] = email
            flash('Successfully logged in!', 'success')
            return redirect(url_for('tracker'))
        else:
            flash('Invalid email or password', 'error')
            return render_template('login.html')
            
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        if password != confirm_password:
            flash('Passwords do not match.', 'error')
            return render_template('register.html')
            
        db = get_db()
        existing_user = db.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
        
        if existing_user:
            flash('Email already registered! Please log in.', 'error')
            return redirect(url_for('login'))
            
        # Save user to SQL database
        db.execute('INSERT INTO users (email, username, password) VALUES (?, ?, ?)', (email, username, password))
        db.commit()
        
        # Log them in automatically after registration
        session['user'] = email
        flash('Registration successful! Welcome to Tracker.', 'success')
        return redirect(url_for('tracker'))
        
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.pop('user', None)
    flash('You have been logged out.', 'success')
    return redirect(url_for('login'))

@app.route('/tracker')
def tracker():
    if 'user' not in session:
        flash('Please login to view your tracker.', 'error')
        return redirect(url_for('login'))
        
    user_tasks = get_user_tasks(session['user'])
    return render_template('tracker.html', tasks_data=user_tasks)

@app.route('/api/toggle_task', methods=['POST'])
def toggle_task():
    if 'user' not in session:
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401
        
    data = request.get_json()
    task_id = data.get('task_id')
    day = data.get('day')
    is_done = data.get('is_done')
    
    db = get_db()
    db.execute('UPDATE tasks SET done = ? WHERE id = ? AND user_email = ?', (1 if is_done else 0, task_id, session['user']))
    db.commit()
    
    user_tasks = get_user_tasks(session['user'])
    
    # Calculate stats for the chart
    days = list(user_tasks.keys())
    completion_rates = []
    
    for d in days:
        day_tasks = user_tasks[d]
        if len(day_tasks) == 0:
            completion_rates.append(0)
        else:
            completed = sum(1 for dt in day_tasks if dt['done'])
            completion_rates.append((completed / len(day_tasks)) * 100)
            
    return jsonify({
        'status': 'success',
        'days': days,
        'completion_rates': completion_rates
    })

@app.route('/api/add_task', methods=['POST'])
def add_task():
    if 'user' not in session:
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401
        
    data = request.get_json()
    day = data.get('day')
    task_name = data.get('task_name').strip() if data.get('task_name') else ''
    
    if not task_name:
        return jsonify({'status': 'error', 'message': 'Task name cannot be empty'}), 400
        
    if day in get_default_tasks().keys():
        new_id = uuid.uuid4().hex
        db = get_db()
        db.execute('INSERT INTO tasks (id, user_email, day, name, done) VALUES (?, ?, ?, ?, ?)', (new_id, session['user'], day, task_name, 0))
        db.commit()
        
        new_task = {
            'id': new_id,
            'name': task_name,
            'done': False
        }
        
        user_tasks = get_user_tasks(session['user'])
        
        # Calculate stats for the chart
        days = list(user_tasks.keys())
        completion_rates = []
        for d in days:
            day_tasks = user_tasks[d]
            if len(day_tasks) == 0:
                completion_rates.append(0)
            else:
                completed = sum(1 for dt in day_tasks if dt['done'])
                completion_rates.append((completed / len(day_tasks)) * 100)
                
        return jsonify({
            'status': 'success',
            'task': new_task,
            'days': days,
            'completion_rates': completion_rates
        })
    return jsonify({'status': 'error', 'message': 'Invalid day'}), 400

if __name__ == '__main__':
    app.run(debug=True, port=5000)
