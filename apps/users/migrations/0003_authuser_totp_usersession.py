from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0002_alter_authuser_managers"),
    ]

    operations = [
        migrations.AddField(
            model_name="authuser",
            name="totp_secret",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="authuser",
            name="totp_enabled",
            field=models.BooleanField(default=False),
        ),
        migrations.CreateModel(
            name="UserSession",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("jti", models.CharField(
                    max_length=255,
                    unique=True,
                    help_text="JWT ID of the current refresh token for this session.",
                )),
                ("device", models.CharField(blank=True, max_length=200)),
                ("browser", models.CharField(blank=True, max_length=200)),
                ("ip_address", models.GenericIPAddressField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("last_active", models.DateTimeField(default=django.utils.timezone.now)),
                ("is_active", models.BooleanField(default=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="user_sessions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "user_session",
                "ordering": ["-last_active"],
            },
        ),
    ]
