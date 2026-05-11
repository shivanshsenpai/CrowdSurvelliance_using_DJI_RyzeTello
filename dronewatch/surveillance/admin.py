"""
Admin views for DroneWatch history records.
"""

from django.contrib import admin
from django.db.models import Count

from .models import CrowdSnapshot, SurveillanceSession


class CrowdSnapshotInline(admin.TabularInline):
    model = CrowdSnapshot
    fields = (
        "timestamp",
        "mode",
        "people_count",
        "cumulative_count",
        "density_alert",
        "weapon_alert",
        "fire_alert",
    )
    readonly_fields = fields
    extra = 0
    can_delete = False
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(SurveillanceSession)
class SurveillanceSessionAdmin(admin.ModelAdmin):
    list_display = (
        "short_session_id",
        "start_time",
        "end_time",
        "duration",
        "status",
        "peak_count",
        "avg_count",
        "total_unique",
        "total_alerts",
        "snapshot_total",
    )
    list_filter = ("is_active", "start_time", "end_time")
    search_fields = ("session_id",)
    readonly_fields = (
        "session_id",
        "start_time",
        "end_time",
        "duration",
        "peak_count",
        "avg_count",
        "total_unique",
        "total_alerts",
        "total_snapshots",
        "snapshot_total",
        "is_active",
    )
    inlines = (CrowdSnapshotInline,)
    date_hierarchy = "start_time"
    ordering = ("-start_time",)

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset.annotate(snapshot_count=Count("snapshots"))

    @admin.display(description="Session")
    def short_session_id(self, obj):
        return obj.session_id[:8]

    @admin.display(description="Status")
    def status(self, obj):
        return "Active" if obj.is_active else "Ended"

    @admin.display(description="Duration")
    def duration(self, obj):
        end_time = obj.end_time
        if end_time is None:
            from django.utils import timezone

            end_time = timezone.now()

        seconds = int((end_time - obj.start_time).total_seconds())
        minutes, seconds = divmod(max(seconds, 0), 60)
        hours, minutes = divmod(minutes, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    @admin.display(description="Snapshots")
    def snapshot_total(self, obj):
        return getattr(obj, "snapshot_count", obj.total_snapshots)

    def has_add_permission(self, request):
        return False


@admin.register(CrowdSnapshot)
class CrowdSnapshotAdmin(admin.ModelAdmin):
    list_display = (
        "timestamp",
        "session_short_id",
        "mode",
        "people_count",
        "cumulative_count",
        "density_alert",
        "weapon_alert",
        "fire_alert",
    )
    list_filter = (
        "mode",
        "density_alert",
        "weapon_alert",
        "fire_alert",
        "timestamp",
    )
    search_fields = ("session__session_id",)
    readonly_fields = (
        "session",
        "timestamp",
        "people_count",
        "cumulative_count",
        "mode",
        "density_alert",
        "weapon_alert",
        "fire_alert",
    )
    date_hierarchy = "timestamp"
    ordering = ("-timestamp",)

    @admin.display(description="Session")
    def session_short_id(self, obj):
        return obj.session.session_id[:8]

    def has_add_permission(self, request):
        return False


admin.site.site_header = "DroneWatch Admin"
admin.site.site_title = "DroneWatch Admin"
admin.site.index_title = "Surveillance History"
