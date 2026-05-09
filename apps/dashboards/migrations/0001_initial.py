import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("datasets", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Dashboard",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=200)),
                ("description", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("dataset", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="dashboards",
                    to="datasets.dataset",
                )),
                ("user", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="dashboards",
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={"db_table": "dashboard", "ordering": ["-updated_at"]},
        ),
        migrations.CreateModel(
            name="DashboardWidget",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=200)),
                ("chart_type", models.CharField(
                    choices=[
                        ("bar", "Bar"), ("line", "Line"), ("scatter", "Scatter"),
                        ("histogram", "Histogram"), ("text", "Text / Annotation"),
                    ],
                    max_length=20,
                )),
                ("chart_params", models.JSONField(blank=True, default=dict)),
                ("chart_config", models.JSONField(blank=True, null=True)),
                ("text_content", models.TextField(blank=True, default="")),
                ("grid_col", models.PositiveSmallIntegerField(default=0)),
                ("grid_row", models.PositiveSmallIntegerField(default=0)),
                ("grid_width", models.PositiveSmallIntegerField(default=6)),
                ("grid_height", models.PositiveSmallIntegerField(default=4)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("dashboard", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="widgets",
                    to="dashboards.dashboard",
                )),
            ],
            options={"db_table": "dashboard_widget", "ordering": ["grid_row", "grid_col"]},
        ),
    ]
