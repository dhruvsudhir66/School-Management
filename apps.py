from flask import Flask, render_template, request, redirect, flash, session
import psycopg2
from flask_bcrypt import Bcrypt
from flask_login import LoginManager, UserMixin, current_user, login_user, logout_user, login_required

# app setup
app = Flask(__name__)

app.secret_key = 'management-system-123456' # secret key

bcrypt = Bcrypt(app)  # bcrypt setup

login_manager = LoginManager()
login_manager = LoginManager(app)
login_manager.login_view = 'login' 


def get_db_connection():  # postgres database connection
    return psycopg2.connect(
        database="postgres",
        user="postgres",
        host="localhost",
        password="qwerty",
        port=5432
    )


class User(UserMixin):  # user class
    def __init__(self, id, name, email, user_type):
        self.id = id
        self.name = name
        self.email = email
        self.user_type = user_type


@login_manager.user_loader
def load_user(user_id):
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Check in the users table
    cur.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
    user = cur.fetchone()
    
    if user:
        user_type = user[1]  # Assuming user_type is in the second column
        return User(id=user[0], name=user[2], email=user[3], user_type=user_type)

    return None
    

conn = get_db_connection()  # database connection
cur = conn.cursor()

cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id SERIAL PRIMARY KEY,
        user_type INT CHECK (user_type IN (1, 2)) NOT NULL,  -- 1 for student, 2 for teacher
        user_name VARCHAR(50) UNIQUE NOT NULL,
        email VARCHAR(100) UNIQUE NOT NULL,
        password VARCHAR(200) NOT NULL,
        signed_in_time TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP  -- Store the time user signed in
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
        UNIQUE (student_id, teacher_id)  -- Prevent duplicate assignments
    );
