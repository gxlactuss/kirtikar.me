"""Google Merchant Center publishing adapter."""
from typing import List
from app.services.publishing.base import (
    CanonicalListing,
    PublicationResult,
    PublicationValidationResult,
)


class GoogleMerchantPublishingAdapter:
    """Publishes canonical listings to Google Merchant Center (Content API for Shopping)."""

    @property
    def channel_name(self) -> str:
        return "google_merchant"

    def validate(self, listing: CanonicalListing) -> PublicationValidationResult:
        errors: List[str] = []
        warnings: List[str] = []

        if not listing.title or not listing.title.strip():
            errors.append("Title is required for Google Merchant publication")
        elif len(listing.title) > 150:
            warnings.append("Google Merchant recommends titles under 150 characters")

        if not listing.description or not listing.description.strip():
            errors.append("Description is required for Google Merchant publication")

        if listing.price is None or listing.price <= 0:
            errors.append("A positive price is required for Google Merchant publication")

        if not listing.media_urls:
            errors.append("At least one product image is required for Google Merchant publication")

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

        external_id = f"online:en:IN:{listing.id}"
        google_payload = {
            "offer_id": external_id,
            "title": listing.title[:150],
            "description": listing.description[:5000],
            "link": f"https://shop.kirtikar.org/products/{listing.id}",
            "image_link": listing.media_urls[0] if listing.media_urls else None,
            "content_language": "en",
            "target_country": "IN",
            "channel": "online",
            "availability": "in_stock",
            "condition": "new",
            "price": {
                "value": f"{listing.price:.2f}",
                "currency": listing.currency or "INR",
            },
            # Explicit exemption for handcrafted artisan goods without barcode/GTIN
            "identifier_exists": False,
            "brand": listing.attributes.get("craft_type", "Artisan Handmade"),
        }

        return PublicationResult(
            success=True,
            channel=self.channel_name,
            external_id=external_id,
            status="published",
            message="Listing published successfully to Google Merchant mock adapter",
            details={
                "content_api_payload": google_payload,
                "feed_ready": True,
            },
        )
