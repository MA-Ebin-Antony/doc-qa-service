from sqlalchemy import Column, Integer, String, Text, JSON, DateTime
from sqlalchemy.orm import declarative_base
import datetime

Base = declarative_base()


class PDFSection(Base):
    __tablename__ = "pdf_sections"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_file = Column(String, nullable=False)
    page_number = Column(Integer, nullable=True)
    heading_level = Column(Integer, nullable=True)
    heading_text = Column(String, nullable=True)
    body_text = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class PDFTable(Base):
    __tablename__ = "pdf_tables"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_file = Column(String, nullable=False)
    page_number = Column(Integer, nullable=True)
    section_heading = Column(String, nullable=True)
    headers = Column(JSON, nullable=False)
    rows = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class ExcelRow(Base):
    __tablename__ = "excel_rows"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_file = Column(String, nullable=False)
    sheet_name = Column(String, nullable=False)
    row_index = Column(Integer, nullable=False)
    data = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
