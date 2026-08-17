from flask import Flask, render_template, request, redirect, flash, session, send_file, g
import mysql.connector
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
import io
import os
from dotenv import load_dotenv
load_dotenv()


# ============================================================
# FLASK APPLICATION
# ============================================================

app = Flask(__name__)

app.secret_key = os.getenv("SECRET_KEY")


# ============================================================
# MYSQL DATABASE CONNECTION
# ============================================================

def get_db_connection():
    return mysql.connector.connect(
        host=os.getenv("MYSQLHOST") or os.getenv("MYSQL_HOST"),
        port=int(os.getenv("MYSQLPORT", "3306")),
        user=os.getenv("MYSQLUSER") or os.getenv("MYSQL_USER"),
        password=os.getenv("MYSQLPASSWORD") or os.getenv("MYSQL_PASSWORD"),
        database=os.getenv("MYSQLDATABASE") or os.getenv("MYSQL_DATABASE"),
        connection_timeout=10
    )


# ============================================================
# DATABASE CONNECTION PER REQUEST
# ============================================================

@app.before_request
def open_db_connection():
    # Login creates its own connection so database errors can be
    # handled inside the login route.
    if request.endpoint in ("login", "logout"):
        return

    g.db = get_db_connection()


@app.teardown_request
def close_db_connection(exception=None):
    db = g.pop("db", None)

    if db and db.is_connected():
        db.close()


# ============================================================
# LOGIN REQUIRED
# ============================================================

def login_required():
    return "user_id" in session


# ============================================================
# LOGIN
# ============================================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        db = None
        cursor = None

        try:
            db = get_db_connection()
            cursor = db.cursor()

            cursor.execute("""
                SELECT user_id, username
                FROM users
                WHERE username = %s AND password = %s
            """, (username, password))

            user = cursor.fetchone()

            if user:
                session["user_id"] = user[0]
                session["username"] = user[1]

                return redirect("/")

            return render_template(
                "login.html",
                error="Invalid username or password"
            )

        except mysql.connector.Error as e:
            print("MySQL Error:", e)

            return render_template(
                "login.html",
                error="Database connection error. Please try again."
            )

        finally:
            if cursor:
                cursor.close()

            if db and db.is_connected():
                db.close()

    return render_template("login.html")
# LOGOUT
# ============================================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect("/login")


# ============================================================
# DASHBOARD
# ============================================================

@app.route("/")
def index():

    if not login_required():
        return redirect("/login")

    cursor = g.db.cursor()

    cursor.execute("""
        SELECT COUNT(*)
        FROM equipment
    """)
    total_equipment = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*)
        FROM equipment
        WHERE LOWER(status) = 'available'
    """)
    available_equipment = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*)
        FROM equipment
        WHERE LOWER(status) = 'under repair'
    """)
    under_repair = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*)
        FROM vendors
    """)
    total_vendors = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*)
        FROM quotations
    """)
    total_quotations = cursor.fetchone()[0]

    cursor.execute("""
        SELECT *
        FROM equipment
        ORDER BY id DESC
        LIMIT 5
    """)
    recent_equipment = cursor.fetchall()

    cursor.execute("""
        SELECT *
        FROM equipment
        WHERE quantity <= 2
        ORDER BY quantity ASC
    """)
    low_stock_equipment = cursor.fetchall()

    cursor.close()

    return render_template(
        "index.html",
        total_equipment=total_equipment,
        available_equipment=available_equipment,
        under_repair=under_repair,
        total_vendors=total_vendors,
        total_quotations=total_quotations,
        recent_equipment=recent_equipment,
        low_stock_equipment=low_stock_equipment
    )


# ============================================================
# VIEW EQUIPMENT
# ============================================================

@app.route("/view")
def view_equipment():

    if not login_required():
        return redirect("/login")

    cursor = g.db.cursor()

    cursor.execute("""
        SELECT *
        FROM equipment
        ORDER BY id DESC
    """)

    equipment = cursor.fetchall()

    cursor.close()

    return render_template(
        "inventory.html",
        equipment=equipment
    )


