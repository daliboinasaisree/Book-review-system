# Book Review Website

A simple online book review website built with Flask and SQLite.

## Features
- User registration and login
- Session management
- Add books with title, author, genre, and description
- Browse books with search, filter, and sort
- Book detail pages with reviews and average rating
- Logged-in users can add, edit, and delete their own reviews
- User dashboard to manage reviews

## Setup
1. Create a Python virtual environment:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

2. Install dependencies:

```powershell
pip install -r requirements.txt
```

3. Run the app:

```powershell
python app.py
```

4. Open `http://127.0.0.1:5000` in your browser.

## Notes
- The app uses SQLite (`book_review.db`) and initializes the database automatically.
- Set `SECRET_KEY` in your environment for production.
