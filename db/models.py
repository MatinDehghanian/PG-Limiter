"""
Database Models for PG-Limiter
SQLAlchemy models for all database tables.
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    Boolean,
    DateTime,
    Text,
    ForeignKey,
    Index,
    JSON,
)
from sqlalchemy.orm import relationship, DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all models"""


class User(Base):
    """
    Panel users cache - stores users fetched from panel with their groups and owner info.
    This allows filtering by owner/admin without re-fetching from panel.
    """
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(255), unique=True, nullable=False, index=True)
    
    # User status from panel
    status = Column(String(50), default="active")  # active, disabled, limited, expired
    
    # Owner/admin info
    owner_id = Column(Integer, nullable=True)  # Admin/owner ID in panel
    owner_username = Column(String(255), nullable=True)  # Admin/owner username
    
    # Group info (stored as JSON array of group IDs)
    group_ids = Column(JSON, default=list)  # [1, 2, 3]
    
    # Data traffic
    data_limit = Column(Float, nullable=True)  # GB
    used_traffic = Column(Float, default=0)  # GB
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    expire_at = Column(DateTime, nullable=True)
    last_synced_at = Column(DateTime, default=datetime.utcnow)
    
    # Extra data from panel
    note = Column(Text, nullable=True)
    
    # Relationships
    limit = relationship("UserLimit", back_populates="user", uselist=False)
    disabled_record = relationship("DisabledUser", back_populates="user", uselist=False)
    violations = relationship("ViolationHistory", back_populates="user")
    
    __table_args__ = (
        Index("ix_users_owner_id", "owner_id"),
        Index("ix_users_status", "status"),
    )
    
    def __repr__(self):
        return f"<User(username='{self.username}', status='{self.status}', owner='{self.owner_username}')>"


class UserLimit(Base):
    """
    Special limits for specific users.
    Users not in this table use the general limit from config.
    """
    __tablename__ = "user_limits"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(255), ForeignKey("users.username", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    limit = Column(Integer, nullable=False, default=2)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship
    user = relationship("User", back_populates="limit")
    
    def __repr__(self):
        return f"<UserLimit(username='{self.username}', limit={self.limit})>"


class ExceptUser(Base):
    """
    Users excluded from IP limiting (whitelisted users).
    These users won't be disabled regardless of IP count.
    """
    __tablename__ = "except_users"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(255), unique=True, nullable=False, index=True)
    reason = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(String(255), nullable=True)  # Admin who added this exception
    
    def __repr__(self):
        return f"<ExceptUser(username='{self.username}')>"


class DisabledUser(Base):
    """
    Currently disabled users with their disable timestamp and scheduled enable time.
    """
    __tablename__ = "disabled_users"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(255), ForeignKey("users.username", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    
    # When the user was disabled
    disabled_at = Column(Float, nullable=False)  # Unix timestamp
    
    # When to automatically re-enable (optional - 0 means use global time_to_active)
    enable_at = Column(Float, nullable=True)  # Unix timestamp, None = use global setting
    
    # Original groups before disabling (for restore when re-enabling)
    original_groups = Column(JSON, default=list)  # [1, 2, 3]
    
    # Reason for disabling
    reason = Column(Text, nullable=True)  # e.g., "IP limit exceeded (3/2)"
    
    # Punishment step applied (for smart punishment system)
    punishment_step = Column(Integer, default=0)
    
    # Relationship
    user = relationship("User", back_populates="disabled_record")
    
    def __repr__(self):
        return f"<DisabledUser(username='{self.username}', disabled_at={self.disabled_at})>"


class SubnetISP(Base):
    """
    ISP cache for IP subnets.
    Stores ISP info for /24 subnets to avoid repeated API calls.
    e.g., for IP 192.168.1.100, subnet would be "192.168.1"
    """
    __tablename__ = "subnet_isp"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    subnet = Column(String(50), unique=True, nullable=False, index=True)  # e.g., "192.168.1"
    
    # ISP information
    isp = Column(String(255), nullable=True)
    country = Column(String(10), nullable=True)  # Country code
    city = Column(String(100), nullable=True)
    region = Column(String(100), nullable=True)
    
    # ASN info
    asn = Column(String(50), nullable=True)  # e.g., "AS12345"
    as_name = Column(String(255), nullable=True)
    
    # Cache metadata
    cached_at = Column(DateTime, default=datetime.utcnow)
    hit_count = Column(Integer, default=1)  # How many times this cache was used
    
    __table_args__ = (
        Index("ix_subnet_isp_country", "country"),
        Index("ix_subnet_isp_isp", "isp"),
    )
    
    def __repr__(self):
        return f"<SubnetISP(subnet='{self.subnet}', isp='{self.isp}', country='{self.country}')>"


class ViolationHistory(Base):
    """
    Violation history for the smart punishment system.
    Tracks when users violated IP limits and what punishment was applied.
    """
    __tablename__ = "violation_history"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(255), ForeignKey("users.username", ondelete="CASCADE"), nullable=False, index=True)
    
    # Violation details
    timestamp = Column(Float, nullable=False)  # Unix timestamp
    step_applied = Column(Integer, nullable=False)  # Which punishment step was applied (0-indexed)
    disable_duration = Column(Integer, nullable=False)  # Duration in minutes (0 = unlimited or warning)
    
    # When the user was re-enabled (for timed disables)
    enabled_at = Column(Float, nullable=True)
    
    # Additional info
    ip_count = Column(Integer, nullable=True)  # How many IPs triggered the violation
    ips = Column(JSON, nullable=True)  # List of IPs that triggered this violation
    
    # Relationship
    user = relationship("User", back_populates="violations")
    
    __table_args__ = (
        Index("ix_violation_history_timestamp", "timestamp"),
    )
    
    def __repr__(self):
        return f"<ViolationHistory(username='{self.username}', step={self.step_applied}, duration={self.disable_duration}m)>"


class Config(Base):
    """
    Configuration storage in database.
    Key-value store for settings that can be changed at runtime.
    """
    __tablename__ = "config"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(255), unique=True, nullable=False, index=True)
    value = Column(JSON, nullable=True)  # Can store any JSON-serializable value
    
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f"<Config(key='{self.key}')>"


class IPHistory(Base):
    """
    IP history for users - tracks which IPs each user has used.
    Useful for reporting and analysis.
    """
    __tablename__ = "ip_history"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(255), index=True, nullable=False)
    ip = Column(String(45), nullable=False)  # IPv4 or IPv6
    
    # Connection info
    node_name = Column(String(255), nullable=True)
    inbound_protocol = Column(String(100), nullable=True)
    
    # Timestamps
    first_seen = Column(DateTime, default=datetime.utcnow)
    last_seen = Column(DateTime, default=datetime.utcnow)
    
    # Connection count
    connection_count = Column(Integer, default=1)
    
    __table_args__ = (
        Index("ix_ip_history_username_ip", "username", "ip"),
        Index("ix_ip_history_last_seen", "last_seen"),
    )
    
    def __repr__(self):
        return f"<IPHistory(username='{self.username}', ip='{self.ip}')>"