# ============================================================
# EQUIPMENT DETAILS
# ============================================================

@app.route("/equipment/<int:equipment_id>")
def equipment_details(equipment_id):

    if not login_required():
        return redirect("/login")

    cursor = g.db.cursor()

    cursor.execute("""
        SELECT *
        FROM equipment
        WHERE id = %s
    """, (equipment_id,))

    equipment = cursor.fetchone()

    cursor.close()

    if equipment is None:
        return "Equipment not found", 404

    return render_template(
        "equipment_details.html",
        equipment=equipment
    )


# ============================================================
# ADD EQUIPMENT
# ============================================================

@app.route("/add", methods=["GET", "POST"])
def add_equipment():

    if not login_required():
        return redirect("/login")

    if request.method == "POST":

        equipment_name = request.form.get(
            "equipment_name", ""
        ).strip()

        model = request.form.get(
            "model", ""
        ).strip()

        quantity = request.form.get(
            "quantity", ""
        ).strip()

        location = request.form.get(
            "location", ""
        ).strip()

        status = request.form.get(
            "status", ""
        ).strip()

        vendor = request.form.get(
            "vendor", ""
        ).strip()

        if (
            not equipment_name
            or not model
            or not quantity
            or not location
            or not status
            or not vendor
        ):

            flash(
                "Please fill all fields.",
                "error"
            )

            return redirect("/add")

        try:

            quantity = int(quantity)

            if quantity <= 0:
                raise ValueError

        except ValueError:

            flash(
                "Quantity must be a positive number.",
                "error"
            )

            return redirect("/add")

        cursor = g.db.cursor()

        cursor.execute("""
            INSERT INTO equipment
            (
                equipment_name,
                model,
                quantity,
                location,
                status,
                vendor
            )
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            equipment_name,
            model,
            quantity,
            location,
            status,
            vendor
        ))

        g.db.commit()
        cursor.close()

        flash(
            "Equipment added successfully!",
            "success"
        )

        return redirect("/")

    return render_template("add.html")


# ============================================================
# UPDATE EQUIPMENT
# ============================================================

@app.route("/update/<int:equipment_id>", methods=["GET", "POST"])
def update_equipment(equipment_id):

    if not login_required():
        return redirect("/login")

    cursor = g.db.cursor()

    if request.method == "POST":

        equipment_name = request.form.get(
            "equipment_name", ""
        ).strip()

        model = request.form.get(
            "model", ""
        ).strip()

        quantity = request.form.get(
            "quantity", ""
        ).strip()

        location = request.form.get(
            "location", ""
        ).strip()

        status = request.form.get(
            "status", ""
        ).strip()

        vendor = request.form.get(
            "vendor", ""
        ).strip()

        if (
            not equipment_name
            or not model
            or not quantity
            or not location
            or not status
            or not vendor
        ):

            cursor.close()

            flash(
                "Please fill all fields.",
                "error"
            )

            return redirect(
                f"/update/{equipment_id}"
            )

        try:

            quantity = int(quantity)

            if quantity <= 0:
                raise ValueError

        except ValueError:

            cursor.close()

            flash(
                "Quantity must be a positive number.",
                "error"
            )

            return redirect(
                f"/update/{equipment_id}"
            )

        cursor.execute("""
            UPDATE equipment
            SET
                equipment_name = %s,
                model = %s,
                quantity = %s,
                location = %s,
                status = %s,
                vendor = %s
            WHERE id = %s
        """, (
            equipment_name,
            model,
            quantity,
            location,
            status,
            vendor,
            equipment_id
        ))

        g.db.commit()
        cursor.close()

        flash(
            "Equipment updated successfully!",
            "success"
        )

        return redirect("/view")

    cursor.execute("""
        SELECT *
        FROM equipment
        WHERE id = %s
    """, (equipment_id,))

    equipment = cursor.fetchone()

    cursor.close()

    if equipment is None:
        return "Equipment not found", 404

    return render_template(
        "update.html",
        equipment=equipment
    )


# ============================================================
# DELETE EQUIPMENT
# ============================================================

@app.route("/delete/<int:equipment_id>")
def delete_equipment(equipment_id):

    if not login_required():
        return redirect("/login")

    cursor = g.db.cursor()

    cursor.execute("""
        DELETE FROM equipment
        WHERE id = %s
    """, (equipment_id,))

    g.db.commit()
    cursor.close()

    flash(
        "Equipment deleted successfully!",
        "success"
    )

    return redirect("/view")


# ============================================================
# SEARCH EQUIPMENT
# ============================================================

@app.route("/search")
def search_equipment():

    if not login_required():
        return redirect("/login")

    query = request.args.get(
        "query", ""
    ).strip()

    cursor = g.db.cursor()

    if query:

        search_value = "%" + query + "%"

        cursor.execute("""
            SELECT *
            FROM equipment
            WHERE
                equipment_name LIKE %s
                OR model LIKE %s
                OR location LIKE %s
                OR status LIKE %s
                OR vendor LIKE %s
            ORDER BY id DESC
        """, (
            search_value,
            search_value,
            search_value,
            search_value,
            search_value
        ))

    else:

        cursor.execute("""
            SELECT *
            FROM equipment
            ORDER BY id DESC
        """)

    equipment = cursor.fetchall()

    cursor.close()

    return render_template(
        "inventory.html",
        equipment=equipment
    )


# ============================================================
# VENDORS
# ============================================================

@app.route("/vendors")
def vendors():

    if not login_required():
        return redirect("/login")

    cursor = g.db.cursor()

    cursor.execute("""
        SELECT *
        FROM vendors
        ORDER BY vendor_id DESC
    """)

    vendor_list = cursor.fetchall()

    cursor.close()

    return render_template(
        "vendors.html",
        vendors=vendor_list
    )


# ============================================================
# ADD VENDOR
# ============================================================

@app.route("/add_vendor", methods=["GET", "POST"])
def add_vendor():

    if not login_required():
        return redirect("/login")

    if request.method == "POST":

        vendor_name = request.form.get(
            "vendor_name", ""
        ).strip()

        contact_person = request.form.get(
            "contact_person", ""
        ).strip()

        phone = request.form.get(
            "phone", ""
        ).strip()

        email = request.form.get(
            "email", ""
        ).strip()

        address = request.form.get(
            "address", ""
        ).strip()

        if not vendor_name:

            flash(
                "Vendor name is required.",
                "error"
            )

            return redirect("/add_vendor")

        cursor = g.db.cursor()

        cursor.execute("""
            INSERT INTO vendors
            (
                vendor_name,
                contact_person,
                phone,
                email,
                address
            )
            VALUES (%s, %s, %s, %s, %s)
        """, (
            vendor_name,
            contact_person,
            phone,
            email,
            address
        ))

        g.db.commit()
        cursor.close()

        flash(
            "Vendor added successfully!",
            "success"
        )

        return redirect("/vendors")

    return render_template("add_vendor.html")


# ============================================================
# EDIT VENDOR
# ============================================================

@app.route(
    "/edit_vendor/<int:vendor_id>",
    methods=["GET", "POST"]
)
def edit_vendor(vendor_id):

    if not login_required():
        return redirect("/login")

    cursor = g.db.cursor()

    if request.method == "POST":

        vendor_name = request.form.get(
            "vendor_name", ""
        ).strip()

        contact_person = request.form.get(
            "contact_person", ""
        ).strip()

        phone = request.form.get(
            "phone", ""
        ).strip()

        email = request.form.get(
            "email", ""
        ).strip()

        address = request.form.get(
            "address", ""
        ).strip()

        if not vendor_name:

            cursor.close()

            flash(
                "Vendor name is required.",
                "error"
            )

            return redirect(
                f"/edit_vendor/{vendor_id}"
            )

        cursor.execute("""
            UPDATE vendors
            SET
                vendor_name = %s,
                contact_person = %s,
                phone = %s,
                email = %s,
                address = %s
            WHERE vendor_id = %s
        """, (
            vendor_name,
            contact_person,
            phone,
            email,
            address,
            vendor_id
        ))

        g.db.commit()
        cursor.close()

        flash(
            "Vendor updated successfully!",
            "success"
        )

        return redirect("/vendors")

    cursor.execute("""
        SELECT *
        FROM vendors
        WHERE vendor_id = %s
    """, (vendor_id,))

    vendor = cursor.fetchone()

    cursor.close()

    if vendor is None:
        return "Vendor not found", 404

    return render_template(
        "edit_vendor.html",
        vendor=vendor
    )


# ============================================================
# DELETE VENDOR
# ============================================================

@app.route("/delete_vendor/<int:vendor_id>")
def delete_vendor(vendor_id):

    if not login_required():
        return redirect("/login")

    cursor = g.db.cursor()

    cursor.execute("""
        DELETE FROM vendors
        WHERE vendor_id = %s
    """, (vendor_id,))

    g.db.commit()
    cursor.close()

    flash(
        "Vendor deleted successfully!",
        "success"
    )

    return redirect("/vendors")


# ============================================================
# QUOTATIONS
# ============================================================

@app.route("/quotations")
def quotations():

    if not login_required():
        return redirect("/login")

    query = request.args.get(
        "query", ""
    ).strip()

    cursor = g.db.cursor()

    if query:

        search_value = "%" + query + "%"

        cursor.execute("""
            SELECT
                quotation_id,
                quotation_number,
                vendor_name,
                equipment_name,
                quotation_date,
                quantity,
                unit_price,
                total_amount,
                status
            FROM quotations
            WHERE
                quotation_number LIKE %s
                OR vendor_name LIKE %s
                OR equipment_name LIKE %s
            ORDER BY quotation_id DESC
        """, (
            search_value,
            search_value,
            search_value
        ))

    else:

        cursor.execute("""
            SELECT
                quotation_id,
                quotation_number,
                vendor_name,
                equipment_name,
                quotation_date,
                quantity,
                unit_price,
                total_amount,
                status
            FROM quotations
            ORDER BY quotation_id DESC
        """)

    quotation_list = cursor.fetchall()

    cursor.close()

    return render_template(
        "quotations.html",
        quotations=quotation_list
    )


# ============================================================
# ADD QUOTATION
# ============================================================

@app.route("/add_quotation", methods=["GET", "POST"])
def add_quotation():

    if not login_required():
        return redirect("/login")

    if request.method == "POST":

        quotation_number = request.form.get(
            "quotation_no", ""
        ).strip()

        vendor_name = request.form.get(
            "vendor", ""
        ).strip()

        equipment_name = request.form.get(
            "equipment", ""
        ).strip()

        quotation_date = request.form.get(
            "date", ""
        ).strip()

        quantity = request.form.get(
            "quantity", ""
        ).strip()

        unit_price = request.form.get(
            "unit_price", ""
        ).strip()

        status = request.form.get(
            "status", ""
        ).strip()

        if (
            not quotation_number
            or not vendor_name
            or not equipment_name
            or not quotation_date
        ):

            flash(
                "Please fill all required fields.",
                "error"
            )

            return redirect("/add_quotation")

        try:

            quantity = int(quantity)
            unit_price = float(unit_price)

            if quantity <= 0:
                raise ValueError

            if unit_price < 0:
                raise ValueError

        except ValueError:

            flash(
                "Please enter valid quantity and unit price.",
                "error"
            )

            return redirect("/add_quotation")

        total_amount = quantity * unit_price

        cursor = g.db.cursor()

        cursor.execute("""
            INSERT INTO quotations
            (
                quotation_number,
                vendor_name,
                equipment_name,
                quotation_date,
                quantity,
                unit_price,
                total_amount,
                status
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            quotation_number,
            vendor_name,
            equipment_name,
            quotation_date,
            quantity,
            unit_price,
            total_amount,
            status
        ))

        g.db.commit()
        cursor.close()

        flash(
            "Quotation added successfully!",
            "success"
        )

        return redirect("/quotations")

    return render_template("add_quotation.html")


