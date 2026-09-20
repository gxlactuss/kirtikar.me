from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@dataclass(frozen=True)
class CanonicalListing:
    id: str
    title: str
    description: str
    price: Optional[float] = None
    currency: str = "INR"
    category: Optional[str] = None
    materials: List[str] = field(default_factory=list)
    dimensions: Optional[str] = None
    media_urls: List[str] = field(default_factory=list)
    attributes: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PublicationValidationResult:
    is_valid: bool
    channel: str
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class PublicationResult:
    success: bool
    channel: str
    external_id: Optional[str] = None
    status: str = "published"
    message: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class PublishingAdapter(Protocol):
    @property
    def channel_name(self) -> str:
        raise NotImplementedError

    def validate(self, listing: CanonicalListing) -> PublicationValidationResult:
        raise NotImplementedError

    def publish(self, listing: CanonicalListing) -> PublicationResult:
        raise NotImplementedError
