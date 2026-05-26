from django.urls import path
from apps.ingestion.views import (
    IngestionRunListView, UploadView,
    ActivityRecordListView, ActivityRecordDetailView,
    ApproveRecordView, RejectRecordView, LockRecordView,
    BulkApproveView, DashboardStatsView,
)

urlpatterns = [
    # Ingestion runs
    path('ingestion/runs/', IngestionRunListView.as_view(), name='ingestion-run-list'),
    path('ingestion/upload/', UploadView.as_view(), name='ingestion-upload'),

    # Activity records
    path('activities/', ActivityRecordListView.as_view(), name='activity-list'),
    path('activities/bulk-approve/', BulkApproveView.as_view(), name='activity-bulk-approve'),
    path('activities/<uuid:pk>/', ActivityRecordDetailView.as_view(), name='activity-detail'),
    path('activities/<uuid:pk>/approve/', ApproveRecordView.as_view(), name='activity-approve'),
    path('activities/<uuid:pk>/reject/', RejectRecordView.as_view(), name='activity-reject'),
    path('activities/<uuid:pk>/lock/', LockRecordView.as_view(), name='activity-lock'),

    # Dashboard
    path('stats/', DashboardStatsView.as_view(), name='dashboard-stats'),
]
