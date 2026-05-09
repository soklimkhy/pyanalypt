from django.urls import path

from .views import ChatSessionViewSet

_v = ChatSessionViewSet.as_view

urlpatterns = [
    path("",                          _v({"get": "list",    "post": "create"})),
    path("<int:pk>/",                 _v({"get": "retrieve", "patch": "partial_update", "delete": "destroy"})),
    path("<int:pk>/message/",         _v({"post": "message"})),
    path("<int:pk>/stream/",          _v({"post": "stream"})),
    path("<int:pk>/clear/",           _v({"delete": "clear"})),
]
