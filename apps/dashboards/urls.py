from django.urls import path

from .views import DashboardViewSet, DashboardWidgetViewSet

_d = DashboardViewSet.as_view
_w = DashboardWidgetViewSet.as_view

urlpatterns = [
    # Dashboard CRUD
    path("",                                    _d({"get": "list",    "post": "create"})),
    path("<int:pk>/",                           _d({"get": "retrieve", "patch": "partial_update", "delete": "destroy"})),
    path("<int:pk>/refresh/",                   _d({"post": "refresh"})),
    path("<int:pk>/share/",                     _d({"post": "share"})),
    path("public/<str:share_token>/",           _d({"get": "public_view"})),

    # Widget CRUD (nested under dashboard)
    path("<int:dashboard_id>/widgets/",         _w({"get": "list", "post": "create"})),
    path("<int:dashboard_id>/widgets/<int:pk>/", _w({"patch": "partial_update", "delete": "destroy"})),
    path("<int:dashboard_id>/widgets/<int:pk>/refresh/", _w({"post": "refresh"})),
]
