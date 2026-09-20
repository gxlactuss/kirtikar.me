from typing import List
from app.services.publishing.base import (
    CanonicalListing,
    PublicationResult,
    PublicationValidationResult,
)


class ONDCPublishingAdapter:
    @property
    def channel_name(self) -> str:
        return "ondc"

    def validate(self, listing: CanonicalListing) -> PublicationValidationResult:
        errors: List[str] = []
        warnings: List[str] = []

        if not listing.title.strip():
            errors.append("Title is required for ONDC publication")

        if not listing.description.strip():
            errors.append("Description is required for ONDC publication")

        if listing.price is None or listing.price <= 0:
            errors.append("A positive price is required for ONDC publication")

        if not listing.media_urls:
            warnings.append("No media URLs provided; ONDC listings typically require at least one product image")

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

        external_id = f"ondc-item-{listing.id}"
        return PublicationResult(
            success=True,
            channel=self.channel_name,
            external_id=external_id,
            status="published",
            message="Listing published successfully to ONDC mock adapter",
            details={
                "bpp_id": "mock-bpp-listing-factory",
                "item_id": external_id,
            },
        )
