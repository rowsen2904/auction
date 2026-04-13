from django.utils.translation import gettext_lazy as _
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
)
from rest_framework import serializers

from .serializers import (
    MyAvailablePropertySerializer,
    PropertyCreateSerializer,
    PropertyImageCreateSerializer,
    PropertyImageSerializer,
    PropertyImageUpdateSerializer,
    PropertyListSerializer,
    PropertyUpdateSerializer,
)


class ErrorResponseSerializer(serializers.Serializer):
    error = serializers.CharField()


class DRFDetailErrorSerializer(serializers.Serializer):
    detail = serializers.CharField()


PROPERTIES_LIST_DOC = _(
    "Returns a paginated list of properties.\n\n"
    "Each property includes `is_editable`:\n"
    "- `true` if the property is not linked to any blocking auction\n"
    "- `true` if all linked auctions are cancelled\n"
    "- `false` if the property is linked to at least one scheduled, active, or finished auction\n\n"
    "A property may participate in:\n"
    "- an OPEN auction via `open_auctions`\n"
    "- a CLOSED lot auction via `lot_auctions`\n\n"
    "Filters are supported via query params:\n"
    "- `type`\n"
    "- `property_class`\n"
    "- `status`\n"
    "- `address` (icontains)\n"
    "- `project` (icontains)\n"
    "- `purpose` (icontains)\n"
    "- `commercial_subtype` (`retail` | `office`)\n"
    "- `rooms`\n"
    "- `price_min`, `price_max`\n"
    "- `area_min`, `area_max`\n"
    "- `delivery_date_before`, `delivery_date_after`\n\n"
    "Sorting:\n"
    "- `ordering` (e.g. `-created_at`, `price`, `area`)\n"
)

MY_PROPERTIES_LIST_DOC = _(
    "Returns a paginated list of properties owned by the authenticated developer.\n\n"
    "Each property includes `is_editable`:\n"
    "- `true` if the property is not linked to any blocking auction\n"
    "- `true` if all linked auctions are cancelled\n"
    "- `false` if linked to any scheduled, active, or finished auction"
)

PROPERTIES_CREATE_DOC = _(
    "Creates a new property.\n\n"
    "Only users with role `developer` can create properties.\n"
    "Owner is set automatically from the authenticated user."
)

PROPERTY_DETAIL_DOC = _(
    "Returns property details including images and `is_editable` flag."
)

PROPERTY_PATCH_DOC = _(
    "Partially updates a property.\n\n"
    "Only the owner (developer who created it) can update the property.\n"
    "Update is forbidden if the property is linked to a blocking auction:\n"
    "- OPEN auction with status scheduled, active, or finished\n"
    "- CLOSED lot auction with status scheduled, active, or finished"
)

PROPERTY_IMAGES_LIST_DOC = _(
    "Returns images for the given property.\n\n" "Ordered by `sort_order` then `id`."
)

PROPERTY_IMAGES_CREATE_DOC = _(
    "Uploads/creates an image record for the given property.\n\n"
    "Only the owner (developer who created the property) can add images.\n\n"
    "You can provide either:\n"
    "- `image` file upload, OR\n"
    "- `external_url`\n"
)

PROPERTY_IMAGE_DELETE_DOC = _(
    "Deletes a property image.\n\n"
    "Only the owner (developer who created the property) can delete the image."
)

PROPERTY_IMAGE_PATCH_DOC = _(
    "Partially updates a property image.\n\n"
    "Only the owner (developer who created the property) can update the image.\n\n"
    "Supported fields:\n"
    "- `is_primary`\n"
    "- `sort_order`\n\n"
    "If `is_primary=true`, all other property images will be marked as `is_primary=false`.\n"
    "If `sort_order` conflicts with another image of the same property, "
    "the endpoint returns a validation error."
)

MY_AVAILABLE_PROPERTIES_LIST_DOC = _(
    "Returns a paginated list of the authenticated developer's properties "
    "that are approved by moderation, published, and not linked to any blocking auction."
)

