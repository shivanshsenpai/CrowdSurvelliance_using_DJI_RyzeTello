"""
DroneWatch — Django Channels WebSocket Consumers.
Streams video frames and telemetry data to the dashboard frontend.
"""

import asyncio
import base64
import json
import time

import cv2
from channels.generic.websocket import AsyncWebsocketConsumer

from .drone_state import state

WS_FPS = 20
DATA_FPS = 4


class VideoConsumer(AsyncWebsocketConsumer):
    """Stream MJPEG frames over WebSocket as base64."""

    async def connect(self):
        await self.accept()
        print("[WS] Video client connected")
        self._running = True
        asyncio.ensure_future(self.stream_video())

    async def disconnect(self, close_code):
        self._running = False
        print("[WS] Video client disconnected")

    async def stream_video(self):
        """Continuously send processed frames to the client."""
        try:
            while self._running and state.running:
                if state.processed_frame is not None:
                    _, buffer = cv2.imencode(
                        ".jpg", state.processed_frame,
                        [cv2.IMWRITE_JPEG_QUALITY, 70]
                    )
                    frame_b64 = base64.b64encode(buffer).decode("utf-8")
                    await self.send(text_data=frame_b64)
                await asyncio.sleep(1.0 / WS_FPS)
        except Exception as e:
            print(f"[WS] Video error: {e}")

    async def receive(self, text_data=None, bytes_data=None):
        # Client doesn't send data on this socket
        pass


class DataConsumer(AsyncWebsocketConsumer):
    """Stream telemetry data as JSON over WebSocket."""

    async def connect(self):
        await self.accept()
        print("[WS] Data client connected")
        self._running = True
        asyncio.ensure_future(self.stream_data())

    async def disconnect(self, close_code):
        self._running = False
        print("[WS] Data client disconnected")

    async def stream_data(self):
        """Continuously send telemetry data to the client."""
        try:
            while self._running and state.running:
                data = {
                    "mode": state.mode,
                    "battery": state.battery,
                    "altitude": state.altitude,
                    "fps": round(state.fps, 1),
                    "current_count": state.current_count,
                    "cumulative_count": state.cumulative_count,
                    "density_alert": state.density_alert,
                    "weapon_alert": state.weapon_alert,
                    "fire_alert": state.fire_alert,
                    "uptime": round(time.time() - state.session_start),
                    "signal": state.signal,
                    "alert_counts": state.alert_counts,
                    "people_history": list(state.people_history)[-60:],
                    "confidence_values": list(state.confidence_values)[-30:],
                    "alerts": list(state.alert_history)[:20],
                    "total_alerts": sum(state.alert_counts.values()),
                }
                await self.send(text_data=json.dumps(data))
                await asyncio.sleep(1.0 / DATA_FPS)
        except Exception as e:
            print(f"[WS] Data error: {e}")

    async def receive(self, text_data=None, bytes_data=None):
        # Client doesn't send data on this socket
        pass
