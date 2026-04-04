"""Models for privilege tagging, conflict checking, and regulatory monitoring."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin


# --- Privilege Tagging ---

class PrivilegeType(str, enum.Enum):
    ATTORNEY_CLIENT = "attorney_client"
    WORK_PRODUCT = "work_product"
    COMMON_INTEREST = "common_interest"
    LITIGATION_HOLD = "litigation_hold"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


class PrivilegeStatus(str, enum.Enum):
    ASSERTED = "asserted"
    WAIVED = "waived"
    DISPUTED = "disputed"
    UNDER_REVIEW = "under_review"


class PrivilegeTag(Base, UUIDMixin, TimestampMixin):
    """Privilege and confidentiality markers on documents and analysis results."""
    __tablename__ = "privilege_tags"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    matter_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("matters.id", ondelete="CASCADE"), index=True)
    analysis_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("analysis_results.id", ondelete="CASCADE"), index=True)

    privilege_type: Mapped[PrivilegeType] = mapped_column(Enum(PrivilegeType), nullable=False, index=True)
    status: Mapped[PrivilegeStatus] = mapped_column(Enum(PrivilegeStatus), default=PrivilegeStatus.ASSERTED)

    # Who and why
    asserted_by_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    basis: Mapped[str] = mapped_column(Text, nullable=False)  # legal basis for the assertion
    scope_description: Mapped[str | None] = mapped_column(Text)  # what specifically is privileged
    attorney_name: Mapped[str | None] = mapped_column(String(255))
    client_name: Mapped[str | None] = mapped_column(String(255))

    # Waiver tracking
    waived_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    waived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    waiver_reason: Mapped[str | None] = mapped_column(Text)
    waiver_scope: Mapped[str | None] = mapped_column(Text)  # partial or full waiver

    # Review
    reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_notes: Mapped[str | None] = mapped_column(Text)

    metadata: Mapped[dict | None] = mapped_column(JSONB)


class PrivilegeLog(Base, UUIDMixin, TimestampMixin):
    """Privilege log entries for litigation hold / discovery responses."""
    __tablename__ = "privilege_log_entries"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    matter_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("matters.id", ondelete="CASCADE"), nullable=False, index=True)
    privilege_tag_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("privilege_tags.id", ondelete="CASCADE"), nullable=False)
    document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"))

    # Standard privilege log fields
    document_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    document_type_description: Mapped[str] = mapped_column(String(255), nullable=False)
    author: Mapped[str | None] = mapped_column(String(500))
    recipients: Mapped[list | None] = mapped_column(JSONB)
    subject_matter: Mapped[str] = mapped_column(Text, nullable=False)
    privilege_claimed: Mapped[str] = mapped_column(String(255), nullable=False)
    basis_for_privilege: Mapped[str] = mapped_column(Text, nullable=False)


# --- Conflict Checking ---

class ConflictStatus(str, enum.Enum):
    NO_CONFLICT = "no_conflict"
    POTENTIAL_CONFLICT = "potential_conflict"
    ACTUAL_CONFLICT = "actual_conflict"
    WAIVED = "waived"
    CLEARED = "cleared"


class ConflictParty(Base, UUIDMixin, TimestampMixin):
    """Known parties tracked across matters for conflict detection."""
    __tablename__ = "conflict_parties"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    normalized_name: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    aliases: Mapped[list | None] = mapped_column(JSONB)  # known aliases, trading names, subsidiaries
    party_type: Mapped[str | None] = mapped_column(String(50))  # individual, company, government, trust
    jurisdiction: Mapped[str | None] = mapped_column(String(100))
    registration_number: Mapped[str | None] = mapped_column(String(100))
    metadata: Mapped[dict | None] = mapped_column(JSONB)


class ConflictMatterParty(Base, UUIDMixin, TimestampMixin):
    """Links parties to matters with their role — the core data for conflict detection."""
    __tablename__ = "conflict_matter_parties"

    matter_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("matters.id", ondelete="CASCADE"), nullable=False, index=True)
    party_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("conflict_parties.id", ondelete="CASCADE"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(100), nullable=False)  # client, counterparty, opposing_counsel, co-party, witness, guarantor
    is_adverse: Mapped[bool] = mapped_column(Boolean, default=False)  # True if this party is adverse to our client


class ConflictCheck(Base, UUIDMixin, TimestampMixin):
    """Record of a conflict-of-interest check."""
    __tablename__ = "conflict_checks"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    matter_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("matters.id", ondelete="SET NULL"), index=True)
    checked_by_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    # What was checked
    party_names_checked: Mapped[list] = mapped_column(JSONB, nullable=False)
    status: Mapped[ConflictStatus] = mapped_column(Enum(ConflictStatus), nullable=False)

    # Results
    conflicts_found: Mapped[list | None] = mapped_column(JSONB)  # list of {matter_id, matter_title, party_name, role, adverse, description}
    resolution: Mapped[str | None] = mapped_column(Text)
    resolved_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Approval
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# --- Regulatory Change Monitoring ---

class MonitoredRegulation(Base, UUIDMixin, TimestampMixin):
    """Regulations, statutes, or legal areas being monitored for changes."""
    __tablename__ = "monitored_regulations"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    created_by_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    jurisdiction: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)  # statute, regulation, case_law, guidance
    source_identifier: Mapped[str | None] = mapped_column(String(500))  # citation or reference
    source_adapter: Mapped[str | None] = mapped_column(String(100))  # which legal source adapter to use

    # Monitoring config
    keywords: Mapped[list | None] = mapped_column(JSONB)  # keywords to watch for
    topics: Mapped[list | None] = mapped_column(JSONB)
    check_frequency_hours: Mapped[int] = mapped_column(Integer, default=24)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # State
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_change_detected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Link to matters affected
    affected_matter_ids: Mapped[list | None] = mapped_column(JSONB)

    alerts: Mapped[list["RegulatoryAlert"]] = relationship(back_populates="regulation", cascade="all, delete-orphan")


class RegulatoryAlert(Base, UUIDMixin, TimestampMixin):
    """An alert generated when a monitored regulation changes."""
    __tablename__ = "regulatory_alerts"

    regulation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("monitored_regulations.id", ondelete="CASCADE"), nullable=False, index=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)

    alert_type: Mapped[str] = mapped_column(String(50), nullable=False)  # new_law, amendment, repeal, new_case, guidance_update
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    impact_assessment: Mapped[str | None] = mapped_column(Text)
    risk_level: Mapped[str | None] = mapped_column(String(20))  # critical, high, medium, low

    source_url: Mapped[str | None] = mapped_column(String(1000))
    source_citation: Mapped[str | None] = mapped_column(String(500))
    source_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Action tracking
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    actioned_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    actioned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    action_notes: Mapped[str | None] = mapped_column(Text)

    affected_matter_ids: Mapped[list | None] = mapped_column(JSONB)

    regulation: Mapped["MonitoredRegulation"] = relationship(back_populates="alerts")


# --- Citation Validation ---

class CitationValidation(Base, UUIDMixin, TimestampMixin):
    """Record of a good-law check on a citation."""
    __tablename__ = "citation_validations"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    checked_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))

    citation: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    jurisdiction: Mapped[str | None] = mapped_column(String(100))

    is_good_law: Mapped[bool] = mapped_column(Boolean, nullable=False)
    treatment: Mapped[str] = mapped_column(String(50), nullable=False)  # positive, negative, cautionary, overruled, repealed, amended, unknown
    negative_treatment: Mapped[str | None] = mapped_column(Text)  # description of negative treatment
    overruled_by: Mapped[str | None] = mapped_column(String(500))
    distinguished_by: Mapped[list | None] = mapped_column(JSONB)
    followed_by_count: Mapped[int] = mapped_column(Integer, default=0)
    cited_by_count: Mapped[int] = mapped_column(Integer, default=0)

    source_adapter: Mapped[str | None] = mapped_column(String(100))
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # cache expiry

    # Link to analysis that used this citation
    analysis_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("analysis_results.id", ondelete="SET NULL"))

    raw_result: Mapped[dict | None] = mapped_column(JSONB)


# --- Feedback ---

class FeedbackRating(str, enum.Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"


class Feedback(Base, UUIDMixin, TimestampMixin):
    """User feedback on AI-generated outputs — drives continuous improvement."""
    __tablename__ = "feedback"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)

    # What was rated
    analysis_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("analysis_results.id", ondelete="CASCADE"), index=True)
    conversation_message_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("conversation_messages.id", ondelete="CASCADE"), index=True)
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # analysis, draft, review, redline, conversation
    resource_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)

    # Rating
    rating: Mapped[FeedbackRating] = mapped_column(Enum(FeedbackRating), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text)  # optional explanation

    # What the user corrected (if negative)
    correction: Mapped[str | None] = mapped_column(Text)  # the corrected answer/text
    correction_type: Mapped[str | None] = mapped_column(String(50))  # wrong_answer, wrong_citation, wrong_risk, missing_info, other

    # Context for learning
    query: Mapped[str | None] = mapped_column(Text)  # the original question/instruction
    jurisdiction: Mapped[str | None] = mapped_column(String(100))
    clause_type: Mapped[str | None] = mapped_column(String(100))  # for deviation false positives
    metadata: Mapped[dict | None] = mapped_column(JSONB)


# --- Webhooks & Notifications ---

class WebhookEventType(str, enum.Enum):
    DOCUMENT_PROCESSED = "document.processed"
    DOCUMENT_FAILED = "document.failed"
    DEADLINE_APPROACHING = "deadline.approaching"
    DEADLINE_OVERDUE = "deadline.overdue"
    REGULATORY_ALERT = "regulatory.alert"
    ANALYSIS_COMPLETED = "analysis.completed"
    CONFLICT_DETECTED = "conflict.detected"
    DIGEST = "digest.scheduled"


class Webhook(Base, UUIDMixin, TimestampMixin):
    """Webhook registration — orgs subscribe URLs to receive event notifications."""
    __tablename__ = "webhooks"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    created_by_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    secret: Mapped[str | None] = mapped_column(String(255))  # HMAC signing secret
    events: Mapped[list] = mapped_column(JSONB, nullable=False)  # list of WebhookEventType values
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Health
    last_triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_status_code: Mapped[int | None] = mapped_column(Integer)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)


class WebhookDelivery(Base, UUIDMixin, TimestampMixin):
    """Log of every webhook delivery attempt."""
    __tablename__ = "webhook_deliveries"

    webhook_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("webhooks.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status_code: Mapped[int | None] = mapped_column(Integer)
    response_body: Mapped[str | None] = mapped_column(Text)
    success: Mapped[bool] = mapped_column(Boolean, default=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer)


class ScheduledDigest(Base, UUIDMixin, TimestampMixin):
    """Scheduled digest configuration — periodic summaries delivered via webhook."""
    __tablename__ = "scheduled_digests"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    created_by_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    schedule: Mapped[str] = mapped_column(String(50), nullable=False)  # daily_9am, weekly_monday, weekly_friday
    webhook_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("webhooks.id", ondelete="SET NULL"))

    # What to include
    include_deadlines: Mapped[bool] = mapped_column(Boolean, default=True)
    include_regulatory_alerts: Mapped[bool] = mapped_column(Boolean, default=True)
    include_pending_reviews: Mapped[bool] = mapped_column(Boolean, default=True)
    include_matter_updates: Mapped[bool] = mapped_column(Boolean, default=True)
    include_feedback_stats: Mapped[bool] = mapped_column(Boolean, default=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# --- Email Intake ---

class EmailIntakeConfig(Base, UUIDMixin, TimestampMixin):
    """Per-org configuration for email-based document ingestion."""
    __tablename__ = "email_intake_configs"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    created_by_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    intake_email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)  # e.g. acme-legal@ingest.mydenning.com
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Defaults applied to ingested documents
    default_document_type: Mapped[str] = mapped_column(String(50), default="contract")
    default_jurisdiction: Mapped[str | None] = mapped_column(String(100))
    default_matter_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("matters.id", ondelete="SET NULL"))
    auto_review: Mapped[bool] = mapped_column(Boolean, default=False)  # auto-run clause extraction after processing
    auto_playbook_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("playbooks.id", ondelete="SET NULL"))  # auto-compare against this playbook

    # Allowed senders (empty = accept from anyone in the org's domain)
    allowed_sender_domains: Mapped[list | None] = mapped_column(JSONB)
    allowed_sender_emails: Mapped[list | None] = mapped_column(JSONB)


class EmailIntakeLog(Base, UUIDMixin, TimestampMixin):
    """Log of every inbound email processed."""
    __tablename__ = "email_intake_logs"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    config_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("email_intake_configs.id", ondelete="CASCADE"), nullable=False)

    sender_email: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[str | None] = mapped_column(String(1000))
    body_preview: Mapped[str | None] = mapped_column(Text)
    attachment_count: Mapped[int] = mapped_column(Integer, default=0)

    # Results
    documents_created: Mapped[list | None] = mapped_column(JSONB)  # [{document_id, title, file_name}]
    status: Mapped[str] = mapped_column(String(50), default="processed")  # processed, rejected, failed
    rejection_reason: Mapped[str | None] = mapped_column(String(500))
