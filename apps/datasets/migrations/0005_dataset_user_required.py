import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def delete_orphan_datasets(apps, schema_editor):
    """Remove datasets with no owner before enforcing the NOT NULL constraint."""
    Dataset = apps.get_model("datasets", "Dataset")
    Dataset.objects.filter(user__isnull=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("datasets", "0004_datasetactivitylog"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(delete_orphan_datasets, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="dataset",
            name="user",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="datasets",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
