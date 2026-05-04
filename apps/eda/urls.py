from django.urls import path

from .views import EDAViewSet

correlation      = EDAViewSet.as_view({"get": "correlation"})
distribution     = EDAViewSet.as_view({"get": "distribution"})
value_counts     = EDAViewSet.as_view({"get": "value_counts"})
crosstab         = EDAViewSet.as_view({"get": "crosstab"})
outlier_summary  = EDAViewSet.as_view({"get": "outlier_summary"})
missing_heatmap  = EDAViewSet.as_view({"get": "missing_heatmap"})
pairwise         = EDAViewSet.as_view({"get": "pairwise"})
association      = EDAViewSet.as_view({"get": "association"})
interpret        = EDAViewSet.as_view({"post": "interpret"})

urlpatterns = [
    path("correlation/<int:dataset_id>/",     correlation,     name="eda-correlation"),
    path("distribution/<int:dataset_id>/",    distribution,    name="eda-distribution"),
    path("value-counts/<int:dataset_id>/",    value_counts,    name="eda-value-counts"),
    path("crosstab/<int:dataset_id>/",        crosstab,        name="eda-crosstab"),
    path("outlier-summary/<int:dataset_id>/", outlier_summary, name="eda-outlier-summary"),
    path("missing-heatmap/<int:dataset_id>/", missing_heatmap, name="eda-missing-heatmap"),
    path("pairwise/<int:dataset_id>/",        pairwise,        name="eda-pairwise"),
    path("association/<int:dataset_id>/",     association,     name="eda-association"),
    path("interpret/<int:dataset_id>/",       interpret,       name="eda-interpret"),
]
