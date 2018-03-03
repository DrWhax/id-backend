# -*- coding: utf-8 -*-
# Generated by Django 1.11.9 on 2018-01-31 18:21
from __future__ import unicode_literals

try:
    from django.conf import settings
    from django.core.exceptions import ImproperlyConfigured
    from django.db import DEFAULT_DB_ALIAS, connections, migrations, models
    from django.db.migrations.recorder import MigrationRecorder
    import django.db.models.deletion
except ImportError as error:
    print(error)


# Fix a bad `social_django` migration.
try:
    BAD_MIGRATION = ('default', '0004_auto_20160423_0400')
    recorder = MigrationRecorder(connections[DEFAULT_DB_ALIAS])
    applied = recorder.applied_migrations()

    if BAD_MIGRATION not in applied:
        recorder.record_applied(*BAD_MIGRATION)
except (NameError, ImproperlyConfigured) as error:
    print(error)


class Migration(migrations.Migration):

    dependencies = [
        ('api_v3', '0008_v1_to_v2_attachments'),
    ]

    operations = [
        migrations.CreateModel(
            name='Subscriber',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.AddField(
            model_name='subscriber',
            name='ticket',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='subscribers', to='api_v3.Ticket'),
        ),
        migrations.AddField(
            model_name='subscriber',
            name='user',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL),
        ),
        migrations.AlterUniqueTogether(
            name='subscriber',
            unique_together=set([('user', 'ticket')]),
        ),
    ]