# ============================================================
# EDIT QUOTATION
# ============================================================

@app.route(
    "/edit_quotation/<int:quotation_id>",
    methods=["GET", "POST"]
)
def edit_quotation(quotation_id):

    if not login_required():
        return redirect("/login")

    cursor = g.db.cursor()

    if request.method == "POST":

        quotation_number = request.form.get(
            "quotation_no", ""
        ).strip()

        vendor_name = request.form.get(
            "vendor", ""
        ).strip()

        equipment_name = request.form.get(
            "equipment", ""
        ).strip()

        quotation_date = request.form.get(
            "date", ""
        ).strip()

        quantity = request.form.get(
            "quantity", ""
        ).strip()

        unit_price = request.form.get(
            "unit_price", ""
        ).strip()

        status = request.form.get(
            "status", ""
        ).strip()

        if (
            not quotation_number
            or not vendor_name
            or not equipment_name
            or not quotation_date
        ):

            cursor.close()

            flash(
                "Please fill all required fields.",
                "error"
            )

            return redirect(
                f"/edit_quotation/{quotation_id}"
            )

        try:

            quantity = int(quantity)
            unit_price = float(unit_price)

            if quantity <= 0:
                raise ValueError

            if unit_price < 0:
                raise ValueError

        except ValueError:

            cursor.close()

            flash(
                "Invalid quantity or unit price.",
                "error"
            )

            return redirect(
                f"/edit_quotation/{quotation_id}"
            )

        total_amount = quantity * unit_price

        cursor.execute("""
            UPDATE quotations
            SET
                quotation_number = %s,
                vendor_name = %s,
                equipment_name = %s,
                quotation_date = %s,
                quantity = %s,
                unit_price = %s,
                total_amount = %s,
                status = %s
            WHERE quotation_id = %s
        """, (
            quotation_number,
            vendor_name,
            equipment_name,
            quotation_date,
            quantity,
            unit_price,
            total_amount,
            status,
            quotation_id
        ))

        g.db.commit()
        cursor.close()

        flash(
            "Quotation updated successfully!",
            "success"
        )

        return redirect("/quotations")

    cursor.execute("""
        SELECT
            quotation_id,
            quotation_number,
            vendor_name,
            equipment_name,
            quotation_date,
            quantity,
            unit_price,
            total_amount,
            status
        FROM quotations
        WHERE quotation_id = %s
    """, (quotation_id,))

    quotation = cursor.fetchone()

    cursor.close()

    if quotation is None:
        return "Quotation not found", 404

    return render_template(
        "edit_quotation.html",
        quotation=quotation
    )


