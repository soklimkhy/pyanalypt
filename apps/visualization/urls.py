from django.urls import path

from .views import VisualizationViewSet

bar       = VisualizationViewSet.as_view({"get": "bar"})
line      = VisualizationViewSet.as_view({"get": "line"})
scatter   = VisualizationViewSet.as_view({"get": "scatter"})
histogram = VisualizationViewSet.as_view({"get": "histogram"})
kpi       = VisualizationViewSet.as_view({"get": "kpi"})
pie       = VisualizationViewSet.as_view({"get": "pie"})
treemap   = VisualizationViewSet.as_view({"get": "treemap"})

urlpatterns = [
    path("bar/<int:dataset_id>/",       bar,       name="viz-bar"),
    path("line/<int:dataset_id>/",      line,      name="viz-line"),
    path("scatter/<int:dataset_id>/",   scatter,   name="viz-scatter"),
    path("histogram/<int:dataset_id>/", histogram, name="viz-histogram"),
    path("kpi/<int:dataset_id>/",       kpi,       name="viz-kpi"),
    path("pie/<int:dataset_id>/",       pie,       name="viz-pie"),
    path("treemap/<int:dataset_id>/",   treemap,   name="viz-treemap"),
]
