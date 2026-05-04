"""
Short-lived JWT tokens for auth-gated file downloads.

Why: file URLs are emitted in JSON API responses and end up in <a href> on
the frontend. <a> requests don't carry the JWT Authorization header. Cookie
auth would conflict with the existing Bearer-only setup. Solution: per-file
JWT signed at response-render time, with a 10 min TTL, embedded as ?t=... in
the download URL. Server validates token + that the requesting user matches
the embedded subject + that the requested object is the one in the token.

Tokens use a separate "type": "download" claim so a leaked download token
can't be misused as an access token (and vice versa).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from django.conf import settings


def _signing_key() -> str:
    return getattr(settings, "DOWNLOAD_TOKEN_SIGNING_KEY", "") or settings.SECRET_KEY


def make_download_token(*, user_id: int, kind: str, ref: str) -> str:
    """
    Make a download token.

    - user_id: who is allowed to use this token (still re-checked at download
               time against the underlying object's permissions).
    - kind:    one of {"user_doc", "deal_ddu", "deal_payment_proof",
                       "developer_template", "document_request_file"}
               — pins the endpoint family.
    - ref:     opaque object reference (e.g. document id, "deal:42:ddu",
               "developer:6").
    """
    ttl = int(getattr(settings, "DOWNLOAD_TOKEN_TTL_SECONDS", 600))
    payload: dict[str, Any] = {
        "uid": int(user_id),
        "knd": kind,
        "ref": str(ref),
        "exp": datetime.now(timezone.utc) + timedelta(seconds=ttl),
        "type": "download",
    }
    return jwt.encode(payload, _signing_key(), algorithm="HS256")


def make_public_download_token(*, kind: str, ref: str) -> str:
    """
    Public, user-agnostic download token — for assets meant to be served
    in the public catalog (e.g. property images). Time-limited, but does
    not bind to a particular user.
    """
    ttl = int(getattr(settings, "DOWNLOAD_TOKEN_TTL_SECONDS", 600))
    payload: dict[str, Any] = {
        "knd": kind,
        "ref": str(ref),
        "exp": datetime.now(timezone.utc) + timedelta(seconds=ttl),
        "type": "download",
    }
    return jwt.encode(payload, _signing_key(), algorithm="HS256")


def verify_public_download_token(token: str, *, kind: str, ref: str) -> None:
    """Validate a public download token. Raises jwt.InvalidTokenError on failure."""
    payload = jwt.decode(token, _signing_key(), algorithms=["HS256"])
    if payload.get("type") != "download":
        raise jwt.InvalidTokenError("Wrong token type.")
    if payload.get("knd") != kind:
        raise jwt.InvalidTokenError("Token kind mismatch.")
    if str(payload.get("ref")) != str(ref):
        raise jwt.InvalidTokenError("Token reference mismatch.")


def verify_download_token(token: str, *, kind: str, ref: str) -> int:
    """
    Validate a download token. Returns the user_id on success.

    Raises jwt.InvalidTokenError on:
    - bad signature
    - expired
    - wrong type (not "download")
    - kind/ref mismatch (token issued for a different file)
    """
    payload = jwt.decode(token, _signing_key(), algorithms=["HS256"])
    if payload.get("type") != "download":
        raise jwt.InvalidTokenError("Wrong token type.")
    if payload.get("knd") != kind:
        raise jwt.InvalidTokenError("Token kind mismatch.")
    if str(payload.get("ref")) != str(ref):
        raise jwt.InvalidTokenError("Token reference mismatch.")
    return int(payload["uid"])


def build_user_document_url(request, *, document_id: int) -> str | None:
    """Signed download URL for a UserDocument, or None if no auth context."""
    if request is None:
        return None
    user_id = getattr(getattr(request, "user", None), "id", None)
    if not user_id:
        return None
    token = make_download_token(
        user_id=user_id, kind="user_doc", ref=str(document_id)
    )
    return request.build_absolute_uri(
        f"/api/v1/files/user-document/{document_id}/?t={token}"
    )


def build_deal_document_url(request, *, deal_id: int, kind: str) -> str | None:
    """
    Signed download URL for a Deal document.

    `kind` is one of {"ddu", "payment_proof"}.
    """
    if request is None:
        return None
    user_id = getattr(getattr(request, "user", None), "id", None)
    if not user_id:
        return None
    token = make_download_token(
        user_id=user_id,
        kind=f"deal_{kind}",
        ref=f"deal:{deal_id}:{kind}",
    )
    return request.build_absolute_uri(
        f"/api/v1/files/deal/{deal_id}/{kind}/?t={token}"
    )


def build_settlement_document_url(
    request, *, settlement_id: int, kind: str
) -> str | None:
    """
    Signed download URL for a DealSettlement receipt.

    `kind` is one of {"broker_payout_receipt", "developer_receipt"}.
    """
    if request is None:
        return None
    user_id = getattr(getattr(request, "user", None), "id", None)
    if not user_id:
        return None
    token = make_download_token(
        user_id=user_id,
        kind=f"settlement_{kind}",
        ref=f"settlement:{settlement_id}:{kind}",
    )
    return request.build_absolute_uri(
        f"/api/v1/files/settlement/{settlement_id}/{kind}/?t={token}"
    )


def build_developer_template_url(request, *, developer_user_id: int) -> str | None:
    """Signed download URL for a developer's DDU template PDF."""
    if request is None:
        return None
    user_id = getattr(getattr(request, "user", None), "id", None)
    if not user_id:
        return None
    token = make_download_token(
        user_id=user_id,
        kind="developer_template",
        ref=f"developer:{developer_user_id}",
    )
    return request.build_absolute_uri(
        f"/api/v1/files/developer/{developer_user_id}/ddu-template/?t={token}"
    )


def build_property_image_url(request, *, image_id: int) -> str | None:
    """
    Public signed download URL for a PropertyImage. Property listings are
    visible to anonymous users in the catalog, so the token is user-agnostic
    and only encodes the image id + expiry.
    """
    if request is None:
        return None
    token = make_public_download_token(
        kind="property_image", ref=str(image_id)
    )
    return request.build_absolute_uri(
        f"/api/v1/files/property-image/{image_id}/?t={token}"
    )


def build_document_request_file_url(request, *, file_id: int) -> str | None:
    """Signed download URL for a DocumentRequestFile (auction docs)."""
    if request is None:
        return None
    user_id = getattr(getattr(request, "user", None), "id", None)
    if not user_id:
        return None
    token = make_download_token(
        user_id=user_id,
        kind="document_request_file",
        ref=str(file_id),
    )
    return request.build_absolute_uri(
        f"/api/v1/files/document-request/{file_id}/?t={token}"
    )
