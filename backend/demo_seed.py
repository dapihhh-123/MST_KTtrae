from backend.database import SessionLocal, engine
from backend import models, utils
from backend.models import Base

def seed_data():
    print("=== Seeding Demo Data ===")
    
    # Create tables if not exist
    Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()
    try:
        # 1. Create Workspace
        ws = models.Workspace(
            id=utils.uid("ws"),
            name="Demo Workspace"
        )
        db.add(ws)
        db.commit()
        print(f"[OK] Created Workspace: {ws.id}")
        
        # 2. Create Session
        sess = models.Session(
            id=utils.uid("sess"),
            workspace_id=ws.id,
            title="Python Basics",
            language="python"
        )
        db.add(sess)
        db.commit()
        print(f"[OK] Created Session: {sess.id}")
        
        # 3. Create Code Snapshot
        code = """def hello():
    print("Hello World")
"""
        snap = models.CodeSnapshot(
            id=utils.uid("snap"),
            session_id=sess.id,
            content=code,
            cursor_line=2,
            cursor_col=5
        )
        db.add(snap)
        db.commit()
        print(f"[OK] Created CodeSnapshot: {snap.id}")
        
        # 4. Create General Thread
        t_gen = models.Thread(
            id=utils.uid("thread"),
            session_id=sess.id,
            type="global",
            title="General",
            summary="Welcome to the session"
        )
        db.add(t_gen)
        db.commit()
        
        # Messages for General
        m1 = models.Message(
            id=utils.uid("msg"),
            thread_id=t_gen.id,
            role="assistant",
            content="Hello! I am your AI tutor."
        )
        m2 = models.Message(
            id=utils.uid("msg"),
            thread_id=t_gen.id,
            role="user",
            content="Hi, help me with Python."
        )
        db.add_all([m1, m2])
        db.commit()
        print(f"[OK] Created General Thread: {t_gen.id} with 2 messages")
        
        # 5. Create Breakout Thread
        t_brk = models.Thread(
            id=utils.uid("thread"),
            session_id=sess.id,
            type="breakout",
            title="Breakout #1",
            anchor={"file": "main.py", "line_start": 1, "line_end": 2}
        )
        db.add(t_brk)
        db.commit()
        
        m3 = models.Message(
            id=utils.uid("msg"),
            thread_id=t_brk.id,
            role="assistant",
            content="Let's focus on this function definition."
        )
        db.add(m3)
        db.commit()
        print(f"[OK] Created Breakout Thread: {t_brk.id} with anchor")
        
        # 6. Create Event
        evt = models.EventLog(
            id=utils.uid("evt"),
            session_id=sess.id,
            type="compile",
            payload={"status": "success", "duration": 120}
        )
        db.add(evt)
        db.commit()
        print(f"[OK] Created Event: {evt.id}")
        
        print("\n=== Seed Complete ===")
        print(f"Workspace ID: {ws.id}")
        print(f"Session ID:   {sess.id}")
        
    except Exception as e:
        print(f"[FAIL] Seeding failed: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    seed_data()