COMPATIBLE_PROPERTIES_LIST_DOC = _(
    "Returns a paginated list of compatible properties for CLOSED lot creation.\n\n"
    "Query params:\n"
    "- `reference_id` (required, UUID of reference property)\n\n"
    "Rules:\n"
    "- reference property must belong to current developer\n"
    "- reference property must be approved and published\n"
    "- backend returns only developer's compatible properties\n"
    "- properties linked to blocking auctions are excluded\n"
    "- price and unit-specific differences are ignored by compatibility rules"
)


properties_list_schema = extend_schema(
    summary="List properties",
    description=PROPERTIES_LIST_DOC,
    responses={
        200: OpenApiResponse(
            response=PropertyListSerializer(many=True),
            description="Paginated list of properties.",
            examples=[
                OpenApiExample(
                    "List example",
                    value={
                        "count": 1,
                        "next": None,
                        "previous": None,
                        "results": [
                            {
                                "id": 1,
                                "reference_id": "e52db7e5-77b9-4fd7-a57b-cf0aa5a20ef0",
                                "developer": 10,
                                "type": "apartment",
                                "project": "Skyline",
                                "project_comment": "Первая очередь, вид на парк",
                                "rooms": 2,
                                "purpose": None,
                                "commercial_subtype": None,
                                "address": "Moscow, Tverskaya 1",
                                "area": "52.50",
                                "property_class": "comfort",
                                "price": "12000000.00",
                                "commission_rate": "2.50",
                                "deadline": "2026-10-01",
                                "delivery_date": "2027-03-01",
                                "status": "published",
                                "images": [],
                                "created_at": "2026-02-04T06:00:00Z",
                                "updated_at": "2026-02-04T06:00:00Z",
                                "moderation_status": "approved",
                                "moderation_rejection_reason": None,
                                "is_editable": True,
                            }
                        ],
                    },
                )
            ],
        )
    },
    parameters=[
        OpenApiParameter(
            name="page",
            type=OpenApiTypes.INT,
            required=False,
            location=OpenApiParameter.QUERY,
        ),
        OpenApiParameter(
            name="page_size",
            type=OpenApiTypes.INT,
            required=False,
            location=OpenApiParameter.QUERY,
        ),
        OpenApiParameter(
            name="type",
            type=OpenApiTypes.STR,
            required=False,
            location=OpenApiParameter.QUERY,
        ),
        OpenApiParameter(
            name="property_class",
            type=OpenApiTypes.STR,
            required=False,
            location=OpenApiParameter.QUERY,
        ),
        OpenApiParameter(
            name="status",
            type=OpenApiTypes.STR,
            required=False,
            location=OpenApiParameter.QUERY,
        ),
        OpenApiParameter(
            name="address",
            type=OpenApiTypes.STR,
            required=False,
            location=OpenApiParameter.QUERY,
        ),
        OpenApiParameter(
            name="project",
            type=OpenApiTypes.STR,
            required=False,
            location=OpenApiParameter.QUERY,
        ),
        OpenApiParameter(
            name="purpose",
            type=OpenApiTypes.STR,
            required=False,
            location=OpenApiParameter.QUERY,
        ),
        OpenApiParameter(
            name="commercial_subtype",
            type=OpenApiTypes.STR,
            required=False,
            location=OpenApiParameter.QUERY,
        ),
        OpenApiParameter(
            name="rooms",
            type=OpenApiTypes.INT,
            required=False,
            location=OpenApiParameter.QUERY,
        ),
        OpenApiParameter(
            name="price_min",
            type=OpenApiTypes.NUMBER,
            required=False,
            location=OpenApiParameter.QUERY,
        ),
        OpenApiParameter(
            name="price_max",
            type=OpenApiTypes.NUMBER,
            required=False,
            location=OpenApiParameter.QUERY,
        ),
        OpenApiParameter(
            name="area_min",
            type=OpenApiTypes.NUMBER,
            required=False,
            location=OpenApiParameter.QUERY,
        ),
        OpenApiParameter(
            name="area_max",
            type=OpenApiTypes.NUMBER,
            required=False,
            location=OpenApiParameter.QUERY,
        ),
        OpenApiParameter(
            name="delivery_date_before",
            type=OpenApiTypes.DATE,
            required=False,
            location=OpenApiParameter.QUERY,
        ),
        OpenApiParameter(
            name="delivery_date_after",
            type=OpenApiTypes.DATE,
            required=False,
            location=OpenApiParameter.QUERY,
        ),
        OpenApiParameter(
            name="ordering",
            type=OpenApiTypes.STR,
            required=False,
            location=OpenApiParameter.QUERY,
            description="Example: `-created_at`, `price`, `area`, `deadline`",
        ),
    ],
    tags=["Properties"],
)

