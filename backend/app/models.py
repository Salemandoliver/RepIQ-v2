"""Data model. JSON columns are used for flexible AI output; works on SQLite and Postgres."""
from datetime import datetime
from sqlalchemy import (String, Integer, Float, Boolean, DateTime, Text, JSON,
                        ForeignKey, Index)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base


class Team(Base):
    __tablename__ = "teams"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    users: Mapped[list["User"]] = relationship(back_populates="team", foreign_keys="User.team_id")


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="recorder")  # admin | analyst | recorder
    job_title: Mapped[str] = mapped_column(String(120), default="Sales Rep")
    # Optional alternate name used to match this user against the trackers (Sales/Activity/
    # Lead), where agents are often recorded with a short or different name.
    short_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"), nullable=True)
    rc_extension_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    avatar_color: Mapped[str] = mapped_column(String(7), default="#6b7280")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    # ---- onboarding / password lifecycle ----
    # True for an invited user who hasn't set a password yet (login blocked until they do).
    must_set_password: Mapped[bool] = mapped_column(Boolean, default=False)
    # One-time token (invite or password-reset link). Cleared once consumed.
    reset_token: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    reset_token_expires: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Set whenever the password changes; embedded in JWTs so a reset invalidates old sessions.
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # ---- leaver bookkeeping ----
    left_on: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    left_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    team: Mapped[Team | None] = relationship(back_populates="users", foreign_keys=[team_id])


class Call(Base):
    __tablename__ = "calls"
    id: Mapped[int] = mapped_column(primary_key=True)
    host_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    direction: Mapped[str] = mapped_column(String(10))  # outbound | inbound
    activity_type: Mapped[str] = mapped_column(String(40), index=True)
    # Outbound - Acquisition | Outbound - In Life | Inbound - Call From Customer |
    # Proposal | Service Call | Voicemail
    from_number: Mapped[str] = mapped_column(String(32), default="")
    to_number: Mapped[str] = mapped_column(String(32), default="")
    customer_name: Mapped[str] = mapped_column(String(255), default="Unknown Customer")
    customer_company: Mapped[str] = mapped_column(String(255), default="")
    started_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    duration_sec: Mapped[int] = mapped_column(Integer, default=0)
    audio_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    # queued | downloading | transcribing | analyzing | completed | failed
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    process_attempts: Mapped[int] = mapped_column(Integer, default=0)
    rc_session_id: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    rc_recording_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    plays: Mapped[int] = mapped_column(Integer, default=0)
    likes: Mapped[int] = mapped_column(Integer, default=0)
    shares: Mapped[int] = mapped_column(Integer, default=0)
    # Outcome logging (Intelligence Layer keystone — powers close rate, predictor, DNA,
    # attribution). One-tap value the rep confirms after the call.
    # order_placed | callback | interested | not_interested | wrong_number | no_answer
    outcome: Mapped[str | None] = mapped_column(String(24), nullable=True, index=True)
    outcome_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    outcome_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    outcome_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    host: Mapped[User | None] = relationship(foreign_keys=[host_id])
    turns: Mapped[list["TranscriptTurn"]] = relationship(back_populates="call",
                                                         cascade="all, delete-orphan",
                                                         order_by="TranscriptTurn.start_sec")
    analysis: Mapped["CallAnalysis | None"] = relationship(back_populates="call", uselist=False,
                                                           cascade="all, delete-orphan")
    scores: Mapped[list["CallScore"]] = relationship(back_populates="call",
                                                     cascade="all, delete-orphan")
    topics: Mapped[list["CallTopic"]] = relationship(back_populates="call",
                                                     cascade="all, delete-orphan")


Index("ix_calls_started_host", Call.started_at, Call.host_id)


class TranscriptTurn(Base):
    __tablename__ = "transcript_turns"
    id: Mapped[int] = mapped_column(primary_key=True)
    call_id: Mapped[int] = mapped_column(ForeignKey("calls.id"), index=True)
    speaker: Mapped[str] = mapped_column(String(10))  # rep | customer
    speaker_name: Mapped[str] = mapped_column(String(120), default="")
    start_sec: Mapped[float] = mapped_column(Float)
    end_sec: Mapped[float] = mapped_column(Float)
    text: Mapped[str] = mapped_column(Text)
    call: Mapped[Call] = relationship(back_populates="turns")


