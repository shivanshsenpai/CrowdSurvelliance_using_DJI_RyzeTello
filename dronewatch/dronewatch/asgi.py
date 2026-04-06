"""
ASGI config for DroneWatch project.
Routes HTTP to Django and WebSocket to Channels consumers.
"""

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dronewatch.settings')
django.setup()

from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application
from surveillance.routing import websocket_urlpatterns

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": URLRouter(websocket_urlpatterns),
})
