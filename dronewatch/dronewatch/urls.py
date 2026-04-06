"""
Root URL configuration for DroneWatch.
"""

from django.urls import path, include

urlpatterns = [
    path('', include('surveillance.urls')),
]