""")

conn.commit()
cur.close()
conn.close()


@app.route('/')
def index():
    return render_template('index.html')


"""Registration"""

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        user_type = request.form['type']
        
        if password == confirm_password:
            conn = get_db_connection()
            cur = conn.cursor()
            
            try:
                cur.execute("SELECT * FROM users WHERE email = %s", (email,))
                existing_user = cur.fetchone()
                
                if existing_user:
                    if user_type == "1":
                        flash('Email already exists.')
                    elif user_type == "2":
                        flash('Email already exists.')
                    return render_template('register.html')
                
                hashed_password = bcrypt.generate_password_hash(password).decode('utf-8') 
                
                cur.execute(
                    "INSERT INTO users (user_type, user_name, email, password) VALUES (%s, %s, %s, %s)", 
                    (user_type, name, email, hashed_password)
                )
                
                conn.commit()
                flash('Registration successful! Please log in.', 'success')
                return render_template('login.html')
            
            except psycopg2.Error as e:
                print(f"Error: {e}")
                flash(f"Error: {str(e)}", 'error')
                return render_template('register.html')
            finally:
                cur.close()
                conn.close()
            
    return render_template('register.html')


"""Login"""

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        conn = get_db_connection()
        cur = conn.cursor()

        # Check in the users table
        cur.execute("SELECT * FROM users WHERE email = %s", (email,))
        user = cur.fetchone()
        
        if user:
            # Check the hashed password
            if bcrypt.check_password_hash(user[4], password):  # Assuming the hashed password is in the 5th column
                user_type = user[1]  # Assuming user_type is the second column
                user_obj = User(id=user[0], name=user[2], email=user[3], user_type=user_type)  # Adjust indexing as necessary
                login_user(user_obj)  # Log in the user

                # Store user info in session
                session['id'] = user[0]  # Assuming name is the 3rd column
                session['user_name'] = user[2]
                flash('Logged in successfully', 'success')
                return redirect('/dashboard')  # Redirect to dashboard or another page
            else:
                flash('Invalid email or password', 'error')
        else:
            flash('Invalid email or password', 'error')

        cur.close()
        conn.close()

    return render_template('login.html')


"""Dashboard"""

@app.route('/dashboard')
@login_required
def dashboard():
    
    id = session['id']  # user id
    
    cur = get_db_connection().cursor()
    cur.execute("SELECT * FROM users WHERE user_id = %s", (id,))
    user = cur.fetchone()
    cur.close()
    
    return render_template('dashboard.html', user_type=user[1])


"""Logout"""

@app.route('/logout')
@login_required
def logout():
    logout_user()
    session.pop('id', None)  # Remove id from session
    session.pop('user_name', None)  # Remove user_name from session
    flash('You have been logged out', 'success')
    return redirect('/login')


@app.route('/assign-students', methods=['GET', 'POST'])
@login_required
def assign_students():
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Fetch students who are not assigned to the current teacher
    cur.execute("""
        SELECT u.user_id, u.user_name, u.email
        FROM users u
        LEFT JOIN student_teacher_assignment sta ON u.user_id = sta.student_id AND sta.teacher_id = %s
        WHERE u.user_type = 1 AND sta.student_id IS NULL
    """, (current_user.id,))
    
    students = cur.fetchall()
    cur.close()
    conn.close()
    
    if request.method == 'POST':
        teacher_id = current_user.id
        selected_student_ids = request.form.getlist('student_ids')
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        try:
            for student_id in selected_student_ids:
                cur.execute("""
                    INSERT INTO student_teacher_assignment (student_id, teacher_id)
                    VALUES (%s, %s)
                    ON CONFLICT (student_id, teacher_id) DO NOTHING  -- Prevent duplicate assignments
                """, (student_id, teacher_id))

            conn.commit()
            flash('Student have been successfully assigned!', 'success')
            return redirect('/view-assigned-students')

        except psycopg2.Error as e:
            print(f"Error: {e}")
            flash('An error occurred while assigning students. Please try again.', 'error')
        finally:
            cur.close()
            conn.close()
        
    return render_template('assign-students.html', students=students)

@app.route('/view-assigned-students', methods=['GET'])
@login_required
def view_assigned_students():
    conn = get_db_connection()
    cur = conn.cursor()

    # Fetch assigned students for the current teacher
    cur.execute("""
        SELECT u.user_id, u.user_name, u.email
        FROM users u
        JOIN student_teacher_assignment sta ON u.user_id = sta.student_id
        WHERE sta.teacher_id = %s
    """, (current_user.id,))

    assigned_students = cur.fetchall()
    cur.close()
    conn.close()
    
    return render_template('view_assigned_students.html', assigned_students=assigned_students)

@app.route('/view-assigned-teachers', methods=['GET'])
@login_required
def view_assigned_teachers():
    conn = get_db_connection()
    cur = conn.cursor()

    # Fetch assigned teachers for the current student
    cur.execute("""
        SELECT u.user_id, u.user_name, u.email
        FROM users u
        JOIN student_teacher_assignment sta ON u.user_id = sta.teacher_id
        WHERE sta.student_id = %s
    """, (current_user.id,))

    assigned_teachers = cur.fetchall()
    cur.close()
    conn.close()
    
    return render_template('view_assigned_teachers.html', assigned_teachers=assigned_teachers)


@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    
    user_id = session['id']
    cur = get_db_connection().cursor()
    cur.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
    user = cur.fetchone()
    cur.close()
    
    user_data = {
        "name": user[2],
        "email": user[3]
    }
    
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        current_password = request.form['current_password']
        
        if bcrypt.check_password_hash(user[4], current_password):
            print("cp1")
            hashed_password = bcrypt.generate_password_hash(request.form['new_password']).decode('utf-8')
            
            conn = get_db_connection()
            cur = conn.cursor()
            
            try:
                cur.execute(
                    "UPDATE users SET user_name = %s, email = %s, password = %s WHERE user_id = %s", 
                    (name, email, hashed_password, user_id)
                )
                conn.commit()
                
                session['user_name'] = name # update session
                
                
                flash('Profile updated successfully', 'success')
                return redirect('/profile')
            except psycopg2.Error as e:
                print(f"Error: {e}")
                flash('An error occurred while updating the profile. Please try again.', 'error')
            finally:
                cur.close()
                conn.close()
    
    return render_template('profile.html', user=user_data)

@app.route('/unassign-student/<int:student_id>', methods=['POST'])
@login_required
def unassign_student(student_id):
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        cur.execute("DELETE FROM student_teacher_assignment WHERE student_id = %s AND teacher_id = %s", (student_id, current_user.id))
        conn.commit()
        flash('Student has been successfully unassigned!', 'success')
        return redirect('/view-assigned-students')
    except psycopg2.Error as e:
        print(f"Error: {e}")
        flash('An error occurred while unassigning the student. Please try again.', 'error')
    finally:
        cur.close()
        conn.close()
    
    return redirect('/view-assigned-students')



if __name__ == '__main__':
    app.run(debug=True)