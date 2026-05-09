from django.urls import path

from .views import MLModelViewSet

_v = MLModelViewSet.as_view

urlpatterns = [
    path("",                         _v({"get": "list",     "post": "create"})),
    path("<int:pk>/",                _v({"get": "retrieve", "delete": "destroy"})),
    path("<int:pk>/predict/",        _v({"post": "predict"})),
    path("algorithms/",              _v({"get": "algorithms"})),
]
