from flask import Flask, render_template, redirect, url_for, request, flash
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_socketio import SocketIO, send
from werkzeug.security import generate_password_hash
from models import User
from forms import RegisterForm, LoginForm
import sqlite3, os
from flask_socketio import SocketIO, send, emit, join_room, leave_room
from flask_login import current_user

online_users = set()

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret'
socketio = SocketIO(app)

login_manager = LoginManager(app)
login_manager.login_view = 'login'

# In-memory user store
def get_user_by_username(username):
    conn = sqlite3.connect("chat.db")
    cur = conn.cursor()
    cur.execute("SELECT id, username, password FROM users WHERE username = ?", (username,))
    row = cur.fetchone()
    conn.close()
    return User(*row) if row else None

def get_user_by_id(user_id):
    conn = sqlite3.connect("chat.db")
    cur = conn.cursor()
    cur.execute("SELECT id, username, password FROM users WHERE id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return User(*row) if row else None

@login_manager.user_loader
def load_user(user_id):
    return get_user_by_id(user_id)

@app.route("/")
def index():
    return redirect(url_for('chat'))

@app.route("/register", methods=["GET", "POST"])
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        conn = sqlite3.connect("chat.db")
        cur = conn.cursor()
        hashed_pw = generate_password_hash(form.password.data)
        try:
            cur.execute("INSERT INTO users (username, password) VALUES (?, ?)", (form.username.data, hashed_pw))
            conn.commit()
        except:
            flash("Username already taken.")
            return redirect(url_for('register'))
        conn.close()
        return redirect(url_for('login'))
    return render_template("register.html", form=form)

@app.route("/login", methods=["GET", "POST"])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = get_user_by_username(form.username.data)
        if user and user.check_password(form.password.data):
            login_user(user)
            return redirect(url_for("chat"))
        flash("Invalid credentials.")
    return render_template("login.html", form=form)

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))

@app.route("/chat")
@login_required
def chat():
    conn = sqlite3.connect("chat.db")
    cur = conn.cursor()
    cur.execute("SELECT username, message, timestamp FROM messages ORDER BY timestamp ASC")
    rows = cur.fetchall()
    conn.close()
    
    history = [f"{row[0]}: {row[1]}" for row in rows]
    return render_template("chat.html", username=current_user.username, history=history)

@socketio.on("connect")
def handle_connect():
    if current_user.is_authenticated:
        online_users.add(current_user.username)
        emit("user_list", list(online_users), broadcast=True)

@socketio.on("disconnect")
def handle_disconnect():
    if current_user.is_authenticated and current_user.username in online_users:
        online_users.remove(current_user.username)
        emit("user_list", list(online_users), broadcast=True)

@socketio.on("message")
def handle_message(msg):
    full_msg = f"{current_user.username}: {msg}"
    
    # Save to DB
    conn = sqlite3.connect("chat.db")
    cur = conn.cursor()
    cur.execute("INSERT INTO messages (username, message) VALUES (?, ?)", (current_user.username, msg))
    conn.commit()
    conn.close()
    
    # Broadcast to all
    send(full_msg, broadcast=True)

def init_db():
    if not os.path.exists("chat.db"):
        conn = sqlite3.connect("chat.db")
        cur = conn.cursor()
        cur.execute('''
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL
            )
        ''')
        cur.execute('''
            CREATE TABLE messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                message TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        conn.close()

if __name__ == "__main__":
    init_db()
    socketio.run(app, debug=True)
