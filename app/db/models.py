import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Identity, Index, Integer, SmallInteger, String, Text, func, text
from sqlalchemy.dialects.postgresql import ARRAY, INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ApiAuditLog(Base):
    __tablename__ = "api_audit_log"
    __table_args__ = (
        Index("ix_api_audit_log_ts", text("ts DESC")),
        Index("ix_api_audit_log_client_ip_ts", "client_ip", text("ts DESC")),
        Index("ix_api_audit_log_errors", "status_code", postgresql_where=text("status_code >= 400")),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    request_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))

    client_ip: Mapped[str | None] = mapped_column(INET)
    x_forwarded_for: Mapped[str | None] = mapped_column(Text)

    method: Mapped[str] = mapped_column(String(10))
    path: Mapped[str] = mapped_column(Text)
    route_template: Mapped[str | None] = mapped_column(Text)
    query_params: Mapped[dict | None] = mapped_column(JSONB)
    request_body: Mapped[dict | list | None] = mapped_column(JSONB)
    request_size: Mapped[int | None] = mapped_column(Integer)

    status_code: Mapped[int] = mapped_column(SmallInteger)
    error_type: Mapped[str | None] = mapped_column(Text)
    error_detail: Mapped[str | None] = mapped_column(Text)
    response_size: Mapped[int | None] = mapped_column(Integer)
    duration_ms: Mapped[int | None] = mapped_column(Integer)

    upstream_service: Mapped[str | None] = mapped_column(Text)
    upstream_status: Mapped[int | None] = mapped_column(SmallInteger)
    upstream_duration_ms: Mapped[int | None] = mapped_column(Integer)
    upstream_calls: Mapped[int | None] = mapped_column(Integer)

    ne_names: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    mml_command: Mapped[str | None] = mapped_column(Text)
