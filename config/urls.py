from django.contrib import admin
from django.urls import include, path
from rust_py_monitor.prometheus import django_metrics_view

urlpatterns = [
    path("admin/", admin.site.urls),
    # rust-py-monitor: Prometheus exposition of request/process metrics.
    path("metrics/", django_metrics_view, name="metrics"),
    path("api/v1/users/", include("apps.users.urls")),
]
