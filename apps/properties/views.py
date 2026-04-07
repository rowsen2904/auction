from auctions.models import Auction
from auctions.permissions import IsDeveloper
from django.db import IntegrityError, transaction
from django.db.models import Prefetch, Q
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from notifications.services import notify_new_property_pending
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .filters import MyPropertyFilter, PublicPropertyFilter
from .models import Property, PropertyImage
from .pagination import PropertyPagination
from .permissions import IsPropertyOwner
from .schemas import (
    my_available_properties_list_schema,
    my_properties_list_schema,
    properties_create_schema,
    properties_list_schema,
    property_delete_schema,
    property_detail_schema,
    property_image_delete_schema,
    property_image_patch_schema,
    property_images_create_schema,
    property_images_list_schema,
    property_patch_schema,
)
from .serializers import (
    MyAvailablePropertySerializer,
    PropertyCreateSerializer,
    PropertyImageCreateSerializer,
    PropertyImageSerializer,
    PropertyImageUpdateSerializer,
    PropertyListSerializer,
    PropertyUpdateSerializer,
)
from .services.compatibility import (
    BLOCKING_AUCTION_STATUSES,
    compatible_properties_qs,
)

OPEN_AUCTIONS_PREFETCH = Prefetch(
    "open_auctions",
    queryset=Auction.objects.only("id", "real_property_id", "status"),
    to_attr="prefetched_open_auctions",
)

LOT_AUCTIONS_PREFETCH = Prefetch(
    "lot_auctions",
    queryset=Auction.objects.only("id", "status"),
    to_attr="prefetched_lot_auctions",
)


class PropertyListCreateView(generics.ListCreateAPIView):
    pagination_class = PropertyPagination
    filterset_class = PublicPropertyFilter
    ordering_fields = ["price", "created_at", "deadline", "area"]
    ordering = ["-created_at"]

    def get_queryset(self):
        return (
            Property.objects.select_related("owner")
            .prefetch_related(
                "images",
                OPEN_AUCTIONS_PREFETCH,
                LOT_AUCTIONS_PREFETCH,
            )
            .filter(
                moderation_status=Property.ModerationStatuses.APPROVED,
                status__in=[
                    Property.PropertyStatuses.PUBLISHED,
                    Property.PropertyStatuses.SOLD,
                ],
            )
        )

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAuthenticated(), IsDeveloper()]
        return [AllowAny()]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return PropertyCreateSerializer
        return PropertyListSerializer

    def perform_create(self, serializer):
        prop = serializer.save(owner=self.request.user)
        if (
            prop.moderation_status == Property.ModerationStatuses.PENDING
            and prop.status != Property.PropertyStatuses.DRAFT
        ):
            notify_new_property_pending(real_property=prop)

    @properties_list_schema
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @properties_create_schema
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)


class MyPropertiesView(generics.ListAPIView):
    pagination_class = PropertyPagination
    filterset_class = MyPropertyFilter
    ordering_fields = ["price", "created_at", "deadline", "area"]
    ordering = ["-created_at"]
    permission_classes = [IsAuthenticated, IsDeveloper]
    serializer_class = PropertyListSerializer

    def get_queryset(self):
        return (
            Property.objects.select_related("owner")
            .prefetch_related(
                "images",
                OPEN_AUCTIONS_PREFETCH,
                LOT_AUCTIONS_PREFETCH,
            )
            .filter(owner=self.request.user)
        )

    @my_properties_list_schema
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class PropertyDetailView(generics.RetrieveUpdateAPIView):
    queryset = Property.objects.select_related("owner").prefetch_related(
        "images",
        OPEN_AUCTIONS_PREFETCH,
        LOT_AUCTIONS_PREFETCH,
    )
    http_method_names = ["get", "patch", "head", "options"]

    def get_permissions(self):
        if self.request.method == "PATCH":
            return [IsAuthenticated(), IsDeveloper(), IsPropertyOwner()]
        return [AllowAny()]

    def get_serializer_class(self):
        if self.request.method == "PATCH":
            return PropertyUpdateSerializer
        return PropertyListSerializer

    @property_detail_schema
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @property_patch_schema
    def patch(self, request, *args, **kwargs):
        return super().patch(request, *args, **kwargs)

    def perform_update(self, serializer):
        prop = serializer.instance

        has_blocking_open_auction = Auction.objects.filter(
            real_property=prop,
            status__in=BLOCKING_AUCTION_STATUSES,
        ).exists()

        has_blocking_lot_auction = Auction.objects.filter(
            properties=prop,
            status__in=BLOCKING_AUCTION_STATUSES,
        ).exists()

        if has_blocking_open_auction or has_blocking_lot_auction:
            raise ValidationError(
                {"detail": "Нельзя редактировать объект, связанный с аукционом."}
            )

        serializer.save()


