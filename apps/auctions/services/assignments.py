from __future__ import annotations

from auctions.models import Auction, Bid
from deals.models import Deal
from deals.services import create_deal_from_bid
from django.db import transaction
from rest_framework.exceptions import ValidationError


def select_closed_auction_winners(
    *, auction: Auction, broker_ids: list[int]
) -> list[Bid]:
    if auction.mode != Auction.Mode.CLOSED:
        raise ValidationError(
            {
                "detail": "Выбор нескольких победителей доступен только для закрытого аукциона."
            }
        )

    if auction.status != Auction.Status.FINISHED:
        raise ValidationError(
            {"detail": "Выбирать победителей можно только после завершения аукциона."}
        )

    broker_ids = list(dict.fromkeys(broker_ids))
    if not broker_ids:
        raise ValidationError({"broker_ids": "Нужно выбрать хотя бы одного брокера."})

    bids = list(
        Bid.objects.filter(
            auction_id=auction.id,
            is_sealed=True,
            broker_id__in=broker_ids,
        ).select_related("broker")
    )

    found_broker_ids = {bid.broker_id for bid in bids}
    missing = [
        broker_id for broker_id in broker_ids if broker_id not in found_broker_ids
    ]
    if missing:
        raise ValidationError(
            {"broker_ids": f"Не найдены ставки для брокеров: {missing}"}
        )

    with transaction.atomic():
        auction.shortlisted_bids.set([bid.id for bid in bids])

        # auto-skip assign screen: 1 property + 1 selected winner
        lot_properties = list(auction.properties.all().only("id", "price"))
        existing_deals = Deal.objects.filter(auction_id=auction.id).exists()

        if len(lot_properties) == 1 and len(bids) == 1 and not existing_deals:
            create_deal_from_bid(
                auction=auction,
                bid=bids[0],
                real_property=lot_properties[0],
            )

        # Set winner_bid on auction when single winner selected
        if len(bids) == 1:
            auction.winner_bid = bids[0]
            auction.save(update_fields=["winner_bid_id"])

    return bids


def assign_closed_auction_properties(
    *, auction: Auction, assignments: list[dict]
) -> list[Deal]:
    """
    assignments = [
      {"broker_id": 10, "property_ids": [1, 2]},
      {"broker_id": 11, "property_ids": [3]},
    ]
    """
    if auction.mode != Auction.Mode.CLOSED:
        raise ValidationError(
            {"detail": "Распределение доступно только для закрытого аукциона."}
        )

    if auction.status != Auction.Status.FINISHED:
        raise ValidationError(
            {"detail": "Распределять объекты можно только после завершения аукциона."}
        )

    if Deal.objects.filter(auction_id=auction.id).exists():
        raise ValidationError({"detail": "Сделки по этому аукциону уже созданы."})

    winner_bids = list(
        auction.shortlisted_bids.select_related("broker").filter(is_sealed=True)
    )
    if not winner_bids:
        raise ValidationError({"detail": "Сначала выберите победителей."})

    winner_bid_by_broker_id = {bid.broker_id: bid for bid in winner_bids}

    lot_properties = list(auction.properties.all().only("id", "price"))
    lot_property_by_id = {prop.id: prop for prop in lot_properties}
    lot_property_ids = set(lot_property_by_id.keys())

    seen_property_ids: set[int] = set()
    created_deals: list[Deal] = []

    with transaction.atomic():
        for item in assignments:
            broker_id = int(item["broker_id"])
            property_ids = [int(x) for x in item.get("property_ids", [])]

            if broker_id not in winner_bid_by_broker_id:
                raise ValidationError(
                    {
                        "detail": f"Брокер {broker_id} не входит в число выбранных победителей."
                    }
                )

            if not property_ids:
                raise ValidationError(
                    {"detail": f"Для брокера {broker_id} не переданы property_ids."}
                )

            for property_id in property_ids:
                if property_id not in lot_property_ids:
                    raise ValidationError(
                        {
                            "detail": f"Объект {property_id} не принадлежит этому аукциону."
                        }
                    )

                if property_id in seen_property_ids:
                    raise ValidationError(
                        {"detail": f"Объект {property_id} назначен более одного раза."}
                    )

                seen_property_ids.add(property_id)

                created_deals.append(
                    create_deal_from_bid(
                        auction=auction,
                        bid=winner_bid_by_broker_id[broker_id],
                        real_property=lot_property_by_id[property_id],
                    )
                )

    if seen_property_ids != lot_property_ids:
        missing = sorted(lot_property_ids - seen_property_ids)
        raise ValidationError(
            {"detail": f"Распределены не все объекты лота. Остались: {missing}"}
        )

    return created_deals
