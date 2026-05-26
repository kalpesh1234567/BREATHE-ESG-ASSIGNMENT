from rest_framework import generics, filters
from rest_framework.response import Response
from rest_framework.views import APIView
from django_filters.rest_framework import DjangoFilterBackend

from apps.ingestion.models import AuditLog
from apps.ingestion.serializers import AuditLogSerializer


class AuditLogListView(generics.ListAPIView):
    """GET /api/audit/ — full audit trail for the org, filterable."""
    serializer_class = AuditLogSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['action']
    ordering_fields = ['timestamp']
    ordering = ['-timestamp']

    def get_queryset(self):
        org = self.request.user.organization
        qs = AuditLog.objects.filter(
            record__organization=org
        ).select_related('actor', 'record')

        record_id = self.request.query_params.get('record')
        if record_id:
            qs = qs.filter(record__id=record_id)

        return qs


class UserProfileView(APIView):
    """GET /api/me/ — return current user info for frontend auth."""
    def get(self, request):
        user = request.user
        return Response({
            'id': str(user.id),
            'username': user.username,
            'email': user.email,
            'full_name': user.get_full_name(),
            'role': user.role,
            'organization': {
                'id': str(user.organization.id) if user.organization else None,
                'name': user.organization.name if user.organization else None,
                'slug': user.organization.slug if user.organization else None,
            },
        })
