import uuid

from django.utils.deprecation import MiddlewareMixin

from core.logging import set_request_id


class RequestIdMiddleware(MiddlewareMixin):
    def process_request(self, request):
        rid = request.headers.get("X-Request-Id") or str(uuid.uuid4())
        set_request_id(rid)
        request.request_id = rid