my_properties_list_schema = extend_schema(
    summary="List my properties",
    description=MY_PROPERTIES_LIST_DOC,
    responses={
        200: OpenApiResponse(
            response=PropertyListSerializer,
            description="Paginated list of the authenticated developer's properties.",
            examples=[
                OpenApiExample(
                    "My properties list example",
                    value={
                        "count": 1,
                        "next": None,
                        "previous": None,
                        "results": [
                            {
                                "id": 1,
                                "reference_id": "e52db7e5-77b9-4fd7-a57b-cf0aa5a20ef0",
                                "developer": 10,
                                "type": "apartment",
                                "project": "Skyline",
                                "project_comment": "Первая очередь, вид на парк",
                                "rooms": 2,
                                "purpose": None,
                                "commercial_subtype": None,
                                "address": "Moscow, Tverskaya 1",
                                "area": "52.50",
                                "property_class": "comfort",
                                "price": "12000000.00",
                                "commission_rate": "2.50",
                                "deadline": "2026-10-01",
                                "delivery_date": "2027-03-01",
                                "status": "published",
                                "images": [],
                                "created_at": "2026-02-04T06:00:00Z",
                                "updated_at": "2026-02-04T06:00:00Z",
                                "moderation_status": "approved",
                                "moderation_rejection_reason": None,
                                "is_editable": True,
                            }
                        ],
                    },
                )
            ],
        ),
        401: OpenApiResponse(description="Unauthorized."),
        403: OpenApiResponse(description="Forbidden (not a developer)."),
    },
    parameters=[
        OpenApiParameter(
            "page", OpenApiTypes.INT, required=False, location=OpenApiParameter.QUERY
        ),
        OpenApiParameter(
            "page_size",
            OpenApiTypes.INT,
            required=False,
            location=OpenApiParameter.QUERY,
        ),
        OpenApiParameter(
            "type", OpenApiTypes.STR, required=False, location=OpenApiParameter.QUERY
        ),
        OpenApiParameter(
            "property_class",
            OpenApiTypes.STR,
            required=False,
            location=OpenApiParameter.QUERY,
        ),
        OpenApiParameter(
            "status", OpenApiTypes.STR, required=False, location=OpenApiParameter.QUERY
        ),
        OpenApiParameter(
            "address", OpenApiTypes.STR, required=False, location=OpenApiParameter.QUERY
        ),
        OpenApiParameter(
            "project", OpenApiTypes.STR, required=False, location=OpenApiParameter.QUERY
        ),
        OpenApiParameter(
            "purpose", OpenApiTypes.STR, required=False, location=OpenApiParameter.QUERY
        ),
        OpenApiParameter(
            "commercial_subtype",
            OpenApiTypes.STR,
            required=False,
            location=OpenApiParameter.QUERY,
        ),
        OpenApiParameter(
            "rooms", OpenApiTypes.INT, required=False, location=OpenApiParameter.QUERY
        ),
        OpenApiParameter(
            "price_min",
            OpenApiTypes.NUMBER,
            required=False,
            location=OpenApiParameter.QUERY,
        ),
        OpenApiParameter(
            "price_max",
            OpenApiTypes.NUMBER,
            required=False,
            location=OpenApiParameter.QUERY,
        ),
        OpenApiParameter(
            "area_min",
            OpenApiTypes.NUMBER,
            required=False,
            location=OpenApiParameter.QUERY,
        ),
        OpenApiParameter(
            "area_max",
            OpenApiTypes.NUMBER,
            required=False,
            location=OpenApiParameter.QUERY,
        ),
        OpenApiParameter(
            "delivery_date_before",
            OpenApiTypes.DATE,
            required=False,
            location=OpenApiParameter.QUERY,
        ),
        OpenApiParameter(
            "delivery_date_after",
            OpenApiTypes.DATE,
            required=False,
            location=OpenApiParameter.QUERY,
        ),
        OpenApiParameter(
            "ordering",
            OpenApiTypes.STR,
            required=False,
            location=OpenApiParameter.QUERY,
            description="Example: `-created_at`, `price`, `area`, `deadline`",
        ),
    ],
    tags=["Properties"],
)

