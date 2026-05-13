import os
import sqlite3
from flask import Flask, g, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, 'book_review.db')
SECRET_KEY = os.environ.get('SECRET_KEY', 'replace-with-a-secure-secret')

app = Flask(__name__)
app.config['SECRET_KEY'] = SECRET_KEY

GENRES = ['Fiction', 'Nonfiction', 'Mystery', 'Sci-Fi', 'Fantasy', 'Romance', 'Biography', 'History', 'Children']


def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db


def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()


@app.teardown_appcontext
def teardown_db(exception):
    close_db(exception)


def init_db():
    db = get_db()
    db.executescript(
        '''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            author TEXT NOT NULL,
            genre TEXT NOT NULL,
            description TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            book_id INTEGER NOT NULL,
            rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
            content TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE
        );
        '''
    )
    db.commit()


@app.before_request
def load_current_user():
    g.user = None
    user_id = session.get('user_id')
    if user_id:
        db = get_db()
        g.user = db.execute('SELECT id, username, email FROM users WHERE id = ?', (user_id,)).fetchone()


@app.route('/')
def home():
    return redirect(url_for('books'))


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username'].strip()
        email = request.form['email'].strip().lower()
        password = request.form['password']
        if not username or not email or not password:
            flash('All fields are required.', 'error')
        else:
            db = get_db()
            try:
                db.execute(
                    'INSERT INTO users (username, email, password) VALUES (?, ?, ?)',
                    (username, email, generate_password_hash(password))
                )
                db.commit()
                flash('Registration successful. Please log in.', 'success')
                return redirect(url_for('login'))
            except sqlite3.IntegrityError:
                flash('Username or email already exists.', 'error')
    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        password = request.form['password']
        db = get_db()
        user = db.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
        if user and check_password_hash(user['password'], password):
            session.clear()
            session['user_id'] = user['id']
            flash(f'Welcome back, {user["username"]}!', 'success')
            return redirect(url_for('books'))
        flash('Invalid email or password.', 'error')
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))


def build_book_query(search, genre, min_rating, sort_by):
    conditions = []
    params = []

    if search:
        conditions.append('(title LIKE ? OR author LIKE ? )')
        params.extend([f'%{search}%', f'%{search}%'])
    if genre and genre != 'All':
        conditions.append('genre = ?')
        params.append(genre)

    where_clause = 'WHERE ' + ' AND '.join(conditions) if conditions else ''
    order_by = 'books.created_at DESC'
    if sort_by == 'rating':
        order_by = 'average_rating IS NULL, average_rating DESC'
    elif sort_by == 'popularity':
        order_by = 'review_count DESC'

    rating_filter = ''
    if min_rating:
        rating_filter = 'HAVING AVG(reviews.rating) >= ?'
        params.append(int(min_rating))

    query = f'''
        SELECT books.*, 
               COUNT(reviews.id) AS review_count,
               ROUND(AVG(reviews.rating), 1) AS average_rating
        FROM books
        LEFT JOIN reviews ON books.id = reviews.book_id
        {where_clause}
        GROUP BY books.id
        {rating_filter}
        ORDER BY {order_by}
    '''
    return query, params


@app.route('/books')
def books():
    search = request.args.get('search', '').strip()
    genre = request.args.get('genre', 'All')
    min_rating = request.args.get('rating', '')
    sort_by = request.args.get('sort', 'newest')

    db = get_db()
    query, params = build_book_query(search, genre, min_rating, sort_by)
    books = db.execute(query, params).fetchall()

    return render_template(
        'books.html',
        books=books,
        genres=['All'] + GENRES,
        selected_genre=genre,
        search=search,
        min_rating=min_rating,
        sort_by=sort_by
    )


@app.route('/book/add', methods=['GET', 'POST'])
def add_book():
    if not g.user:
        return redirect(url_for('login'))
    if request.method == 'POST':
        title = request.form['title'].strip()
        author = request.form['author'].strip()
        genre = request.form['genre']
        description = request.form['description'].strip()
        if not title or not author or not genre or not description:
            flash('All book fields are required.', 'error')
        else:
            db = get_db()
            db.execute(
                'INSERT INTO books (title, author, genre, description) VALUES (?, ?, ?, ?)',
                (title, author, genre, description)
            )
            db.commit()
            flash(f'Book "{title}" added successfully.', 'success')
            return redirect(url_for('books'))
    return render_template('add_book.html', genres=GENRES)


