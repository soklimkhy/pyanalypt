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
            name="ChatSession",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(default="New conversation", max_length=200)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("dataset", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="chat_sessions",
                    to="datasets.dataset",
                )),
                ("user", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="chat_sessions",
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={"db_table": "chat_session", "ordering": ["-updated_at"]},
        ),
        migrations.CreateModel(
            name="ChatMessage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("role", models.CharField(
                    choices=[("user", "User"), ("assistant", "Assistant")],
                    max_length=10,
                )),
                ("content", models.TextField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("context_snapshot", models.JSONField(blank=True, null=True)),
                ("session", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="messages",
                    to="chat.chatsession",
                )),
            ],
            options={"db_table": "chat_message", "ordering": ["created_at"]},
        ),
    ]
