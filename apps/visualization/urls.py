from django.urls import path

from .views import VisualizationViewSet

bar       = VisualizationViewSet.as_view({"get": "bar"})
line      = VisualizationViewSet.as_view({"get": "line"})
scatter   = VisualizationViewSet.as_view({"get": "scatter"})
histogram = VisualizationViewSet.as_view({"get": "histogram"})

urlpatterns = [
    path("bar/<int:dataset_id>/",       bar,       name="viz-bar"),
    path("line/<int:dataset_id>/",      line,      name="viz-line"),
    path("scatter/<int:dataset_id>/",   scatter,   name="viz-scatter"),
    path("histogram/<int:dataset_id>/", histogram, name="viz-histogram"),
]
