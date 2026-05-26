from rest_framework import serializers
from apps.ingestion.models import IngestionRun, ActivityRecord, AuditLog, EmissionFactor
from apps.core.models import User


class IngestionRunSerializer(serializers.ModelSerializer):
    uploaded_by_name = serializers.SerializerMethodField()
    source_type_display = serializers.CharField(source='get_source_type_display', read_only=True)

    class Meta:
        model = IngestionRun
        fields = [
            'id', 'source_type', 'source_type_display', 'filename', 'file_hash',
            'row_count', 'parsed_count', 'error_count', 'status',
            'error_detail', 'uploaded_at', 'completed_at', 'uploaded_by_name',
        ]
        read_only_fields = fields

    def get_uploaded_by_name(self, obj):
        if obj.uploaded_by:
            return obj.uploaded_by.get_full_name() or obj.uploaded_by.username
        return None


class AuditLogSerializer(serializers.ModelSerializer):
    actor_name = serializers.SerializerMethodField()
    action_display = serializers.CharField(source='get_action_display', read_only=True)

    class Meta:
        model = AuditLog
        fields = ['id', 'action', 'action_display', 'actor_name', 'before_state',
                  'after_state', 'note', 'timestamp']
        read_only_fields = fields

    def get_actor_name(self, obj):
        if obj.actor:
            return obj.actor.get_full_name() or obj.actor.username
        return 'System'


class ActivityRecordListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views."""
    scope_display = serializers.CharField(source='get_scope_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    source_type_display = serializers.CharField(source='get_source_type_display', read_only=True)
    reviewed_by_name = serializers.SerializerMethodField()

    class Meta:
        model = ActivityRecord
        fields = [
            'id', 'source_type', 'source_type_display', 'scope', 'scope_display',
            'category', 'period_start', 'period_end', 'facility_code', 'facility_description',
            'quantity_raw', 'unit_raw', 'quantity_normalized', 'unit_normalized',
            'co2e_kg', 'emission_factor_value', 'emission_factor_unit',
            'status', 'status_display', 'is_suspicious', 'suspicion_reasons',
            'is_edited', 'reviewed_by_name', 'reviewed_at', 'created_at',
        ]
        read_only_fields = fields

    def get_reviewed_by_name(self, obj):
        if obj.reviewed_by:
            return obj.reviewed_by.get_full_name() or obj.reviewed_by.username
        return None


class ActivityRecordDetailSerializer(ActivityRecordListSerializer):
    """Full serializer for detail views — includes raw_data and audit log."""
    audit_logs = AuditLogSerializer(many=True, read_only=True)
    ingestion_run = IngestionRunSerializer(read_only=True)

    class Meta(ActivityRecordListSerializer.Meta):
        fields = ActivityRecordListSerializer.Meta.fields + [
            'raw_data', 'original_values', 'flag_reason',
            'edited_by', 'edited_at', 'ingestion_run', 'audit_logs',
        ]


class ActivityRecordEditSerializer(serializers.ModelSerializer):
    """Used by PATCH /api/activities/{id}/ — analyst corrections."""

    class Meta:
        model = ActivityRecord
        fields = ['quantity_raw', 'unit_raw', 'quantity_normalized', 'unit_normalized',
                  'period_start', 'period_end', 'facility_code', 'co2e_kg', 'flag_reason']

    def validate(self, attrs):
        instance = self.instance
        if instance and instance.is_locked:
            raise serializers.ValidationError('Cannot edit a locked record.')
        return attrs
