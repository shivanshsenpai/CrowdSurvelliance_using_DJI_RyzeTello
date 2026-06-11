"""
DroneWatch — Django Views.
REST API endpoints and dashboard template view.
"""

import time

from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import user_passes_test
from django.db.models import Avg, Count, Max, Q
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_GET, require_http_methods

from .drone_state import state, drone_instance
from . import drone_state as drone_state_module
from . import detection as detection_module

MOVE_DISTANCE = 30  # cm per move command


def index(request):
    """Serve the dashboard."""
    return render(request, 'surveillance/index.html')


def analytics_page(request):
    """Serve the analytics report page."""
    return render(request, 'surveillance/analytics.html')


def _is_superuser(user):
    return (
        user is not None
        and user.is_authenticated
        and user.is_active
        and user.is_superuser
    )


def _format_duration(seconds):
    seconds = max(int(seconds or 0), 0)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes}m {seconds}s"
    if minutes:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"


@require_http_methods(["GET", "POST"])
def history_login(request):
    """Custom login page for surveillance history."""
    if _is_superuser(request.user):
        return redirect('history')

    error = None
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        user = authenticate(request, username=username, password=password)
        if _is_superuser(user):
            auth_login(request, user)
            return redirect(request.GET.get("next") or 'history')
        error = "Invalid superuser username or password."

    return render(request, 'surveillance/history_login.html', {"error": error})


@require_GET
def history_logout(request):
    """Log out of the custom history area."""
    auth_logout(request)
    return redirect('history-login')


