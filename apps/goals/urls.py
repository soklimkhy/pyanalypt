from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import AnalysisGoalViewSet, AnalysisQuestionViewSet

router = DefaultRouter()
router.register(r"", AnalysisGoalViewSet, basename="goal")

# Extract named views for manual URL patterns
goal_list       = AnalysisGoalViewSet.as_view({"get": "list",     "post": "create"})
goal_detail     = AnalysisGoalViewSet.as_view({"get": "retrieve", "patch": "partial_update", "delete": "destroy"})
goal_suggest    = AnalysisGoalViewSet.as_view({"post": "suggest"})
goal_generate   = AnalysisGoalViewSet.as_view({"post": "generate"})
goal_regenerate = AnalysisGoalViewSet.as_view({"post": "regenerate"})
goal_save       = AnalysisGoalViewSet.as_view({"post": "save"})

question_list        = AnalysisQuestionViewSet.as_view({"post": "create"})
question_detail      = AnalysisQuestionViewSet.as_view({"patch": "partial_update", "delete": "destroy"})
question_bulk_delete = AnalysisQuestionViewSet.as_view({"delete": "bulk_destroy"})

urlpatterns = [
    path("",                                              goal_list,            name="goal-list"),
    path("<int:pk>/",                                     goal_detail,          name="goal-detail"),
    path("<int:pk>/suggest/",                             goal_suggest,         name="goal-suggest"),
    path("generate/",                                     goal_generate,        name="goal-generate"),
    path("<int:pk>/regenerate/",                          goal_regenerate,      name="goal-regenerate"),
    path("<int:pk>/save/",                                goal_save,            name="goal-save"),
    path("<int:goal_pk>/questions/",                      question_list,        name="goal-question-list"),
    path("<int:goal_pk>/questions/<int:pk>/",             question_detail,      name="goal-question-detail"),
    path("<int:goal_pk>/questions/bulk-delete/",          question_bulk_delete, name="goal-question-bulk-delete"),
]
