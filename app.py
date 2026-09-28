from flask import Flask, request, jsonify
import sqlite3
from datetime import datetime, timedelta

app = Flask(__name__)


# ---------------- DATABASE ----------------

def get_db():
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    return conn


def create_database():
    conn = get_db()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS complaints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            description TEXT NOT NULL,
            latitude REAL,
            longitude REAL,
            department TEXT,
            priority TEXT,
            status TEXT DEFAULT 'Submitted',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Add SLA columns if they do not exist
    try:
        conn.execute(
            "ALTER TABLE complaints ADD COLUMN sla_hours INTEGER"
        )
    except sqlite3.OperationalError:
        pass

    try:
        conn.execute(
            "ALTER TABLE complaints ADD COLUMN sla_deadline TIMESTAMP"
        )
    except sqlite3.OperationalError:
        pass

    conn.commit()
    conn.close()


# ---------------- HOME ----------------

@app.route("/")
def home():
    return "Community Grievance Backend is Working!"


# ---------------- AUTO ROUTING ----------------

def route_complaint(description):
    text = description.lower()

    # Department routing
    if any(word in text for word in ["pothole", "road", "street", "traffic"]):
        department = "Roads"

    elif any(word in text for word in ["garbage", "waste", "dustbin", "trash"]):
        department = "Sanitation"

    elif any(word in text for word in ["water", "pipeline", "leakage", "drinking"]):
        department = "Water"

    elif any(word in text for word in ["streetlight", "lamp", "light"]):
        department = "Electricity"

    else:
        department = "General"

    # Priority detection
    if any(word in text for word in ["urgent", "danger", "accident", "emergency"]):
        priority = "HIGH"

    elif any(word in text for word in ["broken", "leakage", "blocked"]):
        priority = "MEDIUM"

    else:
        priority = "LOW"

    return department, priority


# ---------------- CREATE COMPLAINT ----------------

@app.route("/api/complaints", methods=["POST"])
def create_complaint():

    data = request.get_json()

    description = data.get("description")
    latitude = data.get("latitude")
    longitude = data.get("longitude")

    if not description:
        return jsonify({
            "success": False,
            "message": "Complaint description is required"
        }), 400

    # Automatic department and priority
    department, priority = route_complaint(description)

    # SLA based on priority
    if priority == "HIGH":
        sla_hours = 4

    elif priority == "MEDIUM":
        sla_hours = 12

    else:
        sla_hours = 24

    # Calculate SLA deadline
    sla_deadline = datetime.now() + timedelta(hours=sla_hours)

    conn = get_db()

    cursor = conn.execute("""
        INSERT INTO complaints
        (description, latitude, longitude, department, priority,
         sla_hours, sla_deadline)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        description,
        latitude,
        longitude,
        department,
        priority,
        sla_hours,
        sla_deadline
    ))

    conn.commit()

    complaint_id = cursor.lastrowid

    conn.close()

    return jsonify({
        "success": True,
        "ticket_id": f"CIV-{complaint_id}",
        "department": department,
        "priority": priority,
        "sla_hours": sla_hours,
        "sla_deadline": str(sla_deadline),
        "message": "Complaint submitted successfully",
        "status": "Submitted"
    }), 201


# ---------------- GET ALL COMPLAINTS ----------------

@app.route("/api/complaints", methods=["GET"])
def get_complaints():

    conn = get_db()

    complaints = conn.execute(
        "SELECT * FROM complaints ORDER BY id DESC"
    ).fetchall()

    conn.close()

    return jsonify([dict(row) for row in complaints])


# ---------------- UPDATE STATUS ----------------

@app.route("/api/complaints/<int:complaint_id>/status", methods=["PUT"])
def update_status(complaint_id):

    data = request.get_json()

    status = data.get("status")

    if not status:
        return jsonify({
            "success": False,
            "message": "Status is required"
        }), 400

    conn = get_db()

    cursor = conn.execute("""
        UPDATE complaints
        SET status = ?
        WHERE id = ?
    """, (status, complaint_id))

    conn.commit()

    if cursor.rowcount == 0:
        conn.close()

        return jsonify({
            "success": False,
            "message": "Complaint not found"
        }), 404

    conn.close()

    return jsonify({
        "success": True,
        "ticket_id": f"CIV-{complaint_id}",
        "status": status,
        "message": "Complaint status updated successfully"
    })



# ---------------- SLA ESCALATION ----------------

@app.route("/api/complaints/check-sla", methods=["GET"])
def check_sla():

    conn = get_db()

    complaints = conn.execute("""
        SELECT * FROM complaints
        WHERE sla_deadline IS NOT NULL
        AND status != 'Resolved'
    """).fetchall()

    escalated = []

    current_time = datetime.now()

    for complaint in complaints:

        deadline = datetime.fromisoformat(
            complaint["sla_deadline"]
        )

        if current_time > deadline:

            conn.execute("""
                UPDATE complaints
                SET status = 'Escalated'
                WHERE id = ?
            """, (complaint["id"],))

            escalated.append(
                f"CIV-{complaint['id']}"
            )

    conn.commit()
    conn.close()

    return jsonify({
        "success": True,
        "message": "SLA check completed",
        "escalated_tickets": escalated
    })

# ---------------- RUN FLASK ----------------

if __name__ == "__main__":
    create_database()
    app.run(debug=True)