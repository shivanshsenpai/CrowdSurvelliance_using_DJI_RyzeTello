"""
DroneWatch — Django Views.
REST API endpoints and dashboard template view.
"""

import json
import time

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_GET

from .drone_state import state, drone_instance
from . import drone_state as drone_state_module
from .detection import models_loaded

MOVE_DISTANCE = 30  # cm per move command


def index(request):
    """Serve the dashboard."""
    return render(request, 'surveillance/index.html')


def analytics_page(request):
    """Serve the analytics report page."""
    return render(request, 'surveillance/analytics.html')


@require_GET
def api_analytics_report(request):
    """Generate a full analysis report."""
    from .analytics import generate_report
    session_id = request.GET.get('session_id')
    hours = request.GET.get('hours')
    try:
        hours = float(hours) if hours else None
    except (ValueError, TypeError):
        hours = None
    report = generate_report(session_id=session_id, hours=hours)
    return JsonResponse(report, safe=False)


@require_GET
def api_analytics_history(request):
    """Return time-series snapshot data."""
    from .models import CrowdSnapshot
    hours = request.GET.get('hours', '1')
    try:
        hours = float(hours)
    except (ValueError, TypeError):
        hours = 1

    from django.utils import timezone as tz
    from datetime import timedelta
    cutoff = tz.now() - timedelta(hours=hours)

    snapshots = CrowdSnapshot.objects.filter(
        timestamp__gte=cutoff
    ).values_list('timestamp', 'people_count', 'cumulative_count', 'mode', 'density_alert')

    data = [
        {
            "timestamp": ts.strftime("%H:%M:%S"),
            "datetime": ts.isoformat(),
            "people_count": pc,
            "cumulative_count": cc,
            "mode": m,
            "density_alert": da,
        }
        for ts, pc, cc, m, da in snapshots
    ]
    return JsonResponse({"snapshots": data, "count": len(data)})


@require_GET
def api_analytics_sessions(request):
    """Return list of past surveillance sessions."""
    from .models import SurveillanceSession
    sessions = SurveillanceSession.objects.all()[:20]
    data = []
    for s in sessions:
        duration = 0
        if s.end_time and s.start_time:
            duration = int((s.end_time - s.start_time).total_seconds())
        elif s.start_time:
            from django.utils import timezone as tz
            duration = int((tz.now() - s.start_time).total_seconds())
        data.append({
            "session_id": s.session_id,
            "start_time": s.start_time.strftime("%Y-%m-%d %H:%M:%S"),
            "end_time": s.end_time.strftime("%Y-%m-%d %H:%M:%S") if s.end_time else "Active",
            "duration_sec": duration,
            "peak_count": s.peak_count,
            "avg_count": s.avg_count,
            "total_unique": s.total_unique,
            "total_alerts": s.total_alerts,
            "total_snapshots": s.total_snapshots,
            "is_active": s.is_active,
        })
    return JsonResponse({"sessions": data})


@require_GET
def api_status(request):
    """Get current drone and system status."""
    return JsonResponse({
        "connected": state.connected,
        "demo_mode": state.demo_mode,
        "mode": state.mode,
        "battery": state.battery,
        "altitude": state.altitude,
        "fps": round(state.fps, 1),
        "uptime": round(time.time() - state.session_start),
        "total_frames": state.total_frames,
        "models_loaded": models_loaded,
    })


@csrf_exempt
@require_POST
def api_set_mode(request, mode):
    """Switch detection mode."""
    if mode not in ("human", "weapon", "fire"):
        return JsonResponse({"error": "Invalid mode"}, status=400)
    state.mode = mode
    state.density_alert = False
    state.weapon_alert = False
    state.fire_alert = False
    state.current_count = 0
    state.tracked_people = {}
    print(f"[INFO] Mode switched to {mode.upper()}")
    return JsonResponse({"mode": mode})


@require_GET
def api_alerts(request):
    """Get alert history."""
    return JsonResponse({
        "alerts": list(state.alert_history),
        "counts": state.alert_counts,
    })


@csrf_exempt
@require_POST
def api_drone_control(request, cmd):
    """Send a command to the drone."""
    di = drone_state_module.drone_instance
    if di is None:
        return JsonResponse({"error": "No drone connected (demo mode)"})

    try:
        d = di
        if cmd == "takeoff":
            d.takeoff()
        elif cmd == "land":
            d.land()
        elif cmd == "emergency":
            d.emergency()
        elif cmd == "up":
            d.move_up(MOVE_DISTANCE)
        elif cmd == "down":
            d.move_down(MOVE_DISTANCE)
        elif cmd == "left":
            d.move_left(MOVE_DISTANCE)
        elif cmd == "right":
            d.move_right(MOVE_DISTANCE)
        elif cmd == "forward":
            d.move_forward(MOVE_DISTANCE)
        elif cmd == "back":
            d.move_back(MOVE_DISTANCE)
        elif cmd == "cw":
            d.rotate_clockwise(30)
        elif cmd == "ccw":
            d.rotate_counter_clockwise(30)
        else:
            return JsonResponse(
                {"error": f"Unknown command: {cmd}"}, status=400
            )

        print(f"[DRONE] Command: {cmd}")
        return JsonResponse({"status": "ok", "command": cmd})
    except Exception as e:
        print(f"[DRONE] Command {cmd} failed: {e}")
        return JsonResponse({"error": str(e)})