class PropertyDeleteView(generics.DestroyAPIView):
    permission_classes = [IsAuthenticated, IsDeveloper, IsPropertyOwner]
    http_method_names = ["delete", "head", "options"]

    def get_queryset(self):
        return Property.objects.only(
            "id",
            "owner_id",
            "status",
            "moderation_status",
            "updated_at",
        )

    def perform_destroy(self, instance: Property) -> None:
        with transaction.atomic():
            prop: Property = get_object_or_404(
                Property.objects.select_for_update().only("id", "owner_id", "status"),
                pk=instance.pk,
            )

            if prop.status == Property.PropertyStatuses.SOLD:
                raise ValidationError(
                    {"error": _("Проданное имущество удалить нельзя.")}
                )

            has_running_open_auction = Auction.objects.filter(
                real_property_id=prop.id,
                status__in=BLOCKING_AUCTION_STATUSES,
            ).exists()

            has_running_lot_auction = Auction.objects.filter(
                properties=prop,
                status__in=BLOCKING_AUCTION_STATUSES,
            ).exists()

            if has_running_open_auction or has_running_lot_auction:
                raise ValidationError(
                    {
                        "error": _(
                            "Объект недвижимости нельзя удалить, пока он связан с аукционом."
                        )
                    }
                )

            prop.delete()

    @property_delete_schema
    def delete(self, request, *args, **kwargs):
        super().delete(request, *args, **kwargs)
        return Response(status=status.HTTP_204_NO_CONTENT)