properties_create_schema = extend_schema(
    summary="Create property",
    description=PROPERTIES_CREATE_DOC,
    request=PropertyCreateSerializer,
    responses={
        201: OpenApiResponse(
            response=PropertyCreateSerializer,
            description="Property created.",
            examples=[
                OpenApiExample(
                    "Created",
                    value={
                        "id": 1,
                        "reference_id": "e52db7e5-77b9-4fd7-a57b-cf0aa5a20ef0",
                        "type": "apartment",
                        "project": "Skyline",
                        "project_comment": "Первая очередь, вид на парк",
                        "rooms": 2,
                        "purpose": None,
                        "commercial_subtype": None,
                        "address": "Moscow, Tverskaya 1",
                        "area": "52.50",
                        "property_class": "comfort",
                        "price": "12000000.00",
                        "commission_rate": "2.50",
                        "deadline": "2026-10-01",
                        "delivery_date": "2027-03-01",
                        "status": "draft",
                    },
                )
            ],
        ),
        401: OpenApiResponse(
            response=DRFDetailErrorSerializer,
            description="Unauthorized.",
        ),
        403: OpenApiResponse(
            response=DRFDetailErrorSerializer,
            description="Forbidden (only developer can create).",
        ),
        400: OpenApiResponse(description="Validation error."),
    },
    tags=["Properties"],
)

property_detail_schema = extend_schema(
    summary="Get property detail",
    description=PROPERTY_DETAIL_DOC,
    responses={
        200: OpenApiResponse(
            response=PropertyListSerializer,
            description="Property details.",
        ),
        404: OpenApiResponse(description="Not found."),
    },
    tags=["Properties"],
)

property_patch_schema = extend_schema(
    summary="Update property (partial)",
    description=PROPERTY_PATCH_DOC,
    request=PropertyUpdateSerializer,
    responses={
        200: OpenApiResponse(
            response=PropertyUpdateSerializer,
            description="Property updated.",
        ),
        400: OpenApiResponse(
            response=DRFDetailErrorSerializer,
            description="Validation error or property is linked to a blocking auction.",
        ),
        401: OpenApiResponse(
            response=DRFDetailErrorSerializer,
            description="Unauthorized.",
        ),
        403: OpenApiResponse(
            response=DRFDetailErrorSerializer,
            description="Forbidden (only owner).",
        ),
        404: OpenApiResponse(description="Not found."),
    },
    tags=["Properties"],
)

property_images_list_schema = extend_schema(
    summary="List property images",
    description=PROPERTY_IMAGES_LIST_DOC,
    responses={
        200: OpenApiResponse(
            response=PropertyImageSerializer(many=True),
            description="List of images for the property.",
            examples=[
                OpenApiExample(
                    "Images",
                    value=[
                        {
                            "id": 100,
                            "url": "http://host/media/developers/10/properties/1/abc.jpg",
                            "external_url": None,
                            "sort_order": 0,
                            "is_primary": True,
                            "created_at": "2026-02-04T06:10:00Z",
                        }
                    ],
                )
            ],
        ),
        404: OpenApiResponse(description="Property not found."),
    },
    tags=["Properties"],
)

