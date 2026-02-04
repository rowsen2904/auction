from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthCheckView(APIView):
    @extend_schema(
        summary="Health check",
        description="Check if the server is running",
        tags=["Health"],
    )
    def get(self, request):
        return Response({"status": "ok"}, status=status.HTTP_200_OK)