# ============================================================
# DELETE QUOTATION
# ============================================================

@app.route("/delete_quotation/<int:quotation_id>")
def delete_quotation(quotation_id):

    if not login_required():
        return redirect("/login")

    cursor = g.db.cursor()

    cursor.execute("""
        DELETE FROM quotations
        WHERE quotation_id = %s
    """, (quotation_id,))

    g.db.commit()
    cursor.close()

    flash(
        "Quotation deleted successfully!",
        "success"
    )

    return redirect("/quotations")


# ============================================================
# QUOTATION PDF
# ============================================================

@app.route("/quotation_pdf/<int:quotation_id>")
def quotation_pdf(quotation_id):

    if not login_required():
        return redirect("/login")

    cursor = g.db.cursor()

    cursor.execute("""
        SELECT
            quotation_id,
            quotation_number,
            vendor_name,
            equipment_name,
            quotation_date,
            quantity,
            unit_price,
            total_amount,
            status
        FROM quotations
        WHERE quotation_id = %s
    """, (quotation_id,))

    quotation = cursor.fetchone()

    cursor.close()

    if quotation is None:
        flash("Quotation not found.", "error")
        return redirect("/quotations")

    # ========================================================
    # CREATE PDF
    # ========================================================

    pdf_buffer = io.BytesIO()

    pdf = canvas.Canvas(
        pdf_buffer,
        pagesize=A4
    )

    width, height = A4

    # ========================================================
    # HEADER
    # ========================================================

    pdf.setFont("Helvetica-Bold", 22)

    pdf.drawString(
        25 * mm,
        height - 25 * mm,
        "EQUIPMENT MANAGEMENT SYSTEM"
    )

    pdf.setFont("Helvetica", 10)

    pdf.drawString(
        25 * mm,
        height - 33 * mm,
        "Equipment Inventory & Quotation Management"
    )

    # Header line
    pdf.line(
        25 * mm,
        height - 40 * mm,
        width - 25 * mm,
        height - 40 * mm
    )

    # ========================================================
    # QUOTATION TITLE
    # ========================================================

    pdf.setFont(
        "Helvetica-Bold",
        20
    )

    pdf.drawCentredString(
        width / 2,
        height - 55 * mm,
        "QUOTATION"
    )

    # ========================================================
    # QUOTATION INFORMATION
    # ========================================================

    box_top = height - 70 * mm
    box_bottom = height - 105 * mm

    pdf.rect(
        25 * mm,
        box_bottom,
        width - 50 * mm,
        35 * mm
    )

    pdf.setFont(
        "Helvetica-Bold",
        10
    )

    pdf.drawString(
        30 * mm,
        height - 80 * mm,
        "Quotation Number:"
    )

    pdf.setFont(
        "Helvetica",
        10
    )

    pdf.drawString(
        70 * mm,
        height - 80 * mm,
        str(quotation[1])
    )

    pdf.setFont(
        "Helvetica-Bold",
        10
    )

    pdf.drawString(
        30 * mm,
        height - 90 * mm,
        "Quotation Date:"
    )

    pdf.setFont(
        "Helvetica",
        10
    )

    pdf.drawString(
        70 * mm,
        height - 90 * mm,
        str(quotation[4])
    )

    # ========================================================
    # VENDOR INFORMATION
    # ========================================================

    pdf.setFont(
        "Helvetica-Bold",
        12
    )

    pdf.drawString(
        25 * mm,
        height - 120 * mm,
        "VENDOR INFORMATION"
    )

    pdf.line(
        25 * mm,
        height - 123 * mm,
        width - 25 * mm,
        height - 123 * mm
    )

    pdf.setFont(
        "Helvetica-Bold",
        10
    )

    pdf.drawString(
        30 * mm,
        height - 135 * mm,
        "Vendor:"
    )

    pdf.setFont(
        "Helvetica",
        10
    )

    pdf.drawString(
        60 * mm,
        height - 135 * mm,
        str(quotation[2])
    )

    # ========================================================
    # ITEM TABLE
    # ========================================================

    table_top = height - 155 * mm

    # Column positions

    col1 = 25 * mm
    col2 = 90 * mm
    col3 = 125 * mm
    col4 = 160 * mm
    col5 = 185 * mm

    row_height = 12 * mm

    # Header background
    pdf.rect(
        col1,
        table_top - row_height,
        width - 50 * mm,
        row_height,
        fill=1
    )

    pdf.setFillColorRGB(
        1,
        1,
        1
    )

    pdf.setFont(
        "Helvetica-Bold",
        9
    )

    pdf.drawString(
        col1 + 3 * mm,
        table_top - 8 * mm,
        "Equipment"
    )

    pdf.drawString(
        col2 + 3 * mm,
        table_top - 8 * mm,
        "Quantity"
    )

    pdf.drawString(
        col3 + 3 * mm,
        table_top - 8 * mm,
        "Unit Price"
    )

    pdf.drawString(
        col4 + 3 * mm,
        table_top - 8 * mm,
        "Total"
    )

    # Reset text color
    pdf.setFillColorRGB(
        0,
        0,
        0
    )

    # Table body

    body_top = table_top - row_height

    pdf.rect(
        col1,
        body_top - row_height,
        width - 50 * mm,
        row_height
    )

    pdf.setFont(
        "Helvetica",
        9
    )

    pdf.drawString(
        col1 + 3 * mm,
        body_top - 8 * mm,
        str(quotation[3])
    )

    pdf.drawString(
        col2 + 3 * mm,
        body_top - 8 * mm,
        str(quotation[5])
    )

    pdf.drawString(
        col3 + 3 * mm,
        body_top - 8 * mm,
        f"Rs. {float(quotation[6]):,.2f}"
    )

    pdf.drawString(
        col4 + 3 * mm,
        body_top - 8 * mm,
        f"Rs. {float(quotation[7]):,.2f}"
    )

    # ========================================================
    # TOTAL SECTION
    # ========================================================

    total_y = body_top - 25 * mm

    pdf.setFont(
        "Helvetica-Bold",
        12
    )

    pdf.drawString(
        115 * mm,
        total_y,
        "TOTAL AMOUNT:"
    )

    pdf.setFont(
        "Helvetica-Bold",
        14
    )

    pdf.drawString(
        155 * mm,
        total_y,
        f"Rs. {float(quotation[7]):,.2f}"
    )

    # ========================================================
    # STATUS
    # ========================================================

    pdf.setFont(
        "Helvetica-Bold",
        11
    )

    pdf.drawString(
        25 * mm,
        total_y - 15 * mm,
        "Status:"
    )

    pdf.setFont(
        "Helvetica",
        11
    )

    pdf.drawString(
        50 * mm,
        total_y - 15 * mm,
        str(quotation[8])
    )

    # ========================================================
    # SIGNATURE
    # ========================================================

    signature_y = 55 * mm

    pdf.line(
        30 * mm,
        signature_y,
        85 * mm,
        signature_y
    )

    pdf.line(
        135 * mm,
        signature_y,
        190 * mm,
        signature_y
    )

    pdf.setFont(
        "Helvetica",
        9
    )

    pdf.drawCentredString(
        57 * mm,
        signature_y - 6 * mm,
        "Authorized Signature"
    )

    pdf.drawCentredString(
        162 * mm,
        signature_y - 6 * mm,
        "Vendor Signature"
    )

    # ========================================================
    # FOOTER
    # ========================================================

    pdf.setFont(
        "Helvetica",
        8
    )

    pdf.drawCentredString(
        width / 2,
        20 * mm,
        "Generated by Equipment Management System"
    )

    # Save PDF
    pdf.save()

    pdf_buffer.seek(0)

    return send_file(
        pdf_buffer,
        as_attachment=False,
        download_name=f"quotation_{quotation[1]}.pdf",
        mimetype="application/pdf"
    )

    # ========================================================
    # QUOTATION DETAILS
    # ========================================================

    y = height - 80 * mm

    details = [
        (
            "Quotation No.",
            quotation[1]
        ),
        (
            "Vendor",
            quotation[2]
        ),
        (
            "Equipment",
            quotation[3]
        ),
        (
            "Date",
            quotation[4]
        ),
        (
            "Quantity",
            quotation[5]
        ),
        (
            "Unit Price",
            f"Rs. {float(quotation[6]):,.2f}"
        ),
        (
            "Total Amount",
            f"Rs. {float(quotation[7]):,.2f}"
        ),
        (
            "Status",
            quotation[8]
        )
    ]

    for label, value in details:

        pdf.setFont(
            "Helvetica-Bold",
            11
        )

        pdf.drawString(
            30 * mm,
            y,
            str(label) + ":"
        )

        pdf.setFont(
            "Helvetica",
            11
        )

        pdf.drawString(
            75 * mm,
            y,
            str(value)
        )

        y -= 12 * mm

    # ========================================================
    # TOTAL
    # ========================================================

    y -= 5 * mm

    pdf.setFont(
        "Helvetica-Bold",
        14
    )

    pdf.drawString(
        30 * mm,
        y,
        f"TOTAL AMOUNT: Rs. {float(quotation[7]):,.2f}"
    )

    # ========================================================
    # FOOTER
    # ========================================================

    pdf.setFont(
        "Helvetica",
        9
    )

    pdf.drawString(
        30 * mm,
        20 * mm,
        "Generated by Equipment Management System"
    )

    pdf.save()

    pdf_buffer.seek(0)

    return send_file(
        pdf_buffer,
        as_attachment=False,
        download_name=f"quotation_{quotation[1]}.pdf",
        mimetype="application/pdf"
    )


# ============================================================
# RUN APPLICATION
# ============================================================

if __name__ == "__main__":
    app.run(debug=True)