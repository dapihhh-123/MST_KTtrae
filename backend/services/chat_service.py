from sqlalchemy.orm import Session
from backend import models, schemas, utils
from typing import List, Optional

class ChatService:
    def __init__(self, db: Session):
        self.db = db

    def get_project_threads(self, session_id: str) -> List[models.Thread]:
        return self.db.query(models.Thread).filter(models.Thread.session_id == session_id).all()

    def create_thread(self, thread: schemas.ThreadCreate) -> models.Thread:
        db_thread = models.Thread(
            id=utils.uid("thread"),
            session_id=thread.session_id,
            type=thread.type,
            title=thread.title,
            summary=thread.summary,
            anchor=thread.anchor
        )
        self.db.add(db_thread)
        self.db.commit()
        self.db.refresh(db_thread)

        if db_thread.type == "breakout":
            self.add_message(
                db_thread.id,
                schemas.MessageCreate(
                    role="assistant",
                    content="Breakout created. Ask questions in situ.",
                    meta=None,
                ),
            )
        return db_thread

    def create_breakout(self, thread_create: schemas.ThreadCreate) -> models.Thread:
        # Breakout is just a thread with type="breakout" and an anchor
        return self.create_thread(thread_create)

    def add_message(self, thread_id: str, message: schemas.MessageCreate, message_id: Optional[str] = None) -> models.Message:
        db_message = models.Message(
            id=message_id or utils.uid("msg"),
            thread_id=thread_id,
            role=message.role,
            content=message.content,
            meta=message.meta
        )
        self.db.add(db_message)
        self.db.commit()
        self.db.refresh(db_message)
        return db_message

    def get_thread_messages(self, thread_id: str) -> List[models.Message]:
        return self.db.query(models.Message)\
            .filter(models.Message.thread_id == thread_id)\
            .order_by(models.Message.created_at.asc())\
            .all()