@require_GET
@user_passes_test(_is_superuser, login_url='/history/login/')
def history_page(request):
    """Show past surveillance run history on a custom DroneWatch page."""
    from .models import CrowdSnapshot, SurveillanceSession
    from django.utils import timezone as tz

    sessions = SurveillanceSession.objects.annotate(
        snapshot_count=Count('snapshots'),
        computed_peak=Max('snapshots__people_count'),
        computed_avg=Avg('snapshots__people_count'),
        computed_unique=Max('snapshots__cumulative_count'),
        computed_density_alerts=Count(
            'snapshots',
            filter=Q(snapshots__density_alert=True),
        ),
        computed_weapon_alerts=Count(
            'snapshots',
            filter=Q(snapshots__weapon_alert=True),
        ),
        computed_fire_alerts=Count(
            'snapshots',
            filter=Q(snapshots__fire_alert=True),
        ),
    ).order_by('-start_time')

    selected_session = None
    session_id = request.GET.get('session')
    if session_id:
        selected_session = sessions.filter(session_id=session_id).first()
    if selected_session is None:
        selected_session = sessions.first()

    snapshots = []
    summary = None
    selected_duration = None

    if selected_session:
        snapshot_qs = CrowdSnapshot.objects.filter(
            session=selected_session
        ).order_by('-timestamp')
        snapshots = list(snapshot_qs[:200])

        alert_counts = snapshot_qs.aggregate(
            peak=Max('people_count'),
            average=Avg('people_count'),
            unique=Max('cumulative_count'),
            density=Count('id', filter=Q(density_alert=True)),
            weapon=Count('id', filter=Q(weapon_alert=True)),
            fire=Count('id', filter=Q(fire_alert=True)),
        )

        end_time = selected_session.end_time or tz.now()
        selected_duration = _format_duration(
            (end_time - selected_session.start_time).total_seconds()
        )
        summary = {
            "snapshots": snapshot_qs.count(),
            "peak": alert_counts["peak"] or selected_session.peak_count,
            "average": round(
                alert_counts["average"]
                if alert_counts["average"] is not None
                else selected_session.avg_count,
                2,
            ),
            "unique": alert_counts["unique"] or selected_session.total_unique,
            "alerts": (
                alert_counts["density"]
                + alert_counts["weapon"]
                + alert_counts["fire"]
            ),
            "density_alerts": alert_counts["density"],
            "weapon_alerts": alert_counts["weapon"],
            "fire_alerts": alert_counts["fire"],
        }

    session_cards = []
    for session in sessions[:50]:
        end_time = session.end_time or tz.now()
        duration = _format_duration((end_time - session.start_time).total_seconds())
        density_alerts = session.computed_density_alerts or 0
        weapon_alerts = session.computed_weapon_alerts or 0
        fire_alerts = session.computed_fire_alerts or 0
        session_cards.append({
            "item": session,
            "duration": duration,
            "peak": session.computed_peak or session.peak_count,
            "average": round(
                session.computed_avg
                if session.computed_avg is not None
                else session.avg_count,
                2,
            ),
            "unique": session.computed_unique or session.total_unique,
            "alerts": density_alerts + weapon_alerts + fire_alerts,
            "snapshots": session.snapshot_count or session.total_snapshots,
            "is_selected": (
                selected_session is not None
                and session.session_id == selected_session.session_id
            ),
        })

    return render(request, 'surveillance/history.html', {
        "session_cards": session_cards,
        "selected_session": selected_session,
        "selected_duration": selected_duration,
        "summary": summary,
        "snapshots": snapshots,
    })


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
    sessions = SurveillanceSession.objects.annotate(
        snapshot_count=Count('snapshots'),
        computed_peak=Max('snapshots__people_count'),
        computed_avg=Avg('snapshots__people_count'),
        computed_unique=Max('snapshots__cumulative_count'),
        computed_density_alerts=Count(
            'snapshots',
            filter=Q(snapshots__density_alert=True),
        ),
        computed_weapon_alerts=Count(
            'snapshots',
            filter=Q(snapshots__weapon_alert=True),
        ),
        computed_fire_alerts=Count(
            'snapshots',
            filter=Q(snapshots__fire_alert=True),
        ),
    )[:20]
    data = []
    for s in sessions:
        duration = 0
        if s.end_time and s.start_time:
            duration = int((s.end_time - s.start_time).total_seconds())
        elif s.start_time:
            from django.utils import timezone as tz
            duration = int((tz.now() - s.start_time).total_seconds())
        total_alerts = (
            (s.computed_density_alerts or 0)
            + (s.computed_weapon_alerts or 0)
            + (s.computed_fire_alerts or 0)
        )
        data.append({
            "session_id": s.session_id,
            "start_time": s.start_time.strftime("%Y-%m-%d %H:%M:%S"),
            "end_time": s.end_time.strftime("%Y-%m-%d %H:%M:%S") if s.end_time else "Active",
            "duration_sec": duration,
            "peak_count": s.computed_peak or s.peak_count,
            "avg_count": round(
                s.computed_avg if s.computed_avg is not None else s.avg_count,
                2,
            ),
            "total_unique": s.computed_unique or s.total_unique,
            "total_alerts": total_alerts or s.total_alerts,
            "total_snapshots": s.snapshot_count or s.total_snapshots,
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
        "temperature": state.temperature,
        "fps": round(state.fps, 1),
        "detection_accuracy": state.detection_accuracy,
        "average_confidence": state.average_confidence,
        "recent_detection_count": state.recent_detection_count,
        "startup_memory_count": len(state.startup_people_signatures),
        "startup_people_seen": state.startup_people_seen,
        "startup_memory_limit": state.startup_memory_limit,
        "uptime": round(time.time() - state.session_start),
        "total_frames": state.total_frames,
        "models_loaded": detection_module.models_loaded,
        "weapon_model_backend": detection_module.weapon_model_backend,
        "weapon_input_size": detection_module.WEAPON_YOLOV8_INPUT_SIZE,
        "last_battery_update": state.last_battery_update,
        "last_altitude_update": state.last_altitude_update,
        "telemetry_errors": state.telemetry_errors,
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
    state.weapon_detection_streak = 0
    state.current_count = 0
    state.tracked_people = {}
    state.tracked_people_ignored = {}
    state.tracked_people_memory_slots = {}
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
        with drone_state_module.drone_command_lock:
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