class CallAnalysis(Base):
    __tablename__ = "call_analyses"
    id: Mapped[int] = mapped_column(primary_key=True)
    call_id: Mapped[int] = mapped_column(ForeignKey("calls.id"), unique=True)
    summary_intro: Mapped[str] = mapped_column(Text, default="")
    summary_points: Mapped[list] = mapped_column(JSON, default=list)       # [str]
    action_items: Mapped[list] = mapped_column(JSON, default=list)         # [{owner, text}]
    key_points: Mapped[list] = mapped_column(JSON, default=list)           # [{heading, points:[str]}]
    themes: Mapped[list] = mapped_column(JSON, default=list)               # [{name, description}]
    # Engagement metrics (computed from transcript)
    talk_ratio: Mapped[float] = mapped_column(Float, default=0)            # rep talk %
    longest_monologue_sec: Mapped[float] = mapped_column(Float, default=0)
    longest_customer_story_sec: Mapped[float] = mapped_column(Float, default=0)
    talking_speed_wpm: Mapped[float] = mapped_column(Float, default=0)
    patience_sec: Mapped[float] = mapped_column(Float, default=0)          # avg pause before rep replies
    question_rate: Mapped[float] = mapped_column(Float, default=0)         # questions asked by rep
    sentiment: Mapped[str] = mapped_column(String(20), default="neutral")
    # ---- Intelligence Layer: post-call coaching-card fields ----
    interruptions: Mapped[int] = mapped_column(Integer, default=0)         # rep talked over customer
    filler_count: Mapped[int] = mapped_column(Integer, default=0)          # um/uh/like… in rep speech
    question_breakdown: Mapped[dict] = mapped_column(JSON, default=dict)   # {discovery,closing,clarifying}
    objections: Mapped[list] = mapped_column(JSON, default=list)           # [{type,rep_response,assessment,suggested}]
    strengths: Mapped[list] = mapped_column(JSON, default=list)            # [str]
    improvements: Mapped[list] = mapped_column(JSON, default=list)         # [str]
    one_thing: Mapped[str] = mapped_column(Text, default="")               # the single coaching instruction
    energy_note: Mapped[str] = mapped_column(Text, default="")             # energy & pacing observation
    best_moment: Mapped[dict] = mapped_column(JSON, default=dict)          # {start_sec,end_sec,quote,reason}
    # Co-pilot commitments extracted from the call (drives the rep's daily action plan):
    # {callback, email_promised, missing_info, proposal_needed, next_step} — short strings.
    followups: Mapped[dict] = mapped_column(JSON, default=dict)
    call: Mapped[Call] = relationship(back_populates="analysis")


class Playbook(Base):
    __tablename__ = "playbooks"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    activity_types: Mapped[list] = mapped_column(JSON, default=list)  # which call types it applies to
    criteria: Mapped[list] = mapped_column(JSON, default=list)
    # [{key, name, description (what good looks like), weight}]
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class CallScore(Base):
    __tablename__ = "call_scores"
    id: Mapped[int] = mapped_column(primary_key=True)
    call_id: Mapped[int] = mapped_column(ForeignKey("calls.id"), index=True)
    playbook_id: Mapped[int] = mapped_column(ForeignKey("playbooks.id"))
    overall: Mapped[float] = mapped_column(Float, default=0)  # 0–5
    criteria: Mapped[list] = mapped_column(JSON, default=list)
    # [{key, name, score (1-5), feedback, evidence:[{speaker, at_sec}]}]
    coaching: Mapped[str] = mapped_column(Text, default="")   # AI coaching narrative
    call: Mapped[Call] = relationship(back_populates="scores")
    playbook: Mapped[Playbook] = relationship()


