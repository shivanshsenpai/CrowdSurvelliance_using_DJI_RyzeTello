"""
DroneWatch — Surveillance App URL Configuration.
"""

from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='dashboard'),
    path('analytics', views.analytics_page, name='analytics'),
    path('history/', views.history_page, name='history'),
    path('history/login/', views.history_login, name='history-login'),
    path('history/logout/', views.history_logout, name='history-logout'),
    path('api/status', views.api_status, name='api-status'),
    path('api/mode/<str:mode>', views.api_set_mode, name='api-mode'),
    path('api/alerts', views.api_alerts, name='api-alerts'),
    path('api/drone/<str:cmd>', views.api_drone_control, name='api-drone'),
    path('api/analytics/report', views.api_analytics_report, name='api-analytics-report'),
    path('api/analytics/history', views.api_analytics_history, name='api-analytics-history'),
    path('api/analytics/sessions', views.api_analytics_sessions, name='api-analytics-sessions'),
]
