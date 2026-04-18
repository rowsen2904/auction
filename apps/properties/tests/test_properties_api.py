from datetime import timedelta
from decimal import Decimal

from auctions.models import Auction
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test.client import BytesIO
from django.utils import timezone
from PIL import Image
from properties.models import Property
from rest_framework import status
from rest_framework.test import APITestCase

User = get_user_model()

BASE = "/api/v1/properties/"
BASE_MY_AVAILABLE = "/api/v1/properties/my/available/"


def make_png_file(name: str = "img.png") -> SimpleUploadedFile:
    buf = BytesIO()
    img = Image.new("RGBA", (10, 10), (255, 0, 0, 0))
    img.save(buf, format="PNG")
    buf.seek(0)
    return SimpleUploadedFile(
        name=name,
        content=buf.read(),
        content_type="image/png",
    )


class BasePropertyTestCase(APITestCase):
    def setUp(self):
        self.dev1 = User.objects.create_user(
            email="dev1@test.com",
            password="StrongPass123!",
            role=User.Roles.DEVELOPER,
            is_active=True,
        )
        self.dev2 = User.objects.create_user(
            email="dev2@test.com",
            password="StrongPass123!",
            role=User.Roles.DEVELOPER,
            is_active=True,
        )
        self.broker = User.objects.create_user(
            email="broker@test.com",
            password="StrongPass123!",
            role=User.Roles.BROKER,
            is_active=True,
        )

    def _create_property(
        self,
        owner,
        *,
        p_type="apartment",
        address="Moscow, Tverskaya 1",
        area=Decimal("52.50"),
        p_class="comfort",
        price=Decimal("12000000.00"),
        status_val=Property.PropertyStatuses.PUBLISHED,
        moderation_status_val=Property.ModerationStatuses.APPROVED,
        moderation_rejection_reason=None,
    ) -> Property:
        return Property.objects.create(
            owner=owner,
            type=p_type,
            address=address,
            area=area,
            property_class=p_class,
            price=price,
            status=status_val,
            moderation_status=moderation_status_val,
            moderation_rejection_reason=moderation_rejection_reason,
        )

    def _create_auction(
        self,
        owner,
        prop: Property,
        *,
        status_val=Auction.Status.SCHEDULED,
    ) -> Auction:
        now = timezone.now()
        return Auction.objects.create(
            real_property=prop,
            owner=owner,
            mode=Auction.Mode.OPEN,
            min_price=prop.price,
            start_date=now + timedelta(days=1),
            end_date=now + timedelta(days=2),
            status=status_val,
            min_bid_increment=Decimal("100.00"),
        )


