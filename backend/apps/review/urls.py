from django.urls import path
from apps.review.views import AuditLogListView, UserProfileView

urlpatterns = [
    path('audit/', AuditLogListView.as_view(), name='audit-log-list'),
    path('me/', UserProfileView.as_view(), name='user-profile'),
]
