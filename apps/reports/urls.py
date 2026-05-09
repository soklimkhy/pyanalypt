from django.urls import path

from .views import ReportItemViewSet, ReportViewSet

report_list   = ReportViewSet.as_view({"get": "list",    "post": "create"})
report_detail = ReportViewSet.as_view({"get": "retrieve", "patch": "partial_update", "delete": "destroy"})
report_export = ReportViewSet.as_view({"get": "export"})

item_list   = ReportItemViewSet.as_view({"post": "create"})
item_detail = ReportItemViewSet.as_view({"patch": "partial_update", "delete": "destroy"})

urlpatterns = [
    path("",                                   report_list,   name="report-list"),
    path("<int:pk>/",                          report_detail, name="report-detail"),
    path("<int:pk>/export/",                   report_export, name="report-export"),
    path("<int:report_pk>/items/",             item_list,     name="report-item-list"),
    path("<int:report_pk>/items/<int:pk>/",    item_detail,   name="report-item-detail"),
]
