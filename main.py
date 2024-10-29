from flask import Flask, render_template, request, redirect, flash, session
import psycopg2
from flask_bcrypt import Bcrypt
from flask_login import LoginManager, UserMixin, current_user, login_user, logout_user, login_required

# Flask application setup
app = Flask(__name__)
app.secret_key = 'management-system-123456'

# Setup bcrypt for hashing passwords
bcrypt = Bcrypt(app)

# Setup login manager for handling user sessions
login_manager = LoginManager(app)
login_manager.login_view = 'login'


def get_db_connection():
    """Establish and return a PostgreSQL database connection."""
    return psycopg2.connect(
        database="postgres",
        user="postgres",
        host="localhost",
        password="qwerty",
        port=5432
    )


def initialize_database():
    """Initialize required tables if they do not exist."""
    conn = get_db_connection()
    with conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id SERIAL PRIMARY KEY,
                    user_type INT CHECK (user_type IN (1, 2)) NOT NULL,
                    user_name VARCHAR(50) UNIQUE NOT NULL,
                    email VARCHAR(100) UNIQUE NOT NULL,
                    password VARCHAR(200) NOT NULL,
                    signed_in_time TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS student_teacher_assignment (
                    assignment_id SERIAL PRIMARY KEY,
                    student_id INT NOT NULL,
                    teacher_id INT NOT NULL,
                    is_assigned BOOLEAN DEFAULT TRUE,
                    FOREIGN KEY (student_id) REFERENCES users(user_id) ON DELETE CASCADE,
                    FOREIGN KEY (teacher_id) REFERENCES users(user_id) ON DELETE CASCADE,
                    UNIQUE (student_id, teacher_id)
                );
            """)
    conn.close()


class User(UserMixin):
    """User class for Flask-Login integration."""
    def __init__(self, id, name, email, user_type):
        self.id = id
        self.name = name
        self.email = email
        self.user_type = user_type


@login_manager.user_loader
def load_user(user_id):
    """Load user for login manager."""
    conn = get_db_connection()
    with conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
            user = cur.fetchone()
            if user:
                return User(id=user[0], name=user[2], email=user[3], user_type=user[1])
    return None


@app.route('/')
def index():
    """Homepage route."""
    return render_template('index.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    """User registration route."""
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        user_type = request.form['type']

        if password != confirm_password:
            flash("Passwords do not match", 'error')
            return render_template('register.html')

        conn = get_db_connection()
        with conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM users WHERE email = %s", (email,))
                if cur.fetchone():
                    flash('Email already exists.', 'error')
                    return render_template('register.html')

                hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
                cur.execute(
                    "INSERT INTO users (user_type, user_name, email, password) VALUES (%s, %s, %s, %s)",
                    (user_type, name, email, hashed_password)
                )
            flash('Registration successful! Please log in.', 'success')
            return redirect('/login')
    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    """User login route."""
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        conn = get_db_connection()
        with conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM users WHERE email = %s", (email,))
                user = cur.fetchone()
                if user and bcrypt.check_password_hash(user[4], password):
                    user_obj = User(id=user[0], name=user[2], email=user[3], user_type=user[1])
                    login_user(user_obj)
                    session['id'], session['user_name'] = user[0], user[2]
                    flash('Logged in successfully', 'success')
                    return redirect('/dashboard')
                flash('Invalid email or password', 'error')
    return render_template('login.html')


@app.route('/dashboard')
@login_required
def dashboard():
    """User dashboard route."""
    conn = get_db_connection()
    with conn:
        with conn.cursor() as cur:
            cur.execute("SELECT user_type FROM users WHERE user_id = %s", (current_user.id,))
            user_type = cur.fetchone()[0]
    return render_template('dashboard.html', user_type=user_type)


@app.route('/logout')
@login_required
def logout():
    """User logout route."""
    logout_user()
    session.clear()
    flash('You have been logged out', 'success')
    return redirect('/login')


@app.route('/assign-students', methods=['GET', 'POST'])
@login_required
def assign_students():
    """Assign students to the current teacher."""
    conn = get_db_connection()
    with conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT u.user_id, u.user_name, u.email
                FROM users u
                LEFT JOIN student_teacher_assignment sta ON u.user_id = sta.student_id AND sta.teacher_id = %s
                WHERE u.user_type = 1 AND sta.student_id IS NULL
            """, (current_user.id,))
            students = cur.fetchall()

        if request.method == 'POST':
            selected_student_ids = request.form.getlist('student_ids')
            with conn.cursor() as cur:
                for student_id in selected_student_ids:
                    cur.execute("""
                        INSERT INTO student_teacher_assignment (student_id, teacher_id)
                        VALUES (%s, %s)
                        ON CONFLICT (student_id, teacher_id) DO NOTHING
                    """, (student_id, current_user.id))
            conn.commit()
            flash('Students have been successfully assigned!', 'success')
            return redirect('/view-assigned-students')
    return render_template('assign-students.html', students=students)


@app.route('/view-assigned-students')
@login_required
def view_assigned_students():
    """View students assigned to the current teacher."""
    conn = get_db_connection()
    with conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT u.user_id, u.user_name, u.email
                FROM users u
                JOIN student_teacher_assignment sta ON u.user_id = sta.student_id
                WHERE sta.teacher_id = %s
            """, (current_user.id,))
            assigned_students = cur.fetchall()
    return render_template('view_assigned_students.html', assigned_students=assigned_students)


@app.route('/view-assigned-teachers')
@login_required
def view_assigned_teachers():
    """View teachers assigned to the current student."""
    conn = get_db_connection()
    with conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT u.user_id, u.user_name, u.email
                FROM users u
                JOIN student_teacher_assignment sta ON u.user_id = sta.teacher_id
                WHERE sta.student_id = %s
            """, (current_user.id,))
            assigned_teachers = cur.fetchall()
    return render_template('view_assigned_teachers.html', assigned_teachers=assigned_teachers)


@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    """User profile route."""
    conn = get_db_connection()
    with conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM users WHERE user_id = %s", (current_user.id,))
            user = cur.fetchone()

    user_data = {"name": user[2], "email": user[3]}
    
    if request.method == 'POST':
        name, email = request.form['name'], request.form['email']
        current_password, new_password = request.form['current_password'], request.form['new_password']

        if bcrypt.check_password_hash(user[4], current_password):
            hashed_password = bcrypt.generate_password_hash(new_password).decode('utf-8')
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE users SET user_name = %s, email = %s, password = %s WHERE user_id = %s",
                        (name, email, hashed_password, current_user.id)
                    )
                session['user_name'] = name
                flash('Profile updated successfully', 'success')
                return redirect('/dashboard')
        else:
            flash('Incorrect current password', 'error')
    return render_template('profile.html', user=user_data)


@app.route('/unassign-student/<int:student_id>', methods=['POST'])
@login_required
def unassign_student(student_id):
    """Unassign a student from the current teacher."""
    conn = get_db_connection()
    with conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM student_teacher_assignment WHERE student_id = %s AND teacher_id = %s",
                        (student_id, current_user.id))
        flash('Student has been unassigned successfully', 'success')
    return redirect('/view-assigned-students')


if __name__ == '__main__':
    initialize_database()
    app.run(debug=True)
