"""
DroneWatch — Analytics Engine.
Background recorder that snapshots crowd data every 5 seconds,
and report-generation functions for the analysis API.
"""

import time
import uuid
import threading
from datetime import datetime, timedelta
from collections import defaultdict

from django.utils import timezone
from django.db.models import Avg, Max, Min, Count, Q

from .drone_state import state
from .models import CrowdSnapshot, SurveillanceSession

# ========================= CONSTANTS =========================

SNAPSHOT_INTERVAL = 5  # seconds between snapshots


# ========================= ANALYTICS RECORDER =========================

def summarize_session(session, end_time=None, close=False):
    """Refresh one session's summary fields from its saved snapshots."""
    snapshots = CrowdSnapshot.objects.filter(session=session)
    agg = snapshots.aggregate(
        peak=Max('people_count'),
        avg=Avg('people_count'),
        total=Count('id'),
        unique=Max('cumulative_count'),
        density=Count('id', filter=Q(density_alert=True)),
        weapon=Count('id', filter=Q(weapon_alert=True)),
        fire=Count('id', filter=Q(fire_alert=True)),
    )

    session.peak_count = agg['peak'] or 0
    session.avg_count = round(agg['avg'] or 0, 2)
    session.total_unique = agg['unique'] or 0
    session.total_alerts = (
        (agg['density'] or 0)
        + (agg['weapon'] or 0)
        + (agg['fire'] or 0)
    )
    session.total_snapshots = agg['total'] or 0

    if close:
        session.end_time = end_time or timezone.now()
        session.is_active = False

    session.save()
    return session