property_images_create_schema = extend_schema(
    summary="Add property image",
    description=PROPERTY_IMAGES_CREATE_DOC,
    request=PropertyImageCreateSerializer,
    responses={
        201: OpenApiResponse(
            response=PropertyImageSerializer,
            description="Image created.",
        ),
        401: OpenApiResponse(
            response=DRFDetailErrorSerializer,
            description="Unauthorized.",
        ),
        403: OpenApiResponse(
            response=DRFDetailErrorSerializer,
            description="Forbidden (only owner).",
        ),
        404: OpenApiResponse(
            response=DRFDetailErrorSerializer,
            description="Not found (your view returns 404 when not owner).",
        ),
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Validation / constraint error.",
            examples=[
                OpenApiExample(
                    "Constraint error",
                    value={"error": "Constraint error. Check sort_order / is_primary."},
                )
            ],
        ),
    },
    tags=["Properties"],
)

property_delete_schema = extend_schema(
    summary="Delete property",
    description=(
        "Delete property.\n\n"
        "Only the property owner (developer) can delete it.\n"
        "Deletion is forbidden if the property is sold or linked to a blocking auction.\n"
        "Blocking auction statuses:\n"
        "- scheduled\n"
        "- active\n"
        "- finished\n\n"
        "Checks apply to both:\n"
        "- OPEN auction relation\n"
        "- CLOSED lot auction relation"
    ),
    responses={
        204: OpenApiResponse(description="Property deleted."),
        400: OpenApiResponse(
            description="Property cannot be deleted because it is sold or linked to a blocking auction."
        ),
        401: OpenApiResponse(description="Unauthorized."),
        403: OpenApiResponse(description="Forbidden (only owner)."),
        404: OpenApiResponse(description="Not found."),
    },
    tags=["Properties"],
)

property_image_delete_schema = extend_schema(
    summary="Delete property image",
    description=PROPERTY_IMAGE_DELETE_DOC,
    responses={
        204: OpenApiResponse(description="Property image deleted."),
        401: OpenApiResponse(
            response=DRFDetailErrorSerializer,
            description="Unauthorized.",
        ),
        403: OpenApiResponse(
            response=DRFDetailErrorSerializer,
            description="Forbidden (only developer can delete images).",
        ),
        404: OpenApiResponse(
            response=DRFDetailErrorSerializer,
            description="Not found (property not found, image not found, or not owner).",
        ),
    },
    tags=["Properties"],
)

property_image_patch_schema = extend_schema(
    summary="Update property image",
    description=PROPERTY_IMAGE_PATCH_DOC,
    request=PropertyImageUpdateSerializer,
    responses={
        200: OpenApiResponse(
            response=PropertyImageSerializer,
            description="Property image updated.",
            examples=[
                OpenApiExample(
                    "Update is_primary",
                    value={
                        "id": 100,
                        "url": "http://host/media/developers/10/properties/1/abc.jpg",
                        "external_url": None,
                        "sort_order": 0,
                        "is_primary": True,
                        "created_at": "2026-02-04T06:10:00Z",
                    },
                ),
                OpenApiExample(
                    "Update sort_order",
                    value={
                        "id": 100,
                        "url": "http://host/media/developers/10/properties/1/abc.jpg",
                        "external_url": None,
                        "sort_order": 5,
                        "is_primary": False,
                        "created_at": "2026-02-04T06:10:00Z",
                    },
                ),
            ],
        ),
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Validation / constraint error.",
            examples=[
                OpenApiExample(
                    "Empty payload",
                    value={"error": "Хотя бы одно поле должно быть передано."},
                ),
                OpenApiExample(
                    "Duplicate sort_order",
                    value={
                        "error": "Ошибка ограничения. Проверьте уникальность sort_order."
                    },
                ),
            ],
        ),
        401: OpenApiResponse(
            response=DRFDetailErrorSerializer,
            description="Unauthorized.",
        ),
        403: OpenApiResponse(
            response=DRFDetailErrorSerializer,
            description="Forbidden (only developer can update images).",
        ),
        404: OpenApiResponse(
            response=DRFDetailErrorSerializer,
            description="Not found (property not found, image not found, or not owner).",
        ),
    },
    tags=["Properties"],
)

