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
