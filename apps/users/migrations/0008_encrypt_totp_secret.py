from django.db import migrations
import apps.users.models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0007_alter_authuser_birthday_alter_authuser_email_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='authuser',
            name='totp_secret',
            field=apps.users.models.EncryptedCharField(blank=True, default='', max_length=256),
        ),
    ]
