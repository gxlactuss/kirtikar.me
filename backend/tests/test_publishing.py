from app.services.publishing.base import (
    CanonicalListing,
    PublicationResult,
    PublicationValidationResult,
    PublishingAdapter,
)
from app.services.publishing.ondc import ONDCPublishingAdapter
from app.services.publishing.meta import MetaPublishingAdapter
from app.services.publishing.google import GoogleMerchantPublishingAdapter


def test_publishing_adapter_imports_and_protocol() -> None:
    """Verify that the publishing protocol and models can be imported and instantiated."""
    listing = CanonicalListing(
        id="test-listing-1",
        title="Handcrafted Brass Bell",
        description="Authentic bell handmade by local artisan",
        price=350.0,
        currency="INR",
        category="Handicrafts",
        materials=["Brass"],
        media_urls=["https://example.com/bell.jpg"],
    )
    assert listing.id == "test-listing-1"
    assert listing.price == 350.0
    assert "Brass" in listing.materials


def test_ondc_adapter_implements_protocol() -> None:
    """Verify that ONDCPublishingAdapter implements the PublishingAdapter protocol."""
    adapter = ONDCPublishingAdapter()
    assert isinstance(adapter, PublishingAdapter)
    assert adapter.channel_name == "ondc"


def test_ondc_adapter_deterministic_publish_success() -> None:
    """Verify mock ONDC adapter produces deterministic publish output on valid listing."""
    adapter = ONDCPublishingAdapter()
    listing = CanonicalListing(
        id="listing-xyz-101",
        title="Madhubani Painting",
        description="Traditional handmade folk art",
        price=1200.0,
        currency="INR",
        media_urls=["https://example.com/art.jpg"],
    )

    validation = adapter.validate(listing)
    assert isinstance(validation, PublicationValidationResult)
    assert validation.is_valid is True
    assert validation.channel == "ondc"
    assert len(validation.errors) == 0

    result = adapter.publish(listing)
    assert isinstance(result, PublicationResult)
    assert result.success is True
    assert result.channel == "ondc"
    assert result.external_id == "ondc-item-listing-xyz-101"
    assert result.status == "published"
    assert "mock-bpp-listing-factory" in result.details.get("bpp_id", "")


def test_ondc_adapter_deterministic_validation_failure() -> None:
    """Verify mock ONDC adapter handles validation failures deterministically."""
    adapter = ONDCPublishingAdapter()
    invalid_listing = CanonicalListing(
        id="listing-invalid",
        title="",
        description="",
        price=-10.0,
    )

    validation = adapter.validate(invalid_listing)
    assert validation.is_valid is False
    assert len(validation.errors) >= 3

    result = adapter.publish(invalid_listing)
    assert result.success is False
    assert result.channel == "ondc"
    assert result.status == "validation_failed"
    assert result.external_id is None


def test_meta_adapter_implements_protocol() -> None:
    """Verify that MetaPublishingAdapter implements the PublishingAdapter protocol."""
    adapter = MetaPublishingAdapter()
    assert isinstance(adapter, PublishingAdapter)
    assert adapter.channel_name == "meta"


def test_meta_adapter_publish_success() -> None:
    """Verify Meta adapter formats catalog items for WhatsApp Business Catalog."""
    adapter = MetaPublishingAdapter()
    listing = CanonicalListing(
        id="meta-test-1",
        title="Terracotta Tea Cups",
        description="Set of 6 handcrafted earthen kulhad cups",
        price=350.0,
        currency="INR",
        materials=["Clay"],
        media_urls=["https://example.com/cups.jpg"],
        attributes={"craft_type": "Terracotta"},
    )

    validation = adapter.validate(listing)
    assert validation.is_valid is True
    assert len(validation.errors) == 0

    result = adapter.publish(listing)
    assert result.success is True
    assert result.channel == "meta"
    assert result.external_id == "meta-catalog-item-meta-test-1"
    assert result.status == "published"
    catalog_item = result.details.get("catalog_item", {})
    assert catalog_item["name"] == "Terracotta Tea Cups"
    assert catalog_item["price"] == "350.00"
    assert catalog_item["currency"] == "INR"
    assert catalog_item["availability"] == "in stock"


def test_meta_adapter_validation_failure() -> None:
    """Verify Meta adapter enforces required images and positive pricing."""
    adapter = MetaPublishingAdapter()
    # Missing media_urls and invalid price
    invalid_listing = CanonicalListing(
        id="meta-invalid-1",
        title="Invalid Item",
        description="Missing photo and price",
        price=0.0,
        media_urls=[],
    )
    validation = adapter.validate(invalid_listing)
    assert validation.is_valid is False
    assert any("price" in err for err in validation.errors)
    assert any("image" in err for err in validation.errors)

    result = adapter.publish(invalid_listing)
    assert result.success is False
    assert result.status == "validation_failed"


def test_google_merchant_adapter_implements_protocol() -> None:
    """Verify that GoogleMerchantPublishingAdapter implements PublishingAdapter."""
    adapter = GoogleMerchantPublishingAdapter()
    assert isinstance(adapter, PublishingAdapter)
    assert adapter.channel_name == "google_merchant"


def test_google_merchant_adapter_publish_success() -> None:
    """Verify Google Merchant adapter formats Content API payload with identifier exemption."""
    adapter = GoogleMerchantPublishingAdapter()
    listing = CanonicalListing(
        id="gm-prod-101",
        title="Handcrafted Blue Pottery Ceramic Plate",
        description="Authentic Jaipur floral design pottery",
        price=850.0,
        currency="INR",
        media_urls=["https://example.com/plate.jpg"],
        attributes={"craft_type": "Jaipur Blue Pottery"},
    )

    validation = adapter.validate(listing)
    assert validation.is_valid is True

    result = adapter.publish(listing)
    assert result.success is True
    assert result.channel == "google_merchant"
    assert result.external_id == "online:en:IN:gm-prod-101"

    payload = result.details.get("content_api_payload", {})
    assert payload["identifier_exists"] is False  # Crucial for handmade crafts
    assert payload["offer_id"] == "online:en:IN:gm-prod-101"
    assert payload["price"]["value"] == "850.00"
    assert payload["price"]["currency"] == "INR"


def test_google_merchant_adapter_validation_failure() -> None:
    """Verify Google Merchant validation catches missing images and titles."""
    adapter = GoogleMerchantPublishingAdapter()
    invalid_listing = CanonicalListing(
        id="gm-invalid",
        title="",
        description="Missing title and image",
        price=500.0,
        media_urls=[],
    )
    validation = adapter.validate(invalid_listing)
    assert validation.is_valid is False
    assert len(validation.errors) >= 2
