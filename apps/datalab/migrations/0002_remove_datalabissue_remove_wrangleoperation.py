from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('datalab', '0001_initial'),
    ]

    operations = [
        migrations.DeleteModel(name='WrangleOperation'),
        migrations.DeleteModel(name='DatalabIssue'),
    ]