class Topic(Base):
    __tablename__ = "topics"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    keywords: Mapped[list] = mapped_column(JSON, default=list)
    color: Mapped[str] = mapped_column(String(7), default="#ef4444")
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class CallTopic(Base):
    __tablename__ = "call_topics"
    id: Mapped[int] = mapped_column(primary_key=True)
    call_id: Mapped[int] = mapped_column(ForeignKey("calls.id"), index=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id"), index=True)
    mentions: Mapped[int] = mapped_column(Integer, default=1)
    first_mention_sec: Mapped[float] = mapped_column(Float, default=0)
    duration_sec: Mapped[float] = mapped_column(Float, default=0)
    call: Mapped[Call] = relationship(back_populates="topics")
    topic: Mapped[Topic] = relationship()


class ListenEvent(Base):
    """Powers the Live Feed and play counts."""
    __tablename__ = "listen_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    call_id: Mapped[int] = mapped_column(ForeignKey("calls.id"), index=True)
    listened_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    user: Mapped[User] = relationship()
    call: Mapped[Call] = relationship()


class Comment(Base):
    __tablename__ = "comments"
    id: Mapped[int] = mapped_column(primary_key=True)
    call_id: Mapped[int] = mapped_column(ForeignKey("calls.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    at_sec: Mapped[float | None] = mapped_column(Float, nullable=True)
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    user: Mapped[User] = relationship()


class Report(Base):
    __tablename__ = "reports"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    report_type: Mapped[str] = mapped_column(String(40), default="coaching_profiles")
    frequency: Mapped[str] = mapped_column(String(20), default="weekly")
    period_start: Mapped[datetime] = mapped_column(DateTime)
    period_end: Mapped[datetime] = mapped_column(DateTime)
    team_names: Mapped[list] = mapped_column(JSON, default=list)
    content_md: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SavedSearch(Base):
    __tablename__ = "saved_searches"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    params: Mapped[dict] = mapped_column(JSON, default=dict)


class VocabularyTerm(Base):
    """Custom vocabulary sent to Deepgram as keyterms (BT product names etc.)."""
    __tablename__ = "vocabulary_terms"
    id: Mapped[int] = mapped_column(primary_key=True)
    term: Mapped[str] = mapped_column(String(120), unique=True)


class AskPreset(Base):
    """Stored questions for the Ask CallIQ panel (e.g. 'What are the deal blockers?')."""
    __tablename__ = "ask_presets"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    prompt: Mapped[str] = mapped_column(Text)
    position: Mapped[int] = mapped_column(Integer, default=0)


class Playlist(Base):
    """Curated collections of calls for team learning (e.g. 'Best SPIN calls')."""
    __tablename__ = "playlists"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    owner: Mapped[User] = relationship()
    items: Mapped[list["PlaylistItem"]] = relationship(back_populates="playlist",
                                                       cascade="all, delete-orphan",
                                                       order_by="PlaylistItem.position")


class PlaylistItem(Base):
    __tablename__ = "playlist_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    playlist_id: Mapped[int] = mapped_column(ForeignKey("playlists.id"), index=True)
    call_id: Mapped[int] = mapped_column(ForeignKey("calls.id"), index=True)
    added_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    added_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    playlist: Mapped[Playlist] = relationship(back_populates="items")
    call: Mapped[Call] = relationship()
    adder: Mapped[User | None] = relationship()


class PerformanceVideo(Base):
    """Feature 8 — AI weekly performance video/briefing per rep/BC per week. The Claude script
    always exists; status reaches 'ready' once Higgsfield renders the video (else 'text_only')."""
    __tablename__ = "performance_videos"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    video_type: Mapped[str] = mapped_column(String(30), default="weekly_rep")
    week_start: Mapped[datetime] = mapped_column(DateTime, index=True)  # Monday of the week
    title: Mapped[str] = mapped_column(String(200), default="")
    script: Mapped[str] = mapped_column(Text, default="")              # the spoken script
    headline: Mapped[str] = mapped_column(String(300), default="")     # one-line summary
    data_points: Mapped[dict] = mapped_column(JSON, default=dict)      # the compiled payload
    status: Mapped[str] = mapped_column(String(20), default="scripted")
    # scripted | rendering | ready | text_only | failed
    video_url: Mapped[str | None] = mapped_column(Text, nullable=True)  # HeyGen signed URLs can exceed 500 chars
    higgsfield_job_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    user: Mapped[User] = relationship()


Index("ix_perfvideo_user_week", PerformanceVideo.user_id, PerformanceVideo.week_start)


class Setting(Base):
    """Misc org settings: ai_context, org_name, etc."""
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)