@app.route('/book/<int:book_id>', methods=['GET', 'POST'])
def book_detail(book_id):
    db = get_db()
    book = db.execute('SELECT * FROM books WHERE id = ?', (book_id,)).fetchone()
    if not book:
        flash('Book not found.', 'error')
        return redirect(url_for('books'))

    if request.method == 'POST':
        if not g.user:
            return redirect(url_for('login'))
        rating = int(request.form['rating'])
        content = request.form['content'].strip()
        existing = db.execute(
            'SELECT * FROM reviews WHERE user_id = ? AND book_id = ?',
            (g.user['id'], book_id)
        ).fetchone()
        if not content or rating < 1 or rating > 5:
            flash('Review and rating are required.', 'error')
        elif existing:
            flash('You already submitted a review for this book. Edit it from your dashboard.', 'info')
        else:
            db.execute(
                'INSERT INTO reviews (user_id, book_id, rating, content) VALUES (?, ?, ?, ?)',
                (g.user['id'], book_id, rating, content)
            )
            db.commit()
            flash('Review added successfully.', 'success')
            return redirect(url_for('book_detail', book_id=book_id))

    reviews = db.execute(
        '''
        SELECT reviews.*, users.username
        FROM reviews
        JOIN users ON reviews.user_id = users.id
        WHERE book_id = ?
        ORDER BY reviews.created_at DESC
        ''',
        (book_id,)
    ).fetchall()
    stats = db.execute(
        '''
        SELECT COUNT(*) AS review_count, ROUND(AVG(rating), 1) AS average_rating
        FROM reviews
        WHERE book_id = ?
        ''',
        (book_id,)
    ).fetchone()
    return render_template('book_detail.html', book=book, reviews=reviews, stats=stats)


@app.route('/review/edit/<int:review_id>', methods=['GET', 'POST'])
def edit_review(review_id):
    if not g.user:
        return redirect(url_for('login'))
    db = get_db()
    review = db.execute('SELECT * FROM reviews WHERE id = ?', (review_id,)).fetchone()
    if not review or review['user_id'] != g.user['id']:
        flash('Review not found or access denied.', 'error')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        rating = int(request.form['rating'])
        content = request.form['content'].strip()
        if not content or rating < 1 or rating > 5:
            flash('Valid rating and review text are required.', 'error')
        else:
            db.execute(
                'UPDATE reviews SET rating = ?, content = ? WHERE id = ?',
                (rating, content, review_id)
            )
            db.commit()
            flash('Review updated successfully.', 'success')
            return redirect(url_for('dashboard'))

    return render_template('edit_review.html', review=review)


@app.route('/review/delete/<int:review_id>', methods=['POST'])
def delete_review(review_id):
    if not g.user:
        return redirect(url_for('login'))
    db = get_db()
    review = db.execute('SELECT * FROM reviews WHERE id = ?', (review_id,)).fetchone()
    if review and review['user_id'] == g.user['id']:
        db.execute('DELETE FROM reviews WHERE id = ?', (review_id,))
        db.commit()
        flash('Review deleted successfully.', 'success')
    else:
        flash('Review deletion failed or access denied.', 'error')
    return redirect(url_for('dashboard'))


@app.route('/dashboard')
def dashboard():
    if not g.user:
        return redirect(url_for('login'))
    db = get_db()
    reviews = db.execute(
        '''
        SELECT reviews.*, books.title AS book_title, books.id AS book_id
        FROM reviews
        JOIN books ON books.id = reviews.book_id
        WHERE reviews.user_id = ?
        ORDER BY reviews.created_at DESC
        ''',
        (g.user['id'],)
    ).fetchall()
    return render_template('dashboard.html', reviews=reviews)


if __name__ == '__main__':
    with app.app_context():
        init_db()
    app.run(debug=True)
