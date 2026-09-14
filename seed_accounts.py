"""Script to seed/update teacher and learner test accounts and initial chatroom sessions."""
import sqlite3
from datetime import datetime, timezone
from app import hash_password

def seed():
    con = sqlite3.connect("talkroom.db")
    cur = con.cursor()
    pw_hash = hash_password("Password123!")
    now = datetime.now(timezone.utc).isoformat()

    # 1. Teacher Account
    cur.execute("SELECT id FROM users WHERE email = ?", ("teacher@talkroom.com",))
    t = cur.fetchone()
    if t:
        teacher_id = t[0]
        cur.execute(
            """UPDATE users SET name=?, password_hash=?, role='teacher', teacher_status='active',
               teacher_profile_completed=1, teacher_city=?, teacher_bio=?, payout_phone_number=?,
               phone_number=?, balance_tsh=? WHERE id=?""",
            (
                "Neema M.",
                pw_hash,
                "Dar es Salaam",
                "Mwalimu mzoefu wa Kiswahili na utamaduni. Karibu tujifunze pamoja!",
                "255712345678",
                "255712345678",
                150000,
                teacher_id,
            ),
        )
    else:
        cur.execute(
            """INSERT INTO users (name, email, password_hash, role, teacher_status, teacher_profile_completed,
               teacher_city, teacher_bio, payout_phone_number, phone_number, balance_tsh, created_at)
               VALUES (?, ?, ?, 'teacher', 'active', 1, ?, ?, ?, ?, ?, ?)""",
            (
                "Neema M.",
                "teacher@talkroom.com",
                pw_hash,
                "Dar es Salaam",
                "Mwalimu mzoefu wa Kiswahili na utamaduni. Karibu tujifunze pamoja!",
                "255712345678",
                "255712345678",
                150000,
                now,
            ),
        )
        teacher_id = cur.lastrowid

    # Update legacy test.teacher@talkroom.local as well if present
    cur.execute(
        "UPDATE users SET password_hash=?, teacher_status='active', teacher_profile_completed=1 WHERE email=?",
        (pw_hash, "test.teacher@talkroom.local"),
    )

    # 2. Learner Account
    cur.execute("SELECT id FROM users WHERE email = ?", ("learner@talkroom.com",))
    l = cur.fetchone()
    if l:
        learner_id = l[0]
        cur.execute(
            """UPDATE users SET name=?, password_hash=?, role='learner', phone_number=?, balance_tsh=? WHERE id=?""",
            ("Test Learner", pw_hash, "255787654321", 50000, learner_id),
        )
    else:
        cur.execute(
            """INSERT INTO users (name, email, password_hash, role, phone_number, balance_tsh, created_at)
               VALUES (?, ?, ?, 'learner', ?, ?, ?)""",
            ("Test Learner", "learner@talkroom.com", pw_hash, "255787654321", 50000, now),
        )
        learner_id = cur.lastrowid

    # Update legacy test.learner@talkroom.local as well if present
    cur.execute(
        "UPDATE users SET password_hash=? WHERE email=?",
        (pw_hash, "test.learner@talkroom.local"),
    )

    # 3. Seed an Accepted Booking with an active Conversation for testing
    cur.execute(
        "SELECT id FROM bookings WHERE learner_id = ? AND teacher_name = ? AND status = 'accepted'",
        (learner_id, "Neema M."),
    )
    b_accepted = cur.fetchone()
    if b_accepted:
        booking_accepted_id = b_accepted[0]
    else:
        cur.execute(
            """INSERT INTO bookings (learner_id, teacher_name, topic, duration_minutes, amount_cents, currency, status, created_at)
               VALUES (?, ?, ?, 30, 30000, 'TZS', 'accepted', ?)""",
            (learner_id, "Neema M.", "Kiswahili cha Mazungumzo & Safari", now),
        )
        booking_accepted_id = cur.lastrowid

    # Ensure conversation exists for this booking
    cur.execute("SELECT id FROM conversations WHERE booking_id = ?", (booking_accepted_id,))
    conv = cur.fetchone()
    if conv:
        conv_id = conv[0]
    else:
        cur.execute("INSERT INTO conversations (booking_id, created_at) VALUES (?, ?)", (booking_accepted_id, now))
        conv_id = cur.lastrowid

    # Ensure some initial messages exist in this conversation
    cur.execute("SELECT COUNT(*) FROM messages WHERE conversation_id = ?", (conv_id,))
    msg_count = cur.fetchone()[0]
    if msg_count == 0:
        cur.execute(
            "INSERT INTO messages (conversation_id, sender_id, body, created_at) VALUES (?, ?, ?, ?)",
            (conv_id, teacher_id, "Habari ya leo! Karibu sana kwenye chumba chetu cha mazungumzo ya Kiswahili.", now),
        )
        cur.execute(
            "INSERT INTO messages (conversation_id, sender_id, body, created_at) VALUES (?, ?, ?, ?)",
            (conv_id, learner_id, "Habari mwalimu Neema! Asante sana, nimefurahi sana kuanza kipindi hiki na wewe.", now),
        )
        cur.execute(
            "INSERT INTO messages (conversation_id, sender_id, body, created_at) VALUES (?, ?, ?, ?)",
            (conv_id, teacher_id, "Vizuri mno! Tunaweza kuanza kwa mazoezi ya safari za wanyama Serengeti au mazungumzo ya sokoni.", now),
        )

    # 4. Seed a Requested Booking (pending teacher acceptance) so teacher can test "Accept request"
    cur.execute(
        "SELECT id FROM bookings WHERE learner_id = ? AND teacher_name = ? AND status = 'requested'",
        (learner_id, "Neema M."),
    )
    b_requested = cur.fetchone()
    if not b_requested:
        cur.execute(
            """INSERT INTO bookings (learner_id, teacher_name, topic, duration_minutes, amount_cents, currency, status, created_at)
               VALUES (?, ?, ?, 30, 30000, 'TZS', 'requested', ?)""",
            (learner_id, "Neema M.", "Mazoezi ya Matamshi na Msamiati wa Kiswahili", now),
        )

    con.commit()
    con.close()
    print("Successfully seeded test accounts:")
    print(f"  Teacher: teacher@talkroom.com (Password: Password123!) - ID: {teacher_id}")
    print(f"  Learner: learner@talkroom.com (Password: Password123!) - ID: {learner_id}")
    print(f"  Accepted Booking ID: {booking_accepted_id} (Conversation ID: {conv_id})")

if __name__ == "__main__":
    seed()
