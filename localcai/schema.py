"""Unified internal format.

Every importer produces these objects; every exporter / the runtime consumes them.
Keeping one schema in the middle means adding a new source or a new target
never touches the other side.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class Message:
    author: str               # display name
    is_user: bool
    text: str
    timestamp: str | None = None
    pinned: bool = False
    # Alternative candidates (C.ai "swipes"); text is the chosen one.
    alternatives: list[str] = field(default_factory=list)
    id: str | None = None      # source platform's message id (used to merge re-imports)


@dataclass
class Character:
    name: str
    tagline: str = ""          # C.ai "title"
    description: str = ""      # C.ai "description" / long description
    personality: str = ""
    scenario: str = ""
    greeting: str = ""         # first message
    alternate_greetings: list[str] = field(default_factory=list)
    example_dialogue: str = "" # C.ai "definition"
    creator: str = ""
    avatar_url: str | None = None
    avatar_png: bytes | None = None                 # real avatar image (PNG)
    background: tuple[str, bytes] | None = None      # (mime, data)
    tags: list[str] = field(default_factory=list)
    source: str = "unknown"
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class Chat:
    character_name: str
    user_name: str = "User"
    messages: list[Message] = field(default_factory=list)
    title: str = ""
    created: str | None = None
    source: str = "unknown"
    source_id: str | None = None   # source platform's chat id (same chat → same file)
    # C.ai "conversation facts" (its built-in chat memory): [{"about","category","value"}]
    memories: list[dict] = field(default_factory=list)
    background: tuple[str, bytes] | None = None      # (mime, data)

    @property
    def pins(self) -> list[Message]:
        return [m for m in self.messages if m.pinned]


@dataclass
class Bundle:
    """Everything one import produced."""
    characters: list[Character] = field(default_factory=list)
    chats: list[Chat] = field(default_factory=list)
    # [{"name","description", "avatar_png"?: bytes, "background"?: (mime, bytes)}]
    personas: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def merge(self, other: "Bundle") -> "Bundle":
        self.characters += other.characters
        self.chats += other.chats
        self.personas += other.personas
        self.warnings += other.warnings
        return self

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
