# aws_app.py
from flask import Flask, render_template, request, redirect, flash, session, url_for
from datetime import datetime
import boto3
import uuid
import threading
import webbrowser

app = Flask(__name__)
app.secret_key = 'aws_secret_key_here'

# AWS Configuration
AWS_REGION = 'us-east-1'
USERS_TABLE = 'fixitnow_user'
BOOKINGS_TABLE = 'fixitnow_service'
SNS_TOPIC_ARN = "arn:aws:sns:us-east-1:145023099836:MovieTicketNotifications:b094f83f-6707-411e-962e-2ad0549a0a98"

dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
sns_client = boto3.client('sns', region_name=AWS_REGION)

users_table = dynamodb.Table(USERS_TABLE)
bookings_table = dynamodb.Table(BOOKINGS_TABLE)
# Movie Data (Static / In-Memory)
# ----------------------------
movies = [
    {'id': 1, 'title': 'KUBERA', 'price': 150, 'poster_url': '/static/kubera.jpg'},
    {'id': 2, 'title': 'BHAIRAVAM', 'price': 180, 'poster_url': '/static/bhairavam.jpg'},
    {'id': 3, 'title': 'BILLA', 'price': 200, 'poster_url': '/static/billa.jpg'},
     {'id': 4, 'title': 'MASTER', 'price':160 , 'poster_url': '/static/master.jpg'},
      {'id': 5, 'title': 'VINGIN BOYS', 'price': 250, 'poster_url': '/static/virgin boys.jpg'},
       {'id': 6, 'title': 'JURRASIC WORLD 3D', 'price': 300, 'poster_url': '/static/jurrasic world 3d.jpg'},
]



# ----------------------------
# Utilities
# ----------------------------
def logged_in():
    return 'user_email' in session

def get_movie_by_id(movie_id):
    return next((m for m in movies if m['id'] == movie_id), None)

# ----------------------------
# Routes
# ----------------------------
@app.route('/')
def index():
    return redirect(url_for('movies_list')) if logged_in() else render_template('index.html')

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if logged_in():
        return redirect(url_for('movies_list'))

    if request.method == 'POST':
        name = request.form['name'].strip()
        email = request.form['email'].strip().lower()
        password = request.form['password']

        if not name or not email or not password:
            flash('Please fill out all fields.')
            return render_template('register.html')

        if User.query.get(email):
            flash('Email already registered.')
            return render_template('register.html')

        new_user = User(email=email, name=name, password=password)
        db.session.add(new_user)
        db.session.commit()
        flash('Registration successful! Please login.')
        return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if logged_in():
        return redirect(url_for('movies_list'))

    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        password = request.form['password']
        user = User.query.get(email)

        if user and user.password == password:
            session['user_email'] = email
            flash(f'Welcome back, {user.name}!')
            return redirect(url_for('movies_list'))
        else:
            flash('Invalid email or password.')
            return render_template('login.html')

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user_email', None)
    flash('Logged out successfully.')
    return redirect(url_for('index'))

@app.route('/movies')
def movies_list():
    if not logged_in():
        return redirect(url_for('login'))
    return render_template('movies.html', movies=movies)

@app.route('/book/<int:movie_id>', methods=['GET', 'POST'])
def book_movie(movie_id):
    if not logged_in():
        return redirect(url_for('login'))

    movie = get_movie_by_id(movie_id)
    if not movie:
        flash("Movie not found.")
        return redirect(url_for('movies_list'))

    # Check existing bookings
    booked_seats = []
    existing = Booking.query.filter_by(movie=movie['title']).all()
    for b in existing:
        booked_seats.extend([s.strip() for s in b.seats.split(',')])

    if request.method == 'POST':
        seats_input = request.form.get('seats', '')
        theater = request.form.get('theater', 'Main Hall')
        time = request.form.get('time', '7:00 PM')
        seats_list = [s.strip() for s in seats_input.split(',') if s.strip()]

        for seat in seats_list:
            if seat in booked_seats:
                flash(f"Seat {seat} is already booked.")
                return render_template('book.html', movie=movie, booked_seats=booked_seats)

        total = movie['price'] * len(seats_list)
        new_booking = Booking(
            user_email=session['user_email'],
            movie=movie['title'],
            theater=theater,
            time=time,
            seats=', '.join(seats_list),
            price=movie['price'],
            total_price=total
        )
        db.session.add(new_booking)
        db.session.commit()
        flash("Booking successful!")
        return render_template('booking_confirmed.html', movie=movie, seats=new_booking.seats)

    return render_template('book.html', movie=movie, booked_seats=booked_seats)

@app.route('/dashboard')
def dashboard():
    if not logged_in():
        return redirect(url_for('login'))
    user_email = session['user_email']
    tickets = Booking.query.filter_by(user_email=user_email).all()
    return render_template('tickets.html', tickets=tickets)

@app.route('/services')
def services():
    return render_template('services.html')

# ----------------------------
# Start the App and Initialize DB
# ----------------------------

def sanitize_bad_booking_dates():
    from sqlalchemy import text

    print("🔄 Fixing bad booking_date entries...")
    with db.engine.begin() as conn:
        result = conn.execute(text("SELECT booking_id, booking_date FROM bookings"))
        for booking_id, date_str in result:
            if isinstance(date_str, str):
                try:
                    # Try to parse non-ISO format: '15-07-2025 15:03'
                    dt = datetime.strptime(date_str, "%d-%m-%Y %H:%M")
                    iso_format = dt.isoformat()

                    # Update to correct ISO format
                    conn.execute(text("""
                        UPDATE bookings 
                        SET booking_date = :fixed 
                        WHERE booking_id = :bid
                    """), {"fixed": iso_format, "bid": booking_id})

                    print(f"✅ Fixed booking_id: {booking_id}")
                except ValueError:
                    print(f"❌ Skipped invalid format in booking_id: {booking_id}")

def open_browser():
    webbrowser.open("http://127.0.0.1:5000/")

if __name__ == '__main__':
    threading.Timer(1.25, open_browser).start()
    app.run(debug=True, host='0.0.0.0', port=5000)
