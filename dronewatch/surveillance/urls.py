"""
DroneWatch — Surveillance App URL Configuration.
"""

from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='dashboard'),
    path('api/status', views.api_status, name='api-status'),
    path('api/mode/<str:mode>', views.api_set_mode, name='api-mode'),
    path('api/alerts', views.api_alerts, name='api-alerts'),
    path('api/drone/<str:cmd>', views.api_drone_control, name='api-drone'),
]
