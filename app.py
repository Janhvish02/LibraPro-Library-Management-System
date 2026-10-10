
from flask import Flask, render_template, request, redirect, url_for
import sqlite3
from datetime import date

app = Flask(__name__)

DATABASE = "library.db"
FINE_PER_DAY = 5


# ---------- DATABASE CONNECTION ----------

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


# ---------- FINE CALCULATION ----------

def calculate_fine(due_date, end_date):
    due = date.fromisoformat(due_date)
    end = date.fromisoformat(end_date)

    late_days = max(0, (end - due).days)
    fine = late_days * FINE_PER_DAY

    return late_days, fine


# ---------- CREATE TABLES ----------

def create_table():
    conn = get_db()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            book_name TEXT NOT NULL,
            author TEXT NOT NULL,
            quantity INTEGER NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_name TEXT NOT NULL,
            email TEXT NOT NULL,
            course TEXT NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS issued_books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            book_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            issue_date TEXT NOT NULL,
            due_date TEXT NOT NULL,
            return_date TEXT,
            status TEXT NOT NULL DEFAULT 'Issued'
        )
    """)

    conn.commit()
    conn.close()


create_table()


# ---------- DASHBOARD ----------

@app.route("/")
def home():
    conn = get_db()

    total_books = conn.execute(
        "SELECT COUNT(*) FROM books"
    ).fetchone()[0]

    total_quantity = conn.execute(
        "SELECT COALESCE(SUM(quantity), 0) FROM books"
    ).fetchone()[0]

    low_stock = conn.execute(
        "SELECT COUNT(*) FROM books WHERE quantity <= 2"
    ).fetchone()[0]

    total_students = conn.execute(
        "SELECT COUNT(*) FROM students"
    ).fetchone()[0]

    total_issued = conn.execute("""
        SELECT COUNT(*) FROM issued_books
        WHERE status = 'Issued'
    """).fetchone()[0]

    today = date.today().isoformat()

    overdue_books = conn.execute("""
        SELECT COUNT(*) FROM issued_books
        WHERE status = 'Issued' AND due_date < ?
    """, (today,)).fetchone()[0]

    conn.close()

    return render_template(
        "index.html",
        total_books=total_books,
        total_quantity=total_quantity,
        low_stock=low_stock,
        total_students=total_students,
        total_issued=total_issued,
        overdue_books=overdue_books
    )


# ---------- ADD BOOK ----------

@app.route("/add", methods=["GET", "POST"])
def add():
    if request.method == "POST":
        book_name = request.form.get("book_name", "").strip()
        author = request.form.get("author", "").strip()
        quantity_text = request.form.get("quantity", "").strip()

        if not book_name or not author or not quantity_text:
            return "Please fill in all book details.", 400

        try:
            quantity = int(quantity_text)
            if quantity < 0:
                return "Quantity cannot be negative.", 400
        except ValueError:
            return "Enter a valid quantity.", 400

        conn = get_db()
        conn.execute("""
            INSERT INTO books (book_name, author, quantity)
            VALUES (?, ?, ?)
        """, (book_name, author, quantity))

        conn.commit()
        conn.close()

        return redirect(url_for("view"))

    return render_template("add_book.html")


# ---------- VIEW AND SEARCH BOOKS ----------

@app.route("/view")
def view():
    query = request.args.get("q", "").strip()

    conn = get_db()
    books = conn.execute("""
        SELECT * FROM books
        WHERE book_name LIKE ? OR author LIKE ?
        ORDER BY id DESC
    """, (f"%{query}%", f"%{query}%")).fetchall()

    conn.close()

    return render_template(
        "view_books.html",
        books=books,
        search_query=query
    )


@app.route("/search")
def search():
    return redirect(url_for("view", q=request.args.get("q", "")))


# ---------- EDIT BOOK ----------

@app.route("/edit/<int:id>", methods=["GET", "POST"])
def edit(id):
    conn = get_db()

    book = conn.execute(
        "SELECT * FROM books WHERE id = ?", (id,)
    ).fetchone()

    if book is None:
        conn.close()
        return "Book not found.", 404

    if request.method == "POST":
        book_name = request.form.get("book_name", "").strip()
        author = request.form.get("author", "").strip()
        quantity_text = request.form.get("quantity", "").strip()

        if not book_name or not author or not quantity_text:
            conn.close()
            return "Please fill in all book details.", 400

        try:
            quantity = int(quantity_text)
            if quantity < 0:
                conn.close()
                return "Quantity cannot be negative.", 400
        except ValueError:
            conn.close()
            return "Enter a valid quantity.", 400

        active_loans = conn.execute("""
            SELECT COUNT(*) FROM issued_books
            WHERE book_id = ? AND status = 'Issued'
        """, (id,)).fetchone()[0]

        if quantity < active_loans:
            conn.close()
            return "Quantity cannot be less than currently issued copies.", 400

        conn.execute("""
            UPDATE books
            SET book_name = ?, author = ?, quantity = ?
            WHERE id = ?
        """, (book_name, author, quantity, id))

        conn.commit()
        conn.close()

        return redirect(url_for("view"))

    conn.close()
    return render_template("edit_book.html", book=book)


# ---------- DELETE BOOK ----------

@app.route("/delete/<int:id>", methods=["GET", "POST"])
def delete(id):
    conn = get_db()

    active_loans = conn.execute("""
        SELECT COUNT(*) FROM issued_books
        WHERE book_id = ? AND status = 'Issued'
    """, (id,)).fetchone()[0]

    if active_loans > 0:
        conn.close()
        return "Return this book before deleting it.", 400

    conn.execute("DELETE FROM books WHERE id = ?", (id,))
    conn.commit()
    conn.close()

    return redirect(url_for("view"))


# ---------- VIEW STUDENTS ----------

@app.route("/students")
def students():
    conn = get_db()

    student_list = conn.execute(
        "SELECT * FROM students ORDER BY id DESC"
    ).fetchall()

    conn.close()

    return render_template(
        "students.html",
        students=student_list
    )


# ---------- ADD STUDENT ----------

@app.route("/add_student", methods=["GET", "POST"])
def add_student():
    if request.method == "POST":
        student_name = request.form.get("student_name", "").strip()
        email = request.form.get("email", "").strip()
        course = request.form.get("course", "").strip()

        if not student_name or not email or not course:
            return "Please fill in all student details.", 400

        conn = get_db()
        conn.execute("""
            INSERT INTO students (student_name, email, course)
            VALUES (?, ?, ?)
        """, (student_name, email, course))

        conn.commit()
        conn.close()

        return redirect(url_for("students"))

    return render_template("add_student.html")


# ---------- EDIT STUDENT ----------

@app.route("/edit_student/<int:id>", methods=["GET", "POST"])
def edit_student(id):
    conn = get_db()

    student = conn.execute(
        "SELECT * FROM students WHERE id = ?", (id,)
    ).fetchone()

    if student is None:
        conn.close()
        return "Student not found.", 404

    if request.method == "POST":
        student_name = request.form.get("student_name", "").strip()
        email = request.form.get("email", "").strip()
        course = request.form.get("course", "").strip()

        if not student_name or not email or not course:
            conn.close()
            return "Please fill in all student details.", 400

        conn.execute("""
            UPDATE students
            SET student_name = ?, email = ?, course = ?
            WHERE id = ?
        """, (student_name, email, course, id))

        conn.commit()
        conn.close()

        return redirect(url_for("students"))

    conn.close()
    return render_template("edit_student.html", student=student)


# ---------- DELETE STUDENT ----------

@app.route("/delete_student/<int:id>", methods=["GET", "POST"])
def delete_student(id):
    conn = get_db()

    active_loans = conn.execute("""
        SELECT COUNT(*) FROM issued_books
        WHERE student_id = ? AND status = 'Issued'
    """, (id,)).fetchone()[0]

    if active_loans > 0:
        conn.close()
        return "Return this student's books before deleting.", 400

    conn.execute("DELETE FROM students WHERE id = ?", (id,))
    conn.commit()
    conn.close()

    return redirect(url_for("students"))


# ---------- ISSUE BOOK ----------

@app.route("/issue-books", methods=["GET", "POST"])
def issue_books():
    conn = get_db()

    if request.method == "POST":
        book_id = request.form.get("book_id", "").strip()
        student_id = request.form.get("student_id", "").strip()
        issue_date = request.form.get("issue_date", "").strip()
        due_date = request.form.get("due_date", "").strip()

        if not all([book_id, student_id, issue_date, due_date]):
            conn.close()
            return "Please fill in all issue details.", 400

        try:
            book_id = int(book_id)
            student_id = int(student_id)
            issue = date.fromisoformat(issue_date)
            due = date.fromisoformat(due_date)
        except (ValueError, TypeError):
            conn.close()
            return "Invalid book, student or date.", 400

        if due < issue:
            conn.close()
            return "Due date cannot be before issue date.", 400

        book = conn.execute(
            "SELECT * FROM books WHERE id = ?", (book_id,)
        ).fetchone()

        student = conn.execute(
            "SELECT * FROM students WHERE id = ?", (student_id,)
        ).fetchone()

        if book is None or student is None:
            conn.close()
            return "Selected book or student was not found.", 404

        if book["quantity"] <= 0:
            conn.close()
            return "No copies of this book are currently available.", 400

        conn.execute("""
            INSERT INTO issued_books
            (book_id, student_id, issue_date, due_date, status)
            VALUES (?, ?, ?, ?, 'Issued')
        """, (book_id, student_id, issue_date, due_date))

        conn.execute("""
            UPDATE books
            SET quantity = quantity - 1
            WHERE id = ? AND quantity > 0
        """, (book_id,))

        conn.commit()
        conn.close()

        return redirect(url_for("issued_books"))

    books = conn.execute("""
        SELECT * FROM books
        WHERE quantity > 0
        ORDER BY book_name
    """).fetchall()

    student_list = conn.execute("""
        SELECT * FROM students ORDER BY student_name
    """).fetchall()

    conn.close()

    return render_template(
        "issue_book.html",
        books=books,
        students=student_list
    )


# ---------- ISSUED BOOKS AND FINE ----------

@app.route("/issued-books")
def issued_books():
    conn = get_db()

    records = conn.execute("""
        SELECT
            issued_books.id,
            books.book_name,
            students.student_name,
            issued_books.issue_date,
            issued_books.due_date,
            issued_books.return_date,
            issued_books.status
        FROM issued_books
        JOIN books ON issued_books.book_id = books.id
        JOIN students ON issued_books.student_id = students.id
        ORDER BY issued_books.id DESC
    """).fetchall()

    conn.close()

    today = date.today().isoformat()
    updated_records = []
    total_fine = 0

    for record in records:
        item = dict(record)
        end_date = item["return_date"] or today

        late_days, fine = calculate_fine(
            item["due_date"], end_date
        )

        item["late_days"] = late_days
        item["fine"] = fine
        total_fine += fine
        updated_records.append(item)

    return render_template(
        "issued_books.html",
        records=updated_records,
        today_date=today,
        total_fine=total_fine
    )


# ---------- RETURN BOOK ----------

@app.route("/return-issued/<int:id>", methods=["POST"])
def return_issued(id):
    conn = get_db()

    record = conn.execute("""
        SELECT book_id, status
        FROM issued_books
        WHERE id = ?
    """, (id,)).fetchone()

    if record is None:
        conn.close()
        return "Issue record not found.", 404

    if record["status"] == "Issued":
        conn.execute("""
            UPDATE issued_books
            SET status = 'Returned', return_date = ?
            WHERE id = ?
        """, (date.today().isoformat(), id))

        conn.execute("""
            UPDATE books
            SET quantity = quantity + 1
            WHERE id = ?
        """, (record["book_id"],))

        conn.commit()

    conn.close()
    return redirect(url_for("issued_books"))


# ---------- OLD ROUTES ----------

@app.route("/issue/<int:id>")
def old_issue_route(id):
    return redirect(url_for("issue_books"))


@app.route("/return/<int:id>")
def old_return_route(id):
    return redirect(url_for("issued_books"))


# ---------- REPORTS ----------

@app.route("/reports")
def reports():
    conn = get_db()

    total_books = conn.execute(
        "SELECT COUNT(*) FROM books"
    ).fetchone()[0]

    total_quantity = conn.execute(
        "SELECT COALESCE(SUM(quantity), 0) FROM books"
    ).fetchone()[0]

    total_students = conn.execute(
        "SELECT COUNT(*) FROM students"
    ).fetchone()[0]

    total_issued = conn.execute("""
        SELECT COUNT(*) FROM issued_books
        WHERE status = 'Issued'
    """).fetchone()[0]

    today = date.today().isoformat()

    overdue_books = conn.execute("""
        SELECT COUNT(*) FROM issued_books
        WHERE status = 'Issued' AND due_date < ?
    """, (today,)).fetchone()[0]

    records = conn.execute("""
        SELECT due_date, return_date
        FROM issued_books
    """).fetchall()

    conn.close()

    total_fine = 0

    for record in records:
        end_date = record["return_date"] or today
        _, fine = calculate_fine(record["due_date"], end_date)
        total_fine += fine

    return render_template(
        "reports.html",
        total_books=total_books,
        total_quantity=total_quantity,
        total_students=total_students,
        total_issued=total_issued,
        overdue_books=overdue_books,
        total_fine=total_fine,
        today_date=today
    )


# ---------- RUN APPLICATION ----------

if __name__ == "__main__":
    app.run(debug=True)
