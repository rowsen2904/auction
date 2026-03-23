from auctions.models import Auction
from auctions.permissions import IsDeveloper
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .filters import PropertyFilter
from .models import Property, PropertyImage
from .pagination import PropertyPagination
from .permissions import IsPropertyOwner
from .schemas import (
    my_properties_list_schema,
    properties_create_schema,
    properties_list_schema,
    property_delete_schema,
    property_detail_schema,
    property_images_create_schema,
    property_images_list_schema,
    property_patch_schema,
)
from .serializers import (
    PropertyCreateSerializer,
    PropertyImageCreateSerializer,
    PropertyImageSerializer,
    PropertyImageUpdateSerializer,
    PropertyListSerializer,
    PropertyUpdateSerializer,
)


class PropertyListCreateView(generics.ListCreateAPIView):
    pagination_class = PropertyPagination
    filterset_class = PropertyFilter
    ordering_fields = ["price", "created_at", "deadline", "area"]
    ordering = ["-created_at"]

    def get_queryset(self):
        return (
            Property.objects.select_related("owner")
            .prefetch_related("images")
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
        # Set owner from request.user
        serializer.save(owner=self.request.user)

    @properties_list_schema
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @properties_create_schema
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)


class MyPropertiesView(generics.ListAPIView):
    pagination_class = PropertyPagination
    filterset_class = PropertyFilter
    ordering_fields = ["price", "created_at", "deadline", "area"]
    ordering = ["-created_at"]
    permission_classes = [IsAuthenticated, IsDeveloper]
    serializer_class = PropertyListSerializer

    def get_queryset(self):
        return (
            Property.objects.select_related("owner")
            .prefetch_related("images")
            .filter(owner=self.request.user)
        )

    @my_properties_list_schema
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class PropertyDetailView(generics.RetrieveUpdateAPIView):
    queryset = Property.objects.select_related("owner").prefetch_related("images")
    http_method_names = ["get", "patch", "head", "options"]

    def get_permissions(self):
        if self.request.method in ("PATCH",):
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
                Property.objects.select_for_update().only("id", "owner_id"),
                pk=instance.pk,
            )

            if prop.status == Property.PropertyStatuses.SOLD:
                raise ValidationError(
                    {"error": _("Проданное имущество удалить нельзя.")}
                )

            has_running_auction = Auction.objects.filter(
                real_property_id=prop.id,
                status__in=[
                    Auction.Status.SCHEDULED,
                    Auction.Status.ACTIVE,
                    Auction.Status.FINISHED,
                ],
            ).exists()

            if has_running_auction:
                raise ValidationError(
                    {
                        "error": _(
                            "Объект недвижимости нельзя удалить, "
                            "пока он связан с активным аукционом."
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
        prop = get_object_or_404(
            Property.objects.select_related("owner"),
            id=self.kwargs["pk"],
        )
        return prop

    @property_images_list_schema
    def get(self, request, *args, **kwargs):
        prop = self.get_property()
        imgs = prop.images.all().order_by("sort_order", "id")
        ser = PropertyImageSerializer(imgs, many=True, context={"request": request})
        return Response(ser.data, status=status.HTTP_200_OK)

    @property_images_create_schema
    def post(self, request, *args, **kwargs):
        prop = self.get_property()

        # Object-level permission: only owner can upload
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
                    # Ensure only one primary per property
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
            # Unique sort_order / one primary per property constraints
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
