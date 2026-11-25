
from decimal import Decimal
from uuid import UUID as PythonUUID

from sqlalchemy import (
    BigInteger,
    DateTime,
    Integer,
    Numeric,
    String,
    func,
    ForeignKeyConstraint,
    Index,
    UniqueConstraint,
    Column,
    Text
)
import uuid


from sqlalchemy.dialects.postgresql import UUID

from app.db import Base
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class HealthProfile(Base):
    __tablename__ = "health_profiles"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
    )

    user_id: Mapped[PythonUUID] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=False,
        index=True,
    )

    goals: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    dietary_preferences: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    daily_budget: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )

    daily_calories_target: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2),
        nullable=True,
    )

    daily_protein_target_g: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2),
        nullable=True,
    )

    daily_carbs_target_g: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2),
        nullable=True,
    )

    daily_fat_target_g: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2),
        nullable=True,
    )



class MealLog(Base):
    __tablename__ = "meal_logs"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    user_id: Mapped[PythonUUID] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=False,
        index=True,
    )

    food_name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    meal_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    portion: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    calories: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )

    protein_g: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        default=Decimal("0"),
    )

    carbs_g: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        default=Decimal("0"),
    )

    fat_g: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        default=Decimal("0"),
    )

    cost: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        default=Decimal("0"),
    )

    consumed_at: Mapped[object] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # Every dashboard/meal query filters by user and a date range.
    __table_args__ = (
        Index(
            "idx_meal_logs_user_consumed",
            "user_id",
            "consumed_at",
        ),
    )


class ChatThread(Base):
    __tablename__ = "chat_threads"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id = Column(
        UUID(as_uuid=True),
        nullable=False,
        index=False,
    )
    title = Column(
        String(120),
        nullable=False,
        default="New conversation",
    )
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        UniqueConstraint(
            "id",
            "user_id",
            name="uq_chat_threads_id_user",
        ),
        Index(
            "idx_chat_threads_user_updated",
            "user_id",
            "updated_at",
        ),
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    thread_id = Column(UUID(as_uuid=True), nullable=False)
    user_id = Column(UUID(as_uuid=True), nullable=False)
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    model = Column(String(100), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["thread_id", "user_id"],
            ["chat_threads.id", "chat_threads.user_id"],
            name="fk_chat_message_thread_owner",
            ondelete="CASCADE",
        ),
        Index(
            "idx_chat_messages_thread_created",
            "thread_id",
            "created_at",
        ),
    )
