"""Meta Commerce & WhatsApp Business Catalog publishing adapter."""
from typing import List
from app.services.publishing.base import (
    CanonicalListing,
    PublicationResult,
    PublicationValidationResult,
)


class MetaPublishingAdapter:
    """Publishes canonical listings to Meta Commerce Manager & WhatsApp Business Catalog."""

    @property
    def channel_name(self) -> str:
        return "meta"

    def validate(self, listing: CanonicalListing) -> PublicationValidationResult:
        errors: List[str] = []
        warnings: List[str] = []

        if not listing.title or not listing.title.strip():
            errors.append("Title is required for Meta/WhatsApp catalog publication")

        if not listing.description or not listing.description.strip():
            errors.append("Description is required for Meta/WhatsApp catalog publication")

        if listing.price is None or listing.price <= 0:
            errors.append("A positive price is required for Meta/WhatsApp catalog publication")

        if not listing.media_urls:
            errors.append("At least one product image URL is required for Meta/WhatsApp catalog publication")

        return PublicationValidationResult(
            is_valid=len(errors) == 0,
            channel=self.channel_name,
            errors=errors,
            warnings=warnings,
        )

    def publish(self, listing: CanonicalListing) -> PublicationResult:
        validation = self.validate(listing)
        if not validation.is_valid:
            return PublicationResult(
                success=False,
                channel=self.channel_name,
                external_id=None,
                status="validation_failed",
                message=f"Validation failed: {', '.join(validation.errors)}",
                details={"errors": validation.errors, "warnings": validation.warnings},
            )

        external_id = f"meta-catalog-item-{listing.id}"
        meta_payload = {
            "retailer_id": external_id,
            "name": listing.title,
            "description": listing.description,
            "price": f"{listing.price:.2f}",
            "currency": listing.currency or "INR",
            "availability": "in stock",
            "condition": "new",
            "image_url": listing.media_urls[0] if listing.media_urls else None,
            "brand": listing.attributes.get("craft_type", "Artisan Handmade"),
            "origin_country": "IN",
        }

        return PublicationResult(
            success=True,
            channel=self.channel_name,
            external_id=external_id,
            status="published",
            message="Listing published successfully to Meta / WhatsApp Catalog mock adapter",
            details={
                "catalog_item": meta_payload,
                "whatsapp_interactive_ready": True,
            },
        )
