import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin

import enum


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    LAWYER = "lawyer"
    PARALEGAL = "paralegal"
    VIEWER = "viewer"


class OrgType(str, enum.Enum):
    INDIVIDUAL_WORKSPACE = "individual_workspace"
    LAW_FIRM = "law_firm"


class OrgRole(str, enum.Enum):
    SUPER_ADMIN = "super_admin"
    MANAGING_PARTNER = "managing_partner"
    PARTNER = "partner"
    ASSOCIATE = "associate"
    PARALEGAL = "paralegal"
    TRAINEE = "trainee"
    FINANCE_ADMIN = "finance_admin"
    BILLING_ADMIN = "billing_admin"
    KNOWLEDGE_ADMIN = "knowledge_admin"
    READ_ONLY_GUEST = "read_only_guest"
    # Legacy compat
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"


class MemberStatus(str, enum.Enum):
    ACTIVE = "active"
    PENDING = "pending"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"


class Organization(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    org_type: Mapped[OrgType] = mapped_column(Enum(OrgType), default=OrgType.LAW_FIRM)
    domain: Mapped[str | None] = mapped_column(String(255))
    default_jurisdiction: Mapped[str | None] = mapped_column(String(100))
    default_governing_law: Mapped[str | None] = mapped_column(String(255))
    billing_plan: Mapped[str | None] = mapped_column(String(50))  # starter, professional, enterprise
    logo: Mapped[str | None] = mapped_column(String(1000))  # S3 key or URL
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    members: Mapped[list["OrganizationMember"]] = relationship(back_populates="organization", cascade="all, delete-orphan")
    documents: Mapped[list["Document"]] = relationship(back_populates="organization", cascade="all, delete-orphan")
    matters: Mapped[list["Matter"]] = relationship(back_populates="organization", cascade="all, delete-orphan")
    playbooks: Mapped[list["Playbook"]] = relationship(back_populates="organization", cascade="all, delete-orphan")
    preferences: Mapped[list["OrganizationPreference"]] = relationship(back_populates="organization", cascade="all, delete-orphan")
    teams: Mapped[list["Team"]] = relationship(back_populates="organization", cascade="all, delete-orphan")
    clients: Mapped[list["Client"]] = relationship(back_populates="organization", cascade="all, delete-orphan")


class User(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.LAWYER)
    phone: Mapped[str | None] = mapped_column(String(50))
    title: Mapped[str | None] = mapped_column(String(100))  # e.g. "Senior Associate", "Partner"
    timezone: Mapped[str | None] = mapped_column(String(50), default="UTC")
    profile_photo: Mapped[str | None] = mapped_column(String(1000))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_active_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    memberships: Mapped[list["OrganizationMember"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class OrganizationMember(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "organization_members"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[OrgRole] = mapped_column(Enum(OrgRole), default=OrgRole.MEMBER)

    # Extended fields
    member_title: Mapped[str | None] = mapped_column(String(100))  # role title within the firm
    department: Mapped[str | None] = mapped_column(String(100))
    permissions: Mapped[dict | None] = mapped_column(JSONB)  # granular permission overrides
    invited_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    joined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[MemberStatus] = mapped_column(Enum(MemberStatus), default=MemberStatus.ACTIVE)

    organization: Mapped["Organization"] = relationship(back_populates="members")
    user: Mapped["User"] = relationship(back_populates="memberships", foreign_keys=[user_id])


# --- Teams / Departments ---

class Team(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "teams"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    head_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    practice_area: Mapped[str | None] = mapped_column(String(100))  # litigation, corporate, IP, etc.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    organization: Mapped["Organization"] = relationship(back_populates="teams")


# --- Clients ---

class ClientStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    PROSPECT = "prospect"
    ARCHIVED = "archived"


class ClientType(str, enum.Enum):
    INDIVIDUAL = "individual"
    COMPANY = "company"
    GOVERNMENT = "government"
    NONPROFIT = "nonprofit"
    TRUST = "trust"


class Client(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "clients"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    client_type: Mapped[ClientType] = mapped_column(Enum(ClientType), default=ClientType.COMPANY)
    email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(50))
    address: Mapped[str | None] = mapped_column(Text)
    contact_info: Mapped[dict | None] = mapped_column(JSONB)  # structured contacts
    primary_contact_name: Mapped[str | None] = mapped_column(String(255))
    primary_contact_email: Mapped[str | None] = mapped_column(String(255))
    industry: Mapped[str | None] = mapped_column(String(100))
    jurisdiction: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[ClientStatus] = mapped_column(Enum(ClientStatus), default=ClientStatus.ACTIVE, index=True)
    risk_rating: Mapped[int | None] = mapped_column(Integer)  # 1-5
    billing_preferences: Mapped[dict | None] = mapped_column(JSONB)  # rate, currency, payment terms
    notes: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list | None] = mapped_column(JSONB)
    created_by_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    organization: Mapped["Organization"] = relationship(back_populates="clients")


# Resolve forward references
from app.models.document import Document  # noqa: E402
from app.models.matter import Matter  # noqa: E402
from app.models.playbook import Playbook  # noqa: E402
from app.models.memory import OrganizationPreference  # noqa: E402
