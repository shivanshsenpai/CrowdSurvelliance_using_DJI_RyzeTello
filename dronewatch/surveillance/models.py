"""
DroneWatch — Django Models for Crowd Analytics.
Stores timestamped people-count snapshots and per-session summaries.
"""

from django.db import models


class SurveillanceSession(models.Model):
    """One row per server run — aggregated session statistics."""

    session_id = models.CharField(max_length=64, unique=True, db_index=True)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField(null=True, blank=True)
    peak_count = models.IntegerField(default=0)
    avg_count = models.FloatField(default=0.0)
    total_unique = models.IntegerField(default=0)
    total_alerts = models.IntegerField(default=0)
    total_snapshots = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['-start_time']

    def __str__(self):
        status = "ACTIVE" if self.is_active else "ENDED"
        return f"Session {self.session_id[:8]} ({status}) — peak {self.peak_count}"


class CrowdSnapshot(models.Model):
    """Timestamped people-count reading, recorded every ~5 seconds."""

    session = models.ForeignKey(
        SurveillanceSession,
        on_delete=models.CASCADE,
        related_name='snapshots',
    )
    timestamp = models.DateTimeField(db_index=True)
    people_count = models.IntegerField(default=0)
    cumulative_count = models.IntegerField(default=0)
    mode = models.CharField(max_length=10, default='human')
    density_alert = models.BooleanField(default=False)
    weapon_alert = models.BooleanField(default=False)
    fire_alert = models.BooleanField(default=False)

    class Meta:
        ordering = ['timestamp']

    def __str__(self):
        return f"[{self.timestamp:%H:%M:%S}] {self.people_count} people"