class PropertyImageListCreateView(generics.GenericAPIView):
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAuthenticated(), IsDeveloper()]
        return [AllowAny()]

    def get_property(self) -> Property:
        return get_object_or_404(
            Property.objects.select_related("owner"),
            id=self.kwargs["pk"],
        )

    @property_images_list_schema
    def get(self, request, *args, **kwargs):
        prop = self.get_property()
        imgs = prop.images.all().order_by("sort_order", "id")
        ser = PropertyImageSerializer(imgs, many=True, context={"request": request})
        return Response(ser.data, status=status.HTTP_200_OK)

    @property_images_create_schema
    def post(self, request, *args, **kwargs):
        prop = self.get_property()

        if prop.owner_id != request.user.id:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        ser = PropertyImageCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        data = ser.validated_data
        is_primary = bool(data.get("is_primary", False))
        sort_order = data.get("sort_order", 0)

        try:
            with transaction.atomic():
                if is_primary:
                    PropertyImage.objects.filter(property=prop, is_primary=True).update(
                        is_primary=False
                    )

                img = PropertyImage.objects.create(
                    property=prop,
                    image=data.get("image"),
                    external_url=data.get("external_url"),
                    sort_order=sort_order,
                    is_primary=is_primary,
                )

        except IntegrityError:
            return Response(
                {"error": "Ошибка ограничения. Проверьте sort_order / is_primary."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        out = PropertyImageSerializer(img, context={"request": request})
        return Response(out.data, status=status.HTTP_201_CREATED)


class PropertyImageUpdateView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated, IsDeveloper]
    serializer_class = PropertyImageUpdateSerializer
    parser_classes = [JSONParser]
    http_method_names = ["patch", "delete", "head", "options"]

    def get_property(self) -> Property:
        return get_object_or_404(
            Property.objects.only("id", "owner_id"),
            id=self.kwargs["pk"],
            owner=self.request.user,
        )

    def get_image(self, prop: Property) -> PropertyImage:
        return get_object_or_404(
            PropertyImage.objects.select_related("property"),
            id=self.kwargs["image_id"],
            property=prop,
        )

    @property_image_patch_schema
    def patch(self, request, *args, **kwargs):
        prop = self.get_property()
        image = self.get_image(prop)

        serializer = self.get_serializer(image, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        validated_data = serializer.validated_data

        try:
            with transaction.atomic():
                locked_image = PropertyImage.objects.select_for_update().get(
                    pk=image.pk
                )

                update_fields = []

                if validated_data.get("is_primary") is True:
                    PropertyImage.objects.filter(
                        property=prop,
                        is_primary=True,
                    ).exclude(pk=locked_image.pk).update(is_primary=False)

                    locked_image.is_primary = True
                    update_fields.append("is_primary")

                elif validated_data.get("is_primary") is False:
                    locked_image.is_primary = False
                    update_fields.append("is_primary")

                if "sort_order" in validated_data:
                    locked_image.sort_order = validated_data["sort_order"]
                    update_fields.append("sort_order")

                if update_fields:
                    locked_image.save(update_fields=update_fields)

        except IntegrityError:
            return Response(
                {"error": _("Ошибка ограничения. Проверьте уникальность sort_order.")},
                status=status.HTTP_400_BAD_REQUEST,
            )

        locked_image.refresh_from_db()
        out = PropertyImageSerializer(locked_image, context={"request": request})
        return Response(out.data, status=status.HTTP_200_OK)

    @property_image_delete_schema
    def delete(self, request, *args, **kwargs):
        prop = self.get_property()

        with transaction.atomic():
            image = get_object_or_404(
                PropertyImage.objects.select_for_update(),
                id=self.kwargs["image_id"],
                property=prop,
            )

            was_primary = image.is_primary
            image.delete()

            if was_primary:
                next_image = (
                    PropertyImage.objects.select_for_update()
                    .filter(property=prop)
                    .order_by("sort_order", "id")
                    .first()
                )

                if next_image:
                    next_image.is_primary = True
                    next_image.save(update_fields=["is_primary"])

        return Response(status=status.HTTP_204_NO_CONTENT)


class MyAvailablePropertiesView(generics.ListAPIView):
    pagination_class = PropertyPagination
    permission_classes = [IsAuthenticated, IsDeveloper]
    serializer_class = MyAvailablePropertySerializer
    ordering_fields = ["created_at", "address", "area"]
    ordering = ["-created_at"]

    def get_queryset(self):
        return (
            Property.objects.filter(
                owner=self.request.user,
                moderation_status=Property.ModerationStatuses.APPROVED,
                status=Property.PropertyStatuses.PUBLISHED,
            )
            .exclude(
                Q(open_auctions__status__in=BLOCKING_AUCTION_STATUSES)
                | Q(lot_auctions__status__in=BLOCKING_AUCTION_STATUSES)
            )
            .only(
                "id",
                "reference_id",
                "type",
                "address",
                "area",
                "price",
                "property_class",
                "created_at",
            )
            .order_by(*self.ordering)
            .distinct()
        )

    @my_available_properties_list_schema
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class CompatiblePropertiesView(generics.ListAPIView):
    pagination_class = PropertyPagination
    permission_classes = [IsAuthenticated, IsDeveloper]
    serializer_class = MyAvailablePropertySerializer
    ordering_fields = ["created_at", "address", "area"]
    ordering = ["-created_at"]

    def get_queryset(self):
        reference_id = self.request.query_params.get("reference_id")
        if not reference_id:
            raise ValidationError({"reference_id": "Это поле обязательно."})

        _, qs = compatible_properties_qs(
            user=self.request.user,
            reference_id=reference_id,
        )
        return qs
