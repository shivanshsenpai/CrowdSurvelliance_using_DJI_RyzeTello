"""
DroneWatch — WebSocket URL Routing.
Maps WebSocket paths to consumers.
"""

from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'^ws/video$', consumers.VideoConsumer.as_asgi()),
    re_path(r'^ws/data$', consumers.DataConsumer.as_asgi()),
]