my_available_properties_list_schema = extend_schema(
    summary="List my available properties",
    description=MY_AVAILABLE_PROPERTIES_LIST_DOC,
    responses={
        200: OpenApiResponse(
            response=MyAvailablePropertySerializer,
            description="Paginated list of available properties for auction creation.",
            examples=[
                OpenApiExample(
                    "My available properties list example",
                    value={
                        "count": 2,
                        "next": None,
                        "previous": None,
                        "results": [
                            {
                                "id": 1,
                                "reference_id": "e52db7e5-77b9-4fd7-a57b-cf0aa5a20ef0",
                                "type": "apartment",
                                "project": "Skyline",
                                "rooms": 2,
                                "purpose": None,
                                "address": "Moscow, Tverskaya 1",
                                "area": "52.50",
                                "property_class": "comfort",
                                "price": "12000000.00",
                                "deadline": "2026-10-01",
                                "delivery_date": "2027-03-01",
                            },
                            {
                                "id": 2,
                                "reference_id": "cf7407d7-2577-4455-a53f-7d97f85c1f5a",
                                "type": "apartment",
                                "project": "Skyline",
                                "rooms": 2,
                                "purpose": None,
                                "address": "Saint Petersburg, Nevsky 10",
                                "area": "52.50",
                                "property_class": "comfort",
                                "price": "11800000.00",
                                "deadline": "2026-10-01",
                                "delivery_date": "2027-03-01",
                            },
                        ],
                    },
                )
            ],
        ),
        401: OpenApiResponse(description="Unauthorized."),
        403: OpenApiResponse(description="Forbidden (not a developer)."),
    },
    parameters=[
        OpenApiParameter(
            "page", OpenApiTypes.INT, required=False, location=OpenApiParameter.QUERY
        ),
        OpenApiParameter(
            "page_size",
            OpenApiTypes.INT,
            required=False,
            location=OpenApiParameter.QUERY,
        ),
        OpenApiParameter(
            "ordering",
            OpenApiTypes.STR,
            required=False,
            location=OpenApiParameter.QUERY,
            description="Example: `-created_at`, `address`, `area`",
        ),
    ],
    tags=["Properties"],
)

compatible_properties_list_schema = extend_schema(
    summary="List compatible properties for lot creation",
    description=COMPATIBLE_PROPERTIES_LIST_DOC,
    responses={
        200: OpenApiResponse(
            response=MyAvailablePropertySerializer,
            description="Paginated list of compatible properties.",
        ),
        400: OpenApiResponse(
            response=DRFDetailErrorSerializer,
            description="Validation error.",
        ),
        401: OpenApiResponse(description="Unauthorized."),
        403: OpenApiResponse(description="Forbidden (not a developer)."),
    },
    parameters=[
        OpenApiParameter(
            "reference_id",
            OpenApiTypes.UUID,
            required=True,
            location=OpenApiParameter.QUERY,
        ),
        OpenApiParameter(
            "page",
            OpenApiTypes.INT,
            required=False,
            location=OpenApiParameter.QUERY,
        ),
        OpenApiParameter(
            "page_size",
            OpenApiTypes.INT,
            required=False,
            location=OpenApiParameter.QUERY,
        ),
        OpenApiParameter(
            "ordering",
            OpenApiTypes.STR,
            required=False,
            location=OpenApiParameter.QUERY,
            description="Example: `-created_at`, `address`, `area`",
        ),
    ],
    tags=["Properties"],
)