class PropertyAPITests(BasePropertyTestCase):
    def test_create_property_requires_auth(self):
        resp = self.client.post(
            BASE,
            data={
                "type": "apartment",
                "address": "Moscow, New Address 1",
                "area": "50.00",
                "property_class": "comfort",
                "price": "1000000.00",
                "status": "draft",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_create_property_requires_developer(self):
        self.client.force_authenticate(user=self.broker)

        resp = self.client.post(
            BASE,
            data={
                "type": "apartment",
                "address": "Moscow, New Address 2",
                "area": "50.00",
                "property_class": "comfort",
                "price": "1000000.00",
                "status": "draft",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_create_property_success_sets_owner(self):
        self.client.force_authenticate(user=self.dev1)

        address = "Moscow, Created By Dev1"
        project_comment = "Комментарий к проекту: первая очередь"
        resp = self.client.post(
            BASE,
            data={
                "type": "apartment",
                "address": address,
                "project_comment": project_comment,
                "area": "50.00",
                "property_class": "comfort",
                "price": "1000000.00",
                "status": "draft",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        prop = Property.objects.get(address=address)
        self.assertEqual(prop.owner_id, self.dev1.id)
        self.assertEqual(prop.project_comment, project_comment)
        self.assertEqual(resp.data["project_comment"], project_comment)

    def test_create_property_null_project_comment_saved_as_empty_string(self):
        self.client.force_authenticate(user=self.dev1)

        address = "Moscow, Null Project Comment"
        resp = self.client.post(
            BASE,
            data={
                "type": "apartment",
                "address": address,
                "project_comment": None,
                "area": "50.00",
                "property_class": "comfort",
                "price": "1000000.00",
                "status": "draft",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data["project_comment"], "")

        prop = Property.objects.get(address=address)
        self.assertEqual(prop.project_comment, "")

    def test_create_commercial_property_with_subtype(self):
        self.client.force_authenticate(user=self.dev1)

        address = "Moscow, Commercial Retail"
        resp = self.client.post(
            BASE,
            data={
                "type": "commercial",
                "address": address,
                "commercial_subtype": "retail",
                "area": "120.00",
                "property_class": "business",
                "price": "30000000.00",
                "status": "draft",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data["commercial_subtype"], "retail")

        prop = Property.objects.get(address=address)
        self.assertEqual(prop.commercial_subtype, "retail")

    def test_create_commercial_property_without_subtype_rejected(self):
        self.client.force_authenticate(user=self.dev1)

        resp = self.client.post(
            BASE,
            data={
                "type": "commercial",
                "address": "Moscow, Commercial No Subtype",
                "area": "120.00",
                "property_class": "business",
                "price": "30000000.00",
                "status": "draft",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("commercial_subtype", resp.data)

    def test_create_non_commercial_ignores_subtype(self):
        self.client.force_authenticate(user=self.dev1)

        address = "Moscow, Apartment Ignores Subtype"
        resp = self.client.post(
            BASE,
            data={
                "type": "apartment",
                "address": address,
                "commercial_subtype": "retail",
                "area": "50.00",
                "property_class": "comfort",
                "price": "1000000.00",
                "status": "draft",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertIsNone(resp.data["commercial_subtype"])

        prop = Property.objects.get(address=address)
        self.assertIsNone(prop.commercial_subtype)

    def test_list_properties_paginated(self):
        for i in range(21):
            self._create_property(
                self.dev1,
                address=f"Moscow, Paginated {i}",
                price=Decimal("1000000.00") + i,
            )

        resp = self.client.get(BASE, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        self.assertIn("count", resp.data)
        self.assertIn("results", resp.data)
        self.assertEqual(resp.data["count"], 21)
        self.assertEqual(len(resp.data["results"]), 20)
        self.assertIsNotNone(resp.data["next"])

    def test_filters_work_type_and_price_range(self):
        self._create_property(
            self.dev1,
            p_type="house",
            address="House A",
            price=Decimal("9000000.00"),
        )
        self._create_property(
            self.dev1,
            p_type="house",
            address="House B",
            price=Decimal("15000000.00"),
        )
        self._create_property(
            self.dev1,
            p_type="apartment",
            address="Apt C",
            price=Decimal("7000000.00"),
        )

        resp = self.client.get(
            f"{BASE}?type=house&price_min=10000000&price_max=20000000",
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["count"], 1)
        self.assertEqual(resp.data["results"][0]["type"], "house")
        self.assertEqual(resp.data["results"][0]["address"], "House B")

    def test_list_excludes_not_approved_even_if_published(self):
        self._create_property(
            self.dev1,
            address="Approved Visible",
            status_val=Property.PropertyStatuses.PUBLISHED,
            moderation_status_val=Property.ModerationStatuses.APPROVED,
        )
        self._create_property(
            self.dev1,
            address="Pending Hidden",
            status_val=Property.PropertyStatuses.PUBLISHED,
            moderation_status_val=Property.ModerationStatuses.PENDING,
        )
        self._create_property(
            self.dev1,
            address="Rejected Hidden",
            status_val=Property.PropertyStatuses.PUBLISHED,
            moderation_status_val=Property.ModerationStatuses.REJECTED,
        )

        resp = self.client.get(BASE, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["count"], 1)
        self.assertEqual(resp.data["results"][0]["address"], "Approved Visible")

    def test_list_includes_sold_if_approved(self):
        self._create_property(
            self.dev1,
            address="Sold Visible",
            status_val=Property.PropertyStatuses.SOLD,
            moderation_status_val=Property.ModerationStatuses.APPROVED,
        )

        resp = self.client.get(BASE, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["count"], 1)
        self.assertEqual(resp.data["results"][0]["status"], "sold")

    def test_ordering_by_price_desc(self):
        self._create_property(self.dev1, address="Cheap", price=Decimal("100.00"))
        self._create_property(self.dev1, address="Expensive", price=Decimal("999.00"))

        resp = self.client.get(f"{BASE}?ordering=-price", format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["count"], 2)
        self.assertEqual(resp.data["results"][0]["address"], "Expensive")
        self.assertEqual(resp.data["results"][1]["address"], "Cheap")

    def test_patch_property_only_owner(self):
        prop = self._create_property(self.dev1, address="Only Owner Can Patch")

        self.client.force_authenticate(user=self.dev2)
        resp = self.client.patch(
            f"{BASE}{prop.id}/",
            data={"price": "9999999.00"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_patch_property_owner_can_update(self):
        prop = self._create_property(self.dev1, address="Owner Patch OK")

        self.client.force_authenticate(user=self.dev1)
        resp = self.client.patch(
            f"{BASE}{prop.id}/",
            data={"price": "9999999.00"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        prop.refresh_from_db()
        self.assertEqual(prop.price, Decimal("9999999.00"))

    def test_patch_property_project_comment_resets_moderation_status_to_pending(self):
        prop = self._create_property(
            self.dev1,
            address="Project Comment Patch",
            moderation_status_val=Property.ModerationStatuses.APPROVED,
        )

        self.client.force_authenticate(user=self.dev1)
        resp = self.client.patch(
            f"{BASE}{prop.id}/",
            data={"project_comment": "Обновлённый комментарий"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["project_comment"], "Обновлённый комментарий")

        prop.refresh_from_db()
        self.assertEqual(prop.project_comment, "Обновлённый комментарий")
        self.assertEqual(prop.moderation_status, Property.ModerationStatuses.PENDING)

    def test_patch_property_resets_moderation_status_to_pending_on_change(self):
        prop = self._create_property(
            self.dev1,
            address="Moderation Reset On Change",
            price=Decimal("12000000.00"),
            moderation_status_val=Property.ModerationStatuses.APPROVED,
        )

        self.client.force_authenticate(user=self.dev1)
        resp = self.client.patch(
            f"{BASE}{prop.id}/",
            data={"price": "9999999.00"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        prop.refresh_from_db()
        self.assertEqual(prop.price, Decimal("9999999.00"))
        self.assertEqual(prop.moderation_status, Property.ModerationStatuses.PENDING)

    def test_patch_property_does_not_reset_moderation_status_when_value_not_changed(
        self,
    ):
        prop = self._create_property(
            self.dev1,
            address="Moderation Not Reset Without Change",
            price=Decimal("12000000.00"),
            moderation_status_val=Property.ModerationStatuses.APPROVED,
        )

        self.client.force_authenticate(user=self.dev1)
        resp = self.client.patch(
            f"{BASE}{prop.id}/",
            data={"price": "12000000.00"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        prop.refresh_from_db()
        self.assertEqual(prop.price, Decimal("12000000.00"))
        self.assertEqual(prop.moderation_status, Property.ModerationStatuses.APPROVED)

    def test_patch_property_clears_moderation_rejection_reason_on_change(self):
        prop = self._create_property(
            self.dev1,
            address="Clear Rejection Reason On Change",
            price=Decimal("12000000.00"),
            moderation_status_val=Property.ModerationStatuses.REJECTED,
            moderation_rejection_reason="Old rejection reason",
        )

        self.client.force_authenticate(user=self.dev1)
        resp = self.client.patch(
            f"{BASE}{prop.id}/",
            data={"price": "9999999.00"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        prop.refresh_from_db()
        self.assertEqual(prop.price, Decimal("9999999.00"))
        self.assertEqual(prop.moderation_status, Property.ModerationStatuses.PENDING)
        self.assertIsNone(prop.moderation_rejection_reason)

    def test_patch_property_does_not_clear_rejection_reason_when_value_not_changed(
        self,
    ):
        prop = self._create_property(
            self.dev1,
            address="Keep Rejection Reason Without Change",
            price=Decimal("12000000.00"),
            moderation_status_val=Property.ModerationStatuses.REJECTED,
            moderation_rejection_reason="Still valid rejection reason",
        )

        self.client.force_authenticate(user=self.dev1)
        resp = self.client.patch(
            f"{BASE}{prop.id}/",
            data={"price": "12000000.00"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        prop.refresh_from_db()
        self.assertEqual(prop.price, Decimal("12000000.00"))
        self.assertEqual(prop.moderation_status, Property.ModerationStatuses.REJECTED)
        self.assertEqual(
            prop.moderation_rejection_reason,
            "Still valid rejection reason",
        )

    def test_list_property_has_is_editable_true_when_not_in_auction(self):
        prop = self._create_property(
            self.dev1,
            address="No Auction Editable",
        )

        resp = self.client.get(BASE, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        item = next(x for x in resp.data["results"] if x["id"] == prop.id)
        self.assertIn("is_editable", item)
        self.assertTrue(item["is_editable"])

    def test_list_property_has_is_editable_false_when_auction_scheduled(self):
        prop = self._create_property(
            self.dev1,
            address="Scheduled Auction Not Editable",
        )
        self._create_auction(
            self.dev1,
            prop,
            status_val=Auction.Status.SCHEDULED,
        )

        resp = self.client.get(BASE, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        item = next(x for x in resp.data["results"] if x["id"] == prop.id)
        self.assertIn("is_editable", item)
        self.assertFalse(item["is_editable"])

    def test_list_property_has_is_editable_false_when_auction_active(self):
        prop = self._create_property(
            self.dev1,
            address="Active Auction Not Editable",
        )
        self._create_auction(
            self.dev1,
            prop,
            status_val=Auction.Status.ACTIVE,
        )

        resp = self.client.get(BASE, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        item = next(x for x in resp.data["results"] if x["id"] == prop.id)
        self.assertIn("is_editable", item)
        self.assertFalse(item["is_editable"])

    def test_list_property_has_is_editable_false_when_auction_finished(self):
        prop = self._create_property(
            self.dev1,
            address="Finished Auction Not Editable",
        )
        self._create_auction(
            self.dev1,
            prop,
            status_val=Auction.Status.FINISHED,
        )

        resp = self.client.get(BASE, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        item = next(x for x in resp.data["results"] if x["id"] == prop.id)
        self.assertIn("is_editable", item)
        self.assertFalse(item["is_editable"])

    def test_list_property_has_is_editable_true_when_auction_cancelled(self):
        prop = self._create_property(
            self.dev1,
            address="Cancelled Auction Editable",
        )
        self._create_auction(
            self.dev1,
            prop,
            status_val=Auction.Status.CANCELLED,
        )

        resp = self.client.get(BASE, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        item = next(x for x in resp.data["results"] if x["id"] == prop.id)
        self.assertIn("is_editable", item)
        self.assertTrue(item["is_editable"])

    def test_detail_property_has_is_editable_true_when_not_in_auction(self):
        prop = self._create_property(
            self.dev1,
            address="Detail No Auction Editable",
        )

        resp = self.client.get(f"{BASE}{prop.id}/", format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("is_editable", resp.data)
        self.assertTrue(resp.data["is_editable"])

    def test_detail_property_has_is_editable_false_when_auction_scheduled(self):
        prop = self._create_property(
            self.dev1,
            address="Detail Scheduled Auction Not Editable",
        )
        self._create_auction(
            self.dev1,
            prop,
            status_val=Auction.Status.SCHEDULED,
        )

        resp = self.client.get(f"{BASE}{prop.id}/", format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("is_editable", resp.data)
        self.assertFalse(resp.data["is_editable"])

    def test_detail_property_has_is_editable_true_when_auction_cancelled(self):
        prop = self._create_property(
            self.dev1,
            address="Detail Cancelled Auction Editable",
        )
        self._create_auction(
            self.dev1,
            prop,
            status_val=Auction.Status.CANCELLED,
        )

        resp = self.client.get(f"{BASE}{prop.id}/", format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("is_editable", resp.data)
        self.assertTrue(resp.data["is_editable"])

class MyAvailablePropertiesAPITests(BasePropertyTestCase):
    def test_my_available_properties_requires_auth(self):
        resp = self.client.get(BASE_MY_AVAILABLE, format="json")
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_my_available_properties_requires_developer(self):
        self.client.force_authenticate(user=self.broker)

        resp = self.client.get(BASE_MY_AVAILABLE, format="json")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_my_available_properties_returns_only_current_developer_properties(self):
        self.client.force_authenticate(user=self.dev1)

        self._create_property(self.dev1, address="Dev1 Property 1")
        self._create_property(self.dev1, address="Dev1 Property 2")
        self._create_property(self.dev2, address="Dev2 Hidden Property")

        resp = self.client.get(BASE_MY_AVAILABLE, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["count"], 2)

        addresses = [item["address"] for item in resp.data["results"]]
        self.assertIn("Dev1 Property 1", addresses)
        self.assertIn("Dev1 Property 2", addresses)
        self.assertNotIn("Dev2 Hidden Property", addresses)

    def test_my_available_properties_includes_only_approved_and_published(self):
        self.client.force_authenticate(user=self.dev1)

        self._create_property(
            self.dev1,
            address="Visible Approved Published",
            status_val=Property.PropertyStatuses.PUBLISHED,
            moderation_status_val=Property.ModerationStatuses.APPROVED,
        )
        self._create_property(
            self.dev1,
            address="Hidden Pending",
            status_val=Property.PropertyStatuses.PUBLISHED,
            moderation_status_val=Property.ModerationStatuses.PENDING,
        )
        self._create_property(
            self.dev1,
            address="Hidden Rejected",
            status_val=Property.PropertyStatuses.PUBLISHED,
            moderation_status_val=Property.ModerationStatuses.REJECTED,
        )
        self._create_property(
            self.dev1,
            address="Hidden Draft",
            status_val=Property.PropertyStatuses.DRAFT,
            moderation_status_val=Property.ModerationStatuses.APPROVED,
        )
        self._create_property(
            self.dev1,
            address="Hidden Sold",
            status_val=Property.PropertyStatuses.SOLD,
            moderation_status_val=Property.ModerationStatuses.APPROVED,
        )
        self._create_property(
            self.dev1,
            address="Hidden Archived",
            status_val=Property.PropertyStatuses.ARCHIVED,
            moderation_status_val=Property.ModerationStatuses.APPROVED,
        )

        resp = self.client.get(BASE_MY_AVAILABLE, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["count"], 1)
        self.assertEqual(
            resp.data["results"][0]["address"],
            "Visible Approved Published",
        )

    def test_my_available_properties_excludes_properties_already_in_auction(self):
        self.client.force_authenticate(user=self.dev1)

        available_prop = self._create_property(
            self.dev1,
            address="Available Property",
        )
        busy_prop = self._create_property(
            self.dev1,
            address="Auction Hidden Property",
        )
        self._create_auction(self.dev1, busy_prop)

        resp = self.client.get(BASE_MY_AVAILABLE, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["count"], 1)
        self.assertEqual(resp.data["results"][0]["id"], available_prop.id)
        self.assertEqual(resp.data["results"][0]["address"], "Available Property")

    def test_my_available_properties_returns_expected_fields(self):
        self.client.force_authenticate(user=self.dev1)

        self._create_property(
            self.dev1,
            address="Field Check Property",
            area=Decimal("77.70"),
            price=Decimal("5550000.00"),
            p_type="apartment",
            p_class="comfort",
        )

        resp = self.client.get(BASE_MY_AVAILABLE, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["count"], 1)

        item = resp.data["results"][0]
        self.assertEqual(
            set(item.keys()),
            {
                "id",
                "reference_id",
                "type",
                "address",
                "area",
                "price",
                "property_class",
            },
        )
        self.assertEqual(item["address"], "Field Check Property")
        self.assertEqual(item["area"], "77.70")
        self.assertEqual(item["price"], "5550000.00")
        self.assertEqual(item["type"], "apartment")
        self.assertEqual(item["property_class"], "comfort")
        self.assertIsNotNone(item["reference_id"])

    def test_my_available_properties_paginated(self):
        self.client.force_authenticate(user=self.dev1)

        for i in range(21):
            self._create_property(
                self.dev1,
                address=f"Available Paginated {i}",
                area=Decimal("50.00") + i,
            )

        resp = self.client.get(BASE_MY_AVAILABLE, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        self.assertIn("count", resp.data)
        self.assertIn("results", resp.data)
        self.assertEqual(resp.data["count"], 21)
        self.assertEqual(len(resp.data["results"]), 20)
        self.assertIsNotNone(resp.data["next"])

    def test_my_available_properties_ordering_by_area_desc(self):
        self.client.force_authenticate(user=self.dev1)

        self._create_property(
            self.dev1,
            address="Small Area",
            area=Decimal("40.00"),
        )
        self._create_property(
            self.dev1,
            address="Big Area",
            area=Decimal("90.00"),
        )

        resp = self.client.get(f"{BASE_MY_AVAILABLE}?ordering=-area", format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["count"], 2)
        self.assertEqual(resp.data["results"][0]["address"], "Big Area")
        self.assertEqual(resp.data["results"][1]["address"], "Small Area")

    def test_create_land_property_without_property_class_success(self):
        self.client.force_authenticate(user=self.dev1)

        address = "Land Without Class"
        resp = self.client.post(
            BASE,
            data={
                "type": "land",
                "address": address,
                "area": "50.00",
                "price": "1000000.00",
                "status": "draft",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        prop = Property.objects.get(address=address)
        self.assertEqual(prop.type, "land")
        self.assertIsNone(prop.property_class)

    def test_create_non_land_property_without_property_class_returns_400(self):
        self.client.force_authenticate(user=self.dev1)

        resp = self.client.post(
            BASE,
            data={
                "type": "apartment",
                "address": "Apartment Without Class",
                "area": "50.00",
                "price": "1000000.00",
                "status": "draft",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("property_class", resp.data)

    def test_patch_property_type_to_land_clears_property_class(self):
        prop = self._create_property(
            self.dev1,
            p_type="apartment",
            p_class="comfort",
            address="Patch To Land",
        )

        self.client.force_authenticate(user=self.dev1)
        resp = self.client.patch(
            f"{BASE}{prop.id}/",
            data={"type": "land"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        prop.refresh_from_db()
        self.assertEqual(prop.type, "land")
        self.assertIsNone(prop.property_class)

    def test_patch_land_property_to_non_land_without_property_class_returns_400(self):
        prop = self._create_property(
            self.dev1,
            p_type="land",
            p_class=None,
            address="Land To Apartment Without Class",
        )

        self.client.force_authenticate(user=self.dev1)
        resp = self.client.patch(
            f"{BASE}{prop.id}/",
            data={"type": "apartment"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("property_class", resp.data)