class AnalyticsRecorder:
    """Background thread that periodically snapshots crowd data to the DB."""

    def __init__(self):
        self.session = None
        self.session_id = str(uuid.uuid4())
        self._running = False
        self._thread = None

    def start(self):
        """Create session row and start the recording thread."""
        for stale_session in SurveillanceSession.objects.filter(is_active=True):
            summarize_session(stale_session, end_time=timezone.now(), close=True)

        self.session = SurveillanceSession.objects.create(
            session_id=self.session_id,
            start_time=timezone.now(),
            is_active=True,
        )
        self._running = True
        self._thread = threading.Thread(target=self._record_loop, daemon=True)
        self._thread.start()
        print(f"[ANALYTICS] Recorder started — session {self.session_id[:8]}")

    def stop(self):
        """Finalize session and stop recording."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=10)
        self._finalize_session()
        print(f"[ANALYTICS] Recorder stopped — session {self.session_id[:8]}")

    def _record_loop(self):
        """Main recording loop — runs in a daemon thread."""
        while self._running and state.running:
            try:
                self._take_snapshot()
            except Exception as e:
                print(f"[ANALYTICS] Snapshot error: {e}")
            time.sleep(SNAPSHOT_INTERVAL)

    def _take_snapshot(self):
        """Write one CrowdSnapshot row from current state."""
        CrowdSnapshot.objects.create(
            session=self.session,
            timestamp=timezone.now(),
            people_count=state.current_count,
            cumulative_count=state.cumulative_count,
            mode=state.mode,
            density_alert=state.density_alert,
            weapon_alert=state.weapon_alert,
            fire_alert=state.fire_alert,
        )
        summarize_session(self.session)

    def _finalize_session(self):
        """Update the session row with aggregated statistics."""
        if not self.session:
            return
        try:
            summarize_session(self.session, end_time=timezone.now(), close=True)
        except Exception as e:
            print(f"[ANALYTICS] Session finalize error: {e}")


# Global recorder instance — initialized in apps.py
recorder = None


# ========================= REPORT GENERATION =========================

def generate_report(session_id=None, hours=None):
    """
    Generate a comprehensive analysis report.

    Args:
        session_id: Specific session to report on (latest active if None).
        hours: Limit to last N hours of data.

    Returns:
        dict with full analysis data.
    """
    # Determine queryset
    if session_id:
        try:
            session = SurveillanceSession.objects.get(session_id=session_id)
        except SurveillanceSession.DoesNotExist:
            return {"error": "Session not found"}
        snapshots = CrowdSnapshot.objects.filter(session=session)
    elif hours:
        cutoff = timezone.now() - timedelta(hours=hours)
        snapshots = CrowdSnapshot.objects.filter(timestamp__gte=cutoff)
        session = None
    else:
        # Use the latest session (active or most recent)
        session = SurveillanceSession.objects.first()
        if not session:
            return {"error": "No session data available"}
        snapshots = CrowdSnapshot.objects.filter(session=session)

    if not snapshots.exists():
        return {"error": "No snapshot data available"}

    # ---- Basic aggregates ----
    agg = snapshots.aggregate(
        peak_count=Max('people_count'),
        avg_count=Avg('people_count'),
        min_count=Min('people_count'),
        total_snapshots=Count('id'),
        density_alerts=Count('id', filter=Q(density_alert=True)),
        weapon_alerts=Count('id', filter=Q(weapon_alert=True)),
        fire_alerts=Count('id', filter=Q(fire_alert=True)),
        total_unique=Max('cumulative_count'),
    )

    # ---- Peak time ----
    peak_snapshot = snapshots.order_by('-people_count').first()
    peak_time = peak_snapshot.timestamp.strftime("%H:%M:%S") if peak_snapshot else "N/A"

    # ---- Time-series data (for charts) ----
    timeline = list(snapshots.values_list('timestamp', 'people_count'))
    timeline_data = [
        {
            "timestamp": ts.strftime("%H:%M:%S"),
            "datetime": ts.isoformat(),
            "count": count,
        }
        for ts, count in timeline
    ]

    # ---- Hourly breakdown ----
    hourly = defaultdict(list)
    for ts, count in timeline:
        hourly[ts.strftime("%H:00")].append(count)

    hourly_breakdown = []
    for hour_label in sorted(hourly.keys()):
        counts = hourly[hour_label]
        hourly_breakdown.append({
            "hour": hour_label,
            "avg": round(sum(counts) / len(counts), 1),
            "peak": max(counts),
            "min": min(counts),
            "samples": len(counts),
        })

    # ---- High-density periods ----
    DENSITY_THRESHOLD = 10
    high_density_events = []
    in_event = False
    event_start = None
    event_peak = 0

    for ts, count in timeline:
        if count >= DENSITY_THRESHOLD:
            if not in_event:
                in_event = True
                event_start = ts
                event_peak = count
            else:
                event_peak = max(event_peak, count)
        else:
            if in_event:
                high_density_events.append({
                    "start": event_start.strftime("%H:%M:%S"),
                    "end": ts.strftime("%H:%M:%S"),
                    "peak": event_peak,
                    "duration_sec": int((ts - event_start).total_seconds()),
                })
                in_event = False

    # Close any open event
    if in_event and timeline:
        high_density_events.append({
            "start": event_start.strftime("%H:%M:%S"),
            "end": timeline[-1][0].strftime("%H:%M:%S"),
            "peak": event_peak,
            "duration_sec": int((timeline[-1][0] - event_start).total_seconds()),
        })

    # ---- Trend analysis ----
    trend = "stable"
    if len(timeline) >= 6:
        recent = [c for _, c in timeline[-3:]]
        earlier = [c for _, c in timeline[:3]]
        recent_avg = sum(recent) / len(recent)
        earlier_avg = sum(earlier) / len(earlier)
        diff = recent_avg - earlier_avg
        if diff > 2:
            trend = "increasing"
        elif diff < -2:
            trend = "decreasing"

    # ---- Session info ----
    session_info = None
    if session:
        duration = 0
        if session.end_time and session.start_time:
            duration = int((session.end_time - session.start_time).total_seconds())
        elif session.start_time:
            duration = int((timezone.now() - session.start_time).total_seconds())

        session_info = {
            "session_id": session.session_id,
            "start_time": session.start_time.strftime("%Y-%m-%d %H:%M:%S"),
            "end_time": session.end_time.strftime("%Y-%m-%d %H:%M:%S") if session.end_time else "Active",
            "duration_sec": duration,
            "is_active": session.is_active,
        }

    return {
        "session": session_info,
        "summary": {
            "peak_count": agg['peak_count'] or 0,
            "peak_time": peak_time,
            "avg_count": round(agg['avg_count'] or 0, 1),
            "min_count": agg['min_count'] or 0,
            "total_snapshots": agg['total_snapshots'] or 0,
            "total_unique_people": agg['total_unique'] or 0,
            "density_alerts": agg['density_alerts'],
            "weapon_alerts": agg['weapon_alerts'],
            "fire_alerts": agg['fire_alerts'],
            "total_alerts": agg['density_alerts'] + agg['weapon_alerts'] + agg['fire_alerts'],
        },
        "trend": trend,
        "hourly_breakdown": hourly_breakdown,
        "high_density_events": high_density_events,
        "timeline": timeline_data,
    }
