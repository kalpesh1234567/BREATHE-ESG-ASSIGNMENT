"""
Ingestion and activity record API views.
All views are scoped to request.user.organization — multi-tenant isolation.
"""
from datetime import datetime, timezone
from rest_framework import generics, status, filters
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from django_filters.rest_framework import DjangoFilterBackend
import django_filters

from apps.ingestion.models import IngestionRun, ActivityRecord, AuditLog
from apps.ingestion.serializers import (
    IngestionRunSerializer,
    ActivityRecordListSerializer,
    ActivityRecordDetailSerializer,
    ActivityRecordEditSerializer,
)
from apps.ingestion.service import ingest_file


class OrgMixin:
    """Restrict querysets to the authenticated user's organization."""
    def get_org(self):
        return self.request.user.organization


# ── Ingestion Runs ────────────────────────────────────────────────────────────

class IngestionRunListView(OrgMixin, generics.ListAPIView):
    serializer_class = IngestionRunSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['source_type', 'status']
    ordering_fields = ['uploaded_at', 'parsed_count']
    ordering = ['-uploaded_at']

    def get_queryset(self):
        return IngestionRun.objects.filter(organization=self.get_org())


class UploadView(OrgMixin, APIView):
    """
    POST /api/ingestion/upload/
    Accepts a multipart upload with 'file' and 'source_type' fields.
    Parses synchronously (adequate for file sizes under ~10 MB).
    """

    def post(self, request):
        file_obj = request.FILES.get('file')
        source_type = request.data.get('source_type')

        if not file_obj:
            return Response({'error': 'No file provided'}, status=status.HTTP_400_BAD_REQUEST)

        valid_sources = dict(IngestionRun.SOURCE_CHOICES).keys()
        if source_type not in valid_sources:
            return Response(
                {'error': f'Invalid source_type. Choose from: {list(valid_sources)}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        run = IngestionRun.objects.create(
            organization=self.get_org(),
            uploaded_by=request.user,
            source_type=source_type,
            filename=file_obj.name,
        )

        file_content = file_obj.read()

        try:
            ingest_file(run, file_content, request.user)
        except Exception as exc:
            return Response(
                {'error': str(exc), 'run_id': str(run.id)},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        return Response(IngestionRunSerializer(run).data, status=status.HTTP_201_CREATED)


# ── Activity Records ──────────────────────────────────────────────────────────

class ActivityRecordFilter(django_filters.FilterSet):
    status = django_filters.MultipleChoiceFilter(choices=ActivityRecord.STATUS_CHOICES)
    scope = django_filters.MultipleChoiceFilter(choices=ActivityRecord.SCOPE_CHOICES)
    source_type = django_filters.MultipleChoiceFilter(choices=ActivityRecord.SOURCE_CHOICES)
    period_start_after = django_filters.DateFilter(field_name='period_start', lookup_expr='gte')
    period_start_before = django_filters.DateFilter(field_name='period_start', lookup_expr='lte')
    is_suspicious = django_filters.BooleanFilter()

    class Meta:
        model = ActivityRecord
        fields = ['status', 'scope', 'source_type', 'is_suspicious',
                  'period_start_after', 'period_start_before']


class ActivityRecordListView(OrgMixin, generics.ListAPIView):
    serializer_class = ActivityRecordListSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = ActivityRecordFilter
    search_fields = ['category', 'facility_code', 'facility_description']
    ordering_fields = ['period_start', 'co2e_kg', 'created_at', 'status']
    ordering = ['-period_start']

    def get_queryset(self):
        return ActivityRecord.objects.filter(
            organization=self.get_org()
        ).select_related('reviewed_by', 'ingestion_run')


class ActivityRecordDetailView(OrgMixin, generics.RetrieveUpdateAPIView):
    def get_queryset(self):
        return ActivityRecord.objects.filter(
            organization=self.get_org()
        ).select_related('ingestion_run', 'emission_factor').prefetch_related('audit_logs__actor')

    def get_serializer_class(self):
        if self.request.method in ('PATCH', 'PUT'):
            return ActivityRecordEditSerializer
        return ActivityRecordDetailSerializer

    def perform_update(self, serializer):
        instance = serializer.instance
        if instance.is_locked:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied('Locked records cannot be edited.')

        before = {
            'quantity_raw': str(instance.quantity_raw),
            'unit_raw': instance.unit_raw,
            'quantity_normalized': str(instance.quantity_normalized),
            'co2e_kg': str(instance.co2e_kg) if instance.co2e_kg else None,
        }

        # Snapshot original values before first edit
        if not instance.is_edited:
            serializer.save(
                is_edited=True,
                original_values=before,
                edited_by=self.request.user,
                edited_at=datetime.now(timezone.utc),
            )
        else:
            serializer.save(
                edited_by=self.request.user,
                edited_at=datetime.now(timezone.utc),
            )

        AuditLog.objects.create(
            record=instance,
            actor=self.request.user,
            action=AuditLog.ACTION_EDITED,
            before_state=before,
            after_state={
                'quantity_raw': str(serializer.instance.quantity_raw),
                'unit_raw': serializer.instance.unit_raw,
                'co2e_kg': str(serializer.instance.co2e_kg) if serializer.instance.co2e_kg else None,
            },
        )


# ── Review Actions ────────────────────────────────────────────────────────────

class ApproveRecordView(OrgMixin, APIView):
    def post(self, request, pk):
        record = _get_record(request, pk)
        if record is None:
            return Response({'error': 'Not found'}, status=404)
        if record.is_locked:
            return Response({'error': 'Record is already locked'}, status=400)
        if record.status == ActivityRecord.STATUS_REJECTED:
            return Response({'error': 'Cannot approve a rejected record'}, status=400)

        before = {'status': record.status}
        record.status = ActivityRecord.STATUS_APPROVED
        record.reviewed_by = request.user
        record.reviewed_at = datetime.now(timezone.utc)
        record.save(update_fields=['status', 'reviewed_by', 'reviewed_at'])

        AuditLog.objects.create(
            record=record,
            actor=request.user,
            action=AuditLog.ACTION_APPROVED,
            before_state=before,
            after_state={'status': record.status},
        )
        return Response({'status': 'approved', 'id': str(record.id)})


class RejectRecordView(OrgMixin, APIView):
    def post(self, request, pk):
        record = _get_record(request, pk)
        if record is None:
            return Response({'error': 'Not found'}, status=404)
        if record.is_locked:
            return Response({'error': 'Record is locked'}, status=400)

        reason = request.data.get('reason', '')
        before = {'status': record.status}
        record.status = ActivityRecord.STATUS_REJECTED
        record.flag_reason = reason
        record.reviewed_by = request.user
        record.reviewed_at = datetime.now(timezone.utc)
        record.save(update_fields=['status', 'flag_reason', 'reviewed_by', 'reviewed_at'])

        AuditLog.objects.create(
            record=record,
            actor=request.user,
            action=AuditLog.ACTION_REJECTED,
            before_state=before,
            after_state={'status': record.status, 'reason': reason},
            note=reason,
        )
        return Response({'status': 'rejected', 'id': str(record.id)})


class LockRecordView(OrgMixin, APIView):
    """Lock an approved record for audit. Only admins can lock."""
    def post(self, request, pk):
        if request.user.role != 'admin':
            return Response({'error': 'Only admins can lock records'}, status=403)

        record = _get_record(request, pk)
        if record is None:
            return Response({'error': 'Not found'}, status=404)
        if record.status != ActivityRecord.STATUS_APPROVED:
            return Response({'error': 'Only approved records can be locked'}, status=400)

        record.status = ActivityRecord.STATUS_LOCKED
        record.save(update_fields=['status'])

        AuditLog.objects.create(
            record=record,
            actor=request.user,
            action=AuditLog.ACTION_LOCKED,
            after_state={'status': 'locked'},
        )
        return Response({'status': 'locked', 'id': str(record.id)})


class BulkApproveView(OrgMixin, APIView):
    """POST /api/activities/bulk-approve/ with {ids: [...]}"""
    def post(self, request):
        ids = request.data.get('ids', [])
        if not ids:
            return Response({'error': 'No IDs provided'}, status=400)

        records = ActivityRecord.objects.filter(
            organization=self.get_org(),
            id__in=ids,
        ).exclude(status__in=[ActivityRecord.STATUS_LOCKED, ActivityRecord.STATUS_REJECTED])

        now = datetime.now(timezone.utc)
        updated = []
        for record in records:
            before = {'status': record.status}
            record.status = ActivityRecord.STATUS_APPROVED
            record.reviewed_by = request.user
            record.reviewed_at = now
            record.save(update_fields=['status', 'reviewed_by', 'reviewed_at'])
            AuditLog.objects.create(
                record=record,
                actor=request.user,
                action=AuditLog.ACTION_APPROVED,
                before_state=before,
                after_state={'status': 'approved'},
                note='Bulk approval',
            )
            updated.append(str(record.id))

        return Response({'approved': len(updated), 'ids': updated})


class DashboardStatsView(OrgMixin, APIView):
    """GET /api/stats/ — summary numbers for the dashboard."""
    def get(self, request):
        org = self.get_org()
        qs = ActivityRecord.objects.filter(organization=org)

        from django.db.models import Sum, Count, Q

        stats = qs.aggregate(
            total_co2e=Sum('co2e_kg'),
            total_count=Count('id'),
            pending_count=Count('id', filter=Q(status='pending')),
            flagged_count=Count('id', filter=Q(is_suspicious=True, status='pending')),
            approved_count=Count('id', filter=Q(status='approved')),
            locked_count=Count('id', filter=Q(status='locked')),
            rejected_count=Count('id', filter=Q(status='rejected')),
        )

        scope_breakdown = {}
        for scope in ['1', '2', '3']:
            agg = qs.filter(scope=scope).aggregate(
                co2e=Sum('co2e_kg'),
                count=Count('id'),
            )
            scope_breakdown[f'scope_{scope}'] = {
                'co2e_kg': float(agg['co2e'] or 0),
                'count': agg['count'],
            }

        source_breakdown = qs.values('source_type').annotate(
            co2e=Sum('co2e_kg'),
            count=Count('id'),
        )

        return Response({
            'total_co2e_kg': float(stats['total_co2e'] or 0),
            'total_records': stats['total_count'],
            'pending': stats['pending_count'],
            'flagged': stats['flagged_count'],
            'approved': stats['approved_count'],
            'locked': stats['locked_count'],
            'rejected': stats['rejected_count'],
            'scope_breakdown': scope_breakdown,
            'source_breakdown': list(source_breakdown),
        })


def _get_record(request, pk):
    try:
        return ActivityRecord.objects.get(id=pk, organization=request.user.organization)
    except ActivityRecord.DoesNotExist:
        return None
