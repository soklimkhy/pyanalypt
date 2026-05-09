from django.db import models


class AnalysisGoal(models.Model):
    dataset = models.ForeignKey(
        "datasets.Dataset",
        on_delete=models.CASCADE,
        related_name="goals",
    )
    problem_statement = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Goal for {self.dataset.file_name}"


class AnalysisQuestion(models.Model):
    SOURCE_CHOICES = [
        ("manual", "Manual"),
        ("ai", "AI Generated"),
    ]

    goal = models.ForeignKey(
        AnalysisGoal,
        on_delete=models.CASCADE,
        related_name="questions",
    )
    order = models.PositiveIntegerField(default=0)
    question = models.TextField()
    source = models.CharField(max_length=10, choices=SOURCE_CHOICES, default="manual")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order", "created_at"]

    def __str__(self):
        return f"Q{self.order}: {self.question[:60]}"
