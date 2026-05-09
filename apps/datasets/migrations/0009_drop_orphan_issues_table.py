from django.db import migrations


def drop_orphan_table(apps, schema_editor):
    # CASCADE is PostgreSQL-specific; the table never exists on SQLite/other backends.
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("DROP TABLE IF EXISTS issues_issue CASCADE;")


class Migration(migrations.Migration):
    """
    Drop the orphan `issues_issue` table left behind by a removed app.
    Its FK constraint on datasets_dataset.id was blocking dataset deletion.
    """

    dependencies = [
        ("datasets", "0008_extend_action_choices"),
    ]

    operations = [
        migrations.RunPython(drop_orphan_table, migrations.RunPython.noop),
    ]
