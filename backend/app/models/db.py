"""SQLAlchemy 数据模型 — fireFairy 科研版精简。"""
from sqlalchemy import Column, Integer, String, Text, UniqueConstraint, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import settings

Base = declarative_base()


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"
    __table_args__ = (UniqueConstraint("source_id", "chunk_index", name="uq_knowledge_source_chunk"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    collection = Column(String(64), index=True)
    source = Column(String(256))
    source_id = Column(String(128), index=True)
    chunk_index = Column(Integer, default=0)
    title = Column(String(256))
    text = Column(Text)
    page = Column(Integer, nullable=True)
    section = Column(String(256), nullable=True)
    meta_json = Column(Text, nullable=True)


engine = create_engine(settings.database_url, echo=False)
SessionLocal = sessionmaker(bind=engine)


def init_db():
    # 注册审计日志模型后再建表，确保 audit_logs 一并创建
    from app.agents.project_recorder import AuditLog  # noqa: F401

    Base.metadata.create_all(bind=engine)