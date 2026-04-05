"""
Proactive GF System - Makes AI girlfriend initiate contact

Components:
- ProactiveScheduler: Background job to check and trigger contacts
- DecisionEngine: Smart logic for when/how to contact
- MessageGenerator: Natural proactive messages
- ProactiveAPI: API endpoints for frontend
"""

from .decision_engine import DecisionEngine, ContactType, ContactDecision
from .message_generator import ProactiveMessageGenerator
from .scheduler import ProactiveScheduler

__all__ = [
    "DecisionEngine",
    "ContactType", 
    "ContactDecision",
    "ProactiveMessageGenerator",
    "ProactiveScheduler",
]
