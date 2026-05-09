import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
import apps.mlstudio.models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("datasets", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="MLModel",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=200)),
                ("description", models.TextField(blank=True, default="")),
                ("task_type", models.CharField(
                    choices=[
                        ("regression", "Regression"),
                        ("classification", "Classification"),
                        ("clustering", "Clustering"),
                    ],
                    max_length=20,
                )),
                ("algorithm", models.CharField(max_length=50)),
                ("feature_columns", models.JSONField(help_text="List of column names used as features.")),
                ("target_column", models.CharField(blank=True, default="", max_length=200)),
                ("hyperparams", models.JSONField(blank=True, default=dict)),
                ("test_size", models.FloatField(default=0.2)),
                ("status", models.CharField(
                    choices=[
                        ("pending", "Pending"),
                        ("training", "Training"),
                        ("ready", "Ready"),
                        ("failed", "Failed"),
                    ],
                    default="pending",
                    max_length=20,
                )),
                ("error_message", models.TextField(blank=True, default="")),
                ("metrics", models.JSONField(blank=True, null=True)),
                ("feature_importances", models.JSONField(blank=True, null=True)),
                ("label_classes", models.JSONField(blank=True, default=list)),
                ("train_samples", models.IntegerField(blank=True, null=True)),
                ("test_samples", models.IntegerField(blank=True, null=True)),
                ("training_time_seconds", models.FloatField(blank=True, null=True)),
                ("model_file", models.FileField(blank=True, null=True, upload_to=apps.mlstudio.models._model_upload_path)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("dataset", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="ml_models",
                    to="datasets.dataset",
                )),
                ("user", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="ml_models",
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={"db_table": "ml_model", "ordering": ["-created_at"]},
        ),
    ]
